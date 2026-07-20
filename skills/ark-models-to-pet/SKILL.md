---
name: ark-models-to-pet
description: Convert or batch-convert official Arknights operator building-chibi Spine assets from isHarryh/Ark-Models—including default outfits and skins—into visually reviewed, validated Codex v2 animated pet packages. Use when selecting Ark-Models operators, downloading their model files, mapping Spine animations to Codex pet states, building 16-direction look rows, packaging many Codex pets, or diagnosing an Ark-Models-to-pet conversion.
---

# Ark-Models to Codex Pet

Create Codex v2 pets from extracted game art. Preserve the official art; do not redraw it or use image generation unless the user explicitly asks for a derivative replacement. Treat this as an agent-assisted pipeline: scripts automate deterministic work, while an agent reviews animation semantics, framing, bones, directional signs, and final motion.

## Read the relevant references

- Read [references/ark-models-schema.md](references/ark-models-schema.md) before catalog selection, fetching, or explaining what is available.
- Read [references/action-mapping.md](references/action-mapping.md) before accepting an automatically generated state mapping or calibrating direction controls.
- Read [references/batch-and-exceptions.md](references/batch-and-exceptions.md) before processing more than one model or after any unsupported-model failure.
- Read [references/qa-contract.md](references/qa-contract.md) before assembly, validation, blind direction QA, or delivery.

## Establish paths and dependencies

Resolve the skill directory from this `SKILL.md`; never assume the current working directory. Create a separate job root and keep source assets, intermediate renders, QA artifacts, and deliverables distinct.

Required capabilities:

- Python 3 with Pillow.
- Node.js, pnpm, Playwright, and a Chromium-compatible browser for Spine rendering.
- Network access when querying or downloading Ark-Models.

In Codex Desktop, call the workspace-dependency loader first. Use the returned Node, pnpm, Python, and Node-module paths instead of guessing them. Set `CODEX_NODE_MODULES` for Playwright and `CHROME_EXECUTABLE` if Chrome is not in a standard location.

```bash
ARK_PET_SKILL=/absolute/path/to/ark-models-to-pet
ARK_PET_JOB=/absolute/path/to/job
ARK_PET_RUNTIME=/absolute/path/to/shared-renderer-runtime
mkdir -p "$ARK_PET_JOB"

PNPM=/absolute/path/to/pnpm NODE_BIN=/absolute/path/to/node \
  "$ARK_PET_SKILL/scripts/setup_renderer.sh" "$ARK_PET_RUNTIME"
```

## Select models from the current catalog

Always refresh the catalog near the start of a new batch. Do not rely on counts or model keys copied from an older conversation.

```bash
python3 "$ARK_PET_SKILL/scripts/catalog.py" \
  --category all --format csv \
  --output "$ARK_PET_JOB/operator-models.csv"
```

Use `--category default` for base outfits and `--category skin` for skins. Use exact `--operator` or `--model-key` when selecting one entry. Keep skins separate in reports and output naming. Record the selected `model_key`; it is the stable pipeline input.

For a batch, create a selection CSV whose required column is `model_key`; optional columns such as `pet_name` and `notes` are preserved:

```bash
python3 "$ARK_PET_SKILL/scripts/make_batch_manifest.py" \
  --selection "$ARK_PET_JOB/selection.csv" \
  --output "$ARK_PET_JOB/batch-manifest.json"
```

## Convert one model

### 1. Fetch and preflight

```bash
python3 "$ARK_PET_SKILL/scripts/fetch_model.py" \
  --model-key MODEL_KEY \
  --output-dir "$ARK_PET_JOB/source"

python3 "$ARK_PET_SKILL/scripts/preflight_model.py" \
  --model-dir "$ARK_PET_JOB/source" \
  --json-out "$ARK_PET_JOB/preflight.json"
```

Stop the fast path if preflight reports multiple atlas pages, more than one skeleton, missing files, or unreadable images. Classify and isolate the model rather than forcing it through.

### 2. Render source animations

Render all named animations at eight samples using 384×416. This first render is disposable evidence for mapping, not the final package.

```bash
CODEX_NODE_MODULES=/absolute/path/to/node_modules \
node "$ARK_PET_SKILL/scripts/render_model.mjs" \
  --model-dir "$ARK_PET_JOB/source" \
  --runtime-dir "$ARK_PET_RUNTIME" \
  --output-dir "$ARK_PET_JOB/preview-render" \
  --width 384 --height 416 \
  --framing visible
```

