# Codex Arknights Pets

Approved Codex v2 pet packages converted from Arknights operator building-chibi assets.

This repository intentionally separates conversion outputs from the complete upstream source checkout:

- Upstream source checkout: `../Ark-Models` (not committed here).
- Conversion skill: `ark-models-to-pet` (distributed separately as a portable Skill ZIP).
- Approved packages: `pets/<pet-id>/`.

## Repository contract

Each accepted pet directory contains:

```text
pets/<pet-id>/
  pet.json
  spritesheet.webp|png
  SOURCE.md
  qa/
    validation.json
    preview.png
```

`pet.json` must use `spriteVersionNumber: 2`; its atlas must be a validated 1536×2288 8×11 sheet. Keep original Spine files, raw Atlas PNGs, renderer caches, and unapproved intermediate images outside this repository.

## Start a conversion

1. Refresh the `Ark-Models` checkout.
2. Select a `model_key` from its `models_data.json`.
3. Use the portable `ark-models-to-pet` Skill to render, map, QA, and package the pet.
4. Copy only the approved package directory into `pets/<pet-id>/`.
5. Add one entry to `registry/pets.json`, validate the package, then commit.

See [docs/WORKFLOW.md](docs/WORKFLOW.md) for the review gates and source rules.

## Provenance and rights

Arknights artwork and game assets are owned by their respective rights holders, including Hypergryph. Ark-Models is an extracted-asset source. This repository does not grant redistribution or commercial-use rights. Each package must retain its source identity and rights notice.
