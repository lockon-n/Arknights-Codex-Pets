#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


STAGE_FIELD = {
    "preflight": "preflight",
    "preview-render": "preview_render",
    "map": "mapping_qa",
    "production-render": "production_render",
    "prepare": "frames_qa",
    "standard": "standard_qa",
    "look-probe": "direction_probe",
    "direction-render": "direction_render",
    "atlas": "atlas_qa",
    "direction-evidence": "direction_evidence_qa",
}


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def write_csv(path: Path, jobs: list[dict]) -> None:
    if not jobs:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(jobs[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(jobs)
        temporary = Path(handle.name)
    temporary.replace(path)


def run_logged(command: list[str], log_path: Path, env: dict | None = None) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        tail = "\n".join(completed.stdout.splitlines()[-12:])
        raise RuntimeError(f"exit {completed.returncode}: {tail}")


def execute_job(
    job: dict,
    stage: str,
    source_root: Path,
    job_root: Path,
    skill_dir: Path,
    runtime_dir: Path | None,
    node: str | None,
    node_modules: str | None,
    normalization: str,
    cell_margin: int,
    max_upscale: float,
) -> tuple[str, str | None]:
    model_key = job["model_key"]
    pet_id = job["pet_id"]
    source_dir = source_root / model_key
    output = job_root / pet_id
    output.mkdir(parents=True, exist_ok=True)
    logs = output / "logs"
    python = os.environ.get("PYTHON", os.sys.executable)

    if stage == "preflight":
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "preflight_model.py"),
                "--model-dir",
                str(source_dir),
                "--json-out",
                str(output / "preflight.json"),
            ],
            logs / "preflight.log",
        )
        return model_key, None

    if stage in {"preview-render", "production-render"}:
        if not runtime_dir or not node:
            raise RuntimeError("render stage requires --runtime-dir and --node")
        output_dir = output / ("preview-render" if stage == "preview-render" else "render")
        width, height = ("384", "416") if stage == "preview-render" else ("768", "832")
        animation_args: list[str] = []
        if stage == "production-render":
            mapping = json.loads((output / "mapping.json").read_text(encoding="utf-8"))
            if mapping.get("review_required") is not False:
                raise RuntimeError("mapping.json must have review_required=false before production render")
            animations = sorted({spec["animation"] for spec in mapping["states"].values()})
            animation_args = ["--animations", ",".join(animations)]
        env = os.environ.copy()
        if node_modules:
            env["CODEX_NODE_MODULES"] = node_modules
        run_logged(
            [
                node,
                str(skill_dir / "scripts" / "render_model.mjs"),
                "--model-dir",
                str(source_dir),
                "--runtime-dir",
                str(runtime_dir),
                "--output-dir",
                str(output_dir),
                "--width",
                width,
                "--height",
                height,
                "--framing",
                "visible",
                *animation_args,
            ],
            logs / f"{stage}.log",
            env,
        )
        return model_key, None

    if stage == "map":
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "make_mapping.py"),
                "--metadata",
                str(output / "preview-render" / "render-metadata.json"),
                "--mapping-out",
                str(output / "mapping.json"),
                "--look-config-out",
                str(output / "look-config.json"),
            ],
            logs / "map.log",
        )
        return model_key, None

    if stage == "prepare":
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "prepare_frames.py"),
                "--render-dir",
                str(output / "render"),
                "--mapping",
                str(output / "mapping.json"),
                "--run-dir",
                str(output / "run"),
                "--normalization",
                normalization,
                "--margin",
                str(cell_margin),
                "--max-upscale",
                str(max_upscale),
            ],
            logs / "prepare.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "inspect_frames.py"),
                "--frames-root",
                str(output / "run" / "frames"),
                "--json-out",
                str(output / "run" / "qa" / "frame-review.json"),
                "--require-components",
            ],
            logs / "inspect-frames.log",
        )
        return model_key, None

    if stage == "standard":
        run_dir = output / "run"
        qa_dir = run_dir / "qa"
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "compose_atlas.py"),
                "--frames-root",
                str(run_dir / "frames"),
                "--output",
                str(run_dir / "standard.png"),
                "--webp-output",
                str(run_dir / "standard.webp"),
            ],
            logs / "compose-standard.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "validate_atlas.py"),
                str(run_dir / "standard.webp"),
                "--json-out",
                str(qa_dir / "standard-validation.json"),
                "--min-alpha-margin",
                str(cell_margin if normalization == "safe-max" else 0),
            ],
            logs / "validate-standard.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "make_contact_sheet.py"),
                str(run_dir / "standard.webp"),
                "--output",
                str(qa_dir / "standard-contact.png"),
            ],
            logs / "contact-standard.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "render_animation_previews.py"),
                "--frames-root",
                str(run_dir / "frames"),
                "--output-dir",
                str(qa_dir / "previews"),
            ],
            logs / "preview-standard.log",
        )
        return model_key, None

    if stage in {"look-probe", "direction-render"}:
        if not runtime_dir or not node:
            raise RuntimeError("look render requires --runtime-dir and --node")
        look_config_path = output / "look-config.json"
        look_config = json.loads(look_config_path.read_text(encoding="utf-8"))
        if stage == "look-probe" and look_config.get("mode") != "candidates":
            raise RuntimeError("look-config.json must use mode=candidates for look probes")
        if stage == "direction-render" and (
            look_config.get("mode") != "directions"
            or look_config.get("review_required") is not False
        ):
            raise RuntimeError(
                "look-config.json must use mode=directions and review_required=false"
            )
        animation = look_config.get("animation")
        if not animation:
            raise RuntimeError("look-config.json is missing animation")
        env = os.environ.copy()
        if node_modules:
            env["CODEX_NODE_MODULES"] = node_modules
        run_logged(
            [
                node,
                str(skill_dir / "scripts" / "render_model.mjs"),
                "--model-dir",
                str(source_dir),
                "--runtime-dir",
                str(runtime_dir),
                "--output-dir",
                str(output / ("look-probe" if stage == "look-probe" else "directions")),
                "--animations",
                str(animation),
                "--width",
                "384" if stage == "look-probe" else "768",
                "--height",
                "416" if stage == "look-probe" else "832",
                "--framing",
                "visible",
                "--look-config",
                str(look_config_path),
            ],
            logs / f"{stage}.log",
            env,
        )
        return model_key, None

    if stage == "atlas":
        run_dir = output / "run"
        qa_dir = run_dir / "qa"
        look_dir = output / "directions" / "look-source"
        chroma_path = qa_dir / "chroma-key.json"
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "choose_chroma_key.py"),
                str(look_dir),
                "--json-out",
                str(chroma_path),
            ],
            logs / "choose-chroma.log",
        )
        chroma = json.loads(chroma_path.read_text(encoding="utf-8")).get("hex")
        if not chroma:
            raise RuntimeError("chroma-key.json is missing hex")
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "assemble_extended_atlas.py"),
                "--base-atlas",
                str(run_dir / "standard.png"),
                "--look-cells-dir",
                str(look_dir),
                "--output",
                str(run_dir / "extended-raw.png"),
                "--chroma-key",
                chroma,
                "--cell-margin",
                str(cell_margin),
            ],
            logs / "assemble-v2.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "despill_chroma_edges.py"),
                str(run_dir / "extended-raw.png"),
                "--output",
                str(run_dir / "spritesheet.png"),
                "--webp-output",
                str(run_dir / "spritesheet.webp"),
                "--json-out",
                str(qa_dir / "chroma-despill.json"),
                "--chroma-key",
                chroma,
            ],
            logs / "despill-v2.log",
        )
        run_logged(
            [
                python,
                str(skill_dir / "scripts" / "validate_atlas.py"),
                str(run_dir / "spritesheet.webp"),
                "--require-v2",
                "--chroma-key",
                chroma,
                "--json-out",
                str(qa_dir / "v2-validation.json"),
                "--min-alpha-margin",
                str(cell_margin if normalization == "safe-max" else 0),
            ],
            logs / "validate-v2.log",
        )
        return model_key, None

    if stage == "direction-evidence":
        run_dir = output / "run"
        qa_dir = run_dir / "qa"
        atlas = run_dir / "spritesheet.webp"
        evidence_commands = [
            (
                [
                    python,
                    str(skill_dir / "scripts" / "make_direction_qa_sheet.py"),
                    str(atlas),
                    "--output",
                    str(qa_dir / "directions-labeled.png"),
                ],
                logs / "directions-labeled.log",
            ),
            (
                [
                    python,
                    str(skill_dir / "scripts" / "make_direction_blind_qa_sheet.py"),
                    str(atlas),
                    "--output",
                    str(qa_dir / "directions-blind.png"),
                    "--answer-key",
                    str(qa_dir / "directions-blind-key.json"),
                ],
                logs / "directions-blind.log",
            ),
            (
                [
                    python,
                    str(skill_dir / "scripts" / "measure_direction_continuity.py"),
                    str(atlas),
                    "--json-out",
                    str(qa_dir / "direction-continuity.json"),
                ],
                logs / "direction-continuity.log",
            ),
            (
                [
                    python,
                    str(skill_dir / "scripts" / "make_contact_sheet.py"),
                    str(atlas),
                    "--output",
                    str(qa_dir / "contact-extended.png"),
                ],
                logs / "contact-v2.log",
            ),
        ]
        for command, log in evidence_commands:
            run_logged(command, log)
        return model_key, None

    raise RuntimeError(f"unsupported stage: {stage}")