### Sharpness gate: frame visible pixels, then downscale

Treat skeleton bounds as diagnostic data, not final framing. Spine rigs may contain invisible, detached, or distant attachments that make skeleton bounds much larger than the character. Fitting those bounds can render the visible operator into a tiny region; later normalization then enlarges that tiny raster and produces blur even when the source texture is sharp.

For every final package:

- Use `--framing visible`; the renderer probes rendered alpha across the selected animation samples and records both `skeletonFraming` and corrected `framing` in `render-metadata.json`.
- Render at 768×832 or higher. This is four times the 192×208 target cell in each dimension and is intentionally reduced with Lanczos during normalization. Use 384×416 only for disposable mapping previews.
- Confirm `framingMode` is `visible`, `visibleProbe` is populated, and the character is not clipped in the animation grid.
- Read `run/qa/normalization.json`. `safe-max` must remain at or below 1.0× in source-pixel terms, so the final cell is always downsampled from the high-resolution render. Rerender at higher resolution or repair framing instead of raising `--max-upscale`; raise it only for a documented, visually approved exception.
- Compare the native-size source crop and final 192×208 cell. Do not accept a package merely because the atlas validator passes; the validator cannot restore detail lost before assembly.

Generate labeled evidence where the model exposes many similar actions:

```bash
python3 "$ARK_PET_SKILL/scripts/make_image_grid.py" \
  --input-dir "$ARK_PET_JOB/preview-render/animations" \
  --output "$ARK_PET_JOB/qa/animation-grid.png"
```

### 3. Map animations and inspect the result

```bash
python3 "$ARK_PET_SKILL/scripts/make_mapping.py" \
  --metadata "$ARK_PET_JOB/preview-render/render-metadata.json" \
  --mapping-out "$ARK_PET_JOB/mapping.json" \
  --look-config-out "$ARK_PET_JOB/look-config.json"
```

The generated files are proposals. Inspect the source frames, then edit `mapping.json` so every Codex state has the intended action, frame order, mirroring, and offsets. Inspect `look-config.json`; remove false-positive eye bones and choose the actual head control. Never mark a package complete while `review_required` remains true.

When a whole-frame locomotion mirror is correct except for one fixed readable plate or sign, follow the narrow `counter_mirror_regions` procedure in [references/action-mapping.md](references/action-mapping.md). Measure the region in the final 192×208 cell, rerender all affected frames, and preserve both the original rejection and the repaired native-size evidence. A broad or moving asymmetric detail is not eligible for this adapter.

After the mapping is approved, rerender only the animations referenced by `mapping.json` at production resolution. Use 768×832 or higher and `--framing visible`. Do not normalize the 384×416 preview render into the final atlas.

```bash
CODEX_NODE_MODULES=/absolute/path/to/node_modules \
node "$ARK_PET_SKILL/scripts/render_model.mjs" \
  --model-dir "$ARK_PET_JOB/source" \
  --runtime-dir "$ARK_PET_RUNTIME" \
  --output-dir "$ARK_PET_JOB/render" \
  --animations 'APPROVED,ANIMATIONS' \
  --width 768 --height 832 \
  --framing visible
```

### 4. Normalize state frames and build the standard atlas

```bash
python3 "$ARK_PET_SKILL/scripts/prepare_frames.py" \
  --render-dir "$ARK_PET_JOB/render" \
  --mapping "$ARK_PET_JOB/mapping.json" \
  --run-dir "$ARK_PET_JOB/run" \
  --normalization safe-max \
  --margin 6 \
  --max-upscale 1.0

python3 "$ARK_PET_SKILL/scripts/compose_atlas.py" \
  --frames-root "$ARK_PET_JOB/run/frames" \
  --output "$ARK_PET_JOB/standard.png" \
  --webp-output "$ARK_PET_JOB/standard.webp"

python3 "$ARK_PET_SKILL/scripts/validate_atlas.py" \
  "$ARK_PET_JOB/standard.png" \
  --min-alpha-margin 6 \
  --json-out "$ARK_PET_JOB/qa/standard-validation.json"
```

