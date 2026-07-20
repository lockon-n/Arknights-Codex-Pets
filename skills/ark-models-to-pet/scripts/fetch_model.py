#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from catalog import DEFAULT_INDEX_URL, load_index


RAW_ROOT = "https://raw.githubusercontent.com/isHarryh/Ark-Models/main"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one Ark-Models operator model.")
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--index", default=DEFAULT_INDEX_URL)
    parser.add_argument("--raw-root", default=RAW_ROOT)
    args = parser.parse_args()

    payload = load_index(args.index)
    item = payload["data"].get(args.model_key)
    if not item or item.get("type") != "Operator":
        raise SystemExit(f"operator model not found: {args.model_key}")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for extension, filename in item.get("assetList", {}).items():
        quoted_key = urllib.parse.quote(args.model_key, safe="")
        quoted_file = urllib.parse.quote(filename, safe="")
        url = f"{args.raw_root}/models/{quoted_key}/{quoted_file}"
        target = output_dir / filename
        urllib.request.urlretrieve(url, target)
        downloaded.append({"extension": extension, "filename": filename, "url": url, "bytes": target.stat().st_size})

    required = {".atlas", ".png"}
    available = {entry["extension"] for entry in downloaded}
    if not required.issubset(available) or not ({".skel", ".json"} & available):
        raise SystemExit(f"incomplete Spine model: extensions={sorted(available)}")
    manifest = {
        "ok": True,
        "model_key": args.model_key,
        "metadata": item,
        "files": downloaded,
        "source_index": args.index,
    }
    (output_dir / "model-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output_dir)


if __name__ == "__main__":
    main()
