#!/usr/bin/env python3
"""Audit safe-max geometry and final-cell margins across a completed batch."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of an empty list")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def cell_min_margin(validation: dict) -> int:
    margins = [
        margin
        for cell in validation.get("cells", [])
        if cell.get("used")
        for margin in (cell.get("alpha_margins") or [])
    ]
    if not margins:
        raise RuntimeError("validation report contains no used-cell alpha margins")
    return min(margins)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--required-margin", type=int, default=6)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).expanduser().resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).expanduser().resolve()
    errors: list[str] = []
    jobs: list[dict] = []
    relative_scales: list[float] = []

    for job in manifest["jobs"]:
        pet_id = job["pet_id"]
        qa = job_root / pet_id / "run" / "qa"
        try:
            normalization = json.loads((qa / "normalization.json").read_text(encoding="utf-8"))
            standard = json.loads((qa / "standard-validation.json").read_text(encoding="utf-8"))
            extended = json.loads((qa / "v2-validation.json").read_text(encoding="utf-8"))
            safe = normalization.get("safe_max") or {}
            scale = float(safe["scale"])
            state_scales = {
                round(float(state["scale"]), 12)
                for state in normalization.get("states", {}).values()
            }
            source_canvas = safe.get("source_canvas")
            standard_margin = cell_min_margin(standard)
            extended_margin = cell_min_margin(extended)
            relative_scale = scale / 0.25
            relative_scales.append(relative_scale)
            checks = {
                "normalization": normalization.get("normalization") == "safe-max",
                "reported_margin": normalization.get("margin") == args.required_margin,
                "source_canvas": source_canvas == [768, 832],
                "downsample_only": scale <= 1.0,
                "one_pet_wide_scale": len(state_scales) == 1,
                "standard_validator": standard.get("ok") is True,
                "extended_validator": extended.get("ok") is True,
                "standard_margin": standard_margin >= args.required_margin,
                "extended_margin": extended_margin >= args.required_margin,
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                errors.append(f"{pet_id}: {', '.join(failed)}")
            jobs.append(
                {
                    "pet_id": pet_id,
                    "model_key": job["model_key"],
                    "source_scale": scale,
                    "relative_to_previous_canvas": relative_scale,
                    "standard_min_alpha_margin": standard_margin,
                    "extended_min_alpha_margin": extended_margin,
                    "checks": checks,
                }
            )
        except Exception as error:  # noqa: BLE001
            errors.append(f"{pet_id}: {error}")

    summary = {
        "count": len(relative_scales),
        "minimum": min(relative_scales) if relative_scales else None,
        "p10": percentile(relative_scales, 0.10) if relative_scales else None,
        "median": percentile(relative_scales, 0.50) if relative_scales else None,
        "p90": percentile(relative_scales, 0.90) if relative_scales else None,
        "maximum": max(relative_scales) if relative_scales else None,
    }
    result = {
        "ok": not errors and len(jobs) == len(manifest["jobs"]),
        "required_margin": args.required_margin,
        "scale_relative_to_previous_canvas": summary,
        "errors": errors,
        "jobs": jobs,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "jobs"}, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
