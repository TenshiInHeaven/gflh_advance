from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from targetforge import gflh, sysproxy


class SysProxyTests(unittest.TestCase):
    def test_restore_recreates_original_proxy_server_and_deletes_absent_values(self) -> None:
        fake_key = object()
        snapshot = {
            "ProxyEnable": 1,
            "ProxyServer": "127.0.0.1:17897",
            "ProxyOverride": "localhost;127.*",
            "AutoConfigURL": None,
        }
        with mock.patch.object(sysproxy.winreg, "OpenKey", return_value=fake_key), \
             mock.patch.object(sysproxy.winreg, "CloseKey") as close, \
             mock.patch.object(sysproxy.winreg, "SetValueEx") as set_value, \
             mock.patch.object(sysproxy.winreg, "DeleteValue") as delete_value:
            self.assertTrue(sysproxy.restore(snapshot))
            close.assert_called_once()
            set_value.assert_has_calls([
                mock.call(fake_key, "ProxyEnable", 0, sysproxy.winreg.REG_DWORD, 1),
                mock.call(fake_key, "ProxyServer", 0, sysproxy.winreg.REG_SZ, "127.0.0.1:17897"),
                mock.call(fake_key, "ProxyOverride", 0, sysproxy.winreg.REG_SZ, "localhost;127.*"),
            ])
            delete_value.assert_called_once_with(fake_key, "AutoConfigURL")

    def test_restore_without_backup_does_not_touch_proxy(self) -> None:
        with mock.patch.object(gflh, "_PROXY_BACKUP", None), \
             mock.patch.object(gflh, "_call_set_windows_proxy") as set_proxy:
            self.assertFalse(gflh._restore_system_proxy())
            set_proxy.assert_not_called()

    def test_restore_uses_saved_backup(self) -> None:
        backup = {"ProxyEnable": 1, "ProxyServer": "127.0.0.1:17897",
                  "ProxyOverride": "", "AutoConfigURL": None}
        with mock.patch.object(gflh, "_PROXY_BACKUP", backup), \
             mock.patch.object(gflh.sysproxy, "restore", return_value=True) as restore:
            self.assertTrue(gflh._restore_system_proxy())
            restore.assert_called_once_with(backup)
            self.assertIsNone(gflh._PROXY_BACKUP)


if __name__ == "__main__":
    unittest.main()
