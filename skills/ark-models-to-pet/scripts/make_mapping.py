#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_name(names: list[str], preferred: list[str]) -> str | None:
    folded = {name.casefold(): name for name in names}
    for candidate in preferred:
        if candidate.casefold() in folded:
            return folded[candidate.casefold()]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a reviewable Codex state mapping from rendered Spine metadata.")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--mapping-out", required=True)
    parser.add_argument("--look-config-out", required=True)
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    names = [item["name"] for item in metadata["rendered"]]
    relax = find_name(names, ["Relax", "Default", "Idle"])
    move = find_name(names, ["Move", "Run", "Walk"])
    interact = find_name(names, ["Interact", "Special", "Default"])
    sit = find_name(names, ["Sit", "Relax", "Default"])
    sleep = find_name(names, ["Sleep", "Sit", "Relax"])
    selections = {"relax": relax, "move": move, "interact": interact, "sit": sit, "sleep": sleep}
    missing = [key for key, value in selections.items() if not value]
    if missing:
        raise SystemExit(f"cannot auto-map animation roles: {missing}; available={names}")
    mapping = {
        "review_required": True,
        "notes": "Inspect source previews and edit animation names/indices before production.",
        "states": {
            "idle": {"animation": relax, "indices": [0, 1, 2, 3, 4, 7]},
            "running-right": {"animation": move, "indices": list(range(8))},
            "running-left": {"animation": move, "indices": list(range(8)), "mirror": True},
            "waving": {"animation": interact, "indices": [0, 2, 4, 7]},
            "jumping": {"animation": relax, "indices": [0, 1, 3, 5, 7], "offset_y": [0, -8, -16, -8, 0]},
            "failed": {"animation": sleep, "indices": list(range(8))},
            "waiting": {"animation": sit, "indices": [0, 1, 2, 4, 6, 7]},
            "running": {"animation": interact, "indices": [0, 1, 2, 3, 4, 7]},
            "review": {"animation": relax, "indices": [0, 1, 2, 4, 5, 7]},
        },
    }
    Path(args.mapping_out).write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bone_names = [bone["name"] for bone in metadata.get("bones", [])]
    eye_bones = [name for name in bone_names if "eye" in name.casefold() and not any(token in name.casefold() for token in ["brow", "lid"])]
    head_bone = next((name for name in bone_names if name.casefold() in {"f_head", "head"}), None)
    if not head_bone:
        head_bone = next((name for name in bone_names if "head" in name.casefold()), None)
    # Some early Ark-Models rigs use F_Ai as the face/head parent. It owns the
    # facial expression slots plus F_Touding (hair/top of head), so moving it
    # preserves the whole head instead of separating facial parts.
    if not head_bone and "F_Ai" in bone_names:
        head_bone = "F_Ai"
    look = {
        "mode": "candidates",
        "animation": relax,
        "time": 0,
        "eye_bones": eye_bones,
        "head_bone": head_bone,
        "eye_step": 8,
        "head_step": 3,
        "head_y_step": 3,
        "head_rotation_step": 6,
        "eye_x_up": 0,
        "eye_x_right": 0,
        "eye_y_up": 0,
        "eye_y_right": 0,
        "head_x_up": 0,
        "head_x_right": 0,
        "head_y_up": 0,
        "head_y_right": 0,
        "head_rotation_up": 0,
        "head_rotation_right": 0,
        "review_required": True,
        "notes": "Render candidates, identify screen-coordinate signs, then switch mode to directions and set calibrated coefficients.",
    }
    Path(args.look_config_out).write_text(json.dumps(look, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"mapping": args.mapping_out, "look_config": args.look_config_out, "animations": names, "eye_bones": eye_bones, "head_bone": head_bone}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
