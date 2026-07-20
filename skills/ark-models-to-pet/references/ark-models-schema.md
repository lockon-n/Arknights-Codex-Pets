# Ark-Models catalog and source contract

Use the current `models_data.json` on the `main` branch of `isHarryh/Ark-Models` as the catalog of record. The repository can change, so record retrieval time and, when reproducibility matters, the Git commit SHA.

## Relevant fields

- Top-level `data`: mapping from `model_key` to metadata.
- `type == "Operator"`: operator building-chibi. Exclude enemies and unrelated types.
- `style == "BuildingDefault"`: base/default outfit.
- Other operator styles: treat as skins in selection and reporting.
- `name`, `appellation`, `skinGroupName`: display and outfit labels.
- `assetId`: upstream asset identifier.
- `assetList`: extension-to-filename mapping under `models/<model_key>/`.

The renderer fast path expects one `.atlas`, one `.png`, and one `.skel` or skeleton `.json`. Do not mistake `model-manifest.json` for a Spine skeleton JSON.

## Selection rules

Use `model_key`, not display name, as the job identifier. One operator can have several entries. Report defaults and skins separately. Keep the selected catalog row with every job so renamed outputs retain source identity.

The fetcher downloads only files declared by the catalog entry. If repository layout or branch changes, update the raw root or pin a verified commit instead of scraping filenames heuristically.

## Rights and provenance

Ark-Models contains extracted Arknights assets; artwork and game content belong to their respective rights holders, including Hypergryph. Observe repository notices and applicable terms. This skill grants no redistribution or commercial-use rights. Preserve provenance in packages and do not embed a bulk source mirror in the skill ZIP.
