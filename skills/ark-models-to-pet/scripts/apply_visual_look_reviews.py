#!/usr/bin/env python3
"""Apply explicit standard-atlas and look-probe visual review verdicts."""

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--review", action="append", required=True)
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
    verdicts: dict[str, dict] = {}
    for path in args.review:
        review = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
        for verdict in review.get("jobs", []):
            model_key = verdict.get("model_key")
            if model_key in verdicts:
                raise SystemExit(f"duplicate review for {model_key}")
            if verdict.get("standard_verdict") not in {"approve", "exception"}:
                raise SystemExit(f"invalid standard verdict for {model_key}")
            if verdict.get("look_verdict") not in {"calibrated", "exception"}:
                raise SystemExit(f"invalid look verdict for {model_key}")
            verdicts[model_key] = verdict
    unknown = sorted(set(verdicts) - set(by_key))
    if unknown:
        raise SystemExit(f"review model keys not in manifest: {', '.join(unknown)}")

    job_root = Path(args.job_root).resolve()
    counts = {"standard_pass": 0, "standard_exception": 0, "look_calibrated": 0, "look_exception": 0}
    for model_key, verdict in verdicts.items():
        job = by_key[model_key]
        errors: list[str] = []

        if verdict["standard_verdict"] == "approve":
            job["standard_visual_qa"] = "pass"
            counts["standard_pass"] += 1
        else:
            job["standard_visual_qa"] = "failed"
            errors.append(f"standard visual QA: {verdict.get('standard_reason') or 'exception'}")
            counts["standard_exception"] += 1

        if job.get("direction_qa") == "pass":
            counts["look_calibrated"] += 1
        elif verdict["look_verdict"] == "calibrated":
            config_path = job_root / job["pet_id"] / "look-config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if "eye_bones" in verdict or "head_bone" in verdict:
                metadata_path = (
                    job_root
                    / job["pet_id"]
                    / "look-probe"
                    / "render-metadata.json"
                )
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                bone_parent = {
                    bone["name"]: bone.get("parent")
                    for bone in metadata.get("bones", [])
                }
                selected_eye_bones = list(
                    verdict.get("eye_bones", config.get("eye_bones", []))
                )
                if len(selected_eye_bones) != len(set(selected_eye_bones)):
                    raise SystemExit(f"duplicate eye bone for {model_key}")
                unknown_bones = sorted(
                    bone for bone in selected_eye_bones if bone not in bone_parent
                )
                selected_head_bone = verdict.get(
                    "head_bone", config.get("head_bone")
                )
                if selected_head_bone is not None and selected_head_bone not in bone_parent:
                    unknown_bones.append(selected_head_bone)
                if unknown_bones:
                    raise SystemExit(
                        f"unknown look bone for {model_key}: {', '.join(sorted(set(unknown_bones)))}"
                    )
                selected_eye_set = set(selected_eye_bones)
                for bone in selected_eye_bones:
                    ancestor = bone_parent.get(bone)
                    while ancestor is not None:
                        if ancestor in selected_eye_set:
                            raise SystemExit(
                                f"eye bone hierarchy overlap for {model_key}: {ancestor} -> {bone}"
                            )
                        ancestor = bone_parent.get(ancestor)
                config["eye_bones"] = selected_eye_bones
                config["head_bone"] = selected_head_bone
            eye_magnitude = int(verdict.get("eye_magnitude", 8))
            if eye_magnitude < 0:
                raise SystemExit(f"eye_magnitude for {model_key} must be non-negative")
            eye_x_up = signed(
                verdict.get("eye_x_plus", ""), "up", "down", eye_magnitude
            )
            eye_x_right = signed(
                verdict.get("eye_x_plus", ""),
                "screen-right",
                "screen-left",
                eye_magnitude,
            )
            eye_y_up = signed(
                verdict.get("eye_y_plus", ""), "up", "down", eye_magnitude
            )
            eye_y_right = signed(
                verdict.get("eye_y_plus", ""),
                "screen-right",
                "screen-left",
                eye_magnitude,
            )
            eyes_have_vertical = eye_x_up != 0 or eye_y_up != 0
            eyes_have_horizontal = eye_x_right != 0 or eye_y_right != 0
            eyes_cover_both_axes = (
                bool(config.get("eye_bones"))
                and eyes_have_vertical
                and eyes_have_horizontal
            )
            default_head_translation = 2 if eyes_cover_both_axes else 8
            default_head_rotation = 4 if eyes_cover_both_axes else 10
            head_translation_magnitude = int(
                verdict.get("head_translation_magnitude", default_head_translation)
            )
            head_rotation_magnitude = int(
                verdict.get("head_rotation_magnitude", default_head_rotation)
            )
            if head_translation_magnitude < 0 or head_rotation_magnitude < 0:
                raise SystemExit(
                    f"look magnitudes for {model_key} must be non-negative"
                )
            head_x_up = signed(
                verdict.get("head_x_plus", ""),
                "up",
                "down",
                head_translation_magnitude,
            )
            head_x_right = signed(
                verdict.get("head_x_plus", ""),
                "screen-right",
                "screen-left",
                head_translation_magnitude,
            )
            head_y_up = signed(
                verdict.get("head_y_plus", ""),
                "up",
                "down",
                head_translation_magnitude,
            )
            head_y_right = signed(
                verdict.get("head_y_plus", ""),
                "screen-right",
                "screen-left",
                head_translation_magnitude,
            )
            coefficients = {
                "eye_x_up": eye_x_up,
                "eye_x_right": eye_x_right,
                "eye_y_up": eye_y_up,
                "eye_y_right": eye_y_right,
                "head_x_up": head_x_up,
                "head_x_right": head_x_right,
                "head_y_up": head_y_up,
                "head_y_right": head_y_right,
                "head_rotation_up": 0,
                "head_rotation_right": signed(
                    verdict.get("head_rot_plus", ""),
                    "screen-right",
                    "screen-left",
                    head_rotation_magnitude,
                ),
            }
            coefficient_overrides = verdict.get("coefficients", {})
            if not isinstance(coefficient_overrides, dict):
                raise SystemExit(f"coefficients for {model_key} must be an object")
            unknown_coefficients = sorted(set(coefficient_overrides) - set(coefficients))
            if unknown_coefficients:
                raise SystemExit(
                    f"unknown look coefficient for {model_key}: {', '.join(unknown_coefficients)}"
                )
            for name, value in coefficient_overrides.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise SystemExit(
                        f"look coefficient {model_key}/{name} must be numeric"
                    )
                coefficients[name] = value
            eyes_have_vertical = (
                coefficients["eye_x_up"] != 0 or coefficients["eye_y_up"] != 0
            )
            eyes_have_horizontal = (
                coefficients["eye_x_right"] != 0
                or coefficients["eye_y_right"] != 0
            )
            config.update(
                {
                    "mode": "directions",
                    **coefficients,
                    "review_required": False,
                    "notes": f"Calibrated from final-cell-size batch probe review: {verdict.get('look_reason') or 'visual signs approved'}",
                }
            )
            if (
                not eyes_have_vertical
                and coefficients["head_x_up"] == 0
                and coefficients["head_y_up"] == 0
            ):
                errors.append("look calibration lacks a vertical control")
            if (
                not eyes_have_horizontal
                and coefficients["head_x_right"] == 0
                and coefficients["head_y_right"] == 0
                and coefficients["head_rotation_right"] == 0
            ):
                errors.append("look calibration lacks a horizontal control")
            if not errors or all(not error.startswith("look calibration") for error in errors):
                atomic_json(config_path, config)
                job["direction_qa"] = "calibrated"
                counts["look_calibrated"] += 1
            else:
                job["direction_qa"] = "blocked"
                counts["look_exception"] += 1
        else:
            job["direction_qa"] = "blocked"
            errors.append(f"look probe QA: {verdict.get('look_reason') or 'exception'}")
            counts["look_exception"] += 1

        if errors:
            job["status"] = "exception"
            job["stage"] = (
                "standard-visual-adapter"
                if job.get("standard_visual_qa") == "failed"
                else "direction-adapter"
            )
            job["error"] = "; ".join(errors)
        elif job.get("direction_qa") != "pass":
            job["status"] = "in_progress"
            job["stage"] = "directions-calibrated"
            job["error"] = ""

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(json.dumps({"reviewed": len(verdicts), **counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