`safe-max` first applies every approved mirror, offset, and rotation to the 768×832 official render. It then computes one pet-wide scale from the largest state union, keeps each animation row internally registered, and centers/bottom-aligns each row inside a 192×208 cell with a hard 6px alpha margin. This makes the character as large as the full action set safely permits without enlarging packaged WebP pixels. The scale must be shared by every state; never fit each state at an independent scale. `canvas` remains available when exact cross-state source-canvas coordinates matter more than fill. Use legacy `state-fit` only for a documented exception.

Run `inspect_frames.py`, `make_contact_sheet.py`, and `render_animation_previews.py` for visual inspection. Reject clipping, cross-state size jumps, foot sliding caused by bad alignment, reversed run direction, transparent junk, and semantic mismatches. Pay special attention to wide `failed` poses, jumping top edges, weapon/coat tips, and nonhuman rigs.

### 5. Calibrate and render 16 look directions

Keep `look-config.json` in `candidates` mode first. Render neutral and positive/negative eye/head probes:

```bash
CODEX_NODE_MODULES=/absolute/path/to/node_modules \
node "$ARK_PET_SKILL/scripts/render_model.mjs" \
  --model-dir "$ARK_PET_JOB/source" \
  --runtime-dir "$ARK_PET_RUNTIME" \
  --output-dir "$ARK_PET_JOB/look-probe" \
  --animations Relax \
  --width 768 --height 832 \
  --framing visible \
  --look-config "$ARK_PET_JOB/look-config.json"
```

Inspect the candidates. Change `mode` to `directions` and replace probe step fields with calibrated coefficients:

```json
{
  "mode": "directions",
  "animation": "Relax",
  "time": 0,
  "eye_bones": ["actual_eye_bone_1", "actual_eye_bone_2"],
  "head_bone": "actual_head_bone",
  "eye_x_up": 10,
  "eye_x_right": 0,
  "eye_y_up": 0,
  "eye_y_right": -12,
  "head_x_up": 2,
  "head_rotation_right": 0
}
```

The numeric example is not a universal preset. Derive signs and magnitudes from probe images. A rotated face rig may map local eye X to screen horizontal and local eye Y to screen vertical; in that case use `eye_x_right` and `eye_y_up` rather than forcing the conventional pair. If the rig cannot produce meaningful directions, stop and classify it as a manual exception; do not fake direction rows by shifting the whole character. Render again with the calibrated file; the 16 images appear under `look-source/`.

Do not average mirrored eye-bone axes into a single apparent direction. Compare the recorded screen-coordinate delta for every selected eye control separately. If the same local adjustment moves the left and right pupils in opposite screen directions, the shared-coefficient v2 adapter cannot drive them as one gaze pair. Prefer a genuinely common safe ancestor only when it moves the iris/highlight without dragging eye whites, lids, or brows; otherwise disable independent eye translation for that rig and use the hierarchy-safe complete head control. Record the limitation and preserve the failed paired-eye probe instead of shipping crossed or divergent eyes.

### 6. Assemble and clean the extended v2 atlas

Choose a chroma key far from the character palette:

```bash
python3 "$ARK_PET_SKILL/scripts/choose_chroma_key.py" \
  "$ARK_PET_JOB/look-probe/look-source" \
  --json-out "$ARK_PET_JOB/chroma-key.json"
```

Read the selected hex value and pass the same value through assembly, despill, and validation:

```bash
python3 "$ARK_PET_SKILL/scripts/assemble_extended_atlas.py" \
  --base-atlas "$ARK_PET_JOB/standard.png" \
  --look-cells-dir "$ARK_PET_JOB/look-probe/look-source" \
  --output "$ARK_PET_JOB/extended-raw.png" \
  --chroma-key '#SELECTED'

python3 "$ARK_PET_SKILL/scripts/despill_chroma_edges.py" \
  "$ARK_PET_JOB/extended-raw.png" \
  --output "$ARK_PET_JOB/spritesheet.png" \
  --chroma-key '#SELECTED'

python3 "$ARK_PET_SKILL/scripts/validate_atlas.py" \
  "$ARK_PET_JOB/spritesheet.png" \
  --require-v2 --chroma-key '#SELECTED' \
  --json-out "$ARK_PET_JOB/qa/v2-validation.json"
```

Run `--help` if a bundled script has additional required flags. Do not bypass a failed validator with permissive flags unless the user explicitly accepts and the exception is documented.

### 7. Verify direction semantics and continuity

