#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path


DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/isHarryh/Ark-Models/main/models_data.json"


def load_index(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source) as response:
            return json.load(response)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def operator_rows(payload: dict) -> list[dict]:
    rows = []
    for model_key, item in payload["data"].items():
        if item.get("type") != "Operator":
            continue
        category = "default" if item.get("style") == "BuildingDefault" else "skin"
        rows.append(
            {
                "model_key": model_key,
                "category": category,
                "name": item.get("name", ""),
                "appellation": item.get("appellation", ""),
                "skin_group": item.get("skinGroupName", ""),
                "asset_id": item.get("assetId", ""),
                "model_directory": f"models/{model_key}",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Ark-Models operator catalog.")
    parser.add_argument("--index", default=DEFAULT_INDEX_URL)
    parser.add_argument("--category", choices=["default", "skin", "all"], default="all")
    parser.add_argument("--operator", help="Exact Chinese or English operator name.")
    parser.add_argument("--model-key", help="Exact model key.")
    parser.add_argument("--format", choices=["json", "csv", "keys"], default="json")
    parser.add_argument("--output")
    args = parser.parse_args()

    payload = load_index(args.index)
    rows = operator_rows(payload)
    if args.category != "all":
        rows = [row for row in rows if row["category"] == args.category]
    if args.operator:
        needle = args.operator.casefold()
        rows = [
            row
            for row in rows
            if row["name"].casefold() == needle or row["appellation"].casefold() == needle
        ]
    if args.model_key:
        rows = [row for row in rows if row["model_key"] == args.model_key]
    rows.sort(key=lambda row: (row["name"], row["category"], row["skin_group"], row["model_key"]))

    if args.format == "json":
        result = json.dumps(
            {
                "game_data_version": payload.get("gameDataVersionDescription", "").strip(),
                "count": len(rows),
                "models": rows,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
    elif args.format == "keys":
        result = "\n".join(row["model_key"] for row in rows) + ("\n" if rows else "")
    else:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else ["model_key"])
        writer.writeheader()
        writer.writerows(rows)
        result = buffer.getvalue()

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
