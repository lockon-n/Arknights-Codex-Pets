# Conversion workflow

## What belongs here

Commit only a pet after it has passed source-aware visual and deterministic QA. A package must contain its v2 spritesheet, `pet.json`, provenance note, validation result, and a compact QA preview.

Do not commit the complete Ark-Models checkout, raw Spine `.skel` / `.atlas` / source texture files, unapproved assets, Node dependencies, or renderer caches. The complete source checkout lives next to this repository so the source can be refreshed independently.

## Per-pet intake

Record the following before conversion:

- exact `model_key`
- upstream Git commit SHA
- default outfit or skin category
- display name and proposed `pet-id`
- operator / skin labels from `models_data.json`

Run the portable `ark-models-to-pet` Skill from a separate job folder. Review its generated animation mapping and look-direction controls; they are not automatically authoritative.

## Acceptance gate

Before copying a package into `pets/`, verify:

- `spritesheet.webp` or `spritesheet.png` is exactly 1536×2288.
- `pet.json` declares `spriteVersionNumber: 2` and references that exact file.
- v2 validator passed without unrecorded overrides.
- action rows, scale, transparency, direction semantics, and adjacent-direction continuity passed visual QA.
- `SOURCE.md` identifies the upstream source and model key.
- the registry entry records source commit and approval date.
- packaged spritesheet bytes exactly match the visually approved job output.
- package QA contains labeled directions, extended and standard contacts, continuity metrics, and the exact v2 validation result.

For a batch, keep evidence generation separate from semantic approval. Three isolated blind reviewers must classify randomized cardinal pairs without seeing coefficients or the answer key; resolve ambiguity with a fresh enlarged review sheet or recalibration, never by revealing intent. Independently inspect every final native-cell summary before setting `visual_qa=pass`.

Stage a completed batch outside the repository. The portable skill's staging command accepts only jobs whose `standard_visual_qa`, `direction_qa`, `atlas_qa`, and `visual_qa` fields are all `pass`, validates every package, and produces a registry merge candidate. Inspect those results before importing them here.

## Registry entry

Add an object to `registry/pets.json` using this shape:

```json
{
  "id": "angelina",
  "displayName": "安洁莉娜",
  "modelKey": "build_char_291_aglina",
  "category": "default",
  "upstreamCommit": "<Ark-Models commit SHA>",
  "status": "approved",
  "packagePath": "pets/angelina",
  "approvedAt": "YYYY-MM-DD"
}
```

Use `skin` for non-default outfits. Retain rejected or experimental jobs outside this repository.
