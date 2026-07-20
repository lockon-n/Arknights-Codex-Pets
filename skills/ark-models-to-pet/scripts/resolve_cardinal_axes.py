#!/usr/bin/env python3
"""Repair exact inverse cardinal axes and strengthen consistently ambiguous axes."""

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


def verdict(result: dict, axis: str) -> str:
    cells = [result["cells"][field] for field in CELL_FIELDS[axis]]
    if all(cell.get("pass") is True for cell in cells):
        return "pass"
    observed = [cell.get("observed") for cell in cells]
    if all(value == "ambiguous" for value in observed):
        return "ambiguous"
    if all(
        value not in {None, "ambiguous"} and value != cell.get("expected")
        for value, cell in zip(observed, cells, strict=True)
    ):
        return "inverse"
    return "unsupported"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--validation", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--resolution-log", required=True)
    parser.add_argument("--ambiguity-scale", type=float, default=1.5)
    args = parser.parse_args()
    if not 1 < args.ambiguity_scale <= 2:
        raise SystemExit("--ambiguity-scale must be greater than 1 and at most 2")

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    by_key = {job["model_key"]: job for job in jobs}
    validation = json.loads(Path(args.validation).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    resolutions = []

    for result in validation.get("jobs", []):
        actions = {axis: verdict(result, axis) for axis in AXIS_FIELDS}
        unsupported = [axis for axis, state in actions.items() if state == "unsupported"]
        if unsupported:
            raise SystemExit(
                f"{result['model_key']} has mixed cardinal evidence: {', '.join(unsupported)}"
            )
        changed_axes = {axis: state for axis, state in actions.items() if state != "pass"}
        if not changed_axes:
            continue
        model_key = result["model_key"]
        job = by_key.get(model_key)
        if not job:
            raise SystemExit(f"validation model key not in manifest: {model_key}")
        config_path = job_root / job["pet_id"] / "look-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        changed = {}
        for axis, action in changed_axes.items():
            axis_changes = {}
            for field in AXIS_FIELDS[axis]:
                old = config.get(field, 0)
                if not isinstance(old, (int, float)):
                    raise SystemExit(f"{model_key} {field} is not numeric")
                if not old:
                    continue
                new = -old if action == "inverse" else old * args.ambiguity_scale
                if isinstance(old, int) and float(new).is_integer():
                    new = int(new)
                config[field] = new
                axis_changes[field] = {"from": old, "to": new}
            if not axis_changes:
                raise SystemExit(f"{model_key} {action} {axis} axis has no nonzero coefficients")
            changed[axis] = {"action": action, "coefficients": axis_changes}
        summary = ", ".join(f"{axis}={state}" for axis, state in changed_axes.items())
        config["notes"] = (
            str(config.get("notes") or "")
            + f" Fixed-grid cardinal resolution: {summary}; ambiguous axes scaled by {args.ambiguity_scale:g}."
        ).strip()
        atomic_json(config_path, config)

        job["direction_qa"] = "calibrated"
        job["direction_render"] = "pending"
        job["atlas_qa"] = "pending"
        job["direction_evidence_qa"] = "pending"
        job["visual_qa"] = "pending"
        job["package_qa"] = "pending"
        job["status"] = "in_progress"
        job["stage"] = "direction-axis-resolution"
        job["error"] = ""
        resolutions.append(
            {"model_key": model_key, "pet_id": job["pet_id"], "axes": changed}
        )

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    atomic_json(
        Path(args.resolution_log).resolve(),
        {
            "schema_version": 1,
            "source_validation": Path(args.validation).name,
            "ambiguity_scale": args.ambiguity_scale,
            "jobs": resolutions,
        },
    )
    print(json.dumps({"resolved": len(resolutions)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
