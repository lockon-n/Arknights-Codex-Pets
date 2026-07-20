#!/usr/bin/env python3
"""Build paginated review sheets from final 192x208 standard-atlas cells."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


STATES = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
]
SOURCE_CELL = (192, 208)
THUMB = (96, 104)
CELL = (192, 228)
LABEL_WIDTH = 190
HEADER_HEIGHT = 28


def checker(size: tuple[int, int], square: int = 12) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], square):
        for x in range(0, size[0], square):
            if (x // square + y // square) % 2:
                draw.rectangle((x, y, x + square - 1, y + square - 1), fill=(232, 232, 232, 255))
    return image


def atlas_cell(atlas: Image.Image, row: int, column: int) -> Image.Image:
    left = column * SOURCE_CELL[0]
    top = row * SOURCE_CELL[1]
    return atlas.crop((left, top, left + SOURCE_CELL[0], top + SOURCE_CELL[1]))


def state_cell(atlas: Image.Image, row: int, frame_count: int, label: str) -> Image.Image:
    output = Image.new("RGBA", CELL, (245, 245, 245, 255))
    draw = ImageDraw.Draw(output)
    draw.text((4, 3), label, fill=(0, 0, 0, 255))
    indexes = [0, max(0, frame_count - 1)]
    for slot, index in enumerate(indexes):
        frame = atlas_cell(atlas, row, index).resize(THUMB, Image.Resampling.LANCZOS)
        bg = checker(THUMB)
        bg.alpha_composite(frame)
        output.alpha_composite(bg, (slot * THUMB[0], 20))
    middle = min(frame_count - 1, frame_count // 2)
    frame = atlas_cell(atlas, row, middle).resize(THUMB, Image.Resampling.LANCZOS)
    bg = checker(THUMB)
    bg.alpha_composite(frame)
    output.alpha_composite(bg, (THUMB[0] // 2, 20 + THUMB[1]))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=5)
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = [job for job in payload["jobs"] if job.get("standard_qa") == "pass"]
    per_page = max(1, args.operators_per_page)
    pages = []
    for page_index in range(math.ceil(len(jobs) / per_page)):
        page_jobs = jobs[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (LABEL_WIDTH + len(STATES) * CELL[0], HEADER_HEIGHT + len(page_jobs) * CELL[1]),
            (255, 255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for column, (state, _row, _count) in enumerate(STATES):
            draw.text((LABEL_WIDTH + column * CELL[0] + 4, 7), state, fill=(0, 0, 0, 255))
        entries = []
        for row_index, job in enumerate(page_jobs):
            y = HEADER_HEIGHT + row_index * CELL[1]
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60, 255))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60, 255))
            atlas_path = job_root / job["pet_id"] / "run" / "standard.webp"
            with Image.open(atlas_path) as opened:
                atlas = opened.convert("RGBA")
            for column, (state, atlas_row, count) in enumerate(STATES):
                sheet.alpha_composite(
                    state_cell(atlas, atlas_row, count, state),
                    (LABEL_WIDTH + column * CELL[0], y),
                )
            entries.append(
                {"operator": job["operator"], "pet_id": job["pet_id"], "model_key": job["model_key"]}
            )
        page_path = output_dir / f"standard-review-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=94, subsampling=0)
        pages.append({"page": str(page_path), "jobs": entries})

    index_path = output_dir / "standard-review-index.json"
    index_path.write_text(json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pages": len(pages), "index": str(index_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
