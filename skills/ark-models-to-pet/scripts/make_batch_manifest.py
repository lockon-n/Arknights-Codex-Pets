#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a CSV selection into a resumable batch manifest.")
    parser.add_argument("--selection", required=True, help="CSV with model_key and optional pet_id/display_name columns")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.selection).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    jobs = []
    seen = set()
    gate_fields = (
        "preflight",
        "preview_render",
        "mapping_qa",
        "production_render",
        "frames_qa",
        "standard_qa",
        "standard_visual_qa",
        "direction_probe",
        "direction_render",
        "direction_evidence_qa",
        "direction_qa",
        "atlas_qa",
        "visual_qa",
        "package_qa",
    )
    for row in rows:
        model_key = (row.get("model_key") or "").strip()
        if not model_key or model_key in seen:
            continue
        seen.add(model_key)
        pet_id = (row.get("pet_id") or model_key.lower().replace("#", "-").replace("_", "-")).strip()
        job = {
            key: (value or "").strip()
            for key, value in row.items()
            if key not in {"model_key", "pet_id", "display_name"}
        }
        job.update({
            "model_key": model_key,
            "pet_id": pet_id,
            "display_name": (row.get("display_name") or "").strip(),
            "status": "pending",
            "stage": "catalogued",
            "attempts": 0,
            "qa": None,
            "error": None,
        })
        job.update({field: "pending" for field in gate_fields})
        jobs.append(job)
    payload = {"schema_version": 1, "jobs": jobs}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "jobs": len(jobs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
