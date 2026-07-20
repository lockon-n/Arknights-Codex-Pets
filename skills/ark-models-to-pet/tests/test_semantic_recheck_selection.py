from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge_batch_cardinal_semantic_recheck.py"
FIELDS = ("horizontal_A", "horizontal_B", "vertical_A", "vertical_B")


class SemanticRecheckSelectionTest(unittest.TestCase):
    def test_merges_selected_pass_while_ignoring_unselected_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_values = {
                "horizontal_A": "screen-left",
                "horizontal_B": "screen-right",
                "vertical_A": "up",
                "vertical_B": "down",
            }
            recheck_values = {
                "horizontal_A": "screen-right",
                "horizontal_B": "screen-left",
                "vertical_A": "down",
                "vertical_B": "up",
            }
            base = root / "base.json"
            base_key = root / "base-key.json"
            recheck = root / "recheck.json"
            recheck_key = root / "recheck-key.json"
            output = root / "output.json"
            base.write_text(
                json.dumps({"jobs": [{"model_key": key, **base_values} for key in ("pass", "fail")]}),
                encoding="utf-8",
            )
            base_key.write_text(base.read_text(encoding="utf-8"), encoding="utf-8")
            recheck.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {"model_key": "pass", **recheck_values},
                            {"model_key": "fail", **{field: "ambiguous" for field in FIELDS}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            recheck_key.write_text(
                json.dumps({"jobs": [{"model_key": key, **recheck_values} for key in ("pass", "fail")]}),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base",
                    str(base),
                    "--base-answer-key",
                    str(base_key),
                    "--recheck",
                    str(recheck),
                    "--recheck-answer-key",
                    str(recheck_key),
                    "--model-key",
                    "pass",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads(output.read_text(encoding="utf-8"))
            by_key = {job["model_key"]: job for job in result["jobs"]}
            self.assertIn("semantic_recheck", by_key["pass"])
            self.assertNotIn("semantic_recheck", by_key["fail"])
            self.assertEqual(result["semantic_rechecked_model_keys"], ["pass"])


if __name__ == "__main__":
    unittest.main()
