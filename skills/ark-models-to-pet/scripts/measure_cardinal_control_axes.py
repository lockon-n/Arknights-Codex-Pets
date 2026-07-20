#!/usr/bin/env python3
"""Measure rendered control-bone motion for the four cardinal look poses."""

from __future__ import annotations

import argparse
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


def controls_by_bone(poses: dict[str, list[dict]], label: str) -> dict[str, dict]:
    return {
        control["bone"]: control
        for control in poses.get(label, [])
        if not control.get("missing")
    }


def deltas(
    poses: dict[str, list[dict]],
    start: str,
    end: str,
    coordinate: str,
) -> list[dict]:
    first = controls_by_bone(poses, start)
    second = controls_by_bone(poses, end)
    result = []
    for bone in sorted(first.keys() & second.keys()):
        before = first[bone].get(coordinate)
        after = second[bone].get(coordinate)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        result.append({"bone": bone, "delta": after - before})
    return result


def verdict(values: list[dict], expected_sign: int, epsilon: float) -> str:
    meaningful = [item["delta"] * expected_sign for item in values if abs(item["delta"]) > epsilon]
    if not meaningful:
        return "unmeasurable"
    if all(value > 0 for value in meaningful):
        return "pass"
    if all(value < 0 for value in meaningful):
        return "inverse"
    return "mixed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--epsilon", type=float, default=0.5)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    jobs = []
    for job in manifest["jobs"]:
        metadata_path = job_root / job["pet_id"] / "directions" / "render-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        look_controls = metadata.get("lookControls")
        if not isinstance(look_controls, dict) or look_controls.get("mode") != "directions":
            raise SystemExit(f"{job['model_key']} is missing direction lookControls metadata")
        poses = {pose["label"]: pose.get("controls", []) for pose in look_controls.get("poses", [])}
        horizontal = deltas(poses, "270", "090", "screenX")
        vertical = deltas(poses, "180", "000", "screenY")
        jobs.append(
            {
                "model_key": job["model_key"],
                "pet_id": job["pet_id"],
                "horizontal": {
                    "measurement": "screenX(090)-screenX(270)",
                    "expected": "positive",
                    "controls": horizontal,
                    "verdict": verdict(horizontal, 1, args.epsilon),
                },
                "vertical": {
                    "measurement": "screenY(000)-screenY(180)",
                    "expected": "negative",
                    "controls": vertical,
                    "verdict": verdict(vertical, -1, args.epsilon),
                },
            }
        )

    summary = {
        axis: {
            state: sum(job[axis]["verdict"] == state for job in jobs)
            for state in ("pass", "inverse", "mixed", "unmeasurable")
        }
        for axis in ("horizontal", "vertical")
    }
    atomic_json(
        Path(args.json_out).resolve(),
        {
            "schema_version": 1,
            "epsilon_pixels": args.epsilon,
            "summary": summary,
            "jobs": jobs,
        },
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
