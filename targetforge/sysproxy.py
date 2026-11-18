"""Windows 系统代理快照/还原。

gflzirc.set_windows_proxy(False) 只把 ProxyEnable 置 0，不会恢复原来的
ProxyServer；如果用户原本挂着 Dove/Clash 等代理，关闭后原地址就丢了。
本模块负责在 TargetForge 改代理之前保存注册表原值，并在停止时精确还原。
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - 非 Windows 环境只用于导入/单测
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
PROXY_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


def _notify() -> None:
    try:
        import ctypes

        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:
        pass


def snapshot() -> dict[str, Any] | None:
    """读取当前 Internet Settings 的关键代理值；值不存在时记为 None。"""
    if winreg is None:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS)
    except OSError:
        return None
    try:
        values: dict[str, Any] = {}
        for name in PROXY_VALUES:
            try:
                values[name] = winreg.QueryValueEx(key, name)[0]
            except OSError:
                values[name] = None
        return values
    finally:
        winreg.CloseKey(key)


def restore(values: dict[str, Any] | None) -> bool:
    """把注册表精确还原到 snapshot() 的状态（包括原本不存在的值）。"""
    if winreg is None or not isinstance(values, dict):
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
        )
    except OSError:
        return False
    try:
        for name in PROXY_VALUES:
            value = values.get(name)
            if value is None:
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
                continue
            kind = winreg.REG_DWORD if name == "ProxyEnable" else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, kind, value)
    except OSError:
        return False
    finally:
        winreg.CloseKey(key)
    _notify()
    return True


def describe(values: dict[str, Any] | None) -> str:
    if not isinstance(values, dict):
        return "unknown"
    enabled = values.get("ProxyEnable")
    server = values.get("ProxyServer")
    return f"ProxyEnable={enabled} ProxyServer={server or '—'}"
