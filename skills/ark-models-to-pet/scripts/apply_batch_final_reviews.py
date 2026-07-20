#!/usr/bin/env python3
"""Apply explicit final visual-review verdicts to a resumable batch manifest."""

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
    parser.add_argument("--review", action="append", required=True)
    parser.add_argument("--job-root")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    by_key = {job["model_key"]: job for job in jobs}
    verdicts: dict[str, dict] = {}
    job_root = Path(args.job_root).resolve() if args.job_root else None
    for review_path in args.review:
        review = json.loads(Path(review_path).resolve().read_text(encoding="utf-8"))
        for verdict in review.get("jobs", []):
            model_key = verdict.get("model_key")
            if model_key in verdicts:
                raise SystemExit(f"duplicate final review for {model_key}")
            if model_key not in by_key:
                raise SystemExit(f"final review model key not in manifest: {model_key}")
            if verdict.get("verdict") not in {"approve", "exception"}:
                raise SystemExit(f"invalid final verdict for {model_key}")
            verdicts[model_key] = verdict

    passed = failed = 0
    for model_key, verdict in verdicts.items():
        job = by_key[model_key]
        if verdict["verdict"] == "approve":
            gates = {
                "standard_visual_qa": job.get("standard_visual_qa"),
                "direction_qa": job.get("direction_qa"),
                "atlas_qa": job.get("atlas_qa"),
                "direction_evidence_qa": job.get("direction_evidence_qa"),
            }
            blocked = [field for field, value in gates.items() if value != "pass"]
            if blocked:
                raise SystemExit(
                    f"cannot approve {model_key}; prerequisite gates not pass: {', '.join(blocked)}"
                )
            job["visual_qa"] = "pass"
            job["status"] = "in_progress"
            job["stage"] = "visually-approved"
            job["error"] = ""
            passed += 1
        else:
            job["visual_qa"] = "failed"
            job["status"] = "exception"
            job["stage"] = "final-visual-repair"
            job["error"] = "final visual QA: " + str(verdict.get("reason") or "exception")
            failed += 1
        if job_root:
            qa_dir = job_root / job["pet_id"] / "run" / "qa"
            qa_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(
                qa_dir / "final-visual-review.json",
                {
                    "schema_version": 1,
                    "model_key": model_key,
                    "verdict": verdict["verdict"],
                    "reason": verdict.get("reason", ""),
                },
            )

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(json.dumps({"reviewed": len(verdicts), "passed": passed, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
