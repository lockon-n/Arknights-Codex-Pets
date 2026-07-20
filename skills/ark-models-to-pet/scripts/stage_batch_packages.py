#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from PIL import Image


GATES = (
    "standard_visual_qa",
    "direction_qa",
    "atlas_qa",
    "visual_qa",
)

REQUIRED_QA = {
    "v2-validation.json": "v2-validation.json",
    "directions-labeled.png": "directions-labeled.png",
    "contact-extended.png": "contact-extended.png",
    "direction-continuity.json": "direction-continuity.json",
    "standard-contact.png": "standard-contact.png",
}

OPTIONAL_QA = {
    "blind-validation.json": "blind-validation.json",
    "blind-consensus.json": "blind-consensus.json",
    "chroma-despill.json": "chroma-despill.json",
    "normalization.json": "normalization.json",
    "standard-validation.json": "standard-validation.json",
    "frame-review.json": "frame-review.json",
    "final-visual-review.json": "final-visual-review.json",
}

RESULTS_NAME = "batch-package-results.json"
REGISTRY_NAME = "registry-entries.json"
EXPECTED_ATLAS_SIZE = (1536, 2288)
PET_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class PackageError(RuntimeError):
    pass


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}-",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        temporary = Path(handle.name)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inside_git_worktree(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def scrub_absolute_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: scrub_absolute_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_absolute_paths(item) for item in value]
    if isinstance(value, str) and Path(value).is_absolute():
        return Path(value).name
    return value


