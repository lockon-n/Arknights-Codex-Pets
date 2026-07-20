#!/usr/bin/env python3
"""Apply validated batch cardinal blind-QA results to a resumable manifest."""

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--validation", required=True)
    parser.add_argument("--consensus")
    parser.add_argument("--job-root")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    for job in jobs:
        default_gate = "pending" if job.get("model_key") else "blocked"
        job.setdefault("direction_evidence_qa", default_gate)
    by_key = {job["model_key"]: job for job in jobs}

    validation = json.loads(Path(args.validation).resolve().read_text(encoding="utf-8"))
    consensus_by_key: dict[str, dict] = {}
    if args.consensus:
        consensus = json.loads(Path(args.consensus).resolve().read_text(encoding="utf-8"))
        consensus_by_key = {item["model_key"]: item for item in consensus.get("jobs", [])}
    job_root = Path(args.job_root).resolve() if args.job_root else None
    if bool(args.consensus) != bool(job_root):
        raise SystemExit("--consensus and --job-root must be provided together")
    passed = failed = 0
    for result in validation.get("jobs", []):
        model_key = result.get("model_key")
        if model_key not in by_key:
            raise SystemExit(f"validation model key not in manifest: {model_key}")
        job = by_key[model_key]
        cells = result.get("cells", {})
        cell_results = [cell.get("pass") is True for cell in cells.values()]
        if len(cell_results) == 4 and all(cell_results):
            job["direction_evidence_qa"] = "pass"
            job["direction_qa"] = "pass"
            job["status"] = "in_progress"
            job["stage"] = "direction-approved"
            job["error"] = ""
            passed += 1
        else:
            details = [
                f"{field}: {cell.get('observed')} != {cell.get('expected')}"
                for field, cell in cells.items()
                if cell.get("pass") is not True
            ]
            job["direction_evidence_qa"] = "failed"
            job["direction_qa"] = "failed"
            job["status"] = "exception"
            job["stage"] = "direction-recalibration"
            job["error"] = "blind cardinal QA failed: " + "; ".join(details or ["missing cells"])
            failed += 1
        if job_root:
            qa_dir = job_root / job["pet_id"] / "run" / "qa"
            qa_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(
                qa_dir / "blind-validation.json",
                {
                    "schema_version": 1,
                    "model_key": model_key,
                    "ok": len(cell_results) == 4 and all(cell_results),
                    "cells": cells,
                },
            )
            consensus_item = consensus_by_key.get(model_key)
            if consensus_item is None:
                raise SystemExit(f"consensus is missing model key: {model_key}")
            atomic_json(
                qa_dir / "blind-consensus.json",
                {"schema_version": 1, **consensus_item},
            )

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(json.dumps({"applied": passed + failed, "passed": passed, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
