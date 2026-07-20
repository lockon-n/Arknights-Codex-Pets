#!/usr/bin/env python3
"""Create lossless blind cardinal pairs for jobs that failed a prior review protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


CELL = (192, 208)
FULL = (384, 416)
LOCAL_CROP = 96
LOCAL = (384, 384)
LABEL_WIDTH = 210
HEADER_HEIGHT = 70
ROW_HEIGHT = 438
PANEL_WIDTHS = [FULL[0], FULL[0], LOCAL[0], LOCAL[0]]


def atlas_direction(atlas: Image.Image, index: int) -> Image.Image:
    row = 9 + index // 8
    column = index % 8
    left = column * CELL[0]
    top = row * CELL[1]
    return atlas.crop((left, top, left + CELL[0], top + CELL[1]))


def focus_box(first: Image.Image, second: Image.Image) -> tuple[int, int, int, int]:
    difference = ImageChops.difference(first, second).convert("RGBA")
    weighted_x = weighted_y = total = 0
    for y in range(CELL[1]):
        for x in range(CELL[0]):
            weight = max(difference.getpixel((x, y)))
            if weight <= 0:
                continue
            weighted_x += x * weight
            weighted_y += y * weight
            total += weight
    center_x = weighted_x / total if total else CELL[0] / 2
    center_y = weighted_y / total if total else CELL[1] / 2
    left = min(max(0, round(center_x - LOCAL_CROP / 2)), CELL[0] - LOCAL_CROP)
    top = min(max(0, round(center_y - LOCAL_CROP / 2)), CELL[1] - LOCAL_CROP)
    return left, top, left + LOCAL_CROP, top + LOCAL_CROP


def ordered_cells(atlas: Image.Image, model_key: str) -> tuple[list[Image.Image], dict]:
    rng = random.Random(
        int.from_bytes(hashlib.sha256(model_key.encode("utf-8")).digest()[:8], "big")
    )
    horizontal = [4, 12]
    vertical = [0, 8]
    rng.shuffle(horizontal)
    rng.shuffle(vertical)
    cells = [
        atlas_direction(atlas, horizontal[0]),
        atlas_direction(atlas, horizontal[1]),
        atlas_direction(atlas, vertical[0]),
        atlas_direction(atlas, vertical[1]),
    ]
    return cells, {"horizontal_indices": horizontal, "vertical_indices": vertical}


def direction_label(index: int) -> str:
    labels = {0: "up", 4: "screen-right", 8: "down", 12: "screen-left"}
    try:
        return labels[index]
    except KeyError as error:
        raise RuntimeError(f"unsupported cardinal atlas index: {index}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--failed-validation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=3)
    args = parser.parse_args()

    validation = json.loads(
        Path(args.failed_validation).expanduser().resolve().read_text(encoding="utf-8")
    )
    selected = {
        job["model_key"]
        for job in validation.get("jobs", [])
        if any(cell.get("pass") is not True for cell in job.get("cells", {}).values())
    }
    if not selected:
        raise SystemExit("failed validation contains no jobs requiring recheck")

    manifest = json.loads(Path(args.manifest).expanduser().resolve().read_text(encoding="utf-8"))
    jobs = [job for job in manifest["jobs"] if job.get("model_key") in selected]
    missing = selected - {job.get("model_key") for job in jobs}
    if missing:
        raise SystemExit(f"failed jobs not in manifest: {sorted(missing)}")

    job_root = Path(args.job_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    pairs_dir = output_dir / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[tuple[dict, list[Image.Image], list[Image.Image], list[list[int]]]] = []
    records = []
    answer_jobs = []

    for job in jobs:
        atlas_path = job_root / job["pet_id"] / "run" / "spritesheet.webp"
        with Image.open(atlas_path) as opened:
            atlas = opened.convert("RGBA")
        if atlas.size != (1536, 2288):
            raise SystemExit(f"{job['model_key']}: atlas is not 1536x2288")
        cells, hidden_indices = ordered_cells(atlas, job["model_key"])
        boxes = [focus_box(cells[0], cells[1]), focus_box(cells[2], cells[3])]
        locals_ = [
            cells[0].crop(boxes[0]),
            cells[1].crop(boxes[0]),
            cells[2].crop(boxes[1]),
            cells[3].crop(boxes[1]),
        ]
        files = {}
        for axis, offset in (("horizontal", 0), ("vertical", 2)):
            for label, index in (("A", offset), ("B", offset + 1)):
                full_path = pairs_dir / f"{job['model_key']}-{axis}-{label}-full.png"
                local_path = pairs_dir / f"{job['model_key']}-{axis}-{label}-local.png"
                cells[index].save(full_path)
                locals_[index].save(local_path)
                files[f"{axis}_{label}_full"] = str(full_path)
                files[f"{axis}_{label}_local"] = str(local_path)
        rendered.append((job, cells, locals_, [list(box) for box in boxes]))
        records.append(
            {
                "model_key": job["model_key"],
                "pet_id": job["pet_id"],
                "horizontal_focus_box": list(boxes[0]),
                "vertical_focus_box": list(boxes[1]),
                **files,
            }
        )
        answer_jobs.append(
            {
                "model_key": job["model_key"],
                "pet_id": job["pet_id"],
                "horizontal_A": direction_label(hidden_indices["horizontal_indices"][0]),
                "horizontal_B": direction_label(hidden_indices["horizontal_indices"][1]),
                "vertical_A": direction_label(hidden_indices["vertical_indices"][0]),
                "vertical_B": direction_label(hidden_indices["vertical_indices"][1]),
            }
        )

    offsets = []
    cursor = LABEL_WIDTH
    for width in PANEL_WIDTHS:
        offsets.append(cursor)
        cursor += width
    sheet_width = cursor
    per_page = max(1, args.operators_per_page)
    pages = []
    for page_index in range(math.ceil(len(rendered) / per_page)):
        rows = rendered[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGB",
            (sheet_width, HEADER_HEIGHT + len(rows) * ROW_HEIGHT),
            (255, 255, 255),
        )
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (5, 5),
            "Blind recheck: compare physical position of the changing local cue in A versus B.",
            fill=(0, 0, 0),
        )
        draw.text(
            (5, 24),
            "Use full cells for context and lossless identical-coordinate local crops; ignore fixed body facing.",
            fill=(60, 60, 60),
        )
        headers = ["A full", "B full", "A local", "B local"]
        for column, header in enumerate(headers):
            draw.text((offsets[column] + 5, 48), header, fill=(0, 0, 0))
        page_keys = []
        for row_index, (job, cells, locals_, boxes) in enumerate(rows):
            y = HEADER_HEIGHT + row_index * ROW_HEIGHT
            draw.text((5, y + 8), job["display_name"], fill=(0, 0, 0))
            draw.text((5, y + 28), job["pet_id"], fill=(60, 60, 60))
            draw.text((5, y + 48), job["model_key"], fill=(60, 60, 60))
            # Horizontal pair occupies the upper half; vertical pair the lower half.
            for axis_index, (axis, offset) in enumerate((("H", 0), ("V", 2))):
                axis_y = y + axis_index * (ROW_HEIGHT // 2)
                draw.text((160, axis_y + 8), axis, fill=(0, 0, 0))
                views = [
                    cells[offset].resize(FULL, Image.Resampling.NEAREST),
                    cells[offset + 1].resize(FULL, Image.Resampling.NEAREST),
                    locals_[offset].resize(LOCAL, Image.Resampling.NEAREST),
                    locals_[offset + 1].resize(LOCAL, Image.Resampling.NEAREST),
                ]
                target_height = ROW_HEIGHT // 2 - 8
                for column, view in enumerate(views):
                    if view.height > target_height:
                        view = view.resize(
                            (round(view.width * target_height / view.height), target_height),
                            Image.Resampling.NEAREST,
                        )
                    sheet.paste(view.convert("RGB"), (offsets[column], axis_y))
            page_keys.append(job["model_key"])
        page_path = output_dir / f"cardinal-recheck-{page_index + 1:02d}.png"
        sheet.save(page_path)
        pages.append({"page": str(page_path), "model_keys": page_keys})

    index = {
        "schema_version": 1,
        "instructions": (
            "Do not read the earlier validation or any answer key. Classify physical A/B position "
            "from the lossless full/local pairs only."
        ),
        "jobs": records,
        "pages": pages,
    }
    (output_dir / "cardinal-recheck-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "cardinal-recheck-key.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instructions": "Do not provide this answer key to blind reviewers.",
                "jobs": answer_jobs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(records), "pages": len(pages)}))


if __name__ == "__main__":
    main()
