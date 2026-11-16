"""本地靶机桥接（实验）：只改客户端 Index 响应，不写服务器。

安全边界：
* 只修改 ``Index/index`` 的 ``targettrain_collect_user_info``；
* 保留服务器真实收藏，仅追加本地临时目标；
* 不调用 addCollect，不持久化服务器数据；
* 停止桥接时恢复系统代理并重启游戏，注入条目随客户端内存消失。
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


def _state() -> dict:
    return {
        "state": "idle",
        "pid": 0,
        "port": DEFAULT_PORT,
        "mode": "inject",
        "targets": [],
        "log": "",
    }


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


def _read_proxy() -> dict:
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


def _write_proxy(values: dict) -> None:
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
        ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:
        pass


def _set_proxy(port: int) -> None:
    import gflzirc

    gflzirc.set_windows_proxy(True, f"127.0.0.1:{port}")


def _restore_proxy() -> None:
    backup = _read_json(BACKUP_FILE, None)
    if isinstance(backup, dict):
        _write_proxy(backup)
        try:
            BACKUP_FILE.unlink()
        except OSError:
            pass
        return
    try:
        import gflzirc
        gflzirc.set_windows_proxy(False)
    except Exception:
        pass


def _tail(text: str, lines: int = 80) -> str:
    try:
        return "\n".join(Path(text).read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def status() -> dict:
    state = _state()
    pid = _read_json(PID_FILE, 0)
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = 0
    state["pid"] = pid
    state["targets"] = _targets()
    state["mode"] = (_read_json(MODE_FILE, "inject") or "inject")
    if pid and _pid_alive(pid):
        state["state"] = "running"
    elif pid:
        state["state"] = "stale"
    state["log"] = _tail(LOG_FILE, 100)
    return state


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


def start(targets: list[int] | None = None, mode: str = "inject",
          port: int = DEFAULT_PORT, restart_game: bool = True) -> dict:
    current = status()
    if current["state"] == "running":
        stop(restart_game=False)
    if targets is not None:
        set_targets(targets)
    mode = "inject" if str(mode).lower() == "inject" else "roundtrip"
    MODE_FILE.write_text(mode, encoding="utf-8")
    PORT = int(port)
    try:
        PORT_FILE = BRIDGE_DIR / "bridge_port.txt"
        PORT_FILE.write_text(str(PORT), encoding="utf-8")
    except OSError:
        pass

    previous = _read_proxy()
    BACKUP_FILE.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    LOG_FILE.write_text("", encoding="utf-8")
    STDOUT_FILE.write_text("", encoding="utf-8")

    runner = (
        "from mitmproxy.tools.main import mitmdump\n"
        "mitmdump()\n"
    )
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    stdout = STDOUT_FILE.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-c", runner, "-s", str(ADDON), "-p", str(PORT),
         "--set", "block_global=false", "--ignore-hosts", ".*:443"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=stdout, stderr=subprocess.STDOUT, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    try:
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("mitmproxy 未能在端口启动")
        _set_proxy(PORT)
        if restart_game:
            from targetforge import gflh
            result = gflh.restart_game(wait_ready=True)
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
        return status()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        _restore_proxy()
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        raise


def stop(restart_game: bool = True) -> dict:
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
    _restore_proxy()
    if restart_game:
        try:
            from targetforge import gflh
            gflh.restart_game(wait_ready=True)
        except Exception:
            pass
    return status()
