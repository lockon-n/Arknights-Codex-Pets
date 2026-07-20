#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageOps


def safe_folder(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)


def clear_hidden_rgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0 and (red or green or blue):
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def apply_counter_mirror_regions(
    canvas: Image.Image, state: str, spec: dict
) -> Image.Image:
    """Restore readable local details after a safe whole-frame direction mirror.

    Regions use final 192x208 cell coordinates and are flipped once more in place.
    This is intentionally narrow: it is for an isolated plate/sign whose lettering
    must stay readable, not for reconstructing an arbitrary asymmetric character.
    """
    regions = spec.get("counter_mirror_regions", [])
    if not regions:
        return canvas
    if not spec.get("mirror"):
        raise RuntimeError(
            f"counter_mirror_regions requires mirror=true for {state}"
        )
    corrected = canvas.copy()
    for index, region in enumerate(regions):
        if (
            not isinstance(region, list)
            or len(region) != 4
            or any(isinstance(value, bool) or not isinstance(value, int) for value in region)
        ):
            raise RuntimeError(
                f"counter_mirror_regions[{index}] for {state} must be four integer cell coordinates"
            )
        left, top, right, bottom = region
        if not (0 <= left < right <= 192 and 0 <= top < bottom <= 208):
            raise RuntimeError(
                f"counter_mirror_regions[{index}] for {state} is outside the 192x208 cell: {region}"
            )
        patch = ImageOps.mirror(corrected.crop((left, top, right, bottom)))
        corrected.paste(patch, (left, top, right, bottom))
    return corrected


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize rendered Spine frames into Codex 192x208 state cells.")
    parser.add_argument("--render-dir", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--margin", type=int, default=6)
    parser.add_argument(
        "--normalization",
        choices=["canvas", "safe-max", "state-fit"],
        default="canvas",
        help=(
            "Preserve the renderer canvas, use one pet-wide safe-max scale with per-state "
            "registration, or use legacy per-state fitting."
        ),
    )
    parser.add_argument(
        "--max-upscale",
        type=float,
        default=1.0,
        help=(
            "Fail when normalization would enlarge source pixels beyond this factor "
            "(default: 1.0, so safe-max remains a high-resolution downsample)."
        ),
    )
    parser.add_argument(
        "--source-edge-margin",
        type=int,
        default=2,
        help=(
            "Fail if a transformed source frame comes within this many pixels of the "
            "high-resolution render edge (default: 2)."
        ),
    )
    args = parser.parse_args()
    render_dir = Path(args.render_dir).resolve()
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    if mapping.get("review_required") is not False:
        raise RuntimeError("mapping.json must have review_required=false before preparing production frames")
    run_dir = Path(args.run_dir).resolve()
    frames_root = run_dir / "frames"
    rows = []
    report = {}

    prepared_states = {}
    for state, spec in mapping["states"].items():
        animation_dir = render_dir / "animations" / safe_folder(spec["animation"])
        indices = spec["indices"]
        offsets = spec.get("offset_y", [0] * len(indices))
        rotations = spec.get("rotation_degrees", [0] * len(indices))
        if isinstance(rotations, (int, float)):
            rotations = [rotations] * len(indices)
        if len(rotations) != len(indices):
            raise RuntimeError(f"rotation_degrees length does not match indices for {state}")
        images = []
        for source_index, offset, rotation in zip(indices, offsets, rotations):
            image = Image.open(animation_dir / f"{source_index:02d}.png").convert("RGBA")
            if spec.get("mirror"):
                image = ImageOps.mirror(image)
            if rotation:
                image = image.rotate(
                    float(rotation),
                    resample=Image.Resampling.BICUBIC,
                    expand=False,
                )
            if offset:
                shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
                shifted.alpha_composite(image, (0, offset))
                image = shifted
            images.append(image)
        boxes = [image.getchannel("A").getbbox() for image in images]
        if any(box is None for box in boxes):
            raise RuntimeError(f"empty source frame in {state}")
        for index, (image, box) in enumerate(zip(images, boxes)):
            if box is None:
                continue
            source_margins = (
                box[0],
                box[1],
                image.width - box[2],
                image.height - box[3],
            )
            if min(source_margins) < args.source_edge_margin:
                raise RuntimeError(
                    f"transformed source frame {state}/{index:02d} is too close to the "
                    f"{image.width}x{image.height} render edge: margins={source_margins}, "
                    f"required>={args.source_edge_margin}; rerender with safer framing"
                )
        min_x = min(box[0] for box in boxes)
        min_y = min(box[1] for box in boxes)
        max_x = max(box[2] for box in boxes)
        max_y = max(box[3] for box in boxes)
        union_width = max_x - min_x
        union_height = max_y - min_y
        prepared_states[state] = {
            "spec": spec,
            "images": images,
            "boxes": boxes,
            "union_bbox": (min_x, min_y, max_x, max_y),
            "union_width": union_width,
            "union_height": union_height,
        }

    safe_max = None
    if args.normalization == "safe-max":
        source_sizes = {
            image.size
            for prepared in prepared_states.values()
            for image in prepared["images"]
        }
        if len(source_sizes) != 1:
            raise RuntimeError(
                f"source canvas size changes across states: {sorted(source_sizes)}"
            )
        available_width = 192 - 2 * args.margin
        available_height = 208 - 2 * args.margin
        if available_width <= 0 or available_height <= 0:
            raise RuntimeError(f"margin {args.margin} leaves no usable cell area")
        max_state_union_width = max(
            prepared["union_width"] for prepared in prepared_states.values()
        )
        max_state_union_height = max(
            prepared["union_height"] for prepared in prepared_states.values()
        )
        scale = min(
            available_width / max_state_union_width,
            available_height / max_state_union_height,
        )
        if scale > args.max_upscale:
            raise RuntimeError(
                f"safe-max would enlarge source renders {scale:.3f}x, exceeding "
                f"--max-upscale {args.max_upscale:.3f}; rerender at higher resolution"
            )
        safe_max = {
            "scale": scale,
            "max_state_union_width": max_state_union_width,
            "max_state_union_height": max_state_union_height,
            "available_width": available_width,
            "available_height": available_height,
            "source_canvas": list(next(iter(source_sizes))),
            "registration": "pet-wide scale with per-state union registration",
        }

    for state, prepared in prepared_states.items():
        spec = prepared["spec"]
        images = prepared["images"]
        boxes = prepared["boxes"]
        min_x, min_y, max_x, max_y = prepared["union_bbox"]
        union_width = prepared["union_width"]
        union_height = prepared["union_height"]
        if args.normalization == "canvas":
            source_sizes = {image.size for image in images}
            if len(source_sizes) != 1:
                raise RuntimeError(f"source canvas size changes within {state}: {sorted(source_sizes)}")
            source_width, source_height = images[0].size
            scale = min(192 / source_width, 208 / source_height)
            offset_x = (192 - source_width * scale) / 2
            offset_y = (208 - source_height * scale) / 2
            target_union_width = target_union_height = None
        elif args.normalization == "safe-max":
            if safe_max is None:
                raise RuntimeError("safe-max normalization was not initialized")
            scale = safe_max["scale"]
            target_union_width = max(1, round(union_width * scale))
            target_union_height = max(1, round(union_height * scale))
            offset_x = (192 - target_union_width) // 2
            offset_y = 208 - args.margin - target_union_height
        else:
            available_width = 192 - 2 * args.margin
            available_height = 208 - 2 * args.margin
            scale = min(available_width / union_width, available_height / union_height)
            if scale > args.max_upscale:
                raise RuntimeError(
                    f"{state} would be enlarged {scale:.3f}x during normalization, exceeding "
                    f"--max-upscale {args.max_upscale:.3f}. Rerender with --framing visible at "
                    "768x832 or higher; raise the threshold only for a documented exception."
                )
            offset_x = (192 - union_width * scale) / 2 - min_x * scale
            offset_y = (208 - union_height * scale) / 2 - min_y * scale
        state_dir = frames_root / state
        state_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        output_boxes = []
        for index, (image, box) in enumerate(zip(images, boxes)):
            if args.normalization == "canvas":
                width = max(1, round(image.width * scale))
                height = max(1, round(image.height * scale))
                resized = image.resize((width, height), Image.Resampling.LANCZOS)
                left = round(offset_x)
                top = round(offset_y)
            elif args.normalization == "safe-max":
                crop = image.crop((min_x, min_y, max_x, max_y))
                resized = crop.resize(
                    (target_union_width, target_union_height),
                    Image.Resampling.LANCZOS,
                )
                left = round(offset_x)
                top = round(offset_y)
            else:
                crop = image.crop(box)
                width = max(1, round(crop.width * scale))
                height = max(1, round(crop.height * scale))
                resized = crop.resize((width, height), Image.Resampling.LANCZOS)
                left = round(box[0] * scale + offset_x)
                top = round(box[1] * scale + offset_y)
            canvas = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
            canvas.alpha_composite(resized, (left, top))
            canvas = apply_counter_mirror_regions(canvas, state, spec)
            canvas = clear_hidden_rgb(canvas)
            output = state_dir / f"{index:02d}.png"
            canvas.save(output)
            outputs.append(str(output))
            output_box = canvas.getchannel("A").getbbox()
            output_boxes.append(output_box)
            if output_box is None:
                raise RuntimeError(f"empty normalized frame in {state}/{index:02d}")
            if args.normalization == "safe-max":
                output_margins = (
                    output_box[0],
                    output_box[1],
                    192 - output_box[2],
                    208 - output_box[3],
                )
                if min(output_margins) < args.margin:
                    raise RuntimeError(
                        f"safe-max output {state}/{index:02d} violates the {args.margin}px "
                        f"cell margin: margins={output_margins}"
                    )
        rows.append({"state": state, "frames": outputs, "method": "components"})
        report[state] = {
            "animation": spec["animation"],
            "normalization": args.normalization,
            "scale": scale,
            "source_union_bbox": [min_x, min_y, max_x, max_y],
            "target_union_size": (
                [target_union_width, target_union_height]
                if target_union_width is not None
                else None
            ),
            "target_union_offset": (
                [round(offset_x), round(offset_y)]
                if args.normalization == "safe-max"
                else None
            ),
            "output_bboxes": output_boxes,
            "counter_mirror_regions": spec.get("counter_mirror_regions", []),
        }

    frames_root.mkdir(parents=True, exist_ok=True)
    (frames_root / "frames-manifest.json").write_text(
        json.dumps({"ok": True, "chroma_key": None, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "qa").mkdir(parents=True, exist_ok=True)
    normalization_report = {
        "ok": True,
        "normalization": args.normalization,
        "margin": args.margin,
        "safe_max": safe_max,
        "states": report,
    }
    (run_dir / "qa" / "normalization.json").write_text(
        json.dumps(normalization_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(run_dir)


if __name__ == "__main__":
    main()
