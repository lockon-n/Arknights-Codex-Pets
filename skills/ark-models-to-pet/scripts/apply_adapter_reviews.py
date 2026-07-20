#!/usr/bin/env python3
"""Apply visual direction-adapter verdicts to legacy Spine rigs."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import tempfile
from pathlib import Path


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


def signed(value: str, positive: str, negative: str, magnitude: int) -> int:
    if value == positive:
        return magnitude
    if value == negative:
        return -magnitude
    return 0


def choose_vertical(verdict: dict) -> tuple[str, int] | None:
    controls = (
        ("eye_x_up", verdict.get("eye_x_plus"), 8),
        ("head_x_up", verdict.get("head_x_plus"), 8),
        ("head_y_up", verdict.get("head_y_plus"), 8),
    )
    for field, value, magnitude in controls:
        coefficient = signed(str(value or ""), "up", "down", magnitude)
        if coefficient:
            return field, coefficient
    return None


def choose_horizontal(verdict: dict) -> tuple[str, int] | None:
    controls = (
        ("eye_y_right", verdict.get("eye_y_plus"), 8),
        ("head_x_right", verdict.get("head_x_plus"), 8),
        ("head_y_right", verdict.get("head_y_plus"), 8),
        ("head_rotation_right", verdict.get("head_rot_plus"), 10),
    )
    for field, value, magnitude in controls:
        coefficient = signed(str(value or ""), "screen-right", "screen-left", magnitude)
        if coefficient:
            return field, coefficient
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument(
        "--force-existing",
        action="store_true",
        help="replace an existing calibrated/pass direction setup and invalidate downstream QA",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    for job in jobs:
        default_gate = "pending" if job.get("model_key") else "blocked"
        job.setdefault("standard_visual_qa", default_gate)
        job.setdefault("direction_probe", default_gate)
        job.setdefault("direction_render", default_gate)
        job.setdefault("direction_evidence_qa", default_gate)
        job.setdefault("package_qa", default_gate)
    by_key = {job["model_key"]: job for job in jobs}

    review = json.loads(Path(args.review).resolve().read_text(encoding="utf-8"))
    verdicts = review.get("jobs", [])
    seen: set[str] = set()
    calibrated = skipped = exceptions = 0
    job_root = Path(args.job_root).resolve()

    for verdict in verdicts:
        model_key = str(verdict.get("model_key") or "")
        if not model_key or model_key in seen:
            raise SystemExit(f"missing or duplicate model_key: {model_key!r}")
        seen.add(model_key)
        if model_key not in by_key:
            raise SystemExit(f"review model key not in manifest: {model_key}")
        job = by_key[model_key]
        if job.get("direction_qa") in {"calibrated", "pass"} and not args.force_existing:
            skipped += 1
            continue
        if verdict.get("look_verdict") != "calibrated":
            job["direction_qa"] = "blocked"
            job["status"] = "exception"
            job["stage"] = "direction-adapter"
            job["error"] = str(verdict.get("reason") or "adapter review exception")
            exceptions += 1
            continue

        vertical = choose_vertical(verdict)
        horizontal = choose_horizontal(verdict)
        if not vertical or not horizontal:
            job["direction_qa"] = "blocked"
            job["status"] = "exception"
            job["stage"] = "direction-adapter"
            job["error"] = "adapter review lacks an unambiguous local vertical or horizontal control"
            exceptions += 1
            continue

        config_path = job_root / job["pet_id"] / "look-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for field in (
            "eye_x_up",
            "eye_x_right",
            "eye_y_up",
            "eye_y_right",
            "head_x_up",
            "head_x_right",
            "head_y_up",
            "head_y_right",
            "head_rotation_up",
            "head_rotation_right",
        ):
            config[field] = 0
        config[vertical[0]] = vertical[1]
        config[horizontal[0]] = horizontal[1]
        config["mode"] = "directions"
        config["review_required"] = False
        config["notes"] = (
            "Calibrated by legacy-rig adapter visual review using local controls only: "
            + str(verdict.get("reason") or "approved")
        )
        atomic_json(config_path, config)

        job["direction_qa"] = "calibrated"
        job["direction_render"] = "pending"
        job["atlas_qa"] = "pending"
        job["direction_evidence_qa"] = "pending"
        job["visual_qa"] = "pending"
        job["package_qa"] = "pending"
        job["status"] = "in_progress"
        job["stage"] = "directions-calibrated"
        job["error"] = ""
        calibrated += 1

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(
        json.dumps(
            {
                "reviewed": len(verdicts),
                "calibrated": calibrated,
                "skipped_existing": skipped,
                "exceptions": exceptions,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
