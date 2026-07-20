#!/usr/bin/env python3
"""Hash immutable mapping and direction inputs around an atlas-only rebuild."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(manifest: Path, job_root: Path) -> dict:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    jobs: dict[str, dict] = {}
    for job in payload["jobs"]:
        pet_id = job["pet_id"]
        root = job_root / pet_id
        files = [root / "mapping.json", root / "look-config.json"]
        files.extend(sorted((root / "directions" / "look-source").glob("*.png")))
        if len(files) != 18:
            raise RuntimeError(
                f"{pet_id}: expected mapping, look config, and 16 direction PNGs; got {len(files)} files"
            )
        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise RuntimeError(f"{pet_id}: missing immutable inputs: {missing}")
        jobs[pet_id] = {
            str(path.relative_to(root)): sha256(path)
            for path in files
        }
    return {
        "schema_version": 1,
        "job_count": len(jobs),
        "file_count": sum(len(files) for files in jobs.values()),
        "jobs": jobs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--compare")
    args = parser.parse_args()

    result = snapshot(
        Path(args.manifest).expanduser().resolve(),
        Path(args.job_root).expanduser().resolve(),
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.compare:
        expected = json.loads(Path(args.compare).expanduser().resolve().read_text(encoding="utf-8"))
        if result != expected:
            raise SystemExit("immutable mapping or direction inputs changed during rebuild")

    print(json.dumps({"ok": True, "jobs": result["job_count"], "files": result["file_count"]}))


if __name__ == "__main__":
    main()
