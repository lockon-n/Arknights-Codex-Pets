from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_frames.py"
SPEC = importlib.util.spec_from_file_location("prepare_frames_rerun", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PREPARE_FRAMES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE_FRAMES)


class PrepareFrameRerunTest(unittest.TestCase):
    def test_removes_only_prior_generated_png_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            (state_dir / "00.png").write_bytes(b"old")
            (state_dir / "07.png").write_bytes(b"stale")
            (state_dir / "review.json").write_text("keep\n", encoding="utf-8")

            PREPARE_FRAMES.clear_generated_state_frames(state_dir)

            self.assertFalse((state_dir / "00.png").exists())
            self.assertFalse((state_dir / "07.png").exists())
            self.assertEqual(
                (state_dir / "review.json").read_text(encoding="utf-8"),
                "keep\n",
            )


if __name__ == "__main__":
    unittest.main()
