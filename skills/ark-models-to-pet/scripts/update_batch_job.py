#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import tempfile
from pathlib import Path


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically update one job in a batch JSON and CSV TODO table.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    args = parser.parse_args()

    manifest = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for item in payload["jobs"]:
        default_gate = "pending" if item.get("model_key") else "blocked"
        item.setdefault("standard_visual_qa", default_gate)
        item.setdefault("direction_probe", default_gate)
        item.setdefault("direction_render", default_gate)
        item.setdefault("direction_evidence_qa", default_gate)
        item.setdefault("package_qa", default_gate)
    job = next((item for item in payload["jobs"] if item.get("model_key") == args.model_key), None)
    if not job:
        raise SystemExit(f"model key not found: {args.model_key}")
    updates = {}
    for assignment in args.set:
        if "=" not in assignment:
            raise SystemExit(f"invalid --set value: {assignment}")
        field, value = assignment.split("=", 1)
        if field not in job:
            raise SystemExit(f"unknown job field: {field}")
        updates[field] = value
    job.update(updates)
    atomic_text(manifest, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if args.csv:
        csv_path = Path(args.csv).resolve()
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=csv_path.parent, delete=False
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(payload["jobs"][0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(payload["jobs"])
            temporary = Path(handle.name)
        temporary.replace(csv_path)
    print(json.dumps({"model_key": args.model_key, "updated": updates}, ensure_ascii=False))


if __name__ == "__main__":
    main()
