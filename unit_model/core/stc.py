"""本机 ``stc`` 表的离线解析。

``StreamingAssets/Res/Pc/stc/*.stc`` 是游戏自己的定长表格式，**文件名就是表 id**
（``5000.stc`` ↔ 映射里的 ``item`` 表）。列名来自 ``gf-data-tools`` 的
``stc-mapping/<版本>/<表id>.json``（本机版本 3081，已缓存到
``unit_model/core/cache/stc-mapping/3081/``）。

格式（对照 ``gf-data-dataMiner/resources/tools/project_tools/gfl-data-miner-python`` 的 ``utils/format_stc.py``）::

    ushort  code           表 id
    short   （long 变体为 4 字节）占位
    ushort  row_count      （long 变体为 int）
    byte    col_count
    byte × col_count       列类型：1=byte 5=int 8=long 9=float 11=string
    4 字节                  占位
    int     data_offset
    --- seek(data_offset) ---
    row_count 行，每行按列类型顺序读取
    string = 1 字节占位 + ushort 长度 + utf-8 字节

因此短头长度 = ``15 + col``，长头 = ``19 + col``，可用"``data_offset`` 是否等于头长度"
来自动判定变体。
"""
from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

from unit_model.core import paths

#: 映射版本（本机游戏版本）
MAPPING_VERSION = "3081"

#: 列类型 id -> (struct 格式, 字节数)；11（string）特殊处理
_TYPE_FORMATS: dict[int, tuple[str, int]] = {
    1: ("<b", 1),
    5: ("<i", 4),
    8: ("<q", 8),
    9: ("<f", 4),
}


def mapping_dir() -> Path:
    return paths.STC_MAPPING_DIR / MAPPING_VERSION


def stc_ids() -> list[int]:
    """本机全部 ``.stc`` 的表 id（升序）。"""
    return sorted(int(p.stem) for p in paths.stc_dir().glob("*.stc"))


@lru_cache(maxsize=None)
def load_mapping(table_id: int) -> dict[str, Any] | None:
    """``{"name": ..., "fields": [...]}``；缺映射返回 ``None``。"""
    path = mapping_dir() / f"{table_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@lru_cache(maxsize=1)
def table_index() -> dict[str, int]:
    """表名 -> 表 id（用于按名字取表）。"""
    index: dict[str, int] = {}
    for table_id in stc_ids():
        conf = load_mapping(table_id)
        if conf and conf.get("name"):
            index.setdefault(str(conf["name"]), table_id)
    return index


def resolve_table(name_or_id: str | int) -> tuple[int, dict[str, Any]]:
    """接受表名或表 id，返回 ``(id, 映射)``。

    上游映射缺失的表（本机 5077 / 5078 / 5085 / 5251，任何版本都没有）仍可按 id 解析，
    此时列名退化为 ``col_0`` / ``col_1`` …。
    """
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        table_id = int(name_or_id)
    else:
        index = table_index()
        if str(name_or_id) not in index:
            raise KeyError(f"没有名为 {name_or_id!r} 的 stc 表")
        table_id = index[str(name_or_id)]
    conf = load_mapping(table_id)
    if conf is None:
        return table_id, {"name": f"unk_{table_id}", "fields": [], "unmapped": True}
    return table_id, conf


