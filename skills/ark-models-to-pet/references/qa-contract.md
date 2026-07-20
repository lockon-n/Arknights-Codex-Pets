# Codex v2 pet QA contract

## Geometry

- Cell: 192×208 pixels.
- Columns: 8.
- Standard atlas: 9 rows, 1536×1872.
- Direction extension: 2 rows, 16 frames.
- V2 atlas: 1536×2288.
- Unused cells remain transparent.
- Metadata declares `spriteVersionNumber: 2`.

The bundled packager writes `pet.json` with `id`, `displayName`, `description`, `spriteVersionNumber`, and `spritesheetPath`. It places the lossless atlas beside that file.

The validator checks dimensions, occupancy, unused cells, optional minimum alpha margins, transparency residue, chroma leakage, and chroma edge fringe. Passing is necessary but not sufficient.

## Visual review

Inspect contact sheets and animation previews at native size and intended UI scale. Check identity, costume, semantics, loops, feet, clipping, scale consistency, alpha edges, detached effects, left/right movement, and downscaled readability. A batch final sheet normally shows frame 0 from each state and therefore cannot establish whether the whole animation reads correctly. Final reviewers must inspect the full `contact-extended.png` strips before judging motion or semantics. Treat `waving` as a character-specific official `Interact`/greeting state rather than requiring a literal raised-hand wave. Because a typical source rig has fewer official actions than the nine Codex rows, coherent states may reuse the same source action with different frame windows or timing; reject actual identical/broken output, not the shared animation name alone. For `jumping`, accept a continuous documented vertical offset layered over an official motion; do not require an exaggerated airborne silhouette. Verify detached puffs, sparkles, or props against the high-resolution source-animation frames before labeling them transparency corruption. Preserve frame-0-only or uncalibrated literal-action rejections as failed protocols and repeat with fresh full-strip reviewers.

## Sharpness gate

- Render final source frames with visible-pixel framing at 768×832 or higher. Skeleton bounds are not an acceptable final framing source because invisible or distant rig attachments can shrink the visible character.
- Require `framingMode: visible` and a populated `visibleProbe` in `render-metadata.json`.
- Require `safe-max` source-pixel scales to remain at or below 1.0×. If `prepare_frames.py` reports a larger factor, repair framing or rerender at higher resolution instead of accepting enlarged raster detail.
- Inspect one representative native-size source frame beside its final 192×208 cell. Crisp source textures do not guarantee a crisp pet if the character was rasterized too small before normalization.
- For ordinary jobs, require one pet-wide `safe-max` scale derived from all approved transformed frames. A state may have its own union crop/placement so wide and tall actions use the cell efficiently, but every state must retain internal registration and use exactly the same scale. Independent per-state scale fitting is forbidden because it creates false size jumps.
- Require at least 6 transparent pixels on every side of every used 192×208 cell after lossless WebP encoding. Inspect wide `failed` poses, moving weapon/coat tips, jumping tops, waiting bottoms, robots, and all 16 look cells.
- Treat atlas validation and lossless WebP encoding as necessary but insufficient: neither detects detail already destroyed by an undersized render.

For direction rows, verify cardinal meaning on the labeled sheet and perceptual ordering on the blind sheet. Adjacent frames, including 337.5° to 000°, should change gradually. Metrics can flag outliers but cannot determine gaze semantics.

## Blind protocol

Use three isolated reviewers when authorized and available. Give only the randomized blind sheet and verdict schema—not labels, shuffle mapping, prior verdicts, or coefficients. Combine verdicts, reveal mapping, and validate consensus. Recalibrate meaningful disagreement.

For batches, render paginated cardinals with `make_batch_cardinal_blind_qa.py`; it supports repeated `--model-key` filters for isolated repair jobs. Require every reviewer file to contain the same unique model-key set, combine an odd number of at least three reviews, and apply only the revealed validation result to the manifest. `direction_evidence_qa=review` means evidence exists, not that direction semantics passed.

If native 192×208 cells are inconsistently readable in a multi-row sheet, preserve that failed pass and rerender only the review sheet with `--display-scale 2`. The option uses nearest-neighbor enlargement and does not alter the approved atlas. Use fresh isolated reviewers for the replacement pass; never resolve ambiguity by revealing the key or inferring the intended coefficients.

If reviewers describe the character's fixed body-facing direction or assign the same direction to both members of an opposite A/B pair, reject the protocol rather than the atlas. Generate a fresh focused pass with `make_batch_cardinal_focus_qa.py`. It shows full cells beside identical-coordinate 72-pixel crops centered on A/B difference energy and overlays the same coordinate grid on both crops, without encoding the answer. Instruct fresh reviewers to compare physical position only: which moving local cue is farther left/right or higher/lower in A versus B. Any non-ambiguous horizontal or vertical pair must be mutually opposite. The focused generator derives A/B order from `model_key`, not atlas bytes, so a repaired atlas keeps the same hidden ordering.

When three-reviewer consensus classifies both members of one axis as the exact opposite of the hidden key, treat that as evidence of a reversed calibration—not ambiguity. Use `apply_cardinal_axis_repairs.py` to negate only the nonzero coefficients for the proven reversed axis, reset every downstream gate, rerender the selected jobs, and run a fresh blind pass over only the repaired set. Never change magnitude, animation, or the other axis during this repair.

