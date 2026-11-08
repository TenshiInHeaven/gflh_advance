"""历史靶机配置：把当前收藏标靶保存为带时间戳的存档。

只存靶机配置（order/team + uid/base_url/region），**不存 sign**；
历史存档用于回看/一键加入当前序列，不用于登录或注入凭证加载。
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from targetforge.datapaths import DATA_DIR

HISTORY_DIR = Path(DATA_DIR) / "target_history"
_NAME_RE = re.compile(r"^targets_\d{8}_\d{6}(?:_\d+)?\.json$")
_LOCK = threading.Lock()


def _ensure_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now().astimezone()


def _safe_path(name: str) -> Path:
    raw = Path(str(name or "")).name
    if not _NAME_RE.match(raw):
        raise ValueError(f"非法历史文件名：{name!r}")
    path = (HISTORY_DIR / raw).resolve()
    if path.parent != HISTORY_DIR.resolve():
        raise ValueError("非法历史文件路径")
    return path


def _summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    targets = payload.get("targets")
    if not isinstance(targets, list):
        return None
    count = sum(1 for item in targets if isinstance(item, dict))
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError:
        mtime = None
    return {
        "name": path.name,
        "created_at": payload.get("created_at") or (mtime.isoformat(timespec="seconds") if mtime else None),
        "count": count,
        "uid": payload.get("uid"),
        "base_url": payload.get("base_url"),
        "region": payload.get("region"),
        "label": payload.get("label") or "",
        "size": path.stat().st_size if path.is_file() else 0,
    }


def list_history() -> list[dict[str, Any]]:
    _ensure_dir()
    out = []
    for path in HISTORY_DIR.glob("targets_*.json"):
        item = _summary(path)
        if item is not None:
            out.append(item)
    out.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return out


def save_current(current: dict, *, region: str | None = None,
                 label: str = "") -> dict[str, Any]:
    """把 current_targets() 的结果保存为存档。current 必须包含 targets。"""
    targets = []
    for item in current.get("targets") or []:
        try:
            order = int(item.get("order"))
            team = int(item.get("team"))
        except (TypeError, ValueError):
            continue
        if order > 0 and team > 0:
            targets.append({"order": order, "team": team})
    if not targets:
        raise ValueError("当前没有可保存的靶机配置")
    targets.sort(key=lambda item: item["order"])
    now = _now()
    base_name = f"targets_{now.strftime('%Y%m%d_%H%M%S')}"
    _ensure_dir()
    with _LOCK:
        path = HISTORY_DIR / f"{base_name}.json"
        seq = 1
        while path.exists():
            path = HISTORY_DIR / f"{base_name}_{seq}.json"
            seq += 1
        payload = {
            "schema": "targetforge.target-history.v1",
            "created_at": now.isoformat(timespec="seconds"),
            "label": str(label or "").strip(),
            "uid": current.get("uid"),
            "base_url": current.get("base_url"),
            "region": str(region or current.get("region") or ""),
            "targets": targets,
            "enemies": [str(item["team"]) for item in targets],
            "orders": [item["order"] for item in targets],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _summary(path) or {"name": path.name, "count": len(targets)}


def load_history(name: str) -> dict[str, Any]:
    path = _safe_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"历史存档不存在：{name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("targets"), list):
        raise ValueError(f"历史存档格式不正确：{name}")
    return payload


def delete_history(name: str) -> bool:
    path = _safe_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"历史存档不存在：{name}")
    path.unlink()
    return True
