#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a clean Codex v2 pet directory and optional ZIP.")
    parser.add_argument("--spritesheet", required=True)
    parser.add_argument("--pet-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--asset-id", default="")
    parser.add_argument("--operator-name", default="")
    parser.add_argument("--appellation", default="")
    parser.add_argument("--release-cn", default="")
    parser.add_argument("--catalog-commit", default="")
    parser.add_argument("--category", choices=["default", "skin"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--zip-output")
    parser.add_argument("--validation")
    parser.add_argument("--qa-preview")
    parser.add_argument(
        "--qa-file",
        action="append",
        default=[],
        metavar="SOURCE=NAME",
        help="copy an additional QA file into qa/ under NAME",
    )
    parser.add_argument("--source-url", default="https://github.com/isHarryh/Ark-Models")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.pet_id):
        raise SystemExit("pet id must contain lowercase letters, digits, and single hyphens")
    spritesheet = Path(args.spritesheet).resolve()
    if spritesheet.suffix.lower() not in {".png", ".webp"} or not spritesheet.is_file():
        raise SystemExit("spritesheet must be an existing PNG or WebP")
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        if not output_dir.is_dir():
            raise SystemExit(f"output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise SystemExit(f"refusing to package into non-empty directory: {output_dir}")
    qa_inputs: list[tuple[Path, str]] = []
    for raw, name in ((args.validation, "validation.json"), (args.qa_preview, "preview.png")):
        if raw:
            source = Path(raw).resolve()
            if not source.is_file():
                raise SystemExit(f"QA input does not exist: {source}")
            qa_inputs.append((source, name))

    for assignment in args.qa_file:
        if "=" not in assignment:
            raise SystemExit(f"invalid --qa-file value: {assignment}")
        raw_source, name = assignment.split("=", 1)
        if not name or Path(name).name != name:
            raise SystemExit(f"QA destination must be a plain filename: {name}")
        source = Path(raw_source).resolve()
        if not source.is_file():
            raise SystemExit(f"QA input does not exist: {source}")
        qa_inputs.append((source, name))

    qa_names = [name for _, name in qa_inputs]
    if len(qa_names) != len(set(qa_names)):
        raise SystemExit("QA destination filenames must be unique")

    zip_path = Path(args.zip_output).resolve() if args.zip_output else None
    if zip_path and zip_path.exists():
        raise SystemExit(f"refusing to overwrite existing ZIP: {zip_path}")
    if zip_path and output_dir in zip_path.parents:
        raise SystemExit("ZIP output must be outside the package directory")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    zip_staging: Path | None = None
    published = False
    try:
        sheet_name = f"spritesheet{spritesheet.suffix.lower()}"
        shutil.copy2(spritesheet, staging / sheet_name)
        metadata = {
            "id": args.pet_id,
            "displayName": args.display_name,
            "description": args.description,
            "spriteVersionNumber": 2,
            "spritesheetPath": sheet_name,
        }
        (staging / "pet.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        source_lines = [
            "# Source and rights",
            "",
            f"- Ark-Models source: {args.source_url}",
            f"- Ark-Models catalog commit: `{args.catalog_commit or 'not recorded'}`",
            f"- Model key: `{args.model_key}`",
            f"- Asset ID: `{args.asset_id or 'not recorded'}`",
            f"- Operator: {args.operator_name or args.display_name}",
            f"- English appellation: {args.appellation or 'not recorded'}",
            f"- CN release time: `{args.release_cn or 'not recorded'}`",
            f"- Outfit category: `{args.category}`",
            "",
            "This package contains converted Arknights game art. Artwork and game content "
            "belong to their respective rights holders, including Hypergryph. This package "
            "does not grant redistribution or commercial-use rights.",
            "",
        ]
        (staging / "SOURCE.md").write_text(
            "\n".join(source_lines),
            encoding="utf-8",
        )
        provenance = {
            "sourceUrl": args.source_url,
            "catalogCommit": args.catalog_commit,
            "modelKey": args.model_key,
            "assetId": args.asset_id,
            "operatorName": args.operator_name or args.display_name,
            "appellation": args.appellation,
            "releaseCn": args.release_cn,
            "outfitCategory": args.category,
        }
        (staging / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if qa_inputs:
            qa_dir = staging / "qa"
            qa_dir.mkdir()
            for source, name in qa_inputs:
                shutil.copy2(source, qa_dir / name)

        if zip_path:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=zip_path.parent,
                prefix=f".{zip_path.name}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                zip_staging = Path(handle.name)
            with zipfile.ZipFile(zip_staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.write(path, Path(output_dir.name) / path.relative_to(staging))

        if output_dir.exists():
            output_dir.rmdir()
        staging.replace(output_dir)
        published = True
        if zip_path and zip_staging:
            zip_staging.replace(zip_path)
            zip_staging = None
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)
        if zip_staging and zip_staging.exists():
            zip_staging.unlink()

    print(zip_path or output_dir)


if __name__ == "__main__":
    main()
