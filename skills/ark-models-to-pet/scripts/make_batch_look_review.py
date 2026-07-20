#!/usr/bin/env python3
"""Build paginated final-cell-size review sheets for look-control probes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


PROBES = [
    "neutral",
    "eye-x-minus",
    "eye-x-plus",
    "eye-y-minus",
    "eye-y-plus",
    "head-x-minus",
    "head-x-plus",
    "head-y-minus",
    "head-y-plus",
    "head-rot-minus",
    "head-rot-plus",
]
CELL_WIDTH = 192
CELL_HEIGHT = 228
IMAGE_HEIGHT = 208
LABEL_WIDTH = 190
HEADER_HEIGHT = 28


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=5)
    parser.add_argument("--model-key", action="append", default=[])
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_keys = set(args.model_key)
    jobs = [
        job
        for job in payload["jobs"]
        if job.get("direction_probe") == "pass"
        and (not selected_keys or job.get("model_key") in selected_keys)
    ]
    per_page = max(1, args.operators_per_page)
    pages = []
    for page_index in range(math.ceil(len(jobs) / per_page)):
        page_jobs = jobs[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (LABEL_WIDTH + len(PROBES) * CELL_WIDTH, HEADER_HEIGHT + len(page_jobs) * CELL_HEIGHT),
            (255, 255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for column, probe in enumerate(PROBES):
            draw.text((LABEL_WIDTH + column * CELL_WIDTH + 4, 7), probe, fill=(0, 0, 0, 255))
        entries = []
        for row, job in enumerate(page_jobs):
            y = HEADER_HEIGHT + row * CELL_HEIGHT
            config_path = job_root / job["pet_id"] / "look-config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60, 255))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60, 255))
            draw.text((5, y + 70), f"head={config.get('head_bone') or '-'}", fill=(60, 60, 60, 255))
            draw.text(
                (5, y + 90),
                f"eyes={len(config.get('eye_bones') or [])}",
                fill=(60, 60, 60, 255),
            )
            probe_root = job_root / job["pet_id"] / "look-probe" / "look-candidates"
            for column, probe in enumerate(PROBES):
                x = LABEL_WIDTH + column * CELL_WIDTH
                path = probe_root / f"{probe}.png"
                if not path.is_file():
                    draw.rectangle((x, y, x + CELL_WIDTH - 1, y + CELL_HEIGHT - 1), fill=(230, 230, 230, 255))
                    draw.text((x + 4, y + 4), "missing", fill=(130, 0, 0, 255))
                    continue
                with Image.open(path) as opened:
                    image = opened.convert("RGBA").resize((CELL_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS)
                sheet.alpha_composite(Image.new("RGBA", (CELL_WIDTH, IMAGE_HEIGHT), (242, 242, 242, 255)), (x, y + 20))
                sheet.alpha_composite(image, (x, y + 20))
                draw.text((x + 4, y + 3), probe, fill=(0, 0, 0, 255))
            entries.append(
                {
                    "operator": job["operator"],
                    "pet_id": job["pet_id"],
                    "model_key": job["model_key"],
                    "head_bone": config.get("head_bone"),
                    "eye_bones": config.get("eye_bones") or [],
                }
            )
        page_path = output_dir / f"look-review-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=94, subsampling=0)
        pages.append({"page": str(page_path), "jobs": entries})

    index_path = output_dir / "look-review-index.json"
    index_path.write_text(
        json.dumps({"probe_columns": PROBES, "pages": pages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pages": len(pages), "index": str(index_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
