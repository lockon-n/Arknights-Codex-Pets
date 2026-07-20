#!/usr/bin/env python3
"""Atomically publish an inspected package staging tree into a pet Git repository."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


REQUIRED_PACKAGE = {"pet.json", "spritesheet.webp", "SOURCE.md", "provenance.json", "qa"}


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}-", delete=False) as handle:
        handle.write(payload)
        handle.flush()
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(path: Path, payload: object) -> None:
    atomic_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_symlink(path: Path) -> bool:
    return path.is_symlink() or any(item.is_symlink() for item in path.rglob("*"))


def validate_staging(staging_root: Path) -> tuple[list[dict], dict[str, Path]]:
    registry_path = staging_root / "registry-entries.json"
    results_path = staging_root / "batch-package-results.json"
    packages_root = staging_root / "pets"
    if not registry_path.is_file() or not results_path.is_file() or not packages_root.is_dir():
        raise SystemExit("staging root must contain pets/, registry-entries.json, and batch-package-results.json")
    results = load_json(results_path)
    if any(job.get("outcome") == "failed" for job in results.get("jobs", [])):
        raise SystemExit("batch-package-results.json contains failed jobs")
    registry = load_json(registry_path)
    entries = registry.get("pets", [])
    if not isinstance(entries, list) or not entries:
        raise SystemExit("registry-entries.json contains no pets")
    ids = [entry.get("id") for entry in entries]
    if any(not isinstance(pet_id, str) or not pet_id for pet_id in ids):
        raise SystemExit("staged registry contains an invalid pet id")
    if len(ids) != len(set(ids)):
        raise SystemExit("staged registry contains duplicate pet ids")
    packages = {path.name: path for path in packages_root.iterdir() if path.is_dir()}
    if set(packages) != set(ids):
        missing = sorted(set(ids) - set(packages))
        extra = sorted(set(packages) - set(ids))
        raise SystemExit(f"staged package/registry mismatch; missing={missing}, extra={extra}")
    for entry in entries:
        pet_id = entry["id"]
        package = packages[pet_id]
        if contains_symlink(package):
            raise SystemExit(f"staged package contains a symlink: {pet_id}")
        missing = sorted(name for name in REQUIRED_PACKAGE if not (package / name).exists())
        if missing:
            raise SystemExit(f"staged package {pet_id} is missing: {', '.join(missing)}")
        pet = load_json(package / "pet.json")
        if (
            pet.get("id") != pet_id
            or pet.get("spriteVersionNumber") != 2
            or pet.get("spritesheetPath") != "spritesheet.webp"
        ):
            raise SystemExit(f"staged package has invalid pet.json: {pet_id}")
        if entry.get("packagePath") != f"pets/{pet_id}":
            raise SystemExit(f"staged registry has invalid packagePath: {pet_id}")
    return entries, packages


def merged_registry(existing: dict, incoming: list[dict]) -> dict:
    incoming_by_id = {entry["id"]: entry for entry in incoming}
    merged = []
    seen: set[str] = set()
    for entry in existing.get("pets", []):
        pet_id = entry.get("id")
        if pet_id in seen:
            raise SystemExit(f"existing registry contains duplicate id: {pet_id}")
        seen.add(pet_id)
        merged.append(incoming_by_id.get(pet_id, entry))
    for entry in incoming:
        if entry["id"] not in seen:
            merged.append(entry)
            seen.add(entry["id"])
    return {"schemaVersion": existing.get("schemaVersion", 1), "pets": merged}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-root", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="permit atomically replacing package ids already present in pets/",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    staging_root = Path(args.staging_root).resolve()
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        raise SystemExit(f"repo root is not a Git worktree: {repo_root}")
    if repo_root == staging_root or repo_root in staging_root.parents or staging_root in repo_root.parents:
        raise SystemExit("staging root and repository must not contain one another")
    pets_root = repo_root / "pets"
    registry_path = repo_root / "registry" / "pets.json"
    if not pets_root.is_dir() or not registry_path.is_file():
        raise SystemExit("repository must contain pets/ and registry/pets.json")

    lock_name = hashlib.sha256(str(repo_root).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-publish-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    incoming, staged_packages = validate_staging(staging_root)
    existing_registry = load_json(registry_path)
    conflicts = sorted(pet_id for pet_id in staged_packages if (pets_root / pet_id).exists())
    if conflicts and not args.replace_existing:
        raise SystemExit(
            "existing package ids require --replace-existing: " + ", ".join(conflicts)
        )
    target_registry = merged_registry(existing_registry, incoming)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "staged": len(incoming),
                    "new": len(incoming) - len(conflicts),
                    "replace": conflicts,
                    "registryTotal": len(target_registry["pets"]),
                },
                ensure_ascii=False,
            )
        )
        return

    transaction = Path(tempfile.mkdtemp(prefix=".ark-pet-import-", dir=repo_root))
    candidates = transaction / "candidates"
    backups = transaction / "backups"
    displaced = transaction / "displaced"
    candidates.mkdir()
    backups.mkdir()
    displaced.mkdir()
    original_registry = registry_path.read_bytes()
    published: list[tuple[str, bool]] = []
    try:
        for pet_id, source in staged_packages.items():
            shutil.copytree(source, candidates / pet_id, symlinks=False)
        for entry in incoming:
            pet_id = entry["id"]
            target = pets_root / pet_id
            had_existing = target.exists()
            if had_existing:
                target.replace(backups / pet_id)
            (candidates / pet_id).replace(target)
            published.append((pet_id, had_existing))
        atomic_json(registry_path, target_registry)
    except Exception:
        atomic_bytes(registry_path, original_registry)
        for pet_id, had_existing in reversed(published):
            target = pets_root / pet_id
            if target.exists():
                target.replace(displaced / pet_id)
            backup = backups / pet_id
            if had_existing and backup.exists():
                backup.replace(target)
        raise
    finally:
        if transaction.exists():
            shutil.rmtree(transaction)

    print(
        json.dumps(
            {
                "published": len(incoming),
                "new": len(incoming) - len(conflicts),
                "replaced": conflicts,
                "registryTotal": len(target_registry["pets"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