```bash
python3 "$ARK_PET_SKILL/scripts/make_direction_qa_sheet.py" \
  "$ARK_PET_JOB/spritesheet.png" \
  --output "$ARK_PET_JOB/qa/directions-labeled.png"

python3 "$ARK_PET_SKILL/scripts/make_direction_blind_qa_sheet.py" \
  "$ARK_PET_JOB/spritesheet.png" \
  --output "$ARK_PET_JOB/qa/directions-blind.png" \
  --answer-key "$ARK_PET_JOB/qa/directions-blind-map.json"

python3 "$ARK_PET_SKILL/scripts/measure_direction_continuity.py" \
  "$ARK_PET_JOB/spritesheet.png" \
  --json-out "$ARK_PET_JOB/qa/direction-continuity.json"
```

When subagents are available and the user authorizes delegation, give the blind sheet—not the labeled sheet or mapping—to three independent reviewers. Combine and validate their JSON verdicts with the bundled blind-QA scripts. Otherwise perform a fresh blind pass in a separate inspection context and explicitly report that it was not multi-reviewer QA.

For a large batch, use `make_batch_cardinal_blind_qa.py` to paginate cardinal cells, then `combine_batch_cardinal_reviews.py`, `validate_batch_cardinal_reviews.py`, and `apply_batch_cardinal_validation.py`. Keep the hidden key out of every reviewer context. When one validation contains both proven inverse axes and ambiguous/mixed axes, run `apply_cardinal_axis_repairs.py --skip-unsupported`: it repairs only the proven inversions and records the skipped jobs for manual repair, instead of forcing the whole batch into one verdict. Preserve the original failed protocol. If reviewers mistake fixed body facing for the moving cue, use `make_batch_cardinal_focus_qa.py` with fresh reviewers who compare only physical local-cue position. If a scale-only reassembly leaves mapping, look configuration, and direction-source hashes unchanged but focused JPEG reviewers disagree, do not flip coefficients from that evidence. Generate lossless raw full/local A/B pairs for only the failed jobs with `make_batch_cardinal_recheck_qa.py` and use three fresh isolated reviewers. If rotation or dark/closed eyes still make A/B hard to register, pass that recheck index to `make_batch_cardinal_overlay_qa.py`; its red=A/cyan=B overlay and fixed grid expose paired edge order without revealing semantic labels. Tell reviewers the exact visible cue to follow (pupil center, closed-eye/nose center, or rigid mechanism center), never a rotating hair/leaf/bar endpoint. For eyeless, masked, or closed-eye rigs whose control sign is already corroborated but the native-size cue is genuinely ambiguous, strengthen the coherent head translation/rotation together, rerender, re-audit the 6px safe-max margin, and rerun three-way blind QA; never enlarge the source pixels or invent replacement eyes. Blind, focus, recheck, and overlay protocols may randomize A/B independently: validate each result against its own hidden key and use `merge_batch_cardinal_semantic_recheck.py` with both answer keys to translate confirmed semantics into the original base A/B order. When a mixed recheck page contains both passing and failing jobs, pass repeated `--model-key` values so only independently validated jobs are merged; never let one ambiguous job discard valid repairs or contaminate the final consensus. Never naively merge raw A/B labels across protocols. If reviewer agreement remains unstable, stop coefficient flipping and corroborate physical sign with `measure_cardinal_control_axes.py`; when an off-center rotating attachment visibly moves opposite its bone origin, final-cell visible-cue evidence is authoritative and the pivot exception must be explicitly recorded and re-reviewed.

Generate native-size final sheets with `make_batch_final_review.py` and independently inspect every job before applying verdicts with `apply_batch_final_reviews.py`. The final sheet shows only one atlas cell per state, normally frame 0; it is evidence for identity, scale, framing, and labeled cardinals, not proof of an animation's full semantics. Every final reviewer must also inspect `run/qa/contact-extended.png` (or equivalent full strips) before judging loops or motion. Do not reject `waving` merely because frame 0 resembles idle: the state may use the official `Interact` animation as a character-specific greeting rather than a literal hand wave. Most Ark building rigs expose only five or six official actions for nine Codex rows, so distinct, coherent frame windows may intentionally reuse one source animation; shared source names are not a defect by themselves. Likewise, an attachment that legitimately changes during an official `Move` animation is not by itself corruption. A synthetic `jumping` row may combine an official motion with a deliberately subtle measured vertical arc; require continuous displacement, not a dramatic airborne pose. Before classifying a detached puff, sparkle, or prop as an alpha artifact, compare it with the corresponding high-resolution official source-animation frames; preserve intentional source effects. Preserve any verdict produced from a frame-0-only or uncalibrated literal-action protocol as failed evidence, then repeat final review with fresh reviewers and full strips.