class _Reader:
    """按格式顺序读取的小工具。"""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.pos = 0

    def take(self, size: int) -> bytes:
        chunk = self.payload[self.pos:self.pos + size]
        if len(chunk) != size:
            raise ValueError("读取越界")
        self.pos += size
        return chunk

    def ushort(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def int(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def value(self, type_id: int) -> Any:
        if type_id == 11:
            self.take(1)
            length = self.ushort()
            return self.take(length).decode("utf-8", "replace")
        fmt, size = _TYPE_FORMATS[type_id]
        return struct.unpack(fmt, self.take(size))[0]


def _header(payload: bytes, table_id: int, *, long: bool) -> tuple[int, int, list[int], int]:
    """读头部，返回 ``(row_count, col_count, type_ids, data_offset)``。"""
    reader = _Reader(payload)
    code = reader.ushort()
    if code != table_id:
        raise ValueError(f"表 id 不符：文件里是 {code}，期望 {table_id}")
    reader.take(4 if long else 2)
    rows = reader.int() if long else reader.ushort()
    if rows == 0:
        return 0, 0, [], 0
    cols = reader.take(1)[0]
    types = [reader.take(1)[0] for _ in range(cols)]
    reader.take(4)
    offset = reader.int()
    if offset < reader.pos or offset >= len(payload):
        raise ValueError(f"data_offset={offset} 越界（文件 {len(payload)} 字节）")
    bad = sorted({t for t in types if t not in _TYPE_FORMATS and t != 11})
    if bad:
        raise ValueError(f"未知列类型 {bad}")
    return rows, cols, types, offset


def _select_header(payload: bytes, table_id: int, field_count: int) -> tuple[bool, int, int, list[int], int]:
    """自动判定 short / long 变体。

    判据：``code`` 必须等于表 id、列类型必须合法、且 **列数与映射字段数最接近**。
    （经验：``5038.stc`` 是 long 变体，短变体会把 ``col`` 读成 240 而映射只有 54 列。）
    """
    candidates = []
    errors = []
    for long in (False, True):
        try:
            rows, cols, types, offset = _header(payload, table_id, long=long)
        except (ValueError, struct.error) as exc:
            errors.append(f"{'long' if long else 'short'}: {exc}")
            continue
        candidates.append((abs(cols - field_count), 0 if long else 1, long, rows, cols, types, offset))
    if not candidates:
        raise ValueError("；".join(errors))
    candidates.sort()
    _, _, long, rows, cols, types, offset = candidates[0]
    return long, rows, cols, types, offset


def _parse_rows(
    payload: bytes, names: list[str], types: list[int], offset: int, rows: int
) -> tuple[tuple[dict[str, Any], ...], int]:
    """按给定头部解析，返回 ``(行元组, 结束位置)``；越界会抛 ``ValueError``。"""
    reader = _Reader(payload)
    reader.pos = offset
    out = []
    for _ in range(rows):
        out.append({name: reader.value(type_id) for name, type_id in zip(names, types)})
    return tuple(out), reader.pos


@lru_cache(maxsize=None)
def read_table(name_or_id: str | int) -> tuple[str, tuple[dict[str, Any], ...]]:
    """解析一张表，返回 ``(表名, 行元组)``。结果按表缓存（进程内）。"""
    table_id, conf = resolve_table(name_or_id)
    path = paths.stc_dir() / f"{table_id}.stc"
    payload = path.read_bytes()
    fields = [str(f) for f in (conf.get("fields") or [])]
    has_mapping = bool(fields)

    def names_for(cols: int) -> list[str]:
        names = list(fields) if has_mapping else [f"col_{i}" for i in range(cols)]
        while len(names) < cols:
            names.append(f"unk_{len(names)}")
        return names[:cols]

    # 有映射：列数就是最强判据，直接选变体后解析一次
    if has_mapping:
        long, rows, cols, types, offset = _select_header(payload, table_id, len(fields))
        if rows == 0:
            return str(conf.get("name") or table_id), ()
        out, _ = _parse_rows(payload, names_for(cols), types, offset, rows)
        return str(conf.get("name") or table_id), out

    # 无映射：两种变体各解析一次，取"不越界且正好读到文件尾"的那个
    best: tuple[int, tuple[dict[str, Any], ...]] | None = None
    errors: list[str] = []
    for long in (False, True):
        try:
            rows, cols, types, offset = _header(payload, table_id, long=long)
            if rows == 0:
                return f"unk_{table_id}", ()
            out, end = _parse_rows(payload, names_for(cols), types, offset, rows)
        except (ValueError, struct.error) as exc:
            errors.append(f"{'long' if long else 'short'}: {exc}")
            continue
        score = abs(end - len(payload))
        if best is None or score < best[0]:
            best = (score, out)
    if best is None:
        raise ValueError(f"无法解析 {path.name}：{'；'.join(errors)}")
    return f"unk_{table_id}", best[1]


def table(name_or_id: str | int) -> list[dict[str, Any]]:
    """解析一张表，返回行列表。"""
    return list(read_table(name_or_id)[1])


def table_name(name_or_id: str | int) -> str:
    return read_table(name_or_id)[0]


def describe() -> list[tuple[int, str, int, list[str]]]:
    """``[(id, 表名, 行数, 列名)]``，用于浏览。行数为 -1 表示尚未解析。"""
    out: list[tuple[int, str, int, list[str]]] = []
    for table_id in stc_ids():
        conf = load_mapping(table_id) or {}
        out.append((table_id, str(conf.get("name") or "?"), -1, [str(f) for f in (conf.get("fields") or [])]))
    return out
