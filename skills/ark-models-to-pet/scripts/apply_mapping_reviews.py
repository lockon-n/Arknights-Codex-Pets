#!/usr/bin/env python3
"""Apply explicit visual mapping-review verdicts to job mappings and batch state."""

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
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--review", action="append", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    by_key = {job["model_key"]: job for job in jobs}
    verdicts: dict[str, dict] = {}
    for review_path in args.review:
        review = json.loads(Path(review_path).resolve().read_text(encoding="utf-8"))
        for verdict in review.get("jobs", []):
            model_key = verdict.get("model_key")
            if model_key in verdicts:
                raise SystemExit(f"duplicate review for {model_key}")
            if verdict.get("verdict") not in {"approve", "exception"}:
                raise SystemExit(f"invalid verdict for {model_key}: {verdict.get('verdict')!r}")
            verdicts[model_key] = verdict

    missing = sorted(set(verdicts) - set(by_key))
    if missing:
        raise SystemExit(f"review model keys not in manifest: {', '.join(missing)}")

    job_root = Path(args.job_root).resolve()
    approved = 0
    exceptions = 0
    for model_key, verdict in verdicts.items():
        job = by_key[model_key]
        reason = str(verdict.get("reason") or "visual mapping review")
        if verdict["verdict"] == "exception":
            job["mapping_qa"] = "blocked"
            job["status"] = "exception"
            job["stage"] = "mapping-adapter"
            job["error"] = reason
            exceptions += 1
            continue

        mapping_path = job_root / job["pet_id"] / "mapping.json"
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        state_repairs = verdict.get("states")
        if state_repairs is not None:
            if not isinstance(state_repairs, dict):
                raise SystemExit(f"states repair for {model_key} must be an object")
            unknown_states = sorted(set(state_repairs) - set(mapping.get("states", {})))
            if unknown_states:
                raise SystemExit(
                    f"states repair for {model_key} contains unknown states: {', '.join(unknown_states)}"
                )
            for state, specification in state_repairs.items():
                if not isinstance(specification, dict):
                    raise SystemExit(
                        f"states repair for {model_key}/{state} must be an object"
                    )
                mapping["states"][state] = specification
        already_passed = job.get("mapping_qa") == "pass"
        mapping["review_required"] = False
        if not already_passed:
            mapping["notes"] = f"Approved by batch visual animation review: {reason}"
        atomic_json(mapping_path, mapping)
        job["mapping_qa"] = "pass"
        if not already_passed:
            job["status"] = "in_progress"
            job["stage"] = "mapping-reviewed"
            job["error"] = ""
        approved += 1

    atomic_json(manifest_path, payload)
    if args.csv:
        atomic_csv(Path(args.csv).resolve(), jobs)
    print(
        json.dumps(
            {"reviewed": len(verdicts), "approved": approved, "exceptions": exceptions},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
