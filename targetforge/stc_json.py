"""直接读取导出的 STC JSON 表，不依赖 unit_model。

`dataMiner/stc/tables/<table_id>_<name>.json` 是游戏 STC 表的导出结果；
这里按表名建立索引，供 catalog 构建/队伍详情使用。
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def _table_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "dataMiner" / "stc" / "tables"


class StcJson:
    """极简只读 STC JSON 表访问器。"""

    MAPPING_VERSION = "json"

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory else _table_dir()
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.directory.is_dir():
            raise FileNotFoundError(f"STC JSON 表目录不存在：{self.directory}")
        for path in sorted(self.directory.glob("*.json")) + sorted(self.directory.glob("*.json.gz")):
            try:
                if path.suffix == ".gz":
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        data = json.load(handle)
                else:
                    data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = ""
            rows = None
            if isinstance(data, dict):
                name = str(data.get("table_name") or "").strip()
                rows = data.get("rows")
            elif isinstance(data, list):
                rows = data
            if not name:
                stem = path.name
                if stem.endswith(".json.gz"):
                    stem = stem[:-8]
                elif stem.endswith(".json"):
                    stem = stem[:-5]
                name = stem.split("_", 1)[1] if "_" in stem else stem
            if isinstance(rows, list) and name:
                self._tables[name] = rows

    def table(self, name_or_id: str | int) -> list[dict[str, Any]]:
        self._load()
        if isinstance(name_or_id, int):
            raise KeyError(f"STC JSON 访问器需要表名，不支持数字 id：{name_or_id}")
        name = str(name_or_id)
        rows = self._tables.get(name)
        if rows is None:
            raise KeyError(f"STC JSON 里没有表：{name}（目录 {self.directory}）")
        return rows

    def table_count(self) -> int:
        self._load()
        return len(self._tables)
