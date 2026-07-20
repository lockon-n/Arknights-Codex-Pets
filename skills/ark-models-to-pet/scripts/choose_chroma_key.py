#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


CANDIDATES = ["#00FF00", "#FF00FF", "#0000FF", "#00FFFF", "#FF0000"]


def rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose a chroma key far from visible sprite colors.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    pixels = []
    for raw in args.paths:
        path = Path(raw)
        files = sorted(path.rglob("*.png")) if path.is_dir() else [path]
        for file in files:
            with Image.open(file) as image:
                rgba = image.convert("RGBA")
                pixels.extend((red, green, blue) for red, green, blue, alpha in rgba.getdata() if alpha > 32)
    if not pixels:
        raise SystemExit("no visible pixels found")
    stride = max(1, len(pixels) // 200000)
    sampled = pixels[::stride]
    scores = {}
    for candidate in CANDIDATES:
        cr, cg, cb = rgb(candidate)
        distances = sorted(math.sqrt((red - cr) ** 2 + (green - cg) ** 2 + (blue - cb) ** 2) for red, green, blue in sampled)
        scores[candidate] = distances[max(0, int(len(distances) * 0.01) - 1)]
    selected = max(scores, key=scores.get)
    result = {"ok": True, "hex": selected, "scores_1st_percentile": scores, "sampled_pixels": len(sampled)}
    text = json.dumps(result, indent=2) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
