#!/usr/bin/env python3
"""Record the Git commit containing an approved batch's package bytes."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import re
import tempfile
from pathlib import Path


def atomic_json(path: Path, payload: dict) -> None:
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
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("--commit must be a full lowercase 40-character Git SHA")

    manifest = Path(args.manifest).expanduser().resolve()
    lock_name = hashlib.sha256(str(manifest).encode()).hexdigest()[:16]
    with (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        jobs = payload.get("jobs", [])
        incomplete = [
            job.get("model_key")
            for job in jobs
            if job.get("package_qa") != "pass" or not job.get("package_path")
        ]
        if incomplete:
            raise SystemExit(f"cannot record commit; incomplete packages: {incomplete[:10]}")
        for job in jobs:
            job["commit"] = args.commit
            job["status"] = "complete"
            job["stage"] = "packaged"
            job["error"] = ""
        payload.setdefault("reassembly", {})["package_commit"] = args.commit
        atomic_json(manifest, payload)
        if args.csv:
            atomic_csv(Path(args.csv).expanduser().resolve(), jobs)
    print(json.dumps({"recorded": len(jobs), "commit": args.commit}))


if __name__ == "__main__":
    main()
