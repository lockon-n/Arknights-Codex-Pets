#!/usr/bin/env python3
"""Record completed safe-max audit evidence in a batch manifest."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import tempfile
from pathlib import Path


def atomic_json(path: Path, payload: dict) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--safe-max-audit", required=True)
    parser.add_argument("--calibration-before", required=True)
    parser.add_argument("--calibration-after", required=True)
    parser.add_argument("--cardinal-validation", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    safe_max = json.loads(Path(args.safe_max_audit).expanduser().resolve().read_text(encoding="utf-8"))
    before = json.loads(Path(args.calibration_before).expanduser().resolve().read_text(encoding="utf-8"))
    after = json.loads(Path(args.calibration_after).expanduser().resolve().read_text(encoding="utf-8"))
    cardinal = json.loads(Path(args.cardinal_validation).expanduser().resolve().read_text(encoding="utf-8"))
    if safe_max.get("ok") is not True:
        raise SystemExit("safe-max batch audit is not passing")
    if before != after:
        raise SystemExit("mapping or direction inputs changed during reassembly")
    if cardinal.get("ok") is not True:
        raise SystemExit("final blind cardinal validation is not passing")

    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    with (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        jobs = manifest.get("jobs", [])
        required_gates = (
            "frames_qa",
            "standard_qa",
            "standard_visual_qa",
            "direction_evidence_qa",
            "direction_qa",
            "atlas_qa",
            "visual_qa",
            "package_qa",
        )
        if any(job.get(gate) != "pass" for job in jobs for gate in required_gates):
            raise SystemExit("manifest still contains a non-passing reassembly gate")
        manifest.setdefault("reassembly", {})["audit"] = {
            "verified_jobs": len(jobs),
            "required_alpha_margin": safe_max["required_margin"],
            "scale_relative_to_previous_canvas": safe_max[
                "scale_relative_to_previous_canvas"
            ],
            "immutable_calibration_files": before["file_count"],
            "immutable_calibration_hashes_unchanged": True,
            "blind_cardinal_cells_verified": len(cardinal.get("jobs", [])) * 4,
            "final_visual_jobs_verified": sum(
                job.get("visual_qa") == "pass" for job in jobs
            ),
        }
        atomic_json(manifest_path, manifest)
    print(json.dumps({"ok": True, **manifest["reassembly"]["audit"]}))


if __name__ == "__main__":
    main()
