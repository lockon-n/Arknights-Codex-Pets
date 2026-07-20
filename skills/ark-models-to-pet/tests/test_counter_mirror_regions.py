from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_frames.py"
SPEC = importlib.util.spec_from_file_location("prepare_frames", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PREPARE_FRAMES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE_FRAMES)


class CounterMirrorRegionsTest(unittest.TestCase):
    def test_flips_only_the_requested_final_cell_region(self) -> None:
        image = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        image.putpixel((10, 10), (255, 0, 0, 255))
        image.putpixel((11, 10), (0, 0, 255, 255))
        image.putpixel((12, 10), (0, 255, 0, 255))

        result = PREPARE_FRAMES.apply_counter_mirror_regions(
            image,
            "running-left",
            {"mirror": True, "counter_mirror_regions": [[10, 10, 12, 11]]},
        )

        self.assertEqual(result.getpixel((10, 10)), (0, 0, 255, 255))
        self.assertEqual(result.getpixel((11, 10)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((12, 10)), (0, 255, 0, 255))

    def test_rejects_region_without_whole_frame_mirror(self) -> None:
        image = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        with self.assertRaisesRegex(RuntimeError, "requires mirror=true"):
            PREPARE_FRAMES.apply_counter_mirror_regions(
                image,
                "idle",
                {"counter_mirror_regions": [[10, 10, 12, 11]]},
            )


if __name__ == "__main__":
    unittest.main()