def eligible(job: dict, stage: str, force: bool) -> bool:
    field = STAGE_FIELD[stage]
    if force:
        return bool(job.get("model_key"))
    if job.get(field) not in {"pending", "failed"}:
        return False
    if stage == "preview-render":
        return job.get("preflight") == "pass"
    if stage == "map":
        return job.get("preview_render") == "pass"
    if stage == "production-render":
        return job.get("mapping_qa") == "pass"
    if stage == "prepare":
        return job.get("production_render") == "pass"
    if stage == "standard":
        return job.get("frames_qa") == "pass"
    if stage == "look-probe":
        return job.get("mapping_qa") == "pass"
    if stage == "direction-render":
        return job.get("standard_qa") == "pass" and job.get("direction_qa") == "calibrated"
    if stage == "atlas":
        return job.get("direction_render") == "pass"
    if stage == "direction-evidence":
        return job.get("atlas_qa") == "pass"
    return bool(job.get("model_key"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one resumable stage for an Ark-Models pet batch.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--stage", choices=sorted(STAGE_FIELD), required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--runtime-dir")
    parser.add_argument("--node")
    parser.add_argument("--node-modules")
    parser.add_argument("--model-key", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--normalization",
        choices=["canvas", "safe-max", "state-fit"],
        default="safe-max",
        help="Frame normalization used by prepare/validation stages (default: safe-max).",
    )
    parser.add_argument(
        "--cell-margin",
        type=int,
        default=6,
        help="Minimum final-cell alpha margin for safe-max/look registration (default: 6).",
    )
    parser.add_argument(
        "--max-upscale",
        type=float,
        default=1.0,
        help="Maximum source-pixel upscale allowed during normalization (default: 1.0).",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    lock_name = hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16]
    lock_handle = (Path(tempfile.gettempdir()) / f"ark-pet-batch-{lock_name}.lock").open("a+")
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    csv_path = Path(args.csv).resolve() if args.csv else None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    for job in jobs:
        default_gate = "pending" if job.get("model_key") else "blocked"
        job.setdefault("standard_visual_qa", default_gate)
        job.setdefault("direction_probe", default_gate)
        job.setdefault("direction_render", default_gate)
        job.setdefault("direction_evidence_qa", default_gate)
        job.setdefault("package_qa", default_gate)
    selected_keys = set(args.model_key)
    selected = [
        job
        for job in jobs
        if eligible(job, args.stage, args.force)
        and (not selected_keys or job.get("model_key") in selected_keys)
    ]
    by_key = {job["model_key"]: job for job in jobs}
    field = STAGE_FIELD[args.stage]

    def persist() -> None:
        write_manifest(manifest_path, payload)
        if csv_path:
            write_csv(csv_path, jobs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_to_key = {
            executor.submit(
                execute_job,
                job,
                args.stage,
                Path(args.source_root).resolve(),
                Path(args.job_root).resolve(),
                Path(args.skill_dir).resolve(),
                Path(args.runtime_dir).resolve() if args.runtime_dir else None,
                args.node,
                args.node_modules,
                args.normalization,
                args.cell_margin,
                args.max_upscale,
            ): job["model_key"]
            for job in selected
        }
        for future in concurrent.futures.as_completed(future_to_key):
            model_key = future_to_key[future]
            job = by_key[model_key]
            try:
                future.result()
            except Exception as error:
                job[field] = "failed"
                job["status"] = "exception"
                job["stage"] = args.stage
                job["error"] = str(error)
                outcome = "failed"
            else:
                job[field] = "review" if args.stage in {"map", "direction-evidence"} else "pass"
                job["status"] = "in_progress"
                job["stage"] = {
                    "preflight": "preflighted",
                    "preview-render": "preview-rendered",
                    "map": "mapped",
                    "production-render": "production-rendered",
                    "prepare": "frames-prepared",
                    "standard": "standard-validated",
                    "look-probe": "look-probed",
                    "direction-render": "directions-rendered",
                    "atlas": "v2-validated",
                    "direction-evidence": "direction-review",
                }[args.stage]
                job["error"] = ""
                outcome = job[field]
            persist()
            print(json.dumps({"model_key": model_key, "stage": args.stage, "outcome": outcome}, ensure_ascii=False), flush=True)

    failed = sum(job.get(field) == "failed" for job in jobs)
    passed = sum(job.get(field) in {"pass", "review"} for job in jobs)
    print(json.dumps({"stage": args.stage, "selected": len(selected), "passed": passed, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
