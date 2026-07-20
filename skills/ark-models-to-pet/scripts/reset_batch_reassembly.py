#!/usr/bin/env python3
"""Invalidate downstream gates before rebuilding an existing pet batch."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


RESET_FIELDS = (
    "frames_qa",
    "standard_qa",
    "standard_visual_qa",
    "atlas_qa",
    "direction_evidence_qa",
    "direction_qa",
    "visual_qa",
    "package_qa",
)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_csv(path: Path, jobs: list[dict]) -> None:
    if not jobs:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(jobs[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(jobs)
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("refusing to reset gates without --confirm")

    manifest = Path(args.manifest).expanduser().resolve()
    csv_path = Path(args.csv).expanduser().resolve() if args.csv else None
    lock_name = hashlib.sha256(str(manifest).encode()).hexdigest()[:16]
    with (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        jobs = payload.get("jobs", [])
        if not jobs:
            raise SystemExit("manifest has no jobs")

        unsafe = [
            job.get("model_key")
            for job in jobs
            if job.get("production_render") != "pass"
            or job.get("direction_render") != "pass"
        ]
        if unsafe:
            raise SystemExit(
                "cannot reuse source renders; production/direction render is not passing for: "
                + ", ".join(str(value) for value in unsafe[:12])
            )

        for job in jobs:
            for field in RESET_FIELDS:
                job[field] = "pending"
            job["package_path"] = ""
            job["commit"] = ""
            job["status"] = "in_progress"
            job["stage"] = "reassembly-pending"
            job["error"] = ""

        payload["reassembly"] = {
            "reason": args.reason,
            "normalization": "safe-max",
            "cell_margin": 6,
            "max_source_upscale": 1.0,
            "reset_at": datetime.now(timezone.utc).isoformat(),
            "reused_inputs": [
                "mapping.json",
                "768x832 production renders",
                "look-config.json",
                "768x832 direction source renders",
            ],
        }
        atomic_json(manifest, payload)
        if csv_path:
            atomic_csv(csv_path, jobs)

    print(json.dumps({"ok": True, "jobs_reset": len(jobs), "fields": RESET_FIELDS}))


if __name__ == "__main__":
    main()
