"""区服配置：国服 / 台服 / 日服 / 自定义。

抓包本身自动从流量里识别 ``base_url``；这里的 ``base_url`` 只是已知区服的提示/兜底，
注入时仍以抓到的 base_url 为准。
"""
from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "cn": {
        "id": "cn",
        "title": "国服",
        "short": "CN",
        "capture_mode": "pc",
        "base_url": "",
        "package": "",
        "notes": "Steam / PC 客户端；沿用现有系统代理 + GFLProxy 抓包。",
    },
    "tw": {
        "id": "tw",
        "title": "台服",
        "short": "TW",
        "capture_mode": "emulator",
        "base_url": "https://sn-game.txwy.tw/index.php/1001/",
        "package": "tw.txwy.and.snqx",
        "notes": "安卓模拟器（MuMu 等）；HTTPS MITM + CA，抓包自动识别 base_url。",
    },
    "jp": {
        "id": "jp",
        "title": "日服",
        "short": "JP",
        "capture_mode": "emulator",
        "base_url": "",
        "package": "",
        "notes": "安卓模拟器；服务端域名由抓包自动识别，首次需要装 CA。",
    },
    "custom": {
        "id": "custom",
        "title": "自定义区服",
        "short": "CUSTOM",
        "capture_mode": "emulator",
        "base_url": "",
        "package": "",
        "notes": "其它区服/私有端；base_url 以抓到的流量为准。",
    },
}


def list_regions() -> list[dict[str, Any]]:
    return [dict(value) for value in PROFILES.values()]


def get_region(region: str) -> dict[str, Any]:
    key = str(region or "cn").strip().lower()
    return dict(PROFILES.get(key, PROFILES["cn"]))
