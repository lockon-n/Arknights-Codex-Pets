#!/usr/bin/env python3
"""Replace selected jobs in a full cardinal consensus with a fresh recheck consensus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = ("horizontal_A", "horizontal_B", "vertical_A", "vertical_B")


def load_jobs(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs = payload if isinstance(payload, list) else payload.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit(f"{path}: review must contain a jobs list")
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--recheck", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base = load_jobs(Path(args.base).expanduser().resolve())
    recheck = load_jobs(Path(args.recheck).expanduser().resolve())
    by_key = {job.get("model_key"): job for job in recheck}
    if len(by_key) != len(recheck) or None in by_key:
        raise SystemExit("recheck contains missing or duplicate model keys")

    merged = []
    replaced = set()
    for job in base:
        model_key = job.get("model_key")
        replacement = by_key.get(model_key)
        if replacement is None:
            merged.append(job)
            continue
        missing = [field for field in FIELDS if field not in replacement]
        if missing:
            raise SystemExit(f"{model_key}: recheck is missing {missing}")
        merged.append(
            {
                **job,
                **{field: replacement[field] for field in FIELDS},
                "recheck_votes": replacement.get("votes", {}),
            }
        )
        replaced.add(model_key)

    extra = sorted(set(by_key) - replaced)
    if extra:
        raise SystemExit(f"recheck contains model keys absent from base: {extra}")
    output = Path(args.output).expanduser().resolve()
    output.write_text(
        json.dumps({"jobs": merged, "rechecked_model_keys": sorted(replaced)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(merged), "replaced": len(replaced)}))


if __name__ == "__main__":
    main()
