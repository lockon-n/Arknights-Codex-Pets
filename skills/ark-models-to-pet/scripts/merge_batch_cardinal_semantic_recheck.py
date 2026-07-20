#!/usr/bin/env python3
"""Translate a validated recheck protocol back into a base blind protocol's A/B order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = ("horizontal_A", "horizontal_B", "vertical_A", "vertical_B")


def load_jobs(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs = payload if isinstance(payload, list) else payload.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit(f"{path}: expected a jobs list")
    return jobs


def keyed(jobs: list[dict], label: str) -> dict[str, dict]:
    result = {job.get("model_key"): job for job in jobs}
    if len(result) != len(jobs) or None in result:
        raise SystemExit(f"{label}: missing or duplicate model_key")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--base-answer-key", required=True)
    parser.add_argument("--recheck", required=True)
    parser.add_argument("--recheck-answer-key", required=True)
    parser.add_argument(
        "--model-key",
        action="append",
        default=[],
        help="merge only this validated recheck job; repeat for multiple jobs",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base = load_jobs(Path(args.base).expanduser().resolve())
    base_key = keyed(
        load_jobs(Path(args.base_answer_key).expanduser().resolve()), "base answer key"
    )
    recheck = keyed(load_jobs(Path(args.recheck).expanduser().resolve()), "recheck")
    recheck_key = keyed(
        load_jobs(Path(args.recheck_answer_key).expanduser().resolve()),
        "recheck answer key",
    )

    selected = set(args.model_key)
    if selected:
        missing_review = sorted(selected - set(recheck))
        missing_key = sorted(selected - set(recheck_key))
        if missing_review or missing_key:
            raise SystemExit(
                "selected model keys missing from recheck/recheck answer key: "
                f"review={missing_review}, key={missing_key}"
            )
        recheck = {key: value for key, value in recheck.items() if key in selected}
        recheck_key = {key: value for key, value in recheck_key.items() if key in selected}

    if set(recheck) != set(recheck_key):
        raise SystemExit("recheck jobs do not exactly match the recheck answer key")

    translated = []
    replaced: list[str] = []
    for job in base:
        model_key = job.get("model_key")
        replacement = recheck.get(model_key)
        if replacement is None:
            translated.append(job)
            continue
        if model_key not in base_key:
            raise SystemExit(f"{model_key}: absent from base answer key")
        observed = {field: replacement.get(field) for field in FIELDS}
        expected = {field: recheck_key[model_key].get(field) for field in FIELDS}
        failures = [
            field
            for field in FIELDS
            if observed[field] != expected[field]
            or observed[field] == "ambiguous"
            or observed[field] is None
        ]
        if failures:
            raise SystemExit(
                f"{model_key}: recheck has not passed its own hidden key: {failures}"
            )
        translated_values = {field: base_key[model_key][field] for field in FIELDS}
        translated.append(
            {
                **job,
                **translated_values,
                "semantic_recheck": {
                    "source_observed": observed,
                    "source_expected": expected,
                    "translated_to_base": translated_values,
                    "votes": replacement.get("votes", {}),
                },
            }
        )
        replaced.append(model_key)

    extras = sorted(set(recheck) - {job.get("model_key") for job in base})
    if extras:
        raise SystemExit(f"recheck jobs absent from base consensus: {extras}")

    output = Path(args.output).expanduser().resolve()
    output.write_text(
        json.dumps(
            {"jobs": translated, "semantic_rechecked_model_keys": sorted(replaced)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(translated), "replaced": len(replaced)}))


if __name__ == "__main__":
    main()