Before applying a large repair set, audit reviewer stability. If fewer than half of the axes have unanimous agreement, fresh reviewers reverse many just-repaired axes, or unchanged axes change verdict after a rerender, preserve the failed protocol and stop flipping coefficients. `render_model.mjs` records adjusted control-bone screen coordinates in `render-metadata.json`; run `measure_cardinal_control_axes.py` to identify objectively inverted translations and unmeasurable rotation-only controls. Coordinates are corroborating evidence for physical sign, not a replacement for visual semantics. Resume with fresh reviewers using the explicit physical-position protocol.

If a fixed-order, fixed-grid focused pass yields exact inverse consensus, negate only that axis. If both cells of an axis are consistently `ambiguous` while the deterministic control sign is not inverse, strengthen only that axis by a documented factor no greater than 2 and rerender; do not flip it. `resolve_cardinal_axes.py` applies those two distinct actions, resets downstream gates, and records every coefficient change. Run the same fixed-grid review again so before/after A/B positions remain directly comparable.

For extremely subtle official rigs, human grid judgments can remain method-dependent even after the cue is enlarged. Preserve those results as failed protocols. A numerical blind replacement may use three isolated reviewers that read only the fixed-grid JPGs, crop the documented local columns, mask the static grid, and estimate A-to-B motion with independent robust optical-flow or feature methods. Every reviewer must first pass synthetic right-shift and down-shift sign tests, emit canonical direction enums, and record `dx`/`dy`. Reject a method with systemic axis contradiction; combine the three remaining valid reviews normally. Numerical blind evidence validates physical A/B sign only, so labeled final visual QA must still approve semantic readability, identity, continuity, and appearance.

JPEG grids are convenient evidence, not ground truth. After a normalization-only rebuild, a first numerical pass can disagree because compression, grid lines, hair motion, or whole-head rotation dominates a sub-pixel eye cue. If `mapping.json`, `look-config.json`, and all 16 high-resolution direction sources are hash-identical before and after the rebuild, do not treat that disagreement as authorization to flip coefficients. Feed the failed validation to `make_batch_cardinal_recheck_qa.py`; it emits lossless full cells and identical-coordinate local PNG pairs for only the affected jobs, without an answer key. Use three fresh reviewers who have not seen the prior verdicts. Because blind, focus, and recheck protocols randomize A/B independently, first validate the selected-job consensus against that protocol's own hidden key, then use `merge_batch_cardinal_semantic_recheck.py` with both answer keys to translate confirmed semantics back into the base sheet's A/B order. Never merge raw A/B labels across protocols. Validate the complete translated set again; ambiguity remains a failure until the lossless pass resolves it.

When lossless A/B pairs remain hard to register because a dark closed eye, whole-head rotation, or a rigid mechanism has several moving endpoints, generate a red=A/cyan=B registration sheet with `make_batch_cardinal_overlay_qa.py`. Static pixels become white/gray; paired motion edges separate into red and cyan on an identical-coordinate grid. The reviewer prompt must name one hierarchy-approved visible cue: pupil centers relative to eye whites, a closed-eye/nose center relative to the face, or the center/base of a rigid mechanism. Explicitly exclude rotating hair silhouettes, leaves, bar endpoints, and unrelated red clothing. Preserve the ordinary lossless verdict as failed evidence and use three fresh isolated overlay reviewers.

Control-bone screen coordinates are pivot diagnostics, not guaranteed visible-part coordinates. An off-center attachment can rotate so its bone origin moves right while the pupil, face center, or rigid mechanism center moves left. If repeated visible reviews conflict with the anchor audit, measure the named final-cell component, preserve before/after A/B hashes, change only the affected axis, rerender, and require a fresh blind overlay plus final full-strip review. Record the exception with the bone verdict, visible cue, pixel evidence, coefficient changes, and why the visible semantic result overrides the pivot. Do not generalize one pivot exception to the other axis or other models.

If repeated blind, focused, lossless, and overlay protocols remain method-dependent, reconcile evidence per axis instead of demanding that one noisy protocol pass all four cells or repeatedly flipping correct controls. Preserve every failed protocol. An axis may enter a final reconciliation only when either (a) that axis passed one independently randomized protocol against its own hidden key and its semantic result is translated to the base A/B order, (b) every rendered eye/pupil control measured by `measure_cardinal_control_axes.py` has the correct sign, with no inverse or mixed control, and the labeled final sheet remains visually acceptable, or (c) a documented off-center pivot exception passed final-cell component measurement and a fresh three-reviewer overlay after the selected axis alone was repaired. A rotation-only horizontal axis is unmeasurable by coordinate translation and therefore still requires passing visible evidence. When a later per-axis repair swaps the exact A/B image hashes, translate that axis mechanically and record the hash evidence; do not reuse unchanged labels. Record the evidence source for each reconciled axis, then validate the complete reconciled result against the original base key. This is a stop-loss for reviewer noise, not permission to copy a key without independent physical evidence.

If delegation is unavailable, conduct a fresh blind inspection without labels and disclose the weaker method.

## Delivery QA

Open the packaged atlas itself. Confirm dimensions, alpha, lossless encoding, metadata version, display name, provenance, and ZIP contents. Exclude `node_modules`, browser caches, fetched mirrors, temporary server assets, and machine-specific absolute paths.

For batch staging, require bit-for-bit equality between the approved `run/spritesheet.webp` and the packaged atlas. Keep `v2-validation.json`, `directions-labeled.png`, `contact-extended.png`, `direction-continuity.json`, and `standard-contact.png` inside `qa/`; validate that the JSON is readable and passing and that every image opens successfully. Treat `registry-entries.json` as a merge candidate, not as authorization to overwrite an existing registry.
