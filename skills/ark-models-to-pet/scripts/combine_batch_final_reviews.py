#!/usr/bin/env python3
"""Combine independent final visual reviews with unanimous approval required."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_review(path: Path) -> tuple[str, dict[str, dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviewer = str(payload.get("reviewer") or path.stem)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit(f"{path}: expected jobs list")
    by_key: dict[str, dict] = {}
    for job in jobs:
        key = job.get("model_key")
        verdict = job.get("verdict")
        if not key or key in by_key:
            raise SystemExit(f"{path}: missing or duplicate model_key")
        if verdict not in {"approve", "exception"}:
            raise SystemExit(f"{path}: invalid verdict for {key}")
        by_key[key] = job
    return reviewer, by_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.review) < 2:
        raise SystemExit("at least two independent final reviews are required")

    reviews = [load_review(Path(path).expanduser().resolve()) for path in args.review]
    keys = set(reviews[0][1])
    for reviewer, jobs in reviews[1:]:
        if set(jobs) != keys:
            raise SystemExit(f"{reviewer}: model-key set differs from the first review")

    jobs_out = []
    for key in reviews[0][1]:
        evidence = [
            {
                "reviewer": reviewer,
                "verdict": jobs[key]["verdict"],
                "reason": jobs[key].get("reason", ""),
            }
            for reviewer, jobs in reviews
        ]
        verdict = "approve" if all(item["verdict"] == "approve" for item in evidence) else "exception"
        reason = (
            f"Unanimous approval from {len(evidence)} independent final reviewers."
            if verdict == "approve"
            else "Final reviewers did not unanimously approve: "
            + "; ".join(
                f"{item['reviewer']}={item['verdict']}: {item['reason']}" for item in evidence
            )
        )
        jobs_out.append(
            {
                "model_key": key,
                "verdict": verdict,
                "reason": reason,
                "reviews": evidence,
            }
        )

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"reviewer": "final-consensus", "jobs": jobs_out}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(jobs_out), "approved": sum(j["verdict"] == "approve" for j in jobs_out)}))


if __name__ == "__main__":
    main()
