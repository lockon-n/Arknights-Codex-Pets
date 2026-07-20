#!/usr/bin/env python3
"""Apply explicit standard-state visual verdicts without changing look calibration."""

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
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
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

    manifest = Path(args.manifest).expanduser().resolve()
    lock_name = hashlib.sha256(str(manifest).encode()).hexdigest()[:16]
    with (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        jobs = payload["jobs"]
        by_key = {job["model_key"]: job for job in jobs}
        verdicts: dict[str, dict] = {}
        for review_path in args.review:
            review = json.loads(Path(review_path).expanduser().resolve().read_text(encoding="utf-8"))
            for verdict in review.get("jobs", []):
                model_key = verdict.get("model_key")
                if model_key in verdicts:
                    raise SystemExit(f"duplicate standard review for {model_key}")
                if model_key not in by_key:
                    raise SystemExit(f"standard review model key not in manifest: {model_key}")
                if verdict.get("verdict") not in {"approve", "exception"}:
                    raise SystemExit(f"invalid standard verdict for {model_key}")
                verdicts[model_key] = verdict

        expected = {job["model_key"] for job in jobs if job.get("model_key")}
        missing = sorted(expected - verdicts.keys())
        if missing:
            raise SystemExit(
                f"standard reviews are incomplete: {len(missing)} jobs missing; first={missing[:8]}"
            )

        passed = failed = 0
        job_root = Path(args.job_root).expanduser().resolve() if args.job_root else None
        for model_key, verdict in verdicts.items():
            job = by_key[model_key]
            if job.get("standard_qa") != "pass":
                raise SystemExit(f"cannot visually approve {model_key}; standard_qa is not pass")
            if verdict["verdict"] == "approve":
                job["standard_visual_qa"] = "pass"
                job["status"] = "in_progress"
                job["stage"] = "standard-visually-approved"
                job["error"] = ""
                passed += 1
            else:
                job["standard_visual_qa"] = "failed"
                job["status"] = "exception"
                job["stage"] = "standard-visual-repair"
                job["error"] = "standard visual QA: " + str(
                    verdict.get("reason") or "exception"
                )
                failed += 1
            if job_root:
                atomic_json(
                    job_root / job["pet_id"] / "run" / "qa" / "standard-visual-review.json",
                    {
                        "schema_version": 1,
                        "model_key": model_key,
                        "verdict": verdict["verdict"],
                        "reason": verdict.get("reason", ""),
                    },
                )

        atomic_json(manifest, payload)
        if args.csv:
            atomic_csv(Path(args.csv).expanduser().resolve(), jobs)

    print(json.dumps({"reviewed": len(verdicts), "passed": passed, "failed": failed}))


if __name__ == "__main__":
    main()
