from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from targetforge import bridge_addon, datapaths, local_bridge


class BridgePathTests(unittest.TestCase):
    def test_bridge_addon_data_dir_matches_runtime_data_dir(self) -> None:
        self.assertEqual(bridge_addon.DATA_DIR.resolve(), Path(datapaths.DATA_DIR).resolve())

    def test_bridge_addon_targets_file_matches_runtime_targets_file(self) -> None:
        self.assertEqual(
            bridge_addon.TARGETS_FILE,
            Path(datapaths.DATA_DIR) / "inject_targets.json",
        )

    def test_bridge_addon_honors_data_dir_override(self) -> None:
        with mock.patch.dict(os.environ, {"TARGETFORGE_DATA_DIR": r"C:\tmp\tf-data"}):
            self.assertEqual(bridge_addon._resolve_data_dir(), Path(r"C:\tmp\tf-data"))

    def test_empty_targets_do_not_silently_fall_back_to_test_boss(self) -> None:
        with mock.patch.object(local_bridge, "TARGETS_FILE", Path(self.id()) / "inject_targets.json"):
            self.assertEqual(local_bridge.set_targets([]), [])
            self.assertEqual(local_bridge._targets(), [])


if __name__ == "__main__":
    unittest.main()
