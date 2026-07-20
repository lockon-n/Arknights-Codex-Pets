#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from catalog import DEFAULT_INDEX_URL, load_index, operator_rows


PRTS_API = "https://prts.wiki/api.php"
PRTS_RELEASE_PAGE = "https://prts.wiki/w/干员实装时间"
OFFICIAL_CN_LAUNCH_SOURCES = [
    "https://ak.hypergryph.com/news/201904329.html",
    "https://ak.hypergryph.com/news/201904662.html",
]
PET_ID_OVERRIDES = {
    "115_headbr": "zima",
    "195_glassb": "istina",
    "196_sunbr": "gummy",
}


def fetch_cn_release_rows(release_at: str) -> list[dict]:
    query = {
        "action": "cargoquery",
        "format": "json",
        "tables": "char_obtain,chara",
        "fields": (
            "chara._pageName=operator,chara.rarity=rarity,"
            "char_obtain.cnOnlineTime=release"
        ),
        "join_on": "char_obtain._pageName=chara._pageName",
        "where": f'char_obtain.cnOnlineTime="{release_at}"',
        "order_by": "chara.rarity ASC,chara.charIndex ASC",
        "limit": "500",
    }
    request = urllib.request.Request(
        f"{PRTS_API}?{urllib.parse.urlencode(query)}",
        headers={"User-Agent": "ark-models-to-pet/1.0 release batch builder"},
    )
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
    rows = []
    for entry in payload.get("cargoquery", []):
        title = entry["title"]
        rows.append(
            {
                "operator": title["operator"],
                "rarity": int(title["rarity"]) + 1,
                "release_cn": title["release"],
            }
        )
    return rows


def pet_id_for(appellation: str, model_key: str) -> str:
    if model_key in PET_ID_OVERRIDES:
        return PET_ID_OVERRIDES[model_key]
    normalized = unicodedata.normalize("NFKD", appellation).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if not slug:
        slug = model_key.casefold().replace("_", "-").replace("#", "-")
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


def build_rows(release_rows: list[dict], index_payload: dict, catalog_commit: str) -> list[dict]:
    defaults: dict[str, list[dict]] = {}
    for row in operator_rows(index_payload):
        if row["category"] == "default":
            defaults.setdefault(row["name"], []).append(row)

    result = []
    for release in release_rows:
        matches = defaults.get(release["operator"], [])
        match = matches[0] if len(matches) == 1 else None
        if not matches:
            status, stage, error = "blocked", "catalog-match", "no BuildingDefault model match"
        elif len(matches) > 1:
            status, stage, error = "blocked", "catalog-match", "multiple BuildingDefault model matches"
        else:
            status, stage, error = "pending", "catalogued", ""
        model_key = match["model_key"] if match else ""
        appellation = match["appellation"] if match else ""
        result.append(
            {
                **release,
                "model_key": model_key,
                "appellation": appellation,
                "asset_id": match["asset_id"] if match else "",
                "pet_id": pet_id_for(appellation, model_key) if match else "",
                "display_name": release["operator"],
                "status": status,
                "stage": stage,
                "preflight": "pending" if match else "blocked",
                "preview_render": "pending" if match else "blocked",
                "mapping_qa": "pending" if match else "blocked",
                "production_render": "pending" if match else "blocked",
                "frames_qa": "pending" if match else "blocked",
                "standard_qa": "pending" if match else "blocked",
                "standard_visual_qa": "pending" if match else "blocked",
                "direction_probe": "pending" if match else "blocked",
                "direction_render": "pending" if match else "blocked",
                "direction_evidence_qa": "pending" if match else "blocked",
                "direction_qa": "pending" if match else "blocked",
                "atlas_qa": "pending" if match else "blocked",
                "visual_qa": "pending" if match else "blocked",
                "package_qa": "pending" if match else "blocked",
                "package_path": "",
                "commit": "",
                "error": error,
                "release_source": PRTS_RELEASE_PAGE,
                "catalog_commit": catalog_commit,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a resumable Ark-Models batch table for one CN operator release timestamp."
    )
    parser.add_argument("--release-at", required=True, help="PRTS timestamp, e.g. 2019-04-30 10:00:00")
    parser.add_argument("--index", default=DEFAULT_INDEX_URL)
    parser.add_argument("--catalog-commit", default="")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-json")
    args = parser.parse_args()

    release_rows = fetch_cn_release_rows(args.release_at)
    rows = build_rows(release_rows, load_index(args.index), args.catalog_commit)
    fieldnames = list(rows[0]) if rows else ["operator", "release_cn", "status", "error"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    output_csv = Path(args.output_csv).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv.write_text(buffer.getvalue(), encoding="utf-8")

    if args.output_json:
        output_json = Path(args.output_json).resolve()
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "release_at_cn": args.release_at,
                    "release_source": PRTS_RELEASE_PAGE,
                    "official_launch_sources": OFFICIAL_CN_LAUNCH_SOURCES,
                    "catalog_commit": args.catalog_commit,
                    "jobs": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    blocked = sum(row["status"] == "blocked" for row in rows)
    print(json.dumps({"output": str(output_csv), "jobs": len(rows), "blocked": blocked}, ensure_ascii=False))


if __name__ == "__main__":
    main()
