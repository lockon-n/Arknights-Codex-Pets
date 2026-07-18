#!/usr/bin/env python3
"""Generate the bilingual package progress page from the catalog and registry."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "registry" / "ark-models-operator-chibis-2026-07-13.csv"
REGISTRY = ROOT / "registry" / "pets.json"
OUTPUT = ROOT / "PROGRESS.md"
CATALOG_DATE = "2026-07-13"
CATALOG_COMMIT = "3619a9a7268ec049dbbb30d1cff0ffa6d3fdf5ed"


def escape(value: str) -> str:
    return value.replace("|", "\\|").strip()


def bilingual_name(row: dict[str, str]) -> str:
    chinese = escape(row["operator_cn"])
    english = escape(row["operator_en"])
    return chinese if not english or chinese == english else f"{chinese} / {english}"


def item_line(row: dict[str, str], approved: dict[str, dict]) -> str:
    model_key = row["model_key"]
    package = approved.get(model_key)
    checkbox = "x" if package else " "
    name = bilingual_name(row)
    details: list[str] = []
    if row["category"] == "skin":
        details.append(escape(row["skin_collection"] or "未标注系列 / Unlabelled collection"))
    if row["is_special"] == "yes":
        details.append("异格 / alternate")
    details.append(f"`{escape(model_key)}`")
    if package:
        details.append(f"[package]({package['packagePath']})")
    return f"- [{checkbox}] {name} — " + " — ".join(details)


def grouped_lines(rows: list[dict[str, str]], approved: dict[str, dict]) -> list[str]:
    result: list[str] = []
    for rarity in sorted({int(row["rarity"]) for row in rows}):
        result.extend([f"### {rarity}★", ""])
        result.extend(item_line(row, approved) for row in rows if int(row["rarity"]) == rarity)
        result.append("")
    return result


def percentage(done: int, total: int) -> str:
    return f"{done / total * 100:.1f}%" if total else "0.0%"


def render() -> str:
    with CATALOG.open(encoding="utf-8-sig", newline="") as handle:
        catalog = list(csv.DictReader(handle))
    with REGISTRY.open(encoding="utf-8") as handle:
        registry = json.load(handle)["pets"]

    approved = {
        pet["modelKey"]: pet
        for pet in registry
        if pet.get("status") == "approved"
    }
    catalog_keys = {row["model_key"] for row in catalog}
    unknown = sorted(set(approved) - catalog_keys)
    if unknown:
        raise SystemExit(f"Approved model keys missing from catalog: {', '.join(unknown)}")

    defaults = [row for row in catalog if row["category"] == "default"]
    skins = [row for row in catalog if row["category"] == "skin"]
    default_done = sum(row["model_key"] in approved for row in defaults)
    skin_done = sum(row["model_key"] in approved for row in skins)

    lines = [
        "# 制作进度 / Production Progress",
        "",
        "> 本页由 `registry/pets.json` 与上游模型目录自动生成。请勿手工修改勾选状态。",
        "> This page is generated from `registry/pets.json` and the upstream model catalog. Do not edit checkbox states manually.",
        "",
        "## 总览 / Summary",
        "",
        "本项目会按照国服实装顺序逐步扩充干员，并将皮肤作为独立成品维护。`[x]` 表示成品已经通过 QA 并发布；`[ ]` 表示尚未发布，包括待制作和制作中的项目。",
        "",
        "The collection will expand gradually in CN release order, with outfits maintained as separate packages. `[x]` means the package passed QA and was published; `[ ]` means it is not published yet, including planned and in-progress work.",
        "",
        "| 类别 / Category | 已完成 / Done | 总数 / Total | 进度 / Progress |",
        "|---|---:|---:|---:|",
        f"| 默认干员 / Default operators | {default_done} | {len(defaults)} | {percentage(default_done, len(defaults))} |",
        f"| 皮肤 / Outfits | {skin_done} | {len(skins)} | {percentage(skin_done, len(skins))} |",
        f"| **合计 / Total** | **{default_done + skin_done}** | **{len(catalog)}** | **{percentage(default_done + skin_done, len(catalog))}** |",
        "",
        f"上游目录快照 / Upstream catalog snapshot: `{CATALOG_DATE}`, Ark-Models commit `{CATALOG_COMMIT}` (`zh_CN`).",
        "",
        "## 默认干员 / Default Operators",
        "",
    ]
    lines.extend(grouped_lines(defaults, approved))
    lines.extend([
        "## 皮肤 / Outfits",
        "",
        "皮肤名称沿用 Ark-Models 目录提供的系列标签；目录没有提供的正式中文皮肤标题不会在此推测。",
        "",
        "Outfit labels follow the collection metadata supplied by Ark-Models; official outfit titles absent from that catalog are not inferred here.",
        "",
    ])
    lines.extend(grouped_lines(skins, approved))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if PROGRESS.md is not up to date",
    )
    args = parser.parse_args()
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit("PROGRESS.md is out of date; run scripts/update_progress.py")
        return
    OUTPUT.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
