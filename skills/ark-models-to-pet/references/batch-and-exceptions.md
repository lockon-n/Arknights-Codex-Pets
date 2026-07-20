# Batch execution and exceptions

## Resumable stages

Track: selected, fetched, preflighted, preview-rendered, mapping-reviewed, production-rendered, frames-prepared, standard-validated, directions-calibrated, directions-rendered, v2-assembled, v2-validated, direction-evidence-generated, direction-reviewed, visually-approved, packaged. Keep direction rendering, evidence generation (`direction_evidence_qa`), and semantic approval (`direction_qa`) separate. Store outputs and the latest error, and rerun only a failed stage and downstream dependents.

Every manifest writer must use the same cross-process lock derived from the absolute manifest path and stored in the system temporary directory. The stage runner holds that lock for the full selected stage. Without this rule, a long renderer and a visual-review applicator can each write an old snapshot and silently discard the other's progress.

When an assembly or normalization algorithm changes during a batch, audit and rebuild earlier pilot outputs too. A passing old pilot is not grandfathered into the new batch contract. Reassembly invalidates direction evidence, blind results, final visual QA, and package QA for that job; reset those gates and regenerate evidence from the new atlas. A final sheet comparing standard states with cardinals is the required backstop for cross-row baseline drift.

Use one shared renderer runtime but separate mutable job directories. Start with no more than three concurrent browser renderers; reduce concurrency for large rigs.

Use 384×416 only for all-animation mapping previews. After mapping approval, render only referenced animations at 768×832 or higher. Normalize ordinary jobs with `safe-max`: one scale per pet, per-state union registration, a 6px final alpha margin, and no source-pixel upscaling. Never enlarge an existing atlas or WebP. Preserve row-internal motion and visually reject cross-state size or baseline jumps.

If only the normalization policy changes, validated 768×832 production renders and direction source renders may be reused byte-for-byte. Reset and rebuild frames, standard atlas, extended atlas, direction evidence, blind review, final visual review, and package QA. Snapshot `mapping.json`, `look-config.json`, and direction-source hashes before the rebuild and prove they did not change afterward.

Do not react to a failed post-reassembly JPEG/grid cardinal pass by immediately negating direction coefficients. First prove the immutable input hashes, then regenerate only the failed jobs as lossless full/local A/B PNG pairs with `make_batch_cardinal_recheck_qa.py`. Use three reviewers with no access to the failed consensus or key. Every blind, focus, and recheck sheet randomizes A/B independently, so never copy or naively merge raw A/B labels across protocols. Validate the recheck against its own hidden key, then use `merge_batch_cardinal_semantic_recheck.py` with both the base and recheck answer keys to translate the confirmed semantic directions back into the base sheet's A/B order before rerunning full validation. This distinguishes review-method noise from an actual calibration regression.

The renderer records the actual screen coordinates of adjusted look controls for every probe and direction pose. Use `measure_cardinal_control_axes.py` after a direction render to audit `090 minus 270` on screen X and `000 minus 180` on screen Y. A translated control should be positive horizontally and negative vertically. Rotation-only controls are intentionally reported as unmeasurable and still require focused visual review. This evidence prevents a noisy blind majority from repeatedly flipping a correct local-axis calibration.

Do not silently accept an OCR-derived reviewer key set just because it contains the expected count. Compare it with the hidden key set only after the reviewer has finished; correct model-key spelling mechanically without changing verdicts. Require canonical values (`screen-left`, `screen-right`, `up`, `down`, `ambiguous`) before combining. For numerical reviewers, verify their crop coordinates and optical-flow sign on synthetic translations before trusting any batch-wide pattern.

## Ordinary fast path

An ordinary model has one atlas page, one skeleton, useful idle/locomotion/action animations, and identifiable eye/head controls. A capable agent can normally complete it with the main workflow.

## Exception classes

- **Multiple atlas pages:** extend texture-page mapping; never silently pick the first PNG.
- **Multiple skeletons/textures:** inspect relationships and split the job or add a model adapter.
- **Skeleton JSON collision:** distinguish the Spine skeleton from generated manifests.
- **Missing common animation names:** inspect all animations and author mapping manually.
- **No usable eye/head controls:** require manual rig work; do not shift the whole sprite.
- **A named leaf bone renders no change:** inspect slot ownership and mesh weights. A bone that exists in the hierarchy may own no attachment and influence no mesh vertices; increasing its step cannot make it useful.
- **Asymmetric attachments/effects:** avoid naive mirroring and inspect both directions.
- **Robots, groups, summons, wide bodies:** adjust framing without violating 192×208 cells.
- **Detached particles/props:** ensure cleanup does not remove legitimate components.
- **Zero-duration animation:** choose stable samples and verify repetitions are intentional.
- **Runtime incompatibility:** capture Spine version, console output, and dependency versions first.

After repeated failure for the same reason, remove the job from the ordinary queue, preserve evidence, and continue unrelated jobs. One adapter must not weaken validation for every model.

For an unusual rig, record slot-to-bone ownership, parent/child relationships, world positions, and mesh weights before choosing an adapter. Prefer a rigid natural attention cue such as an independently bound radar/display, then a coherently weighted probe or antenna. Reject controls that move the chassis, split a cap from its cable, or produce zero changed pixels. The Lancet-2 lesson is representative: `F_Muzzle` existed but had no slot or mesh weight and produced byte-identical probes; `bone10` moved only a detached cap; the independently bound `F_Radar` was the valid local cue.

For nonhuman standard states, a state-specific `rotation_degrees` transform may adapt an official `Relax` pose into a clear disabled pose. It must preserve source registration, remain documented in `mapping.json`, and pass standard contact-sheet review.

## Stage approved packages outside the repository

Do not publish directly from the mutable job tree and do not point the batch packager at a Git worktree. After final visual review, stage only jobs whose `standard_visual_qa`, `direction_qa`, `atlas_qa`, and `visual_qa` fields all equal `pass`:

```bash
python3 "$ARK_PET_SKILL/scripts/stage_batch_packages.py" \
  --manifest /absolute/path/to/batch-manifest.json \
  --job-root /absolute/path/to/batch-jobs \
  --staging-root /absolute/path/to/repository-external-staging
```

The command never edits the manifest. It atomically creates validated packages under `pets/<pet-id>/`, writes `registry-entries.json`, and writes `batch-package-results.json`. Each package includes exact-name v2 validation, labeled-direction, extended-contact, direction-continuity, and standard-contact evidence, plus the repository-compatible `validation.json` and `preview.png` aliases. JSON QA is copied with machine-specific absolute paths removed.

The default refuses a non-empty staging root. If a run is interrupted, rerun the same command with `--resume`; existing packages are reused only after complete package validation, and invalid or unrelated contents are never overwritten. Inspect the results and registry files before copying anything into the output repository or committing it.
