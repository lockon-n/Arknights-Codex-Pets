#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def atlas_pages(text: str) -> list[str]:
    pages = []
    previous_blank = True
    for raw in text.splitlines():
        line = raw.strip()
        if line and previous_blank and ":" not in line:
            pages.append(line)
        previous_blank = not line
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight one downloaded Spine model.")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args()
    model_dir = Path(args.model_dir).resolve()
    atlases = list(model_dir.glob("*.atlas"))
    skeletons = list(model_dir.glob("*.skel")) + [
        path for path in model_dir.glob("*.json") if path.name != "model-manifest.json"
    ]
    pngs = list(model_dir.glob("*.png"))
    errors = []
    warnings = []
    if len(atlases) != 1:
        errors.append(f"expected exactly one .atlas, found {len(atlases)}")
    if len(skeletons) != 1:
        errors.append(f"expected exactly one .skel or skeleton .json, found {len(skeletons)}")
    pages = atlas_pages(atlases[0].read_text(encoding="utf-8")) if len(atlases) == 1 else []
    if len(pages) != 1:
        warnings.append(f"renderer fast path expects one atlas page, found {len(pages)}")
    image_info = []
    for path in pngs:
        with Image.open(path) as image:
            image_info.append({"file": path.name, "width": image.width, "height": image.height, "mode": image.mode})
    result = {
        "ok": not errors,
        "model_dir": str(model_dir),
        "atlas": atlases[0].name if len(atlases) == 1 else None,
        "skeleton": skeletons[0].name if len(skeletons) == 1 else None,
        "atlas_pages": pages,
        "images": image_info,
        "errors": errors,
        "warnings": warnings,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text, end="")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
