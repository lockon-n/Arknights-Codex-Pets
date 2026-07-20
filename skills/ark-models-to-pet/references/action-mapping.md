# Animation and direction mapping guide

## Codex state rows

The standard atlas uses 192×208 cells, eight columns, and nine rows:

1. idle: 6 frames
2. running-right: 8 frames
3. running-left: 8 frames
4. waving: 4 frames
5. jumping: 5 frames
6. failed: 8 frames
7. waiting: 6 frames
8. running: 6 frames
9. review: 6 frames

The generated mapping favors common Ark names: `Relax`/`Default`/`Idle` for idle, `Move`/`Run`/`Walk` for locomotion, `Interact`/`Special` for a gesture, `Sit` for waiting, and `Sleep` for failed. These are heuristics.

Inspect all animations and sampled frames. Prefer semantic coherence over name similarity. Reuse animations when necessary, but vary timing or frames so states remain readable. Mirror locomotion only when safe; asymmetric writing, weapons, and effects may require separate handling.

If whole-frame mirroring is otherwise correct but reverses one small, rigid, readable sign or plate, use a narrowly measured final-cell `counter_mirror_regions` rectangle on the mirrored state. The frame preparer flips that local rectangle a second time in place, keeping the lettering readable while the vehicle or body still faces the requested direction. Record the exact 192×208 coordinates, inspect every affected frame at native size, and reject any visible seam or moving label. Do not use this adapter to patch broad character asymmetry, detached effects, or several moving regions.

When a wide source reaction would unnecessarily shrink the pet-wide `safe-max` scale, select a coherent continuous subsequence rather than isolated distant endpoints. Preserve chronological neighbors or use an explicit ping-pong sequence such as `5,6,7,6`; never alternate poses with missing transition frames merely to gain a few percent of size. Playback continuity outranks a marginal scale increase, and the selected loop must be reviewed in motion after normalization.

Keep feet and lower body anchored outside jumping. Avoid inventing motion with large whole-sprite translations when the rig provides suitable animation.

## Direction convention

The 16 labels progress clockwise in 22.5° steps: `000` is up, `090` right, `180` down, and `270` left. Intermediate labels blend axes.

Probe positive and negative eye/head controls before assigning signs. Spine local axes differ by rig, so never copy coefficients blindly. Keep body motion restrained. Remove controls that move eyelids, brows, hair, or the whole skeleton incorrectly. If no usable controls exist, record a manual exception instead of fabricating directions.

Do not trust an eye-like bone name by itself. Trace slot ownership and inspect the rendered probe: an automatically discovered candidate such as a fish, camera, doll, or mascot eye may belong to a hand-held prop rather than the operator's gaze. Remove every false-positive prop control, rerender the candidate sheet, and verify the prop remains byte-stable before calibration.

Also distinguish skeleton bones from slots before accepting or rejecting a control. A rig may expose the real face controls under generic names such as `bone17`, while familiar `F_Head` or `F_*Eye` names exist only as slots; automatic name matching can therefore miss every usable control. Trace each visible eye/head attachment back to its controlling bone and confirm it changes pixels in the probe. When an eye has both a parent eye bone and a leaf pupil/eyeball bone, use the smallest coherent leaf control and do not move parent and child together, which would double the intended displacement and can pull eyelids or lashes apart.

For rotated or nonhuman rigs, either local eye or head translation axis may map to either screen axis. Record `eye_x_plus`, `eye_y_plus`, `head_x_plus`, and `head_y_plus` independently as `up`, `down`, `screen-left`, `screen-right`, or `neutral`. Populate the matching coefficient component (`eye_x_up`, `eye_x_right`, `eye_y_up`, or `eye_y_right`) instead of assuming local eye X is vertical and local eye Y is horizontal. Use the natural local axis that moves only the approved attention cue. Do not force horizontal motion through rotation when a local translation axis is the coherent screen-horizontal control.

Older and nonhuman rigs may use misleading bone names or rotated local axes. Use rendered positive/negative probes to label screen semantics, not the nominal X/Y name. If a candidate produces no changed pixels, verify that visible slots or weighted mesh vertices actually depend on it. A rigid, independently bound radar or antenna is acceptable as a natural attention cue; root, body, chassis, and whole-sprite translations are not.

For a nonhuman rig without `Sit` or `Sleep`, a documented `rotation_degrees` transform may turn an official `Relax` frame into an unmistakable failed/disabled pose. Keep the transform state-specific, preserve source registration, and visually inspect it; do not use this to disguise a missing ordinary-human animation.
