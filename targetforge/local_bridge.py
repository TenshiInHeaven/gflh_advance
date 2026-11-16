"""本地靶机桥接（实验）：只改客户端 Index 响应，不写服务器。

支持：
* pc：Windows 系统代理 + PC 客户端；
* emulator：mitmproxy + adb reverse + 模拟器全局 http_proxy。

安全边界：只追加 targettrain 收藏条目，不调用 addCollect，不持久化服务器数据；
停止桥接时恢复代理/模拟器网络并重启客户端。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from targetforge.datapaths import DATA_DIR

BRIDGE_DIR = Path(DATA_DIR)
ADDON = Path(__file__).with_name("bridge_addon.py")
PID_FILE = BRIDGE_DIR / "bridge_proxy.pid"
BACKUP_FILE = BRIDGE_DIR / "bridge_proxy_backup.json"
TARGETS_FILE = BRIDGE_DIR / "inject_targets.json"
MODE_FILE = BRIDGE_DIR / "inject_mode.txt"
LOG_FILE = BRIDGE_DIR / "inject_proxy.log"
STDOUT_FILE = BRIDGE_DIR / "bridge_stdout.log"
DEFAULT_PORT = 18080
DEFAULT_TARGETS = [7301601]
DEFAULT_PACKAGE = "com.sunborn.girlsfrontline.pt"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _targets() -> list[int]:
    raw = _read_json(TARGETS_FILE, [])
    if isinstance(raw, dict):
        raw = raw.get("targets") or []
    out: list[int] = []
    if isinstance(raw, list):
        for item in raw:
            try:
                tid = int(item)
            except (TypeError, ValueError):
                continue
            if tid > 0 and tid not in out:
                out.append(tid)
    return out[:35]


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def _read_windows_proxy() -> dict:
    import winreg

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
    try:
        out = {}
        for name, default in (("ProxyEnable", 0), ("ProxyServer", ""), ("ProxyOverride", "")):
            try:
                out[name] = winreg.QueryValueEx(key, name)[0]
            except OSError:
                out[name] = default
        return out
    finally:
        winreg.CloseKey(key)


def _write_windows_proxy(values: dict) -> None:
    import winreg

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                         0, winreg.KEY_SET_VALUE)
    try:
        for name, value in values.items():
            if value is None:
                continue
            kind = winreg.REG_DWORD if name == "ProxyEnable" else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, kind, value)
    finally:
        winreg.CloseKey(key)
    try:
        import ctypes
        ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass


def _set_windows_proxy(port: int) -> None:
    import gflzirc
    gflzirc.set_windows_proxy(True, f"127.0.0.1:{port}")


def _restore_windows_proxy(values: dict) -> None:
    if isinstance(values, dict):
        _write_windows_proxy(values)
    else:
        try:
            import gflzirc
            gflzirc.set_windows_proxy(False)
        except Exception:
            pass


def _detect_emulator() -> dict:
    from targetforge import adb
    detected = adb.detect()
    default = detected.get("default") or {}
    path = str(default.get("path") or "")
    serial = str(detected.get("default_serial") or "")
    return {"path": path, "serial": serial}


def _tail(path: Path, lines: int = 80) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def status() -> dict:
    pid = _read_json(PID_FILE, 0)
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = 0
    backup = _read_json(BACKUP_FILE, {}) or {}
    return {
        "state": "running" if pid and _pid_alive(pid) else ("stale" if pid else "idle"),
        "pid": pid,
        "port": int(backup.get("port") or DEFAULT_PORT),
        "mode": str(backup.get("mode") or "inject"),
        "client": str(backup.get("client") or "pc"),
        "targets": _targets(),
        "log": _tail(LOG_FILE, 100),
        "package": str(backup.get("package") or DEFAULT_PACKAGE),
        "adb_path": str(backup.get("adb_path") or ""),
        "serial": str(backup.get("serial") or ""),
    }


def set_targets(targets: list[int]) -> list[int]:
    clean: list[int] = []
    for item in targets or []:
        try:
            tid = int(item)
        except (TypeError, ValueError):
            continue
        if tid > 0 and tid not in clean:
            clean.append(tid)
    if not clean:
        clean = list(DEFAULT_TARGETS)
    if len(clean) > 35:
        raise ValueError("桥接目标最多 35 个")
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FILE.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
    return clean


def _start_mitm(port: int) -> subprocess.Popen:
    runner = "from mitmproxy.tools.main import mitmdump\nmitmdump()\n"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    stdout = STDOUT_FILE.open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-c", runner, "-s", str(ADDON), "-p", str(port),
         "--set", "block_global=false", "--ignore-hosts", ".*:443"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=stdout, stderr=subprocess.STDOUT, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _wait_port(port: int) -> None:
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("mitmproxy 未能在端口启动")


def start(targets: list[int] | None = None, mode: str = "inject",
          port: int = DEFAULT_PORT, restart_game: bool = True,
          client: str = "pc", adb_path: str = "", serial: str = "",
          package: str = DEFAULT_PACKAGE) -> dict:
    current = status()
    if current["state"] == "running":
        stop(restart_game=False)
    if targets is not None:
        set_targets(targets)
    mode = "inject" if str(mode).lower() == "inject" else "roundtrip"
    client = "emulator" if str(client).lower() == "emulator" else "pc"
    package = str(package or DEFAULT_PACKAGE).strip()
    MODE_FILE.write_text(mode, encoding="utf-8")

    emu = {"path": str(adb_path or ""), "serial": str(serial or "")}
    if client == "emulator":
        if not emu["path"] or not emu["serial"]:
            detected = _detect_emulator()
            emu["path"] = emu["path"] or detected["path"]
            emu["serial"] = emu["serial"] or detected["serial"]
        if not emu["path"] or not emu["serial"]:
            raise RuntimeError("未检测到 ADB 或模拟器设备")

    backup = {
        "client": client,
        "port": int(port),
        "mode": mode,
        "package": package,
        "adb_path": emu["path"],
        "serial": emu["serial"],
        "windows": _read_windows_proxy() if client == "pc" else None,
        "emulator_proxy": None,
    }
    if client == "emulator":
        from targetforge import adb
        backup["emulator_proxy"] = adb.get_proxy(emu["path"], emu["serial"]).get("value", "")
    BACKUP_FILE.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    LOG_FILE.write_text("", encoding="utf-8")
    STDOUT_FILE.write_text("", encoding="utf-8")

    proc = _start_mitm(int(port))
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    try:
        _wait_port(int(port))
        if client == "pc":
            _set_windows_proxy(int(port))
            if restart_game:
                from targetforge import gflh
                result = gflh.restart_game(wait_ready=True)
                if result.get("error"):
                    raise RuntimeError(str(result["error"]))
        else:
            from targetforge import adb
            reversed_ = adb.reverse(emu["path"], emu["serial"], int(port))
            proxied = adb.set_proxy(emu["path"], emu["serial"], "127.0.0.1", int(port))
            if not reversed_.get("ok") or not proxied.get("ok"):
                raise RuntimeError(reversed_.get("error") or proxied.get("error") or "模拟器代理设置失败")
            if restart_game and package:
                adb.restart_game(emu["path"], emu["serial"], package)
        return status()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        _cleanup(backup)
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        raise


def _cleanup(backup: dict) -> None:
    client = str(backup.get("client") or "pc")
    if client == "emulator":
        try:
            from targetforge import adb
            path = str(backup.get("adb_path") or "")
            serial = str(backup.get("serial") or "")
            port = int(backup.get("port") or DEFAULT_PORT)
            if path and serial:
                previous = str(backup.get("emulator_proxy") or "")
                if previous and previous not in (":0", "null", "None"):
                    # 恢复原有代理值（若原本不是当前桥接值）
                    adb.set_proxy(path, serial, *previous.rsplit(":", 1))
                else:
                    adb.clear_proxy(path, serial)
                adb.remove_reverse(path, serial, port)
        except Exception:
            pass
    else:
        _restore_windows_proxy(backup.get("windows"))


def stop(restart_game: bool = True) -> dict:
    backup = _read_json(BACKUP_FILE, {}) or {}
    pid = _read_json(PID_FILE, 0)
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = 0
    if pid and _pid_alive(pid):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    _cleanup(backup)
    try:
        BACKUP_FILE.unlink()
    except OSError:
        pass
    if restart_game:
        try:
            if str(backup.get("client") or "pc") == "emulator":
                from targetforge import adb
                path = str(backup.get("adb_path") or "")
                serial = str(backup.get("serial") or "")
                package = str(backup.get("package") or DEFAULT_PACKAGE)
                if path and serial and package:
                    adb.restart_game(path, serial, package)
            else:
                from targetforge import gflh
                gflh.restart_game(wait_ready=True)
        except Exception:
            pass
    return status()
