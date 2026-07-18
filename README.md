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
  provenance.json
  qa/
    validation.json
    preview.png
    v2-validation.json
    directions-labeled.png
    direction-continuity.json
    contact-extended.png
    standard-contact.png
```

`pet.json` must use `spriteVersionNumber: 2`; its atlas must be a validated 1536×2288 8×11 sheet. Keep original Spine files, raw Atlas PNGs, renderer caches, and unapproved intermediate images outside this repository.

Batch TODO manifests live under `batches/`. A row is complete only after source mapping, standard and direction visual QA, v2 validation, final visual review, and package QA all pass.

The ordinary sizing policy is `safe-max`: render official Spine assets at 768×832 or higher, choose one downsampling scale per pet from every approved action, preserve animation-row registration, and require at least 6 transparent pixels on all four sides of every final 192×208 cell. Never enlarge an already packaged spritesheet.

## Start a conversion

1. Refresh the `Ark-Models` checkout.
2. Select a `model_key` from its `models_data.json`.
3. Use the portable `ark-models-to-pet` Skill to render, map, QA, and package the pet.
4. Stage only approved packages outside this Git worktree and validate their exact atlas copies and QA evidence.
5. Publish package directories into `pets/<pet-id>/`, merge their entries into `registry/pets.json`, validate again, then commit.

See [docs/WORKFLOW.md](docs/WORKFLOW.md) for the review gates and source rules.

## Provenance and rights

Arknights artwork and game assets are owned by their respective rights holders, including Hypergryph. Ark-Models is an extracted-asset source. This repository does not grant redistribution or commercial-use rights. Each package must retain its source identity and rights notice.
