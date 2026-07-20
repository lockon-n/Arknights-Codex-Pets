#!/usr/bin/env python3
"""Apply successful validated batch-package results to a resumable manifest."""

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
    parser.add_argument("--results", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    by_key = {job["model_key"]: job for job in jobs}
    results = json.loads(Path(args.results).resolve().read_text(encoding="utf-8"))
    passed = failed = 0
    for result in results.get("jobs", []):
        model_key = result.get("modelKey")
        if model_key not in by_key:
            raise SystemExit(f"package result model key not in manifest: {model_key}")
        job = by_key[model_key]
        outcome = result.get("outcome")
        if outcome in {"packaged", "resumed"}:
            if any(job.get(field) != "pass" for field in ("atlas_qa", "visual_qa", "direction_qa")):
                raise SystemExit(f"cannot mark unapproved package pass: {model_key}")
            job["package_qa"] = "pass"
            job["package_path"] = str(result.get("packagePath") or f"pets/{job['pet_id']}")
            job["status"] = "complete"
            job["stage"] = "packaged"
            job["error"] = ""
            passed += 1
        elif outcome == "failed":
            job["package_qa"] = "failed"
            job["status"] = "exception"
            job["stage"] = "package"
            job["error"] = "package QA: " + str(result.get("error") or "failed")
            failed += 1

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(json.dumps({"applied": passed + failed, "passed": passed, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
