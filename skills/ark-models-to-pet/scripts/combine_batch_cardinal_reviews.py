#!/usr/bin/env python3
"""Combine an odd number of independent batch cardinal blind reviews."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


FIELDS = ["horizontal_A", "horizontal_B", "vertical_A", "vertical_B"]
ALLOWED = {
    "horizontal_A": {"screen-left", "screen-right", "ambiguous"},
    "horizontal_B": {"screen-left", "screen-right", "ambiguous"},
    "vertical_A": {"up", "down", "ambiguous"},
    "vertical_B": {"up", "down", "ambiguous"},
}


def verdict_value(job: dict, field: str) -> str:
    value = job.get(field, job.get(field.lower()))
    if value not in ALLOWED[field]:
        raise SystemExit(
            f"{job.get('model_key')} has invalid or missing {field}: {value!r}"
        )
    return value


def review_jobs(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise SystemExit("review JSON must be a jobs array, a jobs wrapper, or a model-key map")
    if isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    records = []
    for model_key, verdict in payload.items():
        if not isinstance(verdict, dict):
            raise SystemExit("model-key review maps must contain verdict objects")
        records.append({"model_key": model_key, **verdict})
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.review) < 3 or len(args.review) % 2 == 0:
        raise SystemExit("provide an odd number of at least three review files")
    reviews = []
    for path in args.review:
        payload = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
        records = review_jobs(payload)
        review = {job["model_key"]: job for job in records}
        if len(review) != len(records):
            raise SystemExit(f"review contains duplicate model keys: {path}")
        reviews.append(review)
    keys = set(reviews[0])
    if any(set(review) != keys for review in reviews[1:]):
        raise SystemExit("all reviews must contain the same model keys")
    threshold = len(reviews) // 2 + 1
    combined = []
    for model_key in reviews[0]:
        result = {"model_key": model_key, "votes": {}}
        for field in FIELDS:
            counts = Counter(verdict_value(review[model_key], field) for review in reviews)
            value, count = counts.most_common(1)[0]
            result[field] = value if count >= threshold else "ambiguous"
            result["votes"][field] = dict(counts)
        combined.append(result)
    output = Path(args.output).resolve()
    output.write_text(json.dumps({"jobs": combined}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
