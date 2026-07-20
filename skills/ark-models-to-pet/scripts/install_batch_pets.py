#!/usr/bin/env python3
"""Atomically install only the manifest-listed Codex pet files from a repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, source.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--destination-root", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).expanduser().resolve().read_text(encoding="utf-8"))
    repo_root = Path(args.repo_root).expanduser().resolve()
    destination_root = Path(args.destination_root).expanduser().resolve()
    if destination_root == Path(destination_root.anchor):
        raise SystemExit("destination root must not be a filesystem root")

    jobs = manifest.get("jobs", [])
    if not jobs:
        raise SystemExit("manifest has no jobs")
    seen: set[str] = set()
    planned: list[dict] = []
    for job in jobs:
        pet_id = job.get("pet_id")
        if not isinstance(pet_id, str) or not pet_id or pet_id in seen:
            raise SystemExit(f"invalid or duplicate pet_id: {pet_id!r}")
        seen.add(pet_id)
        if job.get("package_qa") != "pass" or not job.get("commit"):
            raise SystemExit(f"{pet_id}: package_qa/commit is not complete")
        package = (repo_root / str(job.get("package_path"))).resolve()
        target = (destination_root / pet_id).resolve()
        if not contained(package, repo_root) or not contained(target, destination_root):
            raise SystemExit(f"{pet_id}: unsafe package or destination path")
        metadata_path = package / "pet.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("id") != pet_id or metadata.get("spriteVersionNumber") != 2:
            raise SystemExit(f"{pet_id}: invalid v2 metadata")
        sheet_name = metadata.get("spritesheetPath")
        if not isinstance(sheet_name, str) or Path(sheet_name).name != sheet_name:
            raise SystemExit(f"{pet_id}: unsafe spritesheetPath")
        sheet_path = package / sheet_name
        if not metadata_path.is_file() or not sheet_path.is_file():
            raise SystemExit(f"{pet_id}: package files are missing")
        planned.append(
            {
                "pet_id": pet_id,
                "source_metadata": metadata_path,
                "source_sheet": sheet_path,
                "target_metadata": target / "pet.json",
                "target_sheet": target / sheet_name,
            }
        )

    for item in planned:
        atomic_copy(item["source_metadata"], item["target_metadata"])
        atomic_copy(item["source_sheet"], item["target_sheet"])

    results = []
    for item in planned:
        metadata_hash = sha256(item["source_metadata"])
        sheet_hash = sha256(item["source_sheet"])
        if sha256(item["target_metadata"]) != metadata_hash:
            raise SystemExit(f"{item['pet_id']}: installed pet.json hash mismatch")
        if sha256(item["target_sheet"]) != sheet_hash:
            raise SystemExit(f"{item['pet_id']}: installed spritesheet hash mismatch")
        results.append(
            {
                "pet_id": item["pet_id"],
                "pet_json_sha256": metadata_hash,
                "spritesheet_sha256": sheet_hash,
            }
        )

    report = {
        "ok": True,
        "installed": len(results),
        "destination_root": str(destination_root),
        "results": results,
    }
    if args.report:
        output = Path(args.report).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "installed": len(results), "destination_root": str(destination_root)}))


if __name__ == "__main__":
    main()