def find_absolute_paths(value: Any, location: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(find_absolute_paths(item, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_absolute_paths(item, f"{location}[{index}]"))
    elif isinstance(value, str) and Path(value).is_absolute():
        found.append(location)
    return found


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageError(f"invalid {label}: {path.name}: {error}") from error


def prepare_qa_inputs(run_dir: Path, temporary: Path) -> dict[str, Path]:
    source_qa = run_dir / "qa"
    prepared: dict[str, Path] = {}
    missing = [name for name in REQUIRED_QA if not (source_qa / name).is_file()]
    if missing:
        raise PackageError("missing required QA: " + ", ".join(sorted(missing)))

    for name in (*REQUIRED_QA, *OPTIONAL_QA):
        source = source_qa / name
        if not source.is_file():
            continue
        destination = temporary / name
        if source.suffix.lower() == ".json":
            payload = load_json(source, f"QA JSON {name}")
            destination.write_text(
                json.dumps(scrub_absolute_paths(payload), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            shutil.copy2(source, destination)
        prepared[name] = destination
    return prepared


def verify_image(path: Path, *, expected_format: str | None = None) -> tuple[int, int, str, str]:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            image_format = image.format or ""
            mode = image.mode
    except Exception as error:
        raise PackageError(f"unreadable image {path.name}: {error}") from error
    if width <= 0 or height <= 0:
        raise PackageError(f"empty image geometry: {path.name}")
    if expected_format and image_format.upper() != expected_format.upper():
        raise PackageError(
            f"unexpected image format for {path.name}: {image_format}, expected {expected_format}"
        )
    return width, height, image_format, mode


def validate_package(
    package_dir: Path,
    job: dict[str, Any],
    source_sheet: Path,
) -> dict[str, Any]:
    required_top = {
        "pet.json",
        "spritesheet.webp",
        "SOURCE.md",
        "provenance.json",
        "qa",
    }
    missing_top = sorted(name for name in required_top if not (package_dir / name).exists())
    if missing_top:
        raise PackageError("package is missing: " + ", ".join(missing_top))

    for path in package_dir.rglob("*"):
        if path.is_symlink():
            raise PackageError(f"package contains a symlink: {path.relative_to(package_dir)}")

    pet = load_json(package_dir / "pet.json", "pet.json")
    expected_pet = {
        "id": job["pet_id"],
        "displayName": job["display_name"],
        "spriteVersionNumber": 2,
        "spritesheetPath": "spritesheet.webp",
    }
    for key, expected in expected_pet.items():
        if pet.get(key) != expected:
            raise PackageError(f"pet.json {key}={pet.get(key)!r}, expected {expected!r}")
    if not isinstance(pet.get("description"), str) or not pet["description"].strip():
        raise PackageError("pet.json description must be non-empty")

    sheet = package_dir / "spritesheet.webp"
    width, height, image_format, mode = verify_image(sheet, expected_format="WEBP")
    if (width, height) != EXPECTED_ATLAS_SIZE or mode != "RGBA":
        raise PackageError(
            f"invalid v2 atlas geometry/mode: {width}x{height} {mode}, expected 1536x2288 RGBA"
        )
    source_hash = sha256(source_sheet)
    package_hash = sha256(sheet)
    if source_hash != package_hash:
        raise PackageError("packaged spritesheet is not a bit-for-bit copy of the approved source")

    provenance = load_json(package_dir / "provenance.json", "provenance.json")
    expected_provenance = {
        "sourceUrl": str(job["package_source_url"]),
        "catalogCommit": str(job.get("catalog_commit", "")),
        "modelKey": str(job["model_key"]),
        "assetId": str(job.get("asset_id", "")),
        "operatorName": str(job.get("operator") or job["display_name"]),
        "appellation": str(job.get("appellation", "")),
        "releaseCn": str(job.get("release_cn", "")),
        "outfitCategory": str(job["package_category"]),
    }
    for key, expected in expected_provenance.items():
        if provenance.get(key) != expected:
            raise PackageError(
                f"provenance.json {key}={provenance.get(key)!r}, expected {expected!r}"
            )

    qa_dir = package_dir / "qa"
    required_packaged_qa = {
        "validation.json",
        "preview.png",
        *REQUIRED_QA,
    }
    missing_qa = sorted(name for name in required_packaged_qa if not (qa_dir / name).is_file())
    if missing_qa:
        raise PackageError("package QA is missing: " + ", ".join(missing_qa))

    validation = load_json(qa_dir / "v2-validation.json", "v2 validation")
    validation_alias = load_json(qa_dir / "validation.json", "validation alias")
    for label, payload in (("v2-validation.json", validation), ("validation.json", validation_alias)):
        if payload.get("ok") is not True or payload.get("errors"):
            raise PackageError(f"{label} does not record a passing atlas")
        if (
            payload.get("sprite_version_number") != 2
            or payload.get("width") != EXPECTED_ATLAS_SIZE[0]
            or payload.get("height") != EXPECTED_ATLAS_SIZE[1]
        ):
            raise PackageError(f"{label} does not describe a 1536x2288 v2 atlas")

    continuity = load_json(qa_dir / "direction-continuity.json", "direction continuity")
    if continuity.get("ok") is not True:
        raise PackageError("direction-continuity.json does not record ok=true")

    for name in ("preview.png", "directions-labeled.png", "contact-extended.png", "standard-contact.png"):
        verify_image(qa_dir / name, expected_format="PNG")

    for json_path in (package_dir / "pet.json", package_dir / "provenance.json", *qa_dir.glob("*.json")):
        absolute_fields = find_absolute_paths(load_json(json_path, str(json_path.relative_to(package_dir))))
        if absolute_fields:
            raise PackageError(
                f"machine-specific absolute paths remain in {json_path.name}: "
                + ", ".join(absolute_fields[:5])
            )

    source_notice = (package_dir / "SOURCE.md").read_text(encoding="utf-8").strip()
    if not source_notice:
        raise PackageError("SOURCE.md is empty")

    return {
        "petJsonVersion": 2,
        "atlas": {
            "format": image_format,
            "mode": mode,
            "width": width,
            "height": height,
            "sha256": package_hash,
            "sourceCopyMatches": True,
        },
        "qaFiles": sorted(path.name for path in qa_dir.iterdir() if path.is_file()),
        "absolutePathLeakage": False,
    }


def format_description(template: str, job: dict[str, Any]) -> str:
    values = {key: str(value) for key, value in job.items() if value is not None}
    try:
        rendered = template.format_map(values).strip()
    except KeyError as error:
        raise PackageError(f"description template references missing field: {error.args[0]}") from error
    if not rendered:
        raise PackageError("description template produced an empty value")
    return rendered


def package_job(
    job: dict[str, Any],
    job_root: Path,
    packages_root: Path,
    package_script: Path,
    description_template: str,
    source_url: str,
) -> dict[str, Any]:
    run_dir = job_root / job["pet_id"] / "run"
    source_sheet = run_dir / "spritesheet.webp"
    if not source_sheet.is_file():
        raise PackageError("approved spritesheet.webp is missing")

    package_target = packages_root / job["pet_id"]
    if package_target.exists():
        return validate_package(package_target, job, source_sheet)

    candidate_root = Path(
        tempfile.mkdtemp(prefix=f".{job['pet_id']}-candidate-", dir=packages_root)
    )
    candidate_package = candidate_root / job["pet_id"]
    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{job['pet_id']}-qa-", dir=candidate_root
        ) as qa_temporary_raw:
            qa_inputs = prepare_qa_inputs(run_dir, Path(qa_temporary_raw))
            command = [
                sys.executable,
                str(package_script),
                "--spritesheet",
                str(source_sheet),
                "--pet-id",
                str(job["pet_id"]),
                "--display-name",
                str(job["display_name"]),
                "--description",
                format_description(description_template, job),
                "--model-key",
                str(job["model_key"]),
                "--asset-id",
                str(job.get("asset_id", "")),
                "--operator-name",
                str(job.get("operator") or job["display_name"]),
                "--appellation",
                str(job.get("appellation", "")),
                "--release-cn",
                str(job.get("release_cn", "")),
                "--catalog-commit",
                str(job.get("catalog_commit", "")),
                "--category",
                str(job["package_category"]),
                "--source-url",
                source_url,
                "--validation",
                str(qa_inputs["v2-validation.json"]),
                "--qa-preview",
                str(qa_inputs["directions-labeled.png"]),
                "--output-dir",
                str(candidate_package),
            ]
            for name, source in sorted(qa_inputs.items()):
                command.extend(["--qa-file", f"{source}={name}"])

            completed = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if completed.returncode:
                tail = "\n".join(completed.stdout.splitlines()[-10:])
                raise PackageError(f"package_pet.py failed: {tail}")

        checks = validate_package(candidate_package, job, source_sheet)
        candidate_package.replace(package_target)
        return checks
    finally:
        if candidate_root.exists():
            shutil.rmtree(candidate_root)


def registry_entry(job: dict[str, Any], approved_at: str) -> dict[str, Any]:
    return {
        "id": job["pet_id"],
        "displayName": job["display_name"],
        "modelKey": job["model_key"],
        "category": job["package_category"],
        "upstreamCommit": job.get("catalog_commit", ""),
        "status": "approved",
        "packagePath": f"pets/{job['pet_id']}",
        "approvedAt": approved_at,
    }


def eligible(job: dict[str, Any]) -> bool:
    return all(job.get(gate) == "pass" for gate in GATES)


def validate_job_identity(job: dict[str, Any], default_category: str) -> dict[str, Any]:
    normalized = dict(job)
    for field in ("pet_id", "display_name", "model_key"):
        if not isinstance(normalized.get(field), str) or not normalized[field].strip():
            raise PackageError(f"job is missing required field: {field}")
    if not PET_ID_PATTERN.fullmatch(normalized["pet_id"]):
        raise PackageError(f"invalid pet_id: {normalized['pet_id']}")
    category = normalized.get("category", default_category)
    if category not in {"default", "skin"}:
        raise PackageError(f"invalid package category for {normalized['pet_id']}: {category}")
    normalized["package_category"] = category
    return normalized


def portable_error(message: str, job_root: Path, staging_root: Path) -> str:
    return message.replace(str(job_root), "<job-root>").replace(
        str(staging_root), "<staging-root>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage validated Ark-Models Codex v2 pet packages without modifying the batch "
            "manifest or a Git repository."
        )
    )
    parser.add_argument("--manifest", required=True, help="read-only batch manifest JSON")
    parser.add_argument("--job-root", required=True, help="root containing PET_ID/run directories")
    parser.add_argument("--staging-root", required=True, help="repository-external output root")
    parser.add_argument("--category", choices=["default", "skin"], default="default")
    parser.add_argument(
        "--description-template",
        default=(
            "Official Arknights building chibi for {display_name}, converted from "
            "Ark-Models as a Codex v2 pet."
        ),
    )
    parser.add_argument(
        "--source-url", default="https://github.com/isHarryh/Ark-Models"
    )
    parser.add_argument("--approved-at", default=date.today().isoformat(), metavar="YYYY-MM-DD")
    parser.add_argument("--model-key", action="append", default=[], help="limit to model key")
    parser.add_argument("--pet-id", action="append", default=[], help="limit to pet id")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="allow an existing staging root and validate/reuse complete packages",
    )
    args = parser.parse_args()

    manifest = Path(args.manifest).resolve()
    job_root = Path(args.job_root).resolve()
    staging_root = Path(args.staging_root).resolve()
    package_script = Path(__file__).resolve().with_name("package_pet.py")

    lock_name = hashlib.sha256(str(staging_root).encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"ark-pet-package-{lock_name}.lock"
    lock_handle = lock_path.open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)

    if not manifest.is_file():
        raise SystemExit(f"manifest does not exist: {manifest}")
    if not job_root.is_dir():
        raise SystemExit(f"job root does not exist: {job_root}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.approved_at):
        raise SystemExit("--approved-at must use YYYY-MM-DD")
    try:
        date.fromisoformat(args.approved_at)
    except ValueError as error:
        raise SystemExit(f"invalid --approved-at: {args.approved_at}") from error
    git_root = inside_git_worktree(staging_root)
    if git_root:
        raise SystemExit(
            f"refusing to stage inside a Git worktree ({git_root}); use a separate staging root"
        )
    if staging_root.exists() and not staging_root.is_dir():
        raise SystemExit(f"staging root is not a directory: {staging_root}")
    if staging_root.exists() and any(staging_root.iterdir()) and not args.resume:
        raise SystemExit(
            f"refusing non-empty staging root: {staging_root}; use --resume only for this batch"
        )

    payload = load_json(manifest, "batch manifest")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SystemExit("batch manifest must contain a jobs array")
    try:
        all_jobs = [validate_job_identity(job, args.category) for job in payload["jobs"]]
    except PackageError as error:
        raise SystemExit(str(error)) from error
    for job in all_jobs:
        if not job.get("catalog_commit") and payload.get("catalog_commit"):
            job["catalog_commit"] = payload["catalog_commit"]
        job["package_source_url"] = args.source_url

    pet_ids = [job["pet_id"] for job in all_jobs]
    model_keys = [job["model_key"] for job in all_jobs]
    if len(pet_ids) != len(set(pet_ids)):
        raise SystemExit("batch manifest contains duplicate pet_id values")
    if len(model_keys) != len(set(model_keys)):
        raise SystemExit("batch manifest contains duplicate model_key values")

    requested_keys = set(args.model_key)
    requested_ids = set(args.pet_id)
    unknown_keys = requested_keys - set(model_keys)
    unknown_ids = requested_ids - set(pet_ids)
    if unknown_keys or unknown_ids:
        details = [
            *(f"unknown model key: {value}" for value in sorted(unknown_keys)),
            *(f"unknown pet id: {value}" for value in sorted(unknown_ids)),
        ]
        raise SystemExit("; ".join(details))

    selected = [
        job
        for job in all_jobs
        if (not requested_keys or job["model_key"] in requested_keys)
        and (not requested_ids or job["pet_id"] in requested_ids)
    ]
    eligible_by_id = {job["pet_id"]: job for job in all_jobs if eligible(job)}

    staging_root.mkdir(parents=True, exist_ok=True)
    if args.resume:
        for path in staging_root.iterdir():
            if path.is_file() and any(
                path.name.startswith(f".{name}-")
                for name in (RESULTS_NAME, REGISTRY_NAME)
            ):
                path.unlink()
    allowed_top = {"pets", RESULTS_NAME, REGISTRY_NAME}
    unexpected = sorted(path.name for path in staging_root.iterdir() if path.name not in allowed_top)
    if unexpected:
        raise SystemExit(
            "staging root contains unexpected entries: " + ", ".join(unexpected)
        )
    packages_root = staging_root / "pets"
    packages_root.mkdir(exist_ok=True)
    if not packages_root.is_dir():
        raise SystemExit(f"package target is not a directory: {packages_root}")
    stale_candidates = [
        path
        for path in packages_root.iterdir()
        if path.is_dir()
        and any(path.name.startswith(f".{pet_id}-candidate-") for pet_id in pet_ids)
    ]
    if stale_candidates and args.resume:
        for path in stale_candidates:
            shutil.rmtree(path)
    existing_unknown = sorted(
        path.name
        for path in packages_root.iterdir()
        if path.name not in eligible_by_id
    )
    if existing_unknown:
        raise SystemExit(
            "staging root contains packages that are not currently eligible in this manifest: "
            + ", ".join(existing_unknown)
        )

    started_at = datetime.now(UTC).isoformat()
    results: list[dict[str, Any]] = []

    def persist_results() -> None:
        counts = {
            outcome: sum(item["outcome"] == outcome for item in results)
            for outcome in ("packaged", "resumed", "skipped", "failed")
        }
        report = {
            "schemaVersion": 1,
            "manifest": manifest.name,
            "gatePolicy": {gate: "pass" for gate in GATES},
            "startedAt": started_at,
            "updatedAt": datetime.now(UTC).isoformat(),
            "resume": bool(args.resume),
            "summary": {"selected": len(selected), **counts},
            "jobs": results,
        }
        atomic_json(staging_root / RESULTS_NAME, report)

    for job in selected:
        gate_values = {gate: job.get(gate, "missing") for gate in GATES}
        base_result = {
            "petId": job["pet_id"],
            "modelKey": job["model_key"],
            "gates": gate_values,
        }
        if not eligible(job):
            result = {
                **base_result,
                "outcome": "skipped",
                "reason": "all four package gates must equal pass",
            }
        else:
            target = packages_root / job["pet_id"]
            was_existing = target.exists()
            try:
                checks = package_job(
                    job,
                    job_root,
                    packages_root,
                    package_script,
                    args.description_template,
                    args.source_url,
                )
            except Exception as error:
                result = {
                    **base_result,
                    "outcome": "failed",
                    "error": portable_error(str(error), job_root, staging_root),
                }
            else:
                result = {
                    **base_result,
                    "outcome": "resumed" if was_existing else "packaged",
                    "packagePath": f"pets/{job['pet_id']}",
                    "checks": checks,
                }
        results.append(result)
        persist_results()
        print(json.dumps(result, ensure_ascii=False), flush=True)

    registry_jobs: list[dict[str, Any]] = []
    registry_failures: list[str] = []
    for pet_id, job in sorted(eligible_by_id.items()):
        package_dir = packages_root / pet_id
        if not package_dir.exists():
            continue
        source_sheet = job_root / pet_id / "run" / "spritesheet.webp"
        try:
            validate_package(package_dir, job, source_sheet)
        except Exception as error:
            registry_failures.append(
                f"{pet_id}: {portable_error(str(error), job_root, staging_root)}"
            )
        else:
            registry_jobs.append(registry_entry(job, args.approved_at))

    atomic_json(
        staging_root / REGISTRY_NAME,
        {"schemaVersion": 1, "pets": registry_jobs},
    )
    persist_results()
    failed_count = sum(item["outcome"] == "failed" for item in results)
    if registry_failures:
        for failure in registry_failures:
            print(json.dumps({"registryValidationError": failure}, ensure_ascii=False), file=sys.stderr)
    print(
        json.dumps(
            {
                "staged": len(registry_jobs),
                "failed": failed_count + len(registry_failures),
                "results": RESULTS_NAME,
                "registry": REGISTRY_NAME,
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed_count or registry_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
