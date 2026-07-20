#!/usr/bin/env python3
"""Invert direction coefficients only where blind cardinal consensus proves an axis is reversed."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import tempfile
from pathlib import Path


AXIS_FIELDS = {
    "horizontal": (
        "eye_x_right",
        "eye_y_right",
        "head_x_right",
        "head_y_right",
        "head_rotation_right",
    ),
    "vertical": (
        "eye_x_up",
        "eye_y_up",
        "head_x_up",
        "head_y_up",
        "head_rotation_up",
    ),
}
CELL_FIELDS = {
    "horizontal": ("horizontal_A", "horizontal_B"),
    "vertical": ("vertical_A", "vertical_B"),
}


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_csv(path: Path, jobs: list[dict]) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(jobs[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(jobs)
        temporary = Path(handle.name)
    temporary.replace(path)


def axis_verdict(result: dict, axis: str) -> str:
    cells = [result["cells"][field] for field in CELL_FIELDS[axis]]
    if all(cell.get("pass") is True for cell in cells):
        return "pass"
    if all(
        cell.get("observed") not in {None, "ambiguous"}
        and cell.get("observed") != cell.get("expected")
        for cell in cells
    ):
        return "inverse"
    return "unsupported"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--validation", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--repair-log", required=True)
    parser.add_argument(
        "--skip-unsupported",
        action="store_true",
        help="repair proven inverse axes while leaving ambiguous or mixed axes for manual review",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    by_key = {job["model_key"]: job for job in jobs}
    validation = json.loads(Path(args.validation).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    repairs = []
    skipped = []

    for result in validation.get("jobs", []):
        axes = [axis for axis in AXIS_FIELDS if axis_verdict(result, axis) == "inverse"]
        unsupported = [axis for axis in AXIS_FIELDS if axis_verdict(result, axis) == "unsupported"]
        if unsupported:
            if args.skip_unsupported:
                skipped.append(
                    {
                        "model_key": result["model_key"],
                        "axes": unsupported,
                        "reason": "ambiguous-or-mixed-blind-cardinal-result",
                    }
                )
                continue
            raise SystemExit(
                f"{result['model_key']} has ambiguous/mixed axes requiring manual repair: {', '.join(unsupported)}"
            )
        if not axes:
            continue
        model_key = result["model_key"]
        job = by_key.get(model_key)
        if not job:
            raise SystemExit(f"validation model key not in manifest: {model_key}")
        config_path = job_root / job["pet_id"] / "look-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        changed: dict[str, dict[str, float]] = {}
        for axis in axes:
            nonzero = []
            for field in AXIS_FIELDS[axis]:
                old = config.get(field, 0)
                if not isinstance(old, (int, float)):
                    raise SystemExit(f"{model_key} {field} is not numeric")
                if old:
                    config[field] = -old
                    changed[field] = {"from": old, "to": -old}
                    nonzero.append(field)
            if not nonzero:
                raise SystemExit(f"{model_key} inverse {axis} axis has no nonzero coefficients")
        config["notes"] = (
            str(config.get("notes") or "")
            + " Blind cardinal consensus proved reversed axis; inverted only: "
            + ", ".join(axes)
            + "."
        ).strip()
        atomic_json(config_path, config)

        job["direction_qa"] = "calibrated"
        job["direction_render"] = "pending"
        job["atlas_qa"] = "pending"
        job["direction_evidence_qa"] = "pending"
        job["visual_qa"] = "pending"
        job["package_qa"] = "pending"
        job["status"] = "in_progress"
        job["stage"] = "direction-axis-repair"
        job["error"] = ""
        repairs.append({"model_key": model_key, "pet_id": job["pet_id"], "axes": axes, "changes": changed})

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    atomic_json(
        Path(args.repair_log).resolve(),
        {
            "schema_version": 1,
            "source_validation": Path(args.validation).name,
            "jobs": repairs,
            "skipped": skipped,
        },
    )
    print(json.dumps({"repaired": len(repairs), "skipped": len(skipped)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
