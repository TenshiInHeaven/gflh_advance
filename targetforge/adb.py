"""安卓模拟器 ADB 辅助：自动检测 MuMu / 雷电 / 夜神 / BlueStacks，装 CA、设代理、重启游戏。

所有命令都在本机执行；ADB 路径/串口可以手动覆盖，不绑定某个品牌。
"""
from __future__ import annotations

import glob
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from targetforge.datapaths import DATA_DIR

ADB_CANDIDATES = [
    r"C:\Program Files\Netease\MuMu\nx_device\*\shell\adb.exe",
    r"D:\Program Files\Netease\MuMu\nx_device\*\shell\adb.exe",
    r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    r"D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    r"C:\LDPlayer\LDPlayer*\adb.exe",
    r"D:\LDPlayer\LDPlayer*\adb.exe",
    r"C:\Program Files\Nox\bin\nox_adb.exe",
    r"D:\Program Files\Nox\bin\nox_adb.exe",
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\BlueStacks\HD-Adb.exe",
    r"D:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"adb.exe",
]


def _run(exe: str, args: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _path_has_exe(path: str) -> bool:
    if path.lower() == "adb.exe":
        return True
    return Path(path).is_file()


def detect() -> dict[str, Any]:
    """扫描常见模拟器 ADB；返回候选、设备列表和默认选择。"""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in ADB_CANDIDATES:
        matches = glob.glob(pattern) if any(ch in pattern for ch in "*?") else [pattern]
        for raw in matches:
            exe = str(Path(raw))
            key = exe.lower()
            if key in seen or not _path_has_exe(exe):
                continue
            seen.add(key)
            item: dict[str, Any] = {"path": exe, "name": _brand_name(exe), "devices": []}
            try:
                out = _run(exe, ["devices", "-l"], timeout=8).stdout
                for line in out.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        item["devices"].append({"serial": parts[0], "model": " ".join(parts[2:])})
                if not item["devices"]:
                    for port in (7555, 5555, 16384, 62001, 21503):
                        serial = f"127.0.0.1:{port}"
                        try:
                            _run(exe, ["connect", serial], timeout=4)
                        except Exception:
                            pass
                    out = _run(exe, ["devices"], timeout=6).stdout
                    for line in out.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == "device":
                            item["devices"].append({"serial": parts[0], "model": ""})
            except (OSError, subprocess.SubprocessError):
                pass
            found.append(item)
    default = next((item for item in found if item["devices"]), found[0] if found else None)
    return {
        "candidates": found,
        "default": default,
        "default_serial": ((default or {}).get("devices") or [{}])[0].get("serial", ""),
    }


def _brand_name(exe: str) -> str:
    low = exe.lower()
    if "mumu" in low:
        return "MuMu"
    if "ldplayer" in low or "ld" in Path(exe).parts[0].lower():
        return "LDPlayer"
    if "nox" in low:
        return "Nox"
    if "bluestacks" in low:
        return "BlueStacks"
    return "ADB"


def _check_device(exe: str, serial: str) -> dict:
    if not Path(exe).is_file() and exe.lower() != "adb.exe":
        return {"ok": False, "error": f"ADB 不存在：{exe}"}
    try:
        out = _run(exe, ["-s", serial, "shell", "getprop", "ro.product.model"], timeout=8)
        if out.returncode != 0:
            return {"ok": False, "error": (out.stderr or out.stdout or "ADB 设备不可用").strip()[:300]}
        return {"ok": True, "model": out.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def _ca_android_name(ca_cert: Path) -> str:
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    digest = hashlib.md5(cert.subject.public_bytes()).digest()
    value = int.from_bytes(digest[:4], "little")
    return f"{value:08x}.0"


def install_ca(exe: str, serial: str, ca_cert: Path) -> dict:
    """把 CA 装进 /system/etc/security/cacerts（bind mount 副本，需 root）。"""
    if not ca_cert.is_file():
        return {"ok": False, "error": f"CA 不存在：{ca_cert}"}
    name = _ca_android_name(ca_cert)
    pem = ca_cert.read_bytes()
    cmds = [
        ["root"],
        ["wait-for-device"],
        # 若之前已经 bind mount 过，先卸载，避免把空的挂载目录当成原始证书目录
        ["shell", "umount /system/etc/security/cacerts >/dev/null 2>&1 || true"],
        ["shell", "rm -rf /data/local/tmp/cacerts; cp -a /system/etc/security/cacerts /data/local/tmp/cacerts"],
        ["push", str(ca_cert), f"/data/local/tmp/cacerts/{name}"],
        ["shell", f"chmod 644 /data/local/tmp/cacerts/{name}; chown root:root /data/local/tmp/cacerts/{name}; "
                  f"chcon u:object_r:system_security_cacerts_file:s0 /data/local/tmp/cacerts/{name}"],
        ["shell", "mount -o bind /data/local/tmp/cacerts /system/etc/security/cacerts"],
        ["shell", f"ls /system/etc/security/cacerts/{name}"],
    ]
    output = []
    for args in cmds:
        try:
            r = _run(exe, ["-s", serial, *args], timeout=40)
            output.append((r.stdout or r.stderr or "").strip()[:200])
            if r.returncode != 0 and args[0] == "shell" and "mount" not in " ".join(args):
                # 某些模拟器 root 已开时 `adb root` 返回非 0，不直接失败；继续尝试
                pass
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": str(exc), "output": output}
    return {"ok": True, "name": name, "output": output}


def set_proxy(exe: str, serial: str, host: str = "127.0.0.1", port: int = 8084) -> dict:
    try:
        r = _run(exe, ["-s", serial, "shell", "settings", "put", "global", "http_proxy",
                       f"{host}:{port}"], timeout=10)
        return {"ok": r.returncode == 0, "value": f"{host}:{port}",
                "error": (r.stderr or "").strip()[:200]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def clear_proxy(exe: str, serial: str) -> dict:
    try:
        r = _run(exe, ["-s", serial, "shell", "settings", "put", "global", "http_proxy", ":0"], timeout=10)
        return {"ok": r.returncode == 0, "error": (r.stderr or "").strip()[:200]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def reverse(exe: str, serial: str, port: int = 8084) -> dict:
    try:
        r = _run(exe, ["-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"], timeout=10)
        return {"ok": r.returncode == 0, "error": (r.stderr or "").strip()[:200]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def restart_game(exe: str, serial: str, package: str) -> dict:
    if not package:
        return {"ok": False, "error": "缺少游戏包名"}
    try:
        _run(exe, ["-s", serial, "shell", "am", "force-stop", package], timeout=15)
        r = _run(exe, ["-s", serial, "shell", "monkey", "-p", package, "-c",
                       "android.intent.category.LAUNCHER", "1"], timeout=20)
        return {"ok": r.returncode == 0, "package": package,
                "error": (r.stderr or "").strip()[:300]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def setup(exe: str, serial: str, ca_cert: Path, package: str,
          port: int = 8084, listen_host: str = "127.0.0.1") -> dict:
    """一键：反代 → 装 CA → 设代理 → 重启游戏。"""
    device = _check_device(exe, serial)
    if not device.get("ok"):
        return {"ok": False, "error": device.get("error")}
    results = {"device": device, "reverse": reverse(exe, serial, port),
               "ca": install_ca(exe, serial, ca_cert),
               "proxy": set_proxy(exe, serial, "127.0.0.1", port)}
    if package:
        results["restart"] = restart_game(exe, serial, package)
    results["ok"] = all(result.get("ok") for key, result in results.items()
                        if key in ("reverse", "ca", "proxy"))
    return results
