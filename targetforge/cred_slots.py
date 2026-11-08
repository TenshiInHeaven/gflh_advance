"""按区服/客户端类别保存「最新一份」登录凭证。

sign 每次重新登录都会变，旧 sign 没有复用价值；因此每个类别只保留一个
`creds_profile_*.json`，新抓包直接覆盖。真正的靶机批次历史由 target_history 负责。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from targetforge.datapaths import DATA_DIR
from targetforge import creds_store

CATEGORIES: dict[str, dict[str, str]] = {
    "cn_pc": {"title": "国服 PC", "file": "creds_profile_cn_pc.json"},
    "cn_revival": {"title": "国服复活版（安卓）", "file": "creds_profile_cn_revival.json"},
    "tw": {"title": "台服 TW", "file": "creds_profile_tw.json"},
    "jp": {"title": "日服 JP", "file": "creds_profile_jp.json"},
    "custom": {"title": "自定义区服", "file": "creds_profile_custom.json"},
}
REGION_TO_CATEGORY = {
    "cn": "cn_pc",
    "cn_pc": "cn_pc",
    "cn_revival": "cn_revival",
    "tw": "tw",
    "taiwan": "tw",
    "jp": "jp",
    "japan": "jp",
    "custom": "custom",
}


def category_for_region(region: str | None) -> str:
    key = str(region or "").strip().lower()
    return REGION_TO_CATEGORY.get(key, "custom")


def slot_path(category: str) -> Path:
    item = CATEGORIES.get(category) or CATEGORIES["custom"]
    return Path(DATA_DIR) / item["file"]


def write_slot(region: str | None, payload: dict[str, Any]) -> Path:
    category = category_for_region(region or payload.get("region"))
    payload = dict(payload)
    payload["region"] = category_for_region(category)
    return creds_store.write_creds(slot_path(category), payload)


def read_slot(category: str) -> dict[str, Any] | None:
    path = slot_path(category)
    return creds_store.read_creds(path) if path.is_file() else None


def list_slots() -> list[dict[str, Any]]:
    """返回每个类别的最新凭证摘要；不存在该类别的文件则跳过。"""
    out: list[dict[str, Any]] = []
    for category, meta in CATEGORIES.items():
        path = Path(DATA_DIR) / meta["file"]
        if not path.is_file():
            continue
        payload = creds_store.read_creds(path)
        if payload is None:
            continue
        enemies = payload.get("enemies") if isinstance(payload.get("enemies"), list) else []
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        out.append({
            "name": path.name,
            "path": str(path),
            "category": category,
            "title": meta["title"],
            "uid": payload.get("uid"),
            "base_url": payload.get("base_url"),
            "targets_count": len(enemies),
            "updated_at": payload.get("captured_at"),
            "mtime": mtime,
        })
    return out
