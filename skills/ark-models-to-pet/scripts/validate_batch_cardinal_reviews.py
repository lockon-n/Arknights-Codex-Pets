#!/usr/bin/env python3
"""Validate combined batch cardinal reviews against a hidden answer key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = ["horizontal_A", "horizontal_B", "vertical_A", "vertical_B"]
ALLOWED = {"screen-left", "screen-right", "up", "down", "ambiguous"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answer-key", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    expected = {
        job["model_key"]: job
        for job in json.loads(Path(args.answer_key).resolve().read_text(encoding="utf-8"))["jobs"]
    }
    observed = {
        job["model_key"]: job
        for job in json.loads(Path(args.review).resolve().read_text(encoding="utf-8"))["jobs"]
    }
    errors = []
    results = []
    for model_key, answer in expected.items():
        verdict = observed.get(model_key)
        if verdict is None:
            errors.append(f"missing verdict for {model_key}")
            continue
        item = {"model_key": model_key, "cells": {}}
        for field in FIELDS:
            value = verdict.get(field)
            if value not in ALLOWED:
                errors.append(f"{model_key} {field} has invalid value {value!r}")
            elif value == "ambiguous":
                errors.append(f"{model_key} {field} is ambiguous")
            elif value != answer[field]:
                errors.append(f"{model_key} {field} classified {value}; expected {answer[field]}")
            item["cells"][field] = {
                "observed": value,
                "expected": answer[field],
                "pass": value == answer[field],
            }
        results.append(item)
    extra = sorted(set(observed) - set(expected))
    if extra:
        errors.append(f"unexpected model keys: {', '.join(extra)}")
    output = {"ok": not errors, "errors": errors, "jobs": results}
    path = Path(args.output).resolve()
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": output["ok"], "errors": len(errors)}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
