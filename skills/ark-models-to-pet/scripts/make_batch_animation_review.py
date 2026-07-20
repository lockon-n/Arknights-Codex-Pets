#!/usr/bin/env python3
"""Build paginated, labeled review sheets from batch animation previews."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


THUMB_SIZE = (96, 104)
CELL_SIZE = (192, 228)
OPERATOR_LABEL_WIDTH = 176
HEADER_HEIGHT = 30


def sample_paths(directory: Path) -> list[Path]:
    frames = sorted(directory.glob("*.png"))
    if not frames:
        return []
    indexes = sorted({0, len(frames) // 3, (2 * len(frames)) // 3, len(frames) - 1})
    return [frames[min(index, len(frames) - 1)] for index in indexes]


def render_cell(directory: Path) -> Image.Image:
    cell = Image.new("RGBA", CELL_SIZE, (242, 242, 242, 255))
    for index, path in enumerate(sample_paths(directory)[:4]):
        with Image.open(path) as opened:
            frame = opened.convert("RGBA").resize(THUMB_SIZE, Image.Resampling.LANCZOS)
        x = (index % 2) * THUMB_SIZE[0]
        y = 20 + (index // 2) * THUMB_SIZE[1]
        cell.alpha_composite(frame, (x, y))
    ImageDraw.Draw(cell).text((5, 4), directory.name, fill=(0, 0, 0, 255))
    return cell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=7)
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = [job for job in payload["jobs"] if job.get("preview_render") == "pass"]
    animation_names = sorted(
        {
            path.name
            for job in jobs
            for path in (job_root / job["pet_id"] / "preview-render" / "animations").iterdir()
            if path.is_dir()
        }
    )
    per_page = max(1, args.operators_per_page)
    pages = []
    for page_index in range(math.ceil(len(jobs) / per_page)):
        page_jobs = jobs[page_index * per_page : (page_index + 1) * per_page]
        width = OPERATOR_LABEL_WIDTH + len(animation_names) * CELL_SIZE[0]
        height = HEADER_HEIGHT + len(page_jobs) * CELL_SIZE[1]
        sheet = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        for column, animation in enumerate(animation_names):
            draw.text(
                (OPERATOR_LABEL_WIDTH + column * CELL_SIZE[0] + 5, 8),
                animation,
                fill=(0, 0, 0, 255),
            )
        entries = []
        for row, job in enumerate(page_jobs):
            y = HEADER_HEIGHT + row * CELL_SIZE[1]
            draw.text((6, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((6, y + 28), job["pet_id"], fill=(70, 70, 70, 255))
            draw.text((6, y + 48), job["model_key"], fill=(70, 70, 70, 255))
            animations_root = job_root / job["pet_id"] / "preview-render" / "animations"
            available = []
            for column, animation in enumerate(animation_names):
                directory = animations_root / animation
                x = OPERATOR_LABEL_WIDTH + column * CELL_SIZE[0]
                if directory.is_dir():
                    sheet.alpha_composite(render_cell(directory), (x, y))
                    available.append(animation)
                else:
                    draw.rectangle((x, y, x + CELL_SIZE[0] - 1, y + CELL_SIZE[1] - 1), fill=(225, 225, 225, 255))
                    draw.text((x + 6, y + 6), "missing", fill=(130, 0, 0, 255))
            entries.append(
                {
                    "operator": job["operator"],
                    "pet_id": job["pet_id"],
                    "model_key": job["model_key"],
                    "animations": available,
                }
            )
        page_path = output_dir / f"animation-review-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=92, subsampling=0)
        pages.append({"page": str(page_path), "jobs": entries})

    index_path = output_dir / "animation-review-index.json"
    index_path.write_text(
        json.dumps({"animation_columns": animation_names, "pages": pages}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pages": len(pages), "index": str(index_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
