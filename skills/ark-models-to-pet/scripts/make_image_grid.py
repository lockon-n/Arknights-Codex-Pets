#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser(description="Make a labeled review grid from PNG files.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    paths = sorted(input_dir.rglob("*.png"))
    if not paths:
        raise SystemExit("no PNG files found")
    cell_width, cell_height, label_height = 384, 416, 24
    rows = (len(paths) + args.columns - 1) // args.columns
    sheet = Image.new("RGBA", (args.columns * cell_width, rows * (cell_height + label_height)), (245, 245, 245, 255))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGBA")
        x = index % args.columns * cell_width
        y = index // args.columns * (cell_height + label_height)
        sheet.alpha_composite(image, (x, y + label_height))
        draw.text((x + 4, y + 4), str(path.relative_to(input_dir)), fill=(0, 0, 0, 255))
    sheet.convert("RGB").save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
