#!/usr/bin/env python3
"""Create paginated native-cell final visual-review sheets for a pet batch."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


CELL = (192, 208)
LABEL_WIDTH = 210
HEADER_HEIGHT = 30
ROW_HEIGHT = 228
COLUMNS = [
    ("Idle", 0, 0),
    ("Run R", 1, 0),
    ("Run L", 2, 0),
    ("Wave", 3, 0),
    ("Failed", 5, 0),
    ("Wait", 6, 0),
    ("Up", 9, 0),
    ("Right", 9, 4),
    ("Down", 10, 0),
    ("Left", 10, 4),
]


def crop_cell(atlas: Image.Image, row: int, column: int) -> Image.Image:
    left = column * CELL[0]
    top = row * CELL[1]
    return atlas.crop((left, top, left + CELL[0], top + CELL[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=5)
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    jobs = [job for job in payload["jobs"] if job.get("atlas_qa") == "pass"]
    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    per_page = max(1, args.operators_per_page)
    pages = []

    for page_index in range(math.ceil(len(jobs) / per_page)):
        page_jobs = jobs[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (LABEL_WIDTH + len(COLUMNS) * CELL[0], HEADER_HEIGHT + len(page_jobs) * ROW_HEIGHT),
            (255, 255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for column, (label, _, _) in enumerate(COLUMNS):
            draw.text((LABEL_WIDTH + column * CELL[0] + 5, 8), label, fill=(0, 0, 0, 255))
        model_keys = []
        for row_index, job in enumerate(page_jobs):
            y = HEADER_HEIGHT + row_index * ROW_HEIGHT
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60, 255))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60, 255))
            atlas_path = job_root / job["pet_id"] / "run" / "spritesheet.webp"
            with Image.open(atlas_path) as opened:
                atlas = opened.convert("RGBA")
            if atlas.size != (1536, 2288):
                raise SystemExit(f"{job['model_key']} atlas is not 1536x2288")
            for column, (_, atlas_row, atlas_column) in enumerate(COLUMNS):
                cell = crop_cell(atlas, atlas_row, atlas_column)
                background = Image.new("RGBA", CELL, (242, 242, 242, 255))
                background.alpha_composite(cell)
                sheet.alpha_composite(background, (LABEL_WIDTH + column * CELL[0], y + 10))
            model_keys.append(job["model_key"])
        page_path = output_dir / f"final-review-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=95, subsampling=0)
        pages.append({"page": str(page_path), "model_keys": model_keys})

    index = {
        "schema_version": 1,
        "instructions": (
            "Inspect native-size standard states plus labeled cardinal cells for sharpness, identity, "
            "framing, alpha edges, scale consistency, and natural localized direction motion."
        ),
        "pages": pages,
    }
    (output_dir / "final-review-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"jobs": len(jobs), "pages": len(pages)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
