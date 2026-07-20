#!/usr/bin/env python3
"""Create blind cardinal sheets with full cells and automatically focused local differences."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


CELL = (192, 208)
FOCUS = (256, 256)
LOCAL_CROP = 72
LABEL_WIDTH = 210
HEADER_HEIGHT = 72
ROW_HEIGHT = 282
HEADERS = [
    "H A full",
    "H B full",
    "H A local",
    "H B local",
    "V A full",
    "V B full",
    "V A local",
    "V B local",
]
WIDTHS = [CELL[0], CELL[0], FOCUS[0], FOCUS[0], CELL[0], CELL[0], FOCUS[0], FOCUS[0]]


def atlas_direction(atlas: Image.Image, index: int) -> Image.Image:
    row = 9 + index // 8
    column = index % 8
    left = column * CELL[0]
    top = row * CELL[1]
    return atlas.crop((left, top, left + CELL[0], top + CELL[1]))


def focus_box(first: Image.Image, second: Image.Image, padding: int = 10) -> tuple[int, int, int, int]:
    difference = ImageChops.difference(first, second).convert("RGBA")
    bbox = difference.getbbox()
    if bbox is None:
        return (0, 0, CELL[0], CELL[1])
    weighted_x = weighted_y = total = 0
    for y in range(CELL[1]):
        for x in range(CELL[0]):
            weight = max(difference.getpixel((x, y)))
            if not weight:
                continue
            weighted_x += x * weight
            weighted_y += y * weight
            total += weight
    center_x = weighted_x / total if total else (bbox[0] + bbox[2]) / 2
    center_y = weighted_y / total if total else (bbox[1] + bbox[3]) / 2
    changed_width = bbox[2] - bbox[0] + padding * 2
    changed_height = bbox[3] - bbox[1] + padding * 2
    size = min(LOCAL_CROP, max(32, min(max(changed_width, changed_height), LOCAL_CROP)))
    left = round(center_x - size / 2)
    top = round(center_y - size / 2)
    left = min(max(0, left), CELL[0] - size)
    top = min(max(0, top), CELL[1] - size)
    right = left + size
    bottom = top + size
    if right > CELL[0]:
        left -= right - CELL[0]
        right = CELL[0]
    if bottom > CELL[1]:
        top -= bottom - CELL[1]
        bottom = CELL[1]
    return (left, top, right, bottom)


def local_view(cell: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    view = cell.crop(box).resize(FOCUS, Image.Resampling.NEAREST)
    overlay = Image.new("RGBA", FOCUS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for position in range(32, FOCUS[0], 32):
        draw.line((position, 0, position, FOCUS[1]), fill=(0, 120, 255, 72), width=1)
        draw.line((0, position, FOCUS[0], position), fill=(0, 120, 255, 72), width=1)
    draw.line((FOCUS[0] // 2, 0, FOCUS[0] // 2, FOCUS[1]), fill=(255, 80, 0, 110), width=1)
    draw.line((0, FOCUS[1] // 2, FOCUS[0], FOCUS[1] // 2), fill=(255, 80, 0, 110), width=1)
    return Image.alpha_composite(view, overlay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=4)
    parser.add_argument("--model-key", action="append", default=[])
    parser.add_argument(
        "--selection-json",
        help="optional JSON containing a jobs array with model_key values",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).resolve().read_text(encoding="utf-8"))
    selected_keys = set(args.model_key)
    if args.selection_json:
        selection = json.loads(Path(args.selection_json).resolve().read_text(encoding="utf-8"))
        selected_keys.update(
            item["model_key"] for item in selection.get("jobs", []) if item.get("model_key")
        )
        if not selected_keys:
            raise SystemExit("selection JSON contains no model_key values")
    jobs = [
        job
        for job in payload["jobs"]
        if job.get("atlas_qa") == "pass"
        and (not selected_keys or job.get("model_key") in selected_keys)
    ]
    missing = selected_keys - {job.get("model_key") for job in jobs}
    if missing:
        raise SystemExit(f"selected model keys are not atlas-approved: {', '.join(sorted(missing))}")

    job_root = Path(args.job_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    records = []
    for job in jobs:
        atlas_path = job_root / job["pet_id"] / "run" / "spritesheet.webp"
        with Image.open(atlas_path) as opened:
            atlas = opened.convert("RGBA")
        if atlas.size != (1536, 2288):
            raise SystemExit(f"{job['model_key']} atlas is not 1536x2288")
        # Keep A/B order stable across repaired atlas builds so a sign change can be
        # compared directly instead of being hidden by a new random permutation.
        rng = random.Random(
            int.from_bytes(hashlib.sha256(job["model_key"].encode("utf-8")).digest()[:8], "big")
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
        horizontal_box = focus_box(cells[0], cells[1])
        vertical_box = focus_box(cells[2], cells[3])
        views = [
            cells[0],
            cells[1],
            local_view(cells[0], horizontal_box),
            local_view(cells[1], horizontal_box),
            cells[2],
            cells[3],
            local_view(cells[2], vertical_box),
            local_view(cells[3], vertical_box),
        ]
        rendered.append((job, views))
        records.append(
            {
                "model_key": job["model_key"],
                "pet_id": job["pet_id"],
                "horizontal_A": horizontal[0][1],
                "horizontal_B": horizontal[1][1],
                "vertical_A": vertical[0][1],
                "vertical_B": vertical[1][1],
                "horizontal_focus_box": list(horizontal_box),
                "vertical_focus_box": list(vertical_box),
                "atlas_sha256": hashlib.sha256(atlas_path.read_bytes()).hexdigest(),
            }
        )

    offsets = []
    cursor = LABEL_WIDTH
    for width in WIDTHS:
        offsets.append(cursor)
        cursor += width
    sheet_width = cursor
    per_page = max(1, args.operators_per_page)
    pages = []
    for page_index in range(math.ceil(len(rendered) / per_page)):
        rows = rendered[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (sheet_width, HEADER_HEIGHT + len(rows) * ROW_HEIGHT),
            (255, 255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (5, 5),
            "Compare physical position only: which moving local cue is farther left/right or higher/lower in A vs B?",
            fill=(0, 0, 0, 255),
        )
        draw.text(
            (5, 23),
            "Ignore fixed body-facing and gaze semantics. Local panels use the same high-energy crop and coordinate grid.",
            fill=(60, 60, 60, 255),
        )
        for column, header in enumerate(HEADERS):
            draw.text((offsets[column] + 5, 48), header, fill=(0, 0, 0, 255))
        page_keys = []
        for row_index, (job, views) in enumerate(rows):
            y = HEADER_HEIGHT + row_index * ROW_HEIGHT
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0, 255))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60, 255))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60, 255))
            for column, view in enumerate(views):
                background = Image.new("RGBA", view.size, (242, 242, 242, 255))
                background.alpha_composite(view)
                sheet.alpha_composite(background, (offsets[column], y + 16))
            page_keys.append(job["model_key"])
        page_path = output_dir / f"cardinal-focus-{page_index + 1:02d}.jpg"
        sheet.convert("RGB").save(page_path, quality=95, subsampling=0)
        pages.append({"page": str(page_path), "model_keys": page_keys})

    (output_dir / "cardinal-focus-key.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instructions": "Do not provide this answer key to blind reviewers.",
                "jobs": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "cardinal-focus-index.json").write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(records), "pages": len(pages)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
