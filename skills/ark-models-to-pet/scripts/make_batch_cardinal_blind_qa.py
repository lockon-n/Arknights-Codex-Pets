#!/usr/bin/env python3
"""Create paginated blind cardinal-direction sheets for a v2 pet batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw


CELL = (192, 208)
LABEL_WIDTH = 210
HEADER_HEIGHT = 28


def atlas_direction(atlas: Image.Image, index: int) -> Image.Image:
    row = 9 + index // 8
    column = index % 8
    left = column * CELL[0]
    top = row * CELL[1]
    return atlas.crop((left, top, left + CELL[0], top + CELL[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=5)
    parser.add_argument("--model-key", action="append", default=[])
    parser.add_argument(
        "--display-scale",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="nearest-neighbor review-sheet scale; source atlas cells remain unchanged",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_keys = set(args.model_key)
    jobs = [
        job
        for job in payload["jobs"]
        if job.get("atlas_qa") == "pass"
        and (not selected_keys or job.get("model_key") in selected_keys)
    ]
    missing = selected_keys - {job.get("model_key") for job in jobs}
    if missing:
        raise SystemExit(f"selected model keys are not atlas-approved: {', '.join(sorted(missing))}")
    records = []
    rendered = []
    for job in jobs:
        atlas_path = job_root / job["pet_id"] / "run" / "spritesheet.webp"
        with Image.open(atlas_path) as opened:
            atlas = opened.convert("RGBA")
        if atlas.size != (1536, 2288):
            raise SystemExit(f"{job['model_key']} atlas is not 1536x2288")
        rng = random.Random(
            int.from_bytes(hashlib.sha256(atlas_path.read_bytes()).digest()[:8], "big")
        )
        horizontal = [(4, "screen-right"), (12, "screen-left")]
        vertical = [(0, "up"), (8, "down")]
        rng.shuffle(horizontal)
        rng.shuffle(vertical)
        cells = [
            atlas_direction(atlas, horizontal[0][0]),
            atlas_direction(atlas, horizontal[1][0]),
            atlas_direction(atlas, vertical[0][0]),
            atlas_direction(atlas, vertical[1][0]),
        ]
        rendered.append((job, cells))
        records.append(
            {
                "model_key": job["model_key"],
                "pet_id": job["pet_id"],
                "horizontal_A": horizontal[0][1],
                "horizontal_B": horizontal[1][1],
                "vertical_A": vertical[0][1],
                "vertical_B": vertical[1][1],
                "atlas_sha256": hashlib.sha256(atlas_path.read_bytes()).hexdigest(),
            }
        )

    per_page = max(1, args.operators_per_page)
    display_cell = (CELL[0] * args.display_scale, CELL[1] * args.display_scale)
    row_height = display_cell[1] + 28
    pages = []
    headers = ["Horizontal A", "Horizontal B", "Vertical A", "Vertical B"]
    for page_index in range(math.ceil(len(rendered) / per_page)):
        page_rows = rendered[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (
                LABEL_WIDTH + 4 * display_cell[0],
                HEADER_HEIGHT + len(page_rows) * row_height,
            ),
            (255, 255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for column, label in enumerate(headers):
            draw.text(
                (LABEL_WIDTH + column * display_cell[0] + 5, 7),
                label,
                fill=(0, 0, 0, 255),
            )
        page_jobs = []
        for row, (job, cells) in enumerate(page_rows):
            y = HEADER_HEIGHT + row * row_height
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60, 255))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60, 255))
            for column, cell in enumerate(cells):
                x = LABEL_WIDTH + column * display_cell[0]
                if args.display_scale > 1:
                    cell = cell.resize(display_cell, Image.Resampling.NEAREST)
                background = Image.new("RGBA", display_cell, (242, 242, 242, 255))
                background.alpha_composite(cell)
                sheet.alpha_composite(background, (x, y + 20))
            page_jobs.append(job["model_key"])
        page_path = output_dir / f"cardinal-blind-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=95, subsampling=0)
        pages.append({"page": str(page_path), "model_keys": page_jobs})

    (output_dir / "cardinal-blind-key.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "display_scale": args.display_scale,
                "instructions": "Do not provide this answer key to blind reviewers.",
                "jobs": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "cardinal-blind-index.json").write_text(
        json.dumps(
            {"display_scale": args.display_scale, "pages": pages},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(records), "pages": len(pages)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
