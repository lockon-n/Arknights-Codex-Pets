from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_cardinal_axis_repairs.py"


class CardinalAxisRepairSkipTest(unittest.TestCase):
    def test_repairs_inverse_job_and_records_ambiguous_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_root = root / "jobs"
            for pet_id in ("inverse-pet", "ambiguous-pet"):
                pet_dir = jobs_root / pet_id
                pet_dir.mkdir(parents=True)
                (pet_dir / "look-config.json").write_text(
                    json.dumps(
                        {
                            "eye_x_right": 3,
                            "eye_y_right": 0,
                            "head_x_right": 0,
                            "head_y_right": -2,
                            "head_rotation_right": -4,
                            "eye_x_up": 0,
                            "eye_y_up": 3,
                            "head_x_up": 2,
                            "head_y_up": 0,
                            "head_rotation_up": 0,
                        }
                    ),
                    encoding="utf-8",
                )

            manifest = root / "batch-manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {"model_key": "inverse", "pet_id": "inverse-pet"},
                            {"model_key": "ambiguous", "pet_id": "ambiguous-pet"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            validation = root / "validation.json"
            validation.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "model_key": "inverse",
                                "cells": {
                                    "horizontal_A": {"observed": "screen-left", "expected": "screen-right", "pass": False},
                                    "horizontal_B": {"observed": "screen-right", "expected": "screen-left", "pass": False},
                                    "vertical_A": {"observed": "up", "expected": "up", "pass": True},
                                    "vertical_B": {"observed": "down", "expected": "down", "pass": True},
                                },
                            },
                            {
                                "model_key": "ambiguous",
                                "cells": {
                                    "horizontal_A": {"observed": "ambiguous", "expected": "screen-right", "pass": False},
                                    "horizontal_B": {"observed": "ambiguous", "expected": "screen-left", "pass": False},
                                    "vertical_A": {"observed": "up", "expected": "up", "pass": True},
                                    "vertical_B": {"observed": "down", "expected": "down", "pass": True},
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            repair_log = root / "repair-log.json"

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--manifest",
                    str(manifest),
                    "--validation",
                    str(validation),
                    "--job-root",
                    str(jobs_root),
                    "--repair-log",
                    str(repair_log),
                    "--skip-unsupported",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            inverse = json.loads((jobs_root / "inverse-pet" / "look-config.json").read_text())
            ambiguous = json.loads((jobs_root / "ambiguous-pet" / "look-config.json").read_text())
            log = json.loads(repair_log.read_text())
            self.assertEqual(inverse["eye_x_right"], -3)
            self.assertEqual(inverse["head_y_right"], 2)
            self.assertEqual(ambiguous["eye_x_right"], 3)
            self.assertEqual(log["jobs"][0]["model_key"], "inverse")
            self.assertEqual(log["skipped"][0]["model_key"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
