"""敌人属性兜底：没有 unit_model 时直接从导出的 STC JSON 表计算。

这不是新造数据：读取的是本仓库/客户端导出的同一份
``enemy_character_type`` 与 ``enemy_standard_attribute`` 表，
算法与 unit_model.core.enemy 保持一致。用于单元测试/精简运行环境。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LEVEL_ATTRS = ("maxlife", "pow", "hit", "dodge", "armor", "armor_piercing",
               "def", "def_break", "shield", "tenacity", "debuff_resistance")
FLAT_ATTRS = ("range", "speed", "rate", "crit", "crit_dmg", "angle", "number")


def _table_paths() -> tuple[Path, Path] | None:
    root = Path(__file__).resolve().parents[1]
    base = root / "dataMiner" / "stc" / "tables"
    type_path = base / "5025_enemy_character_type.json"
    standard_path = base / "5026_enemy_standard_attribute.json"
    if type_path.is_file() and standard_path.is_file():
        return type_path, standard_path
    return None


def _rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []


@lru_cache(maxsize=1)
def _tables() -> tuple[dict[int, dict], dict[int, dict[str, float]]] | None:
    paths = _table_paths()
    if paths is None:
        return None
    type_rows: dict[int, dict] = {}
    for row in _rows(paths[0]):
        try:
            type_rows[int(row.get("id") or 0)] = dict(row)
        except (TypeError, ValueError):
            continue
    standard: dict[int, dict[str, float]] = {}
    for row in _rows(paths[1]):
        try:
            level = int(row.get("level") or 0)
        except (TypeError, ValueError):
            continue
        standard[level] = {
            key: float(row.get(key) or 0.0) for key in LEVEL_ATTRS
        }
    return type_rows, standard


def _standard_at(level: int) -> dict[str, float]:
    tables = _tables()
    if tables is None:
        return {key: 0.0 for key in LEVEL_ATTRS}
    standard = tables[1]
    level = max(1, int(level))
    if level in standard:
        return dict(standard[level])
    series = level // 100
    same = [lv for lv in standard if lv // 100 == series]
    if same:
        lo = max((lv for lv in same if lv < level), default=None)
        hi = min((lv for lv in same if lv > level), default=None)
        if lo is not None and hi is not None:
            t = (level - lo) / float(hi - lo)
            return {key: standard[lo].get(key, 0.0) * (1.0 - t)
                    + standard[hi].get(key, 0.0) * t
                    for key in LEVEL_ATTRS}
        return dict(standard[lo if lo is not None else hi])
    nearest = min(standard, key=lambda lv: abs(lv - level))
    return dict(standard[nearest])


def _anchor_level(row: dict) -> int:
    raw = int(row.get("level") or 100)
    return raw % 10000 if raw >= 1000 else raw


def attributes(type_id: int, level: int | None = None, *,
               scale_by_level: bool = True,
               model: dict | None = None) -> dict[str, float]:
    """返回与 unit_model.core.enemy.enemy_attributes 对齐的属性字典。

    ``model`` 是 catalog 里预计算的 ``stat_model``（types + standard）；
    为 None 时回退到 dataMiner/stc/tables 的 JSON 表。
    """
    model_types: dict | None = None
    model_standard: dict[int, dict[str, float]] | None = None
    if isinstance(model, dict):
        model_types = model.get("types") or {}
        raw_standard = model.get("standard") or {}
        if isinstance(raw_standard, dict):
            model_standard = {int(k): dict(v) for k, v in raw_standard.items()}

    if model_types is not None:
        row = model_types.get(str(type_id))
        if row is None:
            raise KeyError(f"enemy_character_type 里没有 id={type_id}")
        anchor = int(row.get("anchor") or 100)
        values = dict(row.get("values") or {})
        current_level = anchor if level is None else int(level)

        def standard_at(level_value: int) -> dict[str, float]:
            if not model_standard:
                return {key: 0.0 for key in LEVEL_ATTRS}
            level_value = max(1, int(level_value))
            if level_value in model_standard:
                return dict(model_standard[level_value])
            series = level_value // 100
            same = [lv for lv in model_standard if lv // 100 == series]
            if same:
                lo = max((lv for lv in same if lv < level_value), default=None)
                hi = min((lv for lv in same if lv > level_value), default=None)
                if lo is not None and hi is not None:
                    t = (level_value - lo) / float(hi - lo)
                    return {key: model_standard[lo].get(key, 0.0) * (1.0 - t)
                            + model_standard[hi].get(key, 0.0) * t
                            for key in LEVEL_ATTRS}
                return dict(model_standard[lo if lo is not None else hi])
            nearest = min(model_standard, key=lambda lv: abs(lv - level_value))
            return dict(model_standard[nearest])

        ratio_source = standard_at(anchor)
        ratio_now = standard_at(current_level)
        result = {}
        for attr in LEVEL_ATTRS:
            own = float(values.get(attr) or 0.0)
            if scale_by_level and own and ratio_source.get(attr, 0.0) > 0:
                result[attr] = own * ratio_now.get(attr, 0.0) / ratio_source[attr]
            else:
                result[attr] = own
        for attr in FLAT_ATTRS:
            result[attr] = float(values.get(attr) or 0.0)
        return result

    tables = _tables()
    if tables is None:
        raise KeyError("没有可用的 stat_model 或 STC JSON 表")
    type_rows = tables[0]
    row = type_rows.get(int(type_id))
    if row is None:
        raise KeyError(f"enemy_character_type 里没有 id={type_id}")
    anchor = _anchor_level(row)
    current_level = anchor if level is None else int(level)
    ratio_source = _standard_at(anchor)
    ratio_now = _standard_at(current_level)
    values: dict[str, float] = {}
    for attr in LEVEL_ATTRS:
        own = float(row.get(attr) or 0.0)
        if scale_by_level and own and ratio_source.get(attr, 0.0) > 0:
            values[attr] = own * ratio_now.get(attr, 0.0) / ratio_source[attr]
        else:
            values[attr] = own
    for attr in FLAT_ATTRS:
        values[attr] = float(row.get(attr) or 0.0)
    return values


# 与 unit_model.core.enemy 的公开名字对齐，方便 catalog 无感切换
enemy_attributes = attributes