### 8. Package the pet

Create a clean delivery directory and ZIP. The packager writes the current v2 `pet.json` fields (`id`, `displayName`, `description`, `spriteVersionNumber`, and `spritesheetPath`), provenance, and optional QA evidence:

```bash
python3 "$ARK_PET_SKILL/scripts/package_pet.py" \
  --spritesheet "$ARK_PET_JOB/spritesheet.png" \
  --pet-id PET_ID \
  --display-name 'DISPLAY NAME' \
  --description 'SOURCE-AWARE DESCRIPTION' \
  --model-key MODEL_KEY \
  --category default \
  --validation "$ARK_PET_JOB/qa/v2-validation.json" \
  --qa-preview "$ARK_PET_JOB/qa/directions-labeled.png" \
  --output-dir "$ARK_PET_JOB/delivery/PET_ID" \
  --zip-output "$ARK_PET_JOB/delivery/PET_ID.zip"
```

Use `--category skin` for an outfit. Package to ZIP by default; install only when the user explicitly asks. Before installation, compare with a working local v2 pet in case a newer Codex release changes the metadata contract.

## Run a batch safely

Share one refreshed catalog and one renderer runtime. Give each `model_key` an immutable source folder and resumable stage directory. Process ordinary single-page models with bounded concurrency, normally no more than three browser renderers; move exceptional rigs to a separate queue. Update the manifest after each stage and retain failure evidence.

Use `run_batch_stage.py` for resumable stages; its ordinary default is `--normalization safe-max --cell-margin 6 --max-upscale 1.0`. Keep `direction_evidence_qa` separate from `direction_qa`: generating sheets is not semantic approval. All scripts that mutate the shared manifest take the same temp-directory file lock; never add an ad-hoc writer that bypasses it. Use `apply_mapping_reviews.py`, `apply_visual_look_reviews.py`, and `apply_adapter_reviews.py` to turn explicit visual verdicts into calibrated state. An approved mapping-review job may include a partial `states` object; `apply_mapping_reviews.py` validates those state names, atomically applies the exact reviewed frame/animation repairs, and only then clears `review_required`. Prefer this path over hand-editing many per-pet mappings, especially when sparse source sampling would make props appear or disappear between non-adjacent frames. A calibrated look review may supply the hierarchy-reviewed `eye_bones` and `head_bone`; the apply script rejects unknown bones and ancestor/descendant duplicates. It may also set `eye_magnitude`, `head_translation_magnitude`, and `head_rotation_magnitude`; use the smallest normal-size-visible values (commonly 3px for isolated eyes and 2px for head assistance) instead of accepting the large diagnostic probe step as a production coefficient. For a rotated rig whose local axes are diagonal in screen space, include an explicit `coefficients` object so both local axes can contribute to each screen cardinal; this is preferable to forcing a diagonal probe into a single categorical axis.

If a mapping review changes a state's required frame count, rerun `prepare` before rebuilding the standard atlas. `prepare_frames.py` clears only the prior generated PNG cells inside each exact state directory before writing the new sequence, so stale trailing frames cannot produce a false frame-count failure; non-PNG review evidence is preserved. Never work around a count mismatch by accepting extra cells or weakening `inspect_frames.py`.

After all four package gates pass, run `stage_batch_packages.py` into an empty directory outside the Git worktree. Inspect its registry candidate and machine-readable results before publishing anything into the repository.

Never claim every operator can be converted unattended. A capable agent plus this skill can usually finish ordinary rigs, but rig-specific animation names, missing look controls, unusual bodies, multi-page atlases, and skins with special attachments require judgment or adapter work.

## Completion criteria

Report success only when source identity and outfit category are recorded; state mapping is visually approved; final frames were rendered with visible-pixel framing and do not require material upscaling; the v2 validator passes; direction labels and continuity are correct; final motion, sharpness, transparency, framing, and scale pass visual QA; and the ZIP excludes machine caches, dependencies, and unauthorized source mirrors.
