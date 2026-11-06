"""TargetForge 路径常量（唯一数据目录来源）。

默认：``<GF Forge 仓库根>/dataMiner/derived/targetforge``。
可用环境变量 ``TARGETFORGE_DATA_DIR`` 覆盖（部署到别的目录 / 便携版时使用）。
"""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent


def _resolve_data_dir() -> Path:
    override = os.environ.get("TARGETFORGE_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return ROOT / "dataMiner" / "derived" / "targetforge"


DATA_DIR = _resolve_data_dir()
ICON_DIR = DATA_DIR / "icons"
CATALOG_FILE = DATA_DIR / "catalog.json"
STATE_FILE = DATA_DIR / "state.json"
CREDS_LATEST = DATA_DIR / "creds_latest.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
