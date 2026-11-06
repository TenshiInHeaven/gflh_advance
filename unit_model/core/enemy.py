"""敌方单位：等级、属性与布阵。

**等级的存在与作用（由本机数据证实）**

1. 两个等级字段：

   * ``enemy_character_type.level``：单位类型自带的等级（753 个类型是 100，另有 10100 / 20200 /
     30100 / 80100 等）；
   * ``enemy_in_team.level``：**该队伍里这一格的实际等级**（312 种取值）。

   编码是 **``系列 × 100 + 系列内等级``**，系列覆盖 ``0/1/2/100/101/102/…/800/801/802``，
   系列内等级 0~99。

2. **等级确实缩放属性**：同一个单位类型会出现在许多不同等级上
   （972 个类型里 351 个如此；例如胡蜂 type=20005 在队伍里用到 10010~10040）。

3. 等级影响哪些属性由 ``enemy_standard_attribute``（1,900 行）的列决定：

   ======================  ====================================================
   受等级影响               maxlife 生命 / pow 火力 / hit 命中 / dodge 回避 /
                            armor 护甲 / armor_piercing 穿甲 / def 防御(力场) /
                            def_break 破防 / shield / tenacity / debuff_resistance
   不受等级影响（只在类型表） range 射程 / speed 移速 / rate 射速 / crit 暴击 /
                            crit_dmg 爆伤 / angle 朝向 / number 编制 /
                            normal_attack 普攻 / passive_skill 被动技能
   ======================  ====================================================

   ``enemy_in_team`` 用到的 312 个等级里 **311 个能在标准表里查到**（只缺 ``level=0``）。

4. **组合方式（推断，自洽但未实测验证）**：类型表自己的属性列**必然参与**
   —— 否则同等级的敌人属性会完全一样，而捷豹(type 10009) 火力 168 / 命中 350
   与巡游者(type 10001) 火力 11 / 命中 23 明显不同。故取"以类型自身等级为锚点"的比例模型::

       final.attr(level) = type.attr × standard[level].attr / standard[type.level].attr

   证据：斩击者(Ripper) 的 maxlife/hit/dodge 与 ``standard[100]`` 几乎相等
   （794 vs 793.80、23 vs 23.33、15 vs 15.00），而巡游者把 HP 减半、捷豹把火力提高 8 倍
   —— 都符合"等级 100 处锚点 + 逐类型改写"的形态。

   另有 ``enemy_in_team.def_percent``：**按格**的防御百分比修正（0/10/20/30/50/100…）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from unit_model.core import stc

#: 标准属性表的名称字段
STANDARD_TABLE = "enemy_standard_attribute"

#: 受等级影响的属性（标准表的列）
LEVEL_ATTRS = ("maxlife", "pow", "hit", "dodge", "armor", "armor_piercing",
               "def", "def_break", "shield", "tenacity", "debuff_resistance")

#: 只由类型决定、与等级无关的属性
FLAT_ATTRS = ("range", "speed", "rate", "crit", "crit_dmg", "angle", "number")


def level_series(level: int) -> tuple[int, int]:
    """``系列 × 100 + 系列内等级`` → ``(系列, 等级)``。"""
    return int(level) // 100, int(level) % 100


def level_text(level: int) -> str:
    series, inner = level_series(level)
    return f"{level}（系列 {series}，系列内 {inner} 级）"


@lru_cache(maxsize=1)
def standard_attributes() -> dict[int, dict[str, float]]:
    """``enemy_standard_attribute``：等级 → 属性。"""
    out: dict[int, dict[str, float]] = {}
    for row in stc.read_table(STANDARD_TABLE)[1]:
        level = int(row["level"])
        out[level] = {key: float(row.get(key) or 0.0) for key in LEVEL_ATTRS}
    return out


@lru_cache(maxsize=4096)
def standard_at(level: int) -> dict[str, float]:
    """任意整数等级的属性。

    优先精确表；同一系列（level//100）内线性插值；
    跨系列/越界按最近端点 clamp。绝不返回全 0。
    """
    level = max(1, int(level))
    table = standard_attributes()
    if level in table:
        return dict(table[level])
    series = level // 100
    same = [lv for lv in table if lv // 100 == series]
    if same:
        lo = max((lv for lv in same if lv < level), default=None)
        hi = min((lv for lv in same if lv > level), default=None)
        if lo is not None and hi is not None:
            t = (level - lo) / float(hi - lo)
            return {k: float(table[lo].get(k, 0.0)) * (1.0 - t)
                       + float(table[hi].get(k, 0.0)) * t
                    for k in LEVEL_ATTRS}
        return dict(table[lo if lo is not None else hi])
    # 跨系列或超出表尾：取最近等级端点
    nearest = min(table, key=lambda lv: abs(lv - level))
    return dict(table[nearest])


@lru_cache(maxsize=1)
def enemy_types() -> dict[int, dict[str, Any]]:
    """``enemy_character_type``：类型 id → 原始行。"""
    return {int(row["id"]): dict(row) for row in stc.read_table(5025)[1]}


@dataclass(frozen=True)
class EnemyAttributes:
    """一名敌人在某等级下的属性。"""

    type_id: int
    name: str
    code: str
    level: int
    anchor_level: int
    scale: float
    #: 属性键 -> 计算后的值；另含 ``range`` / ``speed`` / ``rate`` / ``crit`` 等
    values: dict[str, float] = field(default_factory=dict)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.values.get(key, default)

    def describe(self) -> str:
        base = (f"{self.name}({self.code}) 等级 {level_text(self.level)} "
                f"锚点 {self.anchor_level} 缩放×{self.scale:.4f}")
        attrs = "  ".join(
            f"{k}={self.values[k]:g}" for k in ("maxlife", "pow", "hit", "dodge", "armor")
            if k in self.values)
        return f"{base}\n    {attrs}\n    射速={self.get('rate'):g} 射程={self.get('range'):g} " \
               f"移速={self.get('speed'):g} 暴击={self.get('crit'):g} 爆伤={self.get('crit_dmg'):g}"


def _anchor_level(row: dict) -> int:
    """类型表 `level` 字段里的**锚点（标准）等级**。

    该字段是 `<tier><等级后 4 位>` 的打包值，实测分布：

    * `100`   —— 753 个（普通）
    * `30100` —— 249 个 → tier 3, 锚点 **100**
    * `20200` —— 25 个  → tier 2, 锚点 **200**
    * `10100` / `80100` → 锚点 **100**

    取模 10000 即可还原锚点。
    """
    raw = int(row.get("level") or 100)
    return raw % 10000 if raw >= 1000 else raw

def enemy_attributes(type_id: int, level: int | None = None, *,
                     scale_by_level: bool = False) -> EnemyAttributes:
    """敌人属性。

    **结论（有实测证据）：属性就是 `enemy_character_type` 自身的列**，
    等级字段只是标签，不参与运行时缩放；强度差异由"同一 code 的多个手工变体"实现
    （例如 Cyclops `10024` lv100 与 `11024` lv30100 的属性各自独立编写）。

    证据（`boss_hp` 是游戏 UI 真的会显示的 BOSS 血量，可当作真值）：

    * ``boss_hp ≈ 类型表 maxlife``：**516 / 529** 个 BOSS 命中（比值中位数 1.000）
    * ``boss_hp ≈ 标准表 maxlife``：**0 / 529** 命中

    因此 ``enemy_standard_attribute`` 不是运行时路径（可能是图鉴/工具用的参考曲线）。
    ``scale_by_level=True`` 保留旧的"标准表锚点缩放"实现，仅作实验对照（已被上述证据否定）。
    """
    types = enemy_types()
    if int(type_id) not in types:
        raise KeyError(f"enemy_character_type 里没有 id={type_id}")
    row = types[int(type_id)]
    anchor = _anchor_level(row)
    level = anchor if level is None else int(level)
    standard = standard_attributes()

    def ratio(attr: str) -> float:
        base = standard_at(anchor).get(attr, 0.0)
        now = standard_at(level).get(attr, 0.0)
        if base <= 0:
            return 1.0
        return now / base

    values: dict[str, float] = {}
    for attr in LEVEL_ATTRS:
        own = float(row.get(attr) or 0.0)
        if scale_by_level and own:
            values[attr] = own * ratio(attr)
        else:
            values[attr] = own                      # 直接用类型表的值
    for attr in FLAT_ATTRS:
        values[attr] = float(row.get(attr) or 0.0)
    return EnemyAttributes(
        type_id=int(type_id),
        name=str(row.get("enemy_info") or ""),
        code=str(row.get("code") or ""),
        level=level,
        anchor_level=anchor,
        scale=ratio("maxlife") if scale_by_level else 1.0,
        values=values,
    )


@dataclass(frozen=True)
class EnemyUnit:
    """布阵里的一名敌人（位置 + 属性 + 每格修正）。"""

    team_id: int
    type_id: int
    x: float
    y: float
    level: int
    number: int
    advance: bool
    def_percent: float
    batch: int
    attributes: EnemyAttributes

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)

    def describe(self) -> str:
        return (f"{self.attributes.name:<10}({self.attributes.code:<9}) "
                f"坐标({self.x:g}, {self.y:g}) 等级{self.level} 编制{self.number} "
                f"生命{self.attributes.get('maxlife'):.1f} 火力{self.attributes.get('pow'):.1f} "
                f"射程{self.attributes.get('range'):g} 移速{self.attributes.get('speed'):g}"
                + (f" 防御修正{self.def_percent:g}%" if self.def_percent else ""))


@lru_cache(maxsize=None)
def enemy_team_units(team_id: int) -> tuple[EnemyUnit, ...]:
    """整支队伍：坐标 + 等级 + 属性（等级取 ``enemy_in_team.level``）。"""
    out: list[EnemyUnit] = []
    for row in stc.read_table(5003)[1]:
        if int(row["enemy_team_id"]) != int(team_id):
            continue
        type_id = int(row["enemy_character_type_id"])
        level = int(row["level"])
        out.append(EnemyUnit(
            team_id=int(team_id),
            type_id=type_id,
            x=float(row["coordinator_x"]),
            y=float(row["coordinator_y"]),
            level=level,
            number=int(row["number"] or 1),
            advance=bool(row["is_advance"]),
            def_percent=float(row["def_percent"] or 0),
            batch=int(row.get("batch") or 0),
            # **按等级倍率参数缩放**（默认开启）。
            #
            # 口径：``enemy_character_type`` 的列是**标准（锚点）等级**时的值，
            # 实际值 = 标准值 × (std[当前等级] / std[锚点等级])。
            # 锚点由 ``level`` 字段还原（``30100`` → 100，见 :func:`_anchor_level`）。
            #
            # 实证：660011 全为 Lv150、锚点 100 → 血量倍率 2.3334，
            # 队伍总血 154,100 × 2.3334 = **359,580**，
            # 与用户实测「总伤害恒为 359,580」精确一致。
            attributes=enemy_attributes(type_id, level, scale_by_level=True),
        ))
    out.sort(key=lambda item: (item.x, -item.y))
    return tuple(out)


def validate_level_model() -> list[tuple[str, bool, str]]:
    """等级/属性模型的证据链断言。"""
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, got: Any, want: Any) -> None:
        checks.append((name, got == want, f"{got!r} vs {want!r}"))

    standard = standard_attributes()
    check("标准属性表行数", len(standard), 1900)
    check("等级 100 有标准值", 100 in standard, True)
    check("等级 120 有标准值", 120 in standard, True)
    check("等级 100 生命 793.8", round(standard[100]["maxlife"], 1), 793.8)

    rows = stc.read_table(5003)[1]
    used = {int(r["level"]) for r in rows}
    check("队伍用到的等级数", len(used), 312)
    check("标准表缺的等级只有 0", sorted(used - set(standard)), [0])
    check("100 → (系列1, 级0)", level_series(100), (1, 0))
    check("30120 → (系列301, 级20)", level_series(30120), (301, 20))

    # ---- 核心证据：boss_hp（游戏 UI 真值）只与"类型表自身 maxlife"一致 ----
    chars = stc.read_table(5025)[1]
    bosses = [r for r in chars
              if int(r.get("boss_hp") or 0) > 0 and float(r.get("maxlife") or 0) > 0]
    same_as_type = same_as_std = 0
    for row in bosses:
        lv = int(row["level"])
        s = standard.get(lv)
        if not s or not s["maxlife"]:
            continue
        boss = float(row["boss_hp"])
        hp_type = float(row["maxlife"])
        if abs(boss - hp_type) / hp_type < 0.02:
            same_as_type += 1
        if abs(boss - s["maxlife"]) / s["maxlife"] < 0.02:
            same_as_std += 1
    total = same_as_type + 0
    check("有 boss_hp 的类型数 >= 500", len(bosses) >= 500, True)
    check("boss_hp = 类型表 maxlife（>= 500 个）", same_as_type >= 500, True)
    check("boss_hp = 标准表 maxlife 的个数为 0", same_as_std, 0)

    # 属性直接用类型表的值（不再按等级缩放）
    prowler = enemy_attributes(10001, 86)
    check("巡游者生命 = 类型值 397（不缩放）", round(prowler.get("maxlife"), 3), 397.0)
    check("巡游者火力 = 类型值 11", round(prowler.get("pow"), 3), 11.0)
    check("巡游者射程 = 4（与等级无关）", prowler.get("range"), 4.0)
    scaled = enemy_attributes(10001, 120, scale_by_level=True)
    check("旧锚点缩放仍可对照（会变大）", scaled.get("maxlife") > prowler.get("maxlife"), True)

    # 同一 code 的多个变体是**独立编写**的：它们之间的属性比值 ≠ 标准表的等级比值
    mismatched = 0
    compared = 0
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in chars:
        code = str(row.get("code") or "")
        if code and int(row.get("level") or 0) > 0:
            by_code.setdefault(code, []).append(row)
    for code, group in by_code.items():
        levels = sorted({int(r["level"]) for r in group})
        if len(levels) < 2:
            continue
        rows_sorted = sorted(group, key=lambda r: -float(r.get("maxlife") or 0))
        a, b = rows_sorted[0], rows_sorted[-1]
        la, lb = int(a["level"]), int(b["level"])
        if la == lb or la not in standard or lb not in standard:
            continue
        va, vb = float(a.get("maxlife") or 0), float(b.get("maxlife") or 0)
        sa, sb = standard[la]["maxlife"], standard[lb]["maxlife"]
        if not va or not vb or not sa or not sb:
            continue
        compared += 1
        if abs(vb / va - sb / sa) > 0.02:
            mismatched += 1
    check("同 code 变体的属性比值 ≠ 标准表等级比值（>= 3 组）",
          mismatched >= 3, True)
    check("可比较的变体组数 >= 3", compared >= 3, True)

    # 队伍装配
    check("队伍 56 有 5 名敌人", len(enemy_team_units(56)), 5)
    check("队伍 56 各格等级不唯一", {u.level for u in enemy_team_units(56)}, {10025, 10050})
    percents = {int(r["def_percent"] or 0) for r in rows}
    check("def_percent 有非零取值（每格防御修正）", max(percents) > 0, True)
    return checks
