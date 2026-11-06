from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from targetforge import creds_store


class CredsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "creds_latest.json"
        self.payload = {"uid": "123456", "sign": "SECRET-SIGN", "enemies": [1, 2], "orders": [1, 2]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_plaintext_legacy_is_readable(self):
        self.path.write_text(json.dumps(self.payload), encoding="utf-8")
        self.assertEqual(creds_store.read_creds(self.path)["sign"], "SECRET-SIGN")

    @unittest.skipUnless(os.name == "nt", "DPAPI 仅 Windows")
    def test_dpapi_roundtrip_and_no_plaintext(self):
        if not creds_store.dpapi_available():
            self.skipTest("本机 DPAPI 不可用")
        creds_store.write_creds(self.path, self.payload)
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("SECRET-SIGN", raw)
        self.assertNotIn("123456", raw)
        self.assertTrue(creds_store.is_encrypted(self.path))
        self.assertEqual(creds_store.read_creds(self.path), self.payload)

    def test_corrupt_or_wrong_marker_returns_none(self):
        self.path.write_text('{"dpapi":"v1","data":"not-base64"}', encoding="utf-8")
        self.assertIsNone(creds_store.read_creds(self.path))
        self.path.write_text("not-json", encoding="utf-8")
        self.assertIsNone(creds_store.read_creds(self.path))


if __name__ == "__main__":
    unittest.main()
