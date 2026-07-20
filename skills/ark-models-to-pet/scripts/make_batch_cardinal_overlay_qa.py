#!/usr/bin/env python3
"""Build blind A/B cardinal sheets with a red-A/cyan-B registration overlay."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


FULL = (384, 416)
LOCAL = (384, 384)
LABEL_WIDTH = 210
HEADER_HEIGHT = 82
ROW_HEIGHT = 438
PANEL_WIDTHS = [FULL[0], FULL[0], LOCAL[0], LOCAL[0], LOCAL[0]]


def registration_overlay(a: Image.Image, b: Image.Image) -> Image.Image:
    a = a.convert("RGBA")
    b = b.convert("RGBA")
    if a.size != b.size:
        raise ValueError("A/B image size mismatch")
    out = Image.new("RGB", a.size, (0, 0, 0))
    ap = a.load()
    bp = b.load()
    op = out.load()
    for y in range(a.height):
        for x in range(a.width):
            ar, ag, ab, aa = ap[x, y]
            br, bg, bb, ba = bp[x, y]
            al = round((0.299 * ar + 0.587 * ag + 0.114 * ab) * aa / 255)
            bl = round((0.299 * br + 0.587 * bg + 0.114 * bb) * ba / 255)
            op[x, y] = (al, bl, bl)
    return out


def add_grid(image: Image.Image, step: int = 16) -> Image.Image:
    image = image.copy()
    draw = ImageDraw.Draw(image)
    for x in range(0, image.width, step):
        draw.line((x, 0, x, image.height - 1), fill=(90, 90, 90), width=1)
    for y in range(0, image.height, step):
        draw.line((0, y, image.width - 1, y), fill=(90, 90, 90), width=1)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--operators-per-page", type=int, default=2)
    args = parser.parse_args()

    source = json.loads(Path(args.index).resolve().read_text(encoding="utf-8"))
    jobs = source["jobs"]
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    offsets = []
    cursor = LABEL_WIDTH
    for width in PANEL_WIDTHS:
        offsets.append(cursor)
        cursor += width
    pages = []
    per_page = max(1, args.operators_per_page)
    for page_index in range(math.ceil(len(jobs) / per_page)):
        page_jobs = jobs[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new("RGB", (cursor, HEADER_HEIGHT + len(page_jobs) * ROW_HEIGHT), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text((5, 5), "Blind overlay recheck: classify the physical position of A versus B.", fill="black")
        draw.text((5, 24), "Registration overlay: red=A contribution, cyan=B contribution, white=overlap.", fill=(50, 50, 50))
        draw.text((5, 43), "Use paired red/cyan edges plus the identical-coordinate grid; ignore body-facing semantics.", fill=(50, 50, 50))
        for x, label in zip(offsets, ["A full", "B full", "A local", "B local", "A(red)+B(cyan) overlay"], strict=True):
            draw.text((x + 5, 62), label, fill="black")
        page_keys = []
        for row_index, job in enumerate(page_jobs):
            y0 = HEADER_HEIGHT + row_index * ROW_HEIGHT
            draw.text((5, y0 + 8), job["pet_id"], fill="black")
            draw.text((5, y0 + 28), job["model_key"], fill=(60, 60, 60))
            for axis_index, axis in enumerate(("horizontal", "vertical")):
                y = y0 + axis_index * (ROW_HEIGHT // 2)
                draw.text((160, y + 8), "H" if axis == "horizontal" else "V", fill="black")
                with Image.open(job[f"{axis}_A_full"]) as opened:
                    a_full = opened.convert("RGBA")
                with Image.open(job[f"{axis}_B_full"]) as opened:
                    b_full = opened.convert("RGBA")
                with Image.open(job[f"{axis}_A_local"]) as opened:
                    a_local = opened.convert("RGBA")
                with Image.open(job[f"{axis}_B_local"]) as opened:
                    b_local = opened.convert("RGBA")
                views = [
                    a_full.resize(FULL, Image.Resampling.NEAREST).convert("RGB"),
                    b_full.resize(FULL, Image.Resampling.NEAREST).convert("RGB"),
                    add_grid(a_local.resize(LOCAL, Image.Resampling.NEAREST).convert("RGB")),
                    add_grid(b_local.resize(LOCAL, Image.Resampling.NEAREST).convert("RGB")),
                    add_grid(registration_overlay(a_local, b_local).resize(LOCAL, Image.Resampling.NEAREST)),
                ]
                target_height = ROW_HEIGHT // 2 - 8
                for column, view in enumerate(views):
                    if view.height > target_height:
                        view = view.resize((round(view.width * target_height / view.height), target_height), Image.Resampling.NEAREST)
                    sheet.paste(view, (offsets[column], y))
            page_keys.append(job["model_key"])
        path = output / f"cardinal-overlay-{page_index + 1:02d}.png"
        sheet.save(path)
        pages.append({"page": str(path), "model_keys": page_keys})
    (output / "cardinal-overlay-index.json").write_text(
        json.dumps({"schema_version": 1, "source_index": str(Path(args.index).resolve()), "pages": pages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"jobs": len(jobs), "pages": len(pages)}))


if __name__ == "__main__":
    main()
