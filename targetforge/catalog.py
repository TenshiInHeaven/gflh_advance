"""靶机工坊 TargetForge —— STC → 章节/关卡/怪种/怪组 数据层（v1.2）。

职责（见 ``contract.md`` §2）：

* :func:`build` 解析本机 STC（game 定长表）+ ``client_text.json`` +
  ``enemy_full_model.csv``，生成 :data:`CATALOG_FILE`（原子写 + 跨进程锁）；
* :func:`load` 单例加载（线程安全、检测 catalog.json mtime 自动重载）；
* :class:`Catalog` 提供 ``/api/chapters``、``/api/stages``、``/api/teams``、
  ``/api/species``、``/api/grayzone/*``、``/api/search`` 需要的查询。

v1.2 变化（用户实测反馈）
------------------------

1. **章节 7 组**：``main``（主线）/ ``event``（活动）/ ``score``（积分关卡）/
   ``tutorial``（教学）/ ``simulation``（模拟作战）/ ``grayzone``（灰域探查）/
   ``orphan``（无固定关卡）。往期复刻、特殊作战并入 event（用 subtitle/tags 标记）。
   积分关卡是 **mission 级**：``mission.event_score`` 非空即积分关卡（权威字段）。
   同一 campaign 里只有部分任务是积分关卡时会拆成 score 章 + event 章（如
    思域迷航 -61：禁止喂食/禁止喂食EX 进 score，其余 20 关留在 event）；全积分
    campaign（贝蒂数、终焉花海+、自画像、-77 静默沙盘…）只生成 score 章。
2. **灰域：区域 → 节点（v1.8）**：真实区域来自
   ``daily_mission_group``（mission→difficulty_group）+ ``daily_mission_difficulty_group``，
   返回 6 个区域：沙尘带/风暴带/硅状带/结晶带/**装甲突击**（爬塔，kind=tower）/
   **特殊区域**（组5/6/未映射去掉爬塔，kind=special，客户端无区域名不编造）。
   ``grayzone_nodes(region, ...)`` 列出区域内节点（mission），节点带 location
   （标题前缀，仅副信息）与 top_species（≤4）。旧的 14 个「地点」降级为兼容字段
   ``areas``，不再作为主结构。
3. **怪种分类改为非互斥 flag**：``has_normal`` / ``has_grayzone`` / ``has_orphan``
   + ``normal_team_count`` / ``gray_zone_team_count`` / ``orphan_team_count``。
   ``species_list(category=...)`` 按 flag 过滤（灰域过滤 = 所有在灰域有队伍的物种）。
4. **效能（power = enemy_team.effect_ext）**：队伍 summary/detail 带
   ``power`` 与 ``power_known``；列表支持 ``power_min/power_max/power_known/sort``。
   **结论（不要编公式）**：常规关卡/普通队伍在客户端里 ``effect_ext == 0``
   （即客户端根本没有这个值，也没有可用的数值反推公式）；只有积分关卡及部分特殊
   队伍有标注，且存在负值（例如 660011 = -100085）。因此 0 一律视为「未标注」，
   负值原样保留，不做任何推断。
5. **小怪头像**：``targetforge/tools/build_icons.py`` 从游戏 ``character<code>.ab``
   导出 ``pic_<Code>_SS`` 到 ``ICON_DIR/<code>.png``；catalog build 扫描
   :data:`ICON_DIR`，在 species / team_summary.species / 队伍详情 members 上加
   ``icon`` 字段（缺失为 ``None``，前端退化显示）。

6. **关卡结算形式（v1.3）**：每个 stage 带 ``settlement``：``type``（score/normal）、
   ``event_score``（``{"mode","params"}``，来自 ``mission.event_score`` 的
   ``mode|参数,...``）、``score_prize``（``{"raw","tiers"}``，来自
   ``mission.score_prize``）、``rank``（积分榜，来自 ``rank`` 表 ``sub_type`` 的
   mission id 列表；同 mission 多行优先 ``type=10`` 常驻积分榜，其次 ``type=6``）。
   这样前端/分析工具可以真正读懂"结算形式"，而不是靠活动名里有没有「+」。

7. **支援队伍（v1.4）**：除 ``spot.enemy_team_id`` / ``boss_team_id``（敌方）外，
   ``spot.ally_team_id`` 指向**支援队伍**（有槽位即收，可收藏/不可收藏都收）。
   stage 详情多了 ``support_teams``（team_summary + ``role:"support"``、
   ``support_count``、``collectable``）与 ``support_team_count``；章节详情的
   stage 行带 ``support_team_count``。支援链接也计入队伍出处（``appearances[].role``）
   与 ``roles``（enemy/support）；只有敌方+支援都无链接的可收藏队伍才进 orphan
   （orphan 从 4381 降到 3802）。stage 的 ``team_count``/敌方 ``teams`` 列表不变。

8. **机场/后续刷新候选（v1.5 / v1.9.6 增强）**：STC **没有显式 mission→机场刷新池映射**；
   按同系列 team id 族推断 ``reserve_teams``：对该 stage 已引用队伍（enemy∪ally∪boss，
   排除 id<=1000）在 3~6 位前缀上取**最短**可用长度；普通关卡取覆盖最多（≥3 个引用）的
   单前缀，**积分关卡**阈值降到 ≥2 且取同长度全部合格前缀的**并集**（引用跨多个 id 族
   时不漏族，如 10158 虚数迷宫+ 跨 222/232/233/234/237）；候选 = 同前缀、有槽位、可收藏、
   未被引用的队伍（id 升序；**普通关卡** ≤80 只是项目为避免列表过长的自设上限，积分关卡不设上限）。
   积分关卡前缀法仍失败时，先**继承同 campaign 兄弟关**已确认的 id 族（只继承与本关引用
   同族的前缀，``reserve_meta.inherited=true``），再退 ±20 邻近窗口。
   若 ``targetforge/manual_spawns.json`` 有该关卡，则用显式固定/刷怪表覆盖推断
   （``reserve_meta.method=manual``，``pool_prefix`` 支持单前缀/逗号/数组多前缀；列出该系列
   全部可能怪组并按 可能刷怪/实际未出现 分类，不受 80 上限影响）。
   stage 详情带 ``reserve_teams``（team_summary +
   ``role:"reserve"`` / ``inferred:true`` / ``reserve_reason``）与 ``reserve_team_count``；
   章节 stage 行只带 ``reserve_team_count``。这是**推断**：不计入 team_count/
   support_team_count，也不改变队伍的 orphan/roles 真实链接状态（只在 detail appearances
   里加 ``role:"reserve"``、``inferred:true`` 的「可能刷新」条目）。

设计取舍
--------
catalog.json 不存"前端完整详情"，而是存**查询所需的紧凑索引**：

* 每支队伍只存槽位（type_id / level / number / def_percent / batch / x / y）
  和汇总字段，队伍详情（成员数值、出处）在 ``Catalog.team()`` 里按需计算，
  展示数值统一走 ``unit_model.core.enemy.enemy_attributes(..., scale_by_level=True)``
  （660011 实测口径：总血 359,580）。这样 JSON 只有 ~7MB，load 远低于 5s。
* 怪种图鉴、类型索引只保留名称/阵营/图鉴号/图标等标签，**不写任何技能字段**
  （skill / trigger / action / buff 等一律不进 JSON）。

数据口径（与 Lead 侦查一致）
---------------------------
* 可收藏有效队伍 = ``enemy_team.targettrain_cancollect == "1"`` 且 ``enemy_in_team``
  有编制 → 13700；
* 队伍↔关卡 = ``spot.enemy_team_id`` ∪ ``mission.boss_team_id``；
* 有可收藏队伍的关卡 → 2345（灰域 1288 / 活动 / 积分关卡 / 主线 140 /
  教学 40 / 模拟作战 9 / 未知 1）；
* 灰域 = ``campaign == -404``：1288 个有可收藏队伍的节点，按真实区域
  （沙尘带/风暴带/硅状带/结晶带/装甲突击爬塔/特殊区域）分组，共 6 个区域；
  mission 标题前缀（共生净土等 14 个）只是节点 location（副信息）；
* 可收藏怪种 = enemy_full_model.csv 的 type→codex 映射 → 264 个 codex。
"""
from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 路径常量统一来自 targetforge/datapaths.py（支持 TARGETFORGE_DATA_DIR 覆盖）
from targetforge.datapaths import CATALOG_FILE, DATA_DIR, ICON_DIR  # noqa: E402

#: 跨进程构建锁（同数据目录）
LOCK_FILE = DATA_DIR / "catalog.lock"

#: 只读数据源
TEXT_FILE = ROOT / "dataMiner" / "derived" / "client_text.json"
MODEL_FILE = ROOT / "dataMiner" / "derived" / "enemy_full_model.csv"

#: JSON schema 版本（结构变更时 +1）
SCHEMA_VERSION = 9

#: 机场/后续刷新候选（reserve）的说明：STC 没有显式 mission→刷新池映射，只能按 id 族推断
RESERVE_REASON = "同系列未入场怪组（机场/后期刷新候选，STC 无显式映射）"
RESERVE_CAP = 80
#: 前缀长度依次尝试（3~6 位，取最短且覆盖 ≥3 个引用队伍的）
RESERVE_PREFIX_LENGTHS: tuple[int, ...] = (3, 4, 5, 6)
#: 前缀法失败时的邻近窗口 fallback（±20，最多 20 支）
RESERVE_NEIGHBOR_WINDOW = 20
RESERVE_NEIGHBOR_CAP = 20

#: 显式固定/刷怪表（实际怪组/效能）；按 stage id 覆盖推断候选。见 manual_spawns.json。
MANUAL_SPAWNS_FILE = Path(__file__).with_name("manual_spawns.json")


def _load_manual_spawns() -> dict[int, dict]:
    try:
        raw = json.loads(MANUAL_SPAWNS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    result: dict[int, dict] = {}
    for key, value in (raw or {}).items():
        try:
            mission_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("entries"), list):
            result[mission_id] = value
    return result


def _pool_prefixes(info: dict) -> list[str]:
    """``pool_prefix`` 归一化：支持单前缀字符串、逗号分隔或数组（多 id 族关卡）。"""
    raw = (info or {}).get("pool_prefix")
    items = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    prefixes: list[str] = []
    for item in items:
        prefix = str(item or "").strip()
        if prefix and prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes

#: 灰域真实区域层级：difficulty_group 1..4 有客户端名称（沙尘带/风暴带/硅状带/结晶带），
#: 组 5/6 与未映射节点归「特殊区域」；「装甲突击」（标题前缀）是爬塔模式，单独成区。
GRAY_REGION_DEFS: tuple[tuple[int, str], ...] = (
    (1, "sand"), (2, "storm"), (3, "silicon"), (4, "crystal"),
)
GRAY_REGION_FALLBACK_TITLES = {1: "沙尘带", 2: "风暴带", 3: "硅状带", 4: "结晶带"}
GRAY_REGION_ORDER = ("sand", "storm", "silicon", "crystal",
                     "armor_assault", "special")
ARMOR_ASSAULT_REGION_ID = "armor_assault"
ARMOR_ASSAULT_TITLE = "装甲突击"
ARMOR_ASSAULT_NOTE = "爬塔关卡，按节点逐个挑战"
SPECIAL_REGION_ID = "special"
SPECIAL_REGION_TITLE = "特殊区域"
SPECIAL_REGION_NOTE = ("组5/6/未映射节点（已把「装甲突击」爬塔节点拆出）；"
                       "客户端无区域名，不编造")

#: mission 文本 key 前缀：``mission-{10000000 + mission_id}``
MISSION_TEXT_BASE = 10_000_000

#: 章节组顺序与标题（v1.2：7 组）
GROUPS: tuple[tuple[str, str], ...] = (
    ("main", "主线"),
    ("event", "活动"),
    ("score", "积分关卡"),
    ("tutorial", "教学"),
    ("simulation", "模拟作战"),
    ("grayzone", "灰域探查"),
    ("orphan", "无固定关卡"),
)
GROUP_TITLES = dict(GROUPS)

#: 章节默认标签（活动内部还会按 往期复刻/特殊作战/积分关卡 细化）
GROUP_TAGS = {
    "main": ["主线"],
    "event": ["活动"],
    "score": ["积分关卡"],
    "tutorial": ["教学"],
    "simulation": ["模拟作战"],
    "grayzone": ["打灰"],
    "orphan": ["无固定关卡"],
}

#: -4040x 积分关卡的标题优先用 mission_event.event_name
#: （例如 -40403 的章节名是「慢休克」，但积分关卡名是「自画像」）
SCORE_SPECIAL_CAMPAIGNS: frozenset[int] = frozenset({-40401, -40402, -40403, -40404, -40405})

#: 模拟作战的固定 mission id 段（1104..1106 的 map_res 是 OPS5_Y，1701..1745 是靶场系列）
SIMULATION_ID_RANGES: tuple[tuple[int, int], ...] = ((1101, 1106), (1701, 1745))

#: 章节列表里关卡摘要的字段（v1.3 settlement / v1.4 support / v1.5 reserve）
STAGE_LIST_KEYS = (
    "id", "title", "code", "difficulty", "recommend_level",
    "team_count", "support_team_count", "reserve_team_count",
    "species_count", "tags", "order", "settlement",
)

#: 队伍详情里展示的数值键（contract §2.3 示例；只展示参数，不含技能）
STAT_KEYS = (
    "maxlife", "pow", "hit", "dodge", "armor", "armor_piercing",
    "range", "speed", "shield", "def", "crit", "crit_dmg", "tenacity",
)

#: 怪种 flag 类别（v1.2：非互斥）
SPECIES_CATEGORIES = ("normal", "grayzone", "orphan")

#: 排序方式（列表查询用）
SORT_MODES = ("default", "power_desc", "power_asc", "hp_desc", "units_desc")

_TAG_RE = re.compile(r"<[^>]*>")
_ICON_UNSAFE_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if number != number else number  # 过滤 NaN


def _json_num(value: Any) -> int | float:
    """把 float 收敛成 JSON 友好的数字（整数就写整数）。"""
    number = _float(value)
    if abs(number - round(number)) < 1e-9:
        return int(round(number))
    return round(number, 4)


def _stat_num(value: Any) -> int | float:
    """展示数值：整数保持整数，小数保留 2 位。"""
    number = _float(value)
    if abs(number - round(number)) < 1e-6:
        return int(round(number))
    return round(number, 2)


def _clean_text(value: Any) -> str:
    """客户端文本清洗：去 ``//n``/``<...>`` 富文本、取 ``|`` 前第一段、压空白。"""
    if value is None:
        return ""
    text = str(value).replace("//n", " ").replace("\u00a0", " ")
    text = _TAG_RE.sub(" ", text)
    text = text.split("|")[0]
    return " ".join(text.split()).strip()


def _is_collectable(value: Any) -> bool:
    """``targettrain_cancollect`` 兼容 int / str 两种存储。"""
    return str(value).strip() == "1"


def _icon_filename(code: Any) -> str | None:
    """code → ICON_DIR 下的图标文件名（小写，非字母数字转 ``_``）。"""
    code = str(code or "").strip()
    if not code:
        return None
    stem = _ICON_UNSAFE_RE.sub("_", code.lower()).strip("_")
    return f"{stem}.png" if stem else None


def _bundle_code_key(code: Any) -> str:
    """code → 游戏 ``character<code>.ab`` 的归一化 key（去掉所有非字母数字）。"""
    return re.sub(r"[^a-z0-9]+", "", str(code or "").lower())


def _optional_bool(value: Any) -> bool | None:
    """``power_known`` 之类的三态参数：None/'' → 不过滤；1/true/yes → True。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("", "all", "any", "none"):
        return None
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return None


def _has_plus(text: Any) -> bool:
    text = str(text or "")
    return "+" in text or "＋" in text


def _plain_text(text_map: dict[str, str], key: Any) -> str:
    """客户端文本的"保标签"清洗：只压空白，保留 ``<活动名>`` 之类的尖括号标题。"""
    raw = str((text_map or {}).get(str(key or ""), ""))
    return " ".join(raw.replace("\u00a0", " ").split()).strip()


def _parse_event_score(raw: Any) -> dict | None:
    """``mission.event_score`` → ``{"mode": "1", "params": 24}``（无配置返回 None）。

    格式：``mode|参数,参数,...``；``params`` = 第 2 段逗号分隔的参数个数
    （忽略空段，例如序列尾部多余的逗号）。
    """
    raw = str(raw or "").strip()
    if not raw:
        return None
    head, sep, tail = raw.partition("|")
    params = len([part for part in tail.split(",") if part.strip()]) if sep else 0
    return {"mode": head.strip(), "params": params}


def _parse_score_prize(raw: Any) -> dict | None:
    """``mission.score_prize`` → ``{"raw": ..., "tiers": 2}``（无配置返回 None）。

    格式：``tier-flag|奖励1,奖励2,...``；``tiers`` = 第 2 段逗号分组项数。
    """
    raw = str(raw or "").strip()
    if not raw:
        return None
    _, sep, tail = raw.partition("|")
    tiers = len([part for part in tail.split(",") if part.strip()]) if sep else 0
    return {"raw": raw, "tiers": tiers}


# ---------------------------------------------------------------------------
# 文件锁 / 原子写
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def _file_lock(timeout: float = 300.0) -> Iterator[None]:
    """跨进程构建锁（Windows 用 msvcrt，其它平台用 fcntl）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_FILE, "a+b")
    locked = False
    try:
        deadline = time.time() + timeout
        if os.name == "nt":  # pragma: no cover - Windows 分支
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    if time.time() > deadline:
                        raise RuntimeError(
                            f"另一个进程正在构建 catalog（等待 {LOCK_FILE.name} 超时 {timeout:.0f}s）")
                    time.sleep(0.2)
        else:  # pragma: no cover - 非 Windows 分支
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
        yield
    finally:
        if locked:
            try:
                if os.name == "nt":  # pragma: no cover
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _atomic_write(payload: dict) -> int:
    """原子写 catalog.json（同目录 tmp + os.replace），返回写入字节数。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = CATALOG_FILE.with_name(f"{CATALOG_FILE.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, CATALOG_FILE)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return len(raw)


def _icon_files() -> set[str]:
    """ICON_DIR 下现有图标文件名（小写比较）。"""
    try:
        files = {path.name.lower() for path in ICON_DIR.glob("*.png")}
    except OSError:
        return set()
    return files


def _source_mtime_ns() -> int:
    """所有数据源里最新的 mtime（用于 build 的缓存新鲜度判断）。"""
    latest = 0
    for path in (TEXT_FILE, MODEL_FILE, Path(__file__)):
        try:
            latest = max(latest, path.stat().st_mtime_ns)
        except OSError:
            pass
    # 图标目录：build_icons 重新导出后应触发 catalog 重建
    try:
        for path in ICON_DIR.glob("*.png"):
            try:
                latest = max(latest, path.stat().st_mtime_ns)
            except OSError:
                pass
    except OSError:
        pass
    try:
        from unit_model.core import stc

        stc_dir = stc.paths.stc_dir()
        mapping_dir = stc.mapping_dir()
    except Exception:  # noqa: BLE001 - 数据缺失时退化为只比文本/CSV
        return latest
    for directory, pattern in ((stc_dir, "*.stc"), (mapping_dir, "*.json")):
        try:
            files = directory.glob(pattern)
        except OSError:
            continue
        for path in files:
            try:
                latest = max(latest, path.stat().st_mtime_ns)
            except OSError:
                pass
    return latest


def _catalog_mtime_ns() -> int | None:
    try:
        return CATALOG_FILE.stat().st_mtime_ns
    except OSError:
        return None


def _read_payload() -> dict:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def _meta_from_payload(payload: dict, *, json_size: int | None = None) -> dict:
    meta = {
        "built_at": payload.get("built_at"),
        "counts": dict(payload.get("counts") or {}),
        "sources": dict(payload.get("sources") or {}),
        "elapsed_s": payload.get("elapsed_s"),
        "schema": payload.get("schema", SCHEMA_VERSION),
    }
    if json_size is not None:
        meta["json_size"] = json_size
    return meta


def _cached_meta(*, force: bool = False) -> dict | None:
    """缓存可用（存在且比所有数据源新）时返回 meta，否则 None。"""
    if force:
        return None
    mtime = _catalog_mtime_ns()
    if mtime is None:
        return None
    try:
        if mtime < _source_mtime_ns():
            return None
        payload = _read_payload()
        json_size = CATALOG_FILE.stat().st_size
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema") != SCHEMA_VERSION:
        return None
    return _meta_from_payload(payload, json_size=json_size)


# ---------------------------------------------------------------------------
# STC 解析 → payload
# ---------------------------------------------------------------------------
def _load_model_rows() -> list[dict]:
    if not MODEL_FILE.is_file():
        raise RuntimeError(
            f"缺 {MODEL_FILE.relative_to(ROOT)}：先跑 scripts/build_enemy_full_model.py")
    with MODEL_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_text() -> dict[str, str]:
    if not TEXT_FILE.is_file():
        return {}
    try:
        payload = json.loads(TEXT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 坏文件兜底
        raise RuntimeError(f"client_text.json 解析失败：{exc}") from exc
    return payload if isinstance(payload, dict) else {}


def _load_stc_tables() -> dict[str, Any]:
    """一次性读取需要的 STC 表（stc 模块内部按表缓存，重复调用便宜）。"""
    try:
        from unit_model.core import stc
    except Exception as exc:  # noqa: BLE001 - 数据缺失/依赖缺失都给出可操作提示
        raise RuntimeError(
            f"无法导入 unit_model.core.stc：{exc}；请在仓库根目录用系统 python 运行，"
            "并确认 local_paths.json 指向本机游戏目录") from exc

    def table(name: str) -> list[dict]:
        try:
            return stc.table(name)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"解析 STC 表 {name} 失败：{exc}") from exc

    return {
        "stc_module": stc,
        "enemy_team": table("enemy_team"),
        "enemy_in_team": table("enemy_in_team"),
        "enemy_character_type": table("enemy_character_type"),
        "enemy_illustration": table("enemy_illustration"),
        "mission": table("mission"),
        "spot": table("spot"),
        "mission_event": table("mission_event"),
        "normal_activity": table("normal_activity"),
        "rank": table("rank"),
        "daily_mission_group": table("daily_mission_group"),
        "daily_mission_difficulty_group": table("daily_mission_difficulty_group"),
    }


def _mission_text_key(mid: int) -> str:
    return f"mission-{MISSION_TEXT_BASE + mid}"


def _mission_title(mid: int, mission: dict | None, text: dict[str, str]) -> str:
    raw = ""
    if mission:
        raw = text.get(str(mission.get("name") or ""), "")
    if not raw:
        raw = text.get(_mission_text_key(mid), "")
    clean = _clean_text(raw)
    return clean or f"关卡 {mid}"


def _type_display_name(row: dict, text: dict[str, str]) -> str:
    name = _clean_text(text.get(str(row.get("name") or "")))
    if name:
        return name
    info = _clean_text(row.get("enemy_info"))
    if info and not info.startswith("enemy_character_type-"):
        return info
    return _clean_text(row.get("code")) or str(row.get("id") or "")


def _gray_area(title: str) -> str:
    """灰域区域 = 标题第一个 ``-`` 之前的前缀（去尾部编号/空格，兼容不换行空格）。"""
    title = _clean_text(title)
    if "-" in title:
        return title.split("-")[0].strip()
    return title.strip()


def _stage_tags(mission: dict | None) -> list[str]:
    if not mission:
        return ["普通"]
    emergency = _int(mission.get("if_emergency"))
    if emergency == 1:
        return ["紧急"]
    if emergency == 2:
        return ["模拟作战"]
    if emergency == 3:
        return ["复刻"]
    return ["普通"]


def _stage_code(mission: dict | None) -> str:
    """关卡显示编号：``{campaign}-{sub}``，紧急/模拟/复刻加后缀区分同名关卡。

    STC 里同一 campaign 的普通关、紧急关、模拟作战关会共用 sub（如 campaign 1 的
    ``1-1`` / ``1-1E`` / ``1-1M``），不加后缀会出现 4 个 ``1-1``。
    """
    if not mission:
        return ""
    emergency = _int(mission.get("if_emergency"))
    suffix = {1: "E", 2: "M", 3: "R"}.get(emergency, "")
    return f"{_int(mission.get('campaign'))}-{mission.get('sub')}{suffix}"


def _is_simulation_mission(mid: int, mission: dict) -> bool:
    map_res = str(mission.get("map_res_name") or "")
    if map_res.startswith("Moni"):
        return True
    return any(low <= mid <= high for low, high in SIMULATION_ID_RANGES)


def _classify_mission(
    mid: int,
    mission: dict,
    *,
    score_mission_ids: set[int],
) -> tuple[str | None, str | None]:
    """返回 ``(category, chapter_id)``；None 表示该关卡不产生章节。

    积分关卡 = ``mission.event_score`` 非空的 mission（mission 级，见任务 v1.4）；
    同一 campaign 的其它任务仍归 event 章节，全积分 campaign 只生成 score 章节。
    """
    campaign = _int(mission.get("campaign"))
    map_res = str(mission.get("map_res_name") or "")

    # 1. 灰域（不产关卡列表，单独成章）
    if campaign == -404:
        return ("grayzone", "grayzone")
    # 2. 教学：按 campaign 一章
    if -10006 <= campaign <= -10000:
        return ("tutorial", f"tutorial-{campaign}")
    # 3. 模拟作战/靶场（Moni 图 / 1101..1106 / 1701..1745）
    if _is_simulation_mission(mid, mission):
        return ("simulation", "simulation")
    # 4. 主线：campaign 0..13、id < 90000、非模拟作战地图
    if 0 <= campaign <= 13 and mid < 90000 and not map_res.startswith("Moni"):
        return ("main", f"main-{campaign}")
    # 5. 积分关卡：mission.event_score 非空（mission 级判定）
    if mid in score_mission_ids:
        return ("score", f"score-{campaign}")
    # 6. 其余全部并入活动（往期复刻 / 特殊作战 也在这里，靠 subtitle/tags 区分）
    return ("event", f"event-{campaign}")


def _build_payload() -> dict:
    """解析全部数据源，构造 catalog payload（纯函数，不写文件）。"""
    started = time.time()
    text = _load_text()
    tables = _load_stc_tables()
    model_rows = _load_model_rows()

    try:
        from unit_model.core import enemy as enemy_mod
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法导入 unit_model.core.enemy：{exc}") from exc

    # ---- 基础索引 -----------------------------------------------------
    teams_by_id: dict[int, dict] = {}
    for row in tables["enemy_team"]:
        teams_by_id[_int(row.get("id"))] = row

    slots_by_team: dict[int, list[dict]] = defaultdict(list)
    for row in tables["enemy_in_team"]:
        team_id = _int(row.get("enemy_team_id"))
        if team_id:
            slots_by_team[team_id].append(row)

    type_rows: dict[int, dict] = {}
    for row in tables["enemy_character_type"]:
        type_rows[_int(row.get("id"))] = row

    missions: dict[int, dict] = {}
    for row in tables["mission"]:
        missions[_int(row.get("id"))] = row

    # enemy_full_model.csv：type → codex / 阵营 / BOSS / 是否可契约捕获（只用映射与标签）
    type_codex: dict[int, int] = {}
    type_faction: dict[int, str] = {}
    type_boss: dict[int, bool] = {}
    type_capturable: dict[int, bool] = {}
    for row in model_rows:
        type_id = _int(row.get("type_id"))
        if not type_id:
            continue
        codex = _int(row.get("codex_no"))
        if codex:
            type_codex[type_id] = codex
        type_faction[type_id] = str(row.get("faction_name") or "")
        type_boss[type_id] = _int(row.get("boss")) == 1
        type_capturable[type_id] = str(row.get("capturable") or "").strip() == "1"

    # 图鉴（codex 编号 = enemy_illustration.id；名称 = 行内 name 文本 key）
    illustration_by_id: dict[int, list[dict]] = defaultdict(list)
    for row in tables["enemy_illustration"]:
        illustration_by_id[_int(row.get("id"))].append(row)
    for rows in illustration_by_id.values():
        rows.sort(key=lambda item: _int(item.get("sub_id")))

    # 活动 / 复刻名映射 + 积分关卡判定
    campaign_to_event: dict[int, str] = {}
    for row in tables["mission_event"]:
        event_name = _clean_text(text.get(str(row.get("event_name") or ""), ""))
        for part in str(row.get("mission_campaign") or "").split(","):
            part = part.strip()
            if part and part.lstrip("-").isdigit():
                campaign_to_event.setdefault(_int(part), event_name)
    campaign_to_act: dict[int, dict] = {}
    for row in tables["normal_activity"]:
        campaign_to_act[_int(row.get("campaign_id"))] = {
            "name": _clean_text(text.get(str(row.get("name") or ""), "")),
            "chapter_name": _clean_text(text.get(str(row.get("chapter_name") or ""), "")),
            "tag": _clean_text(text.get(str(row.get("tag") or ""), "")),
        }
    # 含「+」的活动 campaign（用于 event 章节的「往期复刻」标记，如 魔方行动+ -6/-7；
    # 是否积分关卡由 mission.event_score 决定，见 mission_teams 构建后的判定）
    plus_campaigns: set[int] = set()
    for campaign, activity in campaign_to_act.items():
        if _has_plus(activity.get("chapter_name")):
            plus_campaigns.add(campaign)
    for campaign, event_name in campaign_to_event.items():
        if _has_plus(event_name):
            plus_campaigns.add(campaign)

    # ---- 积分榜（rank 表）：sub_type 逗号列表就是 mission id -----------------
    # 同一 mission 多行时优先 type=10「常驻积分榜」，其次 type=6「活动积分榜」。
    rank_priority = {10: 0, 6: 1}
    mission_rank: dict[int, dict] = {}
    for row in tables["rank"]:
        rank_type = _int(row.get("type"))
        priority = rank_priority.get(rank_type)
        if priority is None:
            continue
        rank_payload = {
            "id": _int(row.get("id")),
            "name": _plain_text(text, row.get("name")),
            "title": _plain_text(text, row.get("title")),
            "type": rank_type,
            "score_rewards": str(row.get("score_rewards") or ""),
        }
        for token in str(row.get("sub_type") or "").split(","):
            token = token.strip()
            if not token.lstrip("-").isdigit():
                continue
            mission_id = _int(token)
            current = mission_rank.get(mission_id)
            if current is None or priority < rank_priority.get(current["type"], 99):
                mission_rank[mission_id] = dict(rank_payload)

    # ---- 可收藏有效队伍 -------------------------------------------------
    collectable: set[int] = {
        team_id for team_id, row in teams_by_id.items()
        if _is_collectable(row.get("targettrain_cancollect")) and slots_by_team.get(team_id)
    }

    # ---- 队伍 ↔ 关卡关联（spot ∪ boss_team_id） ------------------------
    mission_teams: dict[int, set[int]] = defaultdict(set)
    team_missions: dict[int, set[int]] = defaultdict(set)
    for row in tables["spot"]:
        team_id = _int(row.get("enemy_team_id"))
        mission_id = _int(row.get("mission_id"))
        if team_id > 0 and mission_id > 0 and team_id in collectable:
            mission_teams[mission_id].add(team_id)
            team_missions[team_id].add(mission_id)
    for mission_id, mission in missions.items():
        raw = str(mission.get("boss_team_id") or "")
        for token in re.split(r"[;,]", raw):
            token = token.strip()
            if not token.lstrip("-").isdigit():
                continue
            team_id = _int(token)
            if team_id in collectable:
                mission_teams[mission_id].add(team_id)
                team_missions[team_id].add(mission_id)

    # ---- 积分关卡判定（权威字段：mission.event_score 非空，mission 级） ----
    # 用户实测：积分关卡是 mission 级而不是 campaign 级。
    # 只有 event_score 非空、且该 mission 有可收藏队伍、且不是灰域的任务才算积分关卡；
    # 同一 campaign 的其它任务仍留在 event 章节（混合活动会拆成 event+score 两章）。
    score_mission_ids: set[int] = set()
    for mission_id in mission_teams:
        mission = missions.get(mission_id)
        if mission is None:
            continue
        if _int(mission.get("campaign")) == -404:
            continue
        if str(mission.get("event_score") or "").strip():
            score_mission_ids.add(mission_id)
    score_campaigns: set[int] = {
        _int((missions.get(mid) or {}).get("campaign")) for mid in score_mission_ids
    }

    # ---- 关卡归类 → 章节骨架（每个 campaign 一章，不跨 campaign 合并） --
    gray_stage_ids: list[int] = []
    mid_chapter: dict[int, str] = {}
    chapters: dict[str, dict] = {}
    chapter_campaign: dict[str, int | None] = {}

    for mission_id in mission_teams:
        mission = missions.get(mission_id)
        if mission is None:
            # spot 里有 mission_id 不在 mission 表（例 404101）→ 「特殊作战·未知」
            chapter = chapters.setdefault("event-unknown", {
                "category": "event",
                "kind": "unknown",
                "title": "特殊作战·未知",
                "subtitle": "mission 表缺失的节点",
                "tags": ["特殊作战"],
                "stage_ids": [],
            })
            chapter["stage_ids"].append(mission_id)
            mid_chapter[mission_id] = "event-unknown"
            continue
        category, chapter_id = _classify_mission(
            mission_id, mission, score_mission_ids=score_mission_ids)
        if category is None:
            continue
        campaign = _int(mission.get("campaign"))
        if category == "grayzone":
            gray_stage_ids.append(mission_id)
            mid_chapter[mission_id] = "grayzone"
            continue
        chapter = chapters.get(chapter_id)
        if chapter is None:
            chapter = chapters[chapter_id] = {
                "category": category,
                "kind": "normal",
                "title": "",
                "subtitle": "",
                "tags": list(GROUP_TAGS.get(category, [])),
                "stage_ids": [],
            }
            chapter_campaign[chapter_id] = campaign
        chapter["stage_ids"].append(mission_id)
        mid_chapter[mission_id] = chapter_id

    # ---- 支援队伍链接（spot.ally_team_id；只收"该队伍有槽位"的，支援与敌方分开） --
    support_team_missions: dict[int, set[int]] = defaultdict(set)
    support_mission_teams: dict[int, list[int]] = defaultdict(list)
    support_row_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    all_support_team_ids: set[int] = set()
    for row in tables["spot"]:
        team_id = _int(row.get("ally_team_id"))
        mission_id = _int(row.get("mission_id"))
        if team_id > 0:
            all_support_team_ids.add(team_id)
        if team_id <= 0 or mission_id <= 0 or not slots_by_team.get(team_id):
            continue
        support_team_missions[team_id].add(mission_id)
        if team_id not in support_mission_teams[mission_id]:
            support_mission_teams[mission_id].append(team_id)
        support_row_counts[mission_id][team_id] += 1
    stage_mission_ids = set(mission_teams)

    def _is_gray_mission(mission_id: int) -> bool:
        return _int((missions.get(mission_id) or {}).get("campaign")) == -404

    # ---- 机场/后续刷新候选（reserve，推断） ----------------------------
    # STC 没有显式 mission→机场刷新池映射，只能按 team id 族推断：
    # 1) 对已引用队伍（enemy ∪ ally ∪ boss，排除 id<=1000）从 3/4/5/6 位前缀依次尝试，
    #    取**最短**且覆盖 >=3 个引用队伍的前缀；**积分关卡**阈值降到 >=2，且同长度取
    #    全部合格前缀的**并集**（引用跨多个 id 族时不漏族）；普通关卡仍只取覆盖最多的
    #    单前缀（同长度取覆盖最多、再按前缀字典序）；
    # 2) 候选 = 同前缀、有槽位、可收藏、未被引用的队伍（id 升序；普通关 <=80，积分关不设限）；
    # 3) 积分关卡前缀法失败时，先继承同 campaign 兄弟关已确认的 id 族（只继承与本关
    #    引用同族的前缀），仍不行才 fallback：引用 id ±20 邻近窗口（普通关 <=20）。
    prefix_lists: dict[int, dict[str, list[int]]] = {
        length: defaultdict(list) for length in RESERVE_PREFIX_LENGTHS
    }
    for collectable_id in collectable:
        if collectable_id <= 1000:      # 低 id 是教程/通用队伍，不作为候选
            continue
        id_text = str(collectable_id)
        for length in RESERVE_PREFIX_LENGTHS:
            if len(id_text) >= length:
                prefix_lists[length][id_text[:length]].append(collectable_id)
    for prefix_map in prefix_lists.values():
        for ids in prefix_map.values():
            ids.sort()
    stage_reserve_teams: dict[int, list[int]] = {}
    stage_reserve_meta: dict[int, dict] = {}

    def _referenced_ids(mission_id: int) -> tuple[set[int], list[int]]:
        referenced = set(mission_teams.get(mission_id, set()))
        referenced |= set(support_mission_teams.get(mission_id, set()))
        return referenced, [team_id for team_id in referenced if team_id > 1000]

    def _prefix_options(ref_ids: list[int], *, min_refs: int,
                        union: bool) -> tuple[int, list[tuple[int, str]]]:
        """最短可用前缀长度上的合格前缀（count, prefix）列表。

        union=True 时返回该长度**全部**合格前缀（多 id 族并集，积分关卡用）；
        union=False 只保留覆盖最多的一个（普通关卡，控制列表体积）。
        """
        for length in RESERVE_PREFIX_LENGTHS:
            tally: Counter = Counter(
                str(team_id)[:length] for team_id in ref_ids
                if len(str(team_id)) >= length
            )
            options = [(count, prefix) for prefix, count in tally.items()
                       if count >= min_refs]
            if not options:
                continue
            options.sort(key=lambda item: (-item[0], item[1]))
            return length, options if union else options[:1]
        return 0, []

    def _pool_of(chosen: list[tuple[int, str]]) -> set[int]:
        pool: set[int] = set()
        for length, prefix in chosen:
            pool.update(prefix_lists[length].get(prefix, []))
        return pool

    def _record(mission_id: int, candidates: list[int], *,
                chosen: list[tuple[int, str]], refs: int,
                method: str, inherited: bool = False) -> None:
        stage_reserve_teams[mission_id] = candidates
        stage_reserve_meta[mission_id] = {
            "prefix": ",".join(prefix for _length, prefix in chosen),
            "prefixes": [prefix for _length, prefix in chosen],
            "prefix_length": chosen[0][0] if chosen else 0,
            "refs": refs,
            "method": method,
            "count": len(candidates),
            **({"inherited": True} if inherited else {}),
        }

    deferred: list[int] = []
    for mission_id in mission_teams:
        referenced, ref_ids = _referenced_ids(mission_id)
        candidates: list[int] = []
        chosen: list[tuple[int, str]] = []
        chosen_count = 0
        if ref_ids:
            is_score = mission_id in score_mission_ids
            chosen_length, options = _prefix_options(
                ref_ids, min_refs=2 if is_score else 3, union=is_score)
            chosen = [(chosen_length, prefix) for _count, prefix in options]
            chosen_count = sum(count for count, _prefix in options)
            if chosen:
                candidates = sorted(team_id for team_id in _pool_of(chosen)
                                    if team_id not in referenced)
                # 积分关卡容易有大量机场/后续刷新队伍；不设 80 上限，避免把真实候选截掉。
                # 普通关卡仍用上限控制缓存/页面体积。
                if not is_score:
                    candidates = candidates[:RESERVE_CAP]
        if candidates:
            _record(mission_id, candidates, chosen=chosen,
                    refs=chosen_count, method="prefix")
        else:
            deferred.append(mission_id)

    # ---- 同 campaign 前缀继承（仅积分关卡） ----------------------------
    # 引用太少触发不了前缀法的积分关卡（如 10520/10521 只有 2 支 941xxx、11101 只有
    # 1 支 652xxx），复用同活动兄弟关已确认的 id 族；只继承与本关引用同族的前缀，
    # 避免 ±20 邻近窗口漏掉大半池子（941 池 160 支窗口只捞 14/20 支）。
    campaign_prefixes: dict[int, set[tuple[int, str]]] = defaultdict(set)
    for mission_id, meta in stage_reserve_meta.items():
        if mission_id not in score_mission_ids:
            continue
        campaign = _int((missions.get(mission_id) or {}).get("campaign"))
        length = _int(meta.get("prefix_length"))
        if not campaign or not length:
            continue
        for prefix in meta.get("prefixes") or []:
            if prefix:
                campaign_prefixes[campaign].add((length, prefix))
    neighbor_fallback: list[int] = []
    for mission_id in deferred:
        referenced, ref_ids = _referenced_ids(mission_id)
        inherited: list[tuple[int, str]] = []
        if mission_id in score_mission_ids and ref_ids:
            campaign = _int((missions.get(mission_id) or {}).get("campaign"))
            inherited = [(length, prefix)
                         for length, prefix in sorted(campaign_prefixes.get(campaign, set()))
                         if any(str(ref_id).startswith(prefix) for ref_id in ref_ids)]
        candidates: list[int] = []
        if inherited:
            candidates = sorted(team_id for team_id in _pool_of(inherited)
                                if team_id not in referenced)
        if candidates:
            _record(mission_id, candidates, chosen=inherited,
                    refs=0, method="prefix", inherited=True)
        else:
            neighbor_fallback.append(mission_id)

    for mission_id in neighbor_fallback:
        referenced, ref_ids = _referenced_ids(mission_id)
        candidates = []
        if ref_ids:
            # fallback：引用 id 邻近窗口（±20）
            nearest_distance: dict[int, int] = {}
            for team_id in collectable:
                if team_id <= 1000 or team_id in referenced:
                    continue
                distance = min(abs(team_id - ref_id) for ref_id in ref_ids)
                if distance <= RESERVE_NEIGHBOR_WINDOW:
                    nearest_distance[team_id] = distance
            candidates = [team_id for team_id, _distance in
                          sorted(nearest_distance.items(),
                                 key=lambda item: (item[1], item[0]))]
            if mission_id not in score_mission_ids:
                candidates = candidates[:RESERVE_NEIGHBOR_CAP]
        if candidates:
            _record(mission_id, candidates, chosen=[],
                    refs=0, method="neighbor")
    reserve_team_missions: dict[int, list[int]] = defaultdict(list)
    for mission_id, team_ids in stage_reserve_teams.items():
        for team_id in team_ids:
            reserve_team_missions[team_id].append(mission_id)
    for ids in reserve_team_missions.values():
        ids.sort()

    # ---- 显式怪组表：固定/刷怪表 + 表中没有的「未实际出现怪组」 ----
    manual_effects: dict[int, int] = {}
    manual_spawns = _load_manual_spawns()
    for mission_id, info in manual_spawns.items():
        entries = [entry for entry in info.get("entries") or []
                   if isinstance(entry, dict) and _int(entry.get("team")) > 0]
        if not entries:
            continue
        actual_ids = sorted({_int(entry.get("team")) for entry in entries})
        pool_prefixes = _pool_prefixes(info)
        possible_ids = sorted(team_id for team_id in collectable
                              if pool_prefixes
                              and any(str(team_id).startswith(prefix)
                                      for prefix in pool_prefixes))
        stage_team_ids = set(mission_teams.get(mission_id, set()))
        actual_visible = [team_id for team_id in actual_ids
                          if team_id not in stage_team_ids]
        not_appeared = [team_id for team_id in possible_ids
                        if team_id not in set(actual_ids)
                        and team_id not in stage_team_ids]
        reserve_ids = actual_visible + not_appeared
        stage_reserve_teams[mission_id] = reserve_ids
        stage_reserve_meta[mission_id] = {
            "method": "manual",
            "prefix": ",".join(pool_prefixes),
            "prefixes": pool_prefixes,
            "prefix_length": min((len(prefix) for prefix in pool_prefixes),
                                 default=0),
            "refs": len(actual_ids),
            "count": len(reserve_ids),
            "title": str(info.get("title") or ""),
            "author": str(info.get("author") or ""),
            "source_url": str(info.get("source_url") or ""),
            "entries": entries,
            "actual_count": len(actual_ids),
            "spawn_count": len(actual_visible),
            "not_appeared_count": len(not_appeared),
            "possible_count": len(possible_ids),
            "in_stage_count": len(actual_ids) - len(actual_visible),
        }
        for team_id in reserve_ids:
            missions_list = reserve_team_missions.setdefault(team_id, [])
            if mission_id not in missions_list:
                missions_list.append(mission_id)
                missions_list.sort()
        for entry in entries:
            power = _int(entry.get("power"))
            if power:
                manual_effects[_int(entry.get("team"))] = power

    # ---- 队伍记录（详情数值按需计算，这里只存紧凑索引） ----------------
    team_records: list[dict] = []
    team_species: dict[int, set[int]] = {}
    team_flags: dict[int, dict] = {}
    team_gray_mission_count: dict[int, int] = {}
    used_type_ids: set[int] = set()
    type_slot_counts: Counter = Counter()

    def scaled_attributes(type_id: int, level: int):
        try:
            return enemy_mod.enemy_attributes(type_id, level, scale_by_level=True)
        except (KeyError, ValueError):
            return None

    for team_id in sorted(collectable):
        team_row = teams_by_id[team_id]
        raw_slots = sorted(
            slots_by_team[team_id],
            key=lambda item: (_float(item.get("coordinator_x")),
                              -_float(item.get("coordinator_y"))),
        )
        slots: list[list] = []
        species: set[int] = set()
        faction_counter: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        hp_total = 0.0
        has_boss = False
        full_forcefield = False
        batch_max = 0
        for slot in raw_slots:
            type_id = _int(slot.get("enemy_character_type_id"))
            level = _int(slot.get("level"))
            number = max(1, _int(slot.get("number"), 1))
            def_percent = _float(slot.get("def_percent"))
            batch = _int(slot.get("batch"))
            x = _float(slot.get("coordinator_x"))
            y = _float(slot.get("coordinator_y"))
            used_type_ids.add(type_id)
            type_slot_counts[type_id] += 1
            batch_max = max(batch_max, batch)
            codex = type_codex.get(type_id, 0)
            if codex:
                species.add(codex)
            faction = type_faction.get(type_id) or ""
            if faction:
                faction_counter[faction][0] += 1
                faction_counter[faction][1] += max(
                    1.0, _float((type_rows.get(type_id) or {}).get("maxlife")))
            if type_boss.get(type_id):
                has_boss = True
            if def_percent >= 100:
                full_forcefield = True
            attributes = scaled_attributes(type_id, level)
            if attributes is not None:
                hp_total += attributes.get("maxlife") * number
                if not faction:
                    faction_counter["其它"][0] += 1
            slots.append([
                type_id, level, number, _json_num(def_percent), batch,
                _json_num(x), _json_num(y),
            ])

        appearances = sorted(team_missions.get(team_id, ()))
        support_appearances = sorted(support_team_missions.get(team_id, ()))
        enemy_stage = [mid for mid in appearances if mid in stage_mission_ids]
        support_stage = [mid for mid in support_appearances if mid in stage_mission_ids]
        stage_appearances = enemy_stage + [mid for mid in support_stage
                                           if mid not in set(enemy_stage)]
        # 代表出处：优先敌方固定关卡，其次支援固定关卡
        rep_stage = None
        for pool in (enemy_stage, support_stage):
            non_gray = [mid for mid in pool if not _is_gray_mission(mid)]
            if non_gray:
                rep_stage = min(
                    non_gray,
                    key=lambda mid: (_int((missions.get(mid) or {}).get("order")), mid),
                )
                break
        is_gray = any(_is_gray_mission(mid) for mid in stage_appearances)
        is_orphan = not appearances and not support_appearances
        roles: list[str] = []
        if appearances:
            roles.append("enemy")
        if support_appearances:
            roles.append("support")
        team_flags[team_id] = {
            "fixed": any(not _is_gray_mission(mid) for mid in stage_appearances),
            "gray": is_gray,
            "orphan": is_orphan,
        }
        team_species[team_id] = species

        if faction_counter:
            faction_name = max(
                faction_counter,
                key=lambda name: (faction_counter[name][0], faction_counter[name][1]),
            )
        else:
            faction_name = "其它"

        tags: list[str] = []
        if has_boss:
            tags.append("BOSS")
        if full_forcefield:
            tags.append("满力场")

        power = _int(team_row.get("effect_ext")) or manual_effects.get(team_id, 0)
        team_records.append({
            "id": team_id,
            "power": power,
            "power_known": power != 0,
            "units": len(slots),
            "hp_total": int(round(hp_total)),
            "faction": faction_name,
            "tags": tags,
            "species": sorted(species),
            "members": slots,
            "appearances": appearances,
            "support_appearances": support_appearances,
            "reserve_appearances": sorted(reserve_team_missions.get(team_id, ())),
            "roles": roles,
            "collectable": True,
            "gray_zone": is_gray,
            "orphan": is_orphan,
            "rep_stage": rep_stage,
            "fight_type": _int(team_row.get("fight_type")),
            "use_building": str(team_row.get("use_building") or ""),
            "batch_max": batch_max,
        })

    # ---- 不可收藏的支援队伍（仅用于 stage.support_teams 展示） ----------
    support_only_records: list[dict] = []

    def build_support_only_record(team_id: int) -> dict:
        team_row = teams_by_id.get(team_id) or {}
        raw_slots = sorted(
            slots_by_team.get(team_id, []),
            key=lambda item: (_float(item.get("coordinator_x")),
                              -_float(item.get("coordinator_y"))),
        )
        slots: list[list] = []
        species: set[int] = set()
        faction_counter: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        hp_total = 0.0
        has_boss = False
        for slot in raw_slots:
            type_id = _int(slot.get("enemy_character_type_id"))
            level = _int(slot.get("level"))
            number = max(1, _int(slot.get("number"), 1))
            used_type_ids.add(type_id)
            type_slot_counts[type_id] += 1
            codex = type_codex.get(type_id, 0)
            if codex:
                species.add(codex)
            faction = type_faction.get(type_id) or ""
            if faction:
                faction_counter[faction][0] += 1
                faction_counter[faction][1] += max(
                    1.0, _float((type_rows.get(type_id) or {}).get("maxlife")))
            if type_boss.get(type_id):
                has_boss = True
            attributes = scaled_attributes(type_id, level)
            if attributes is not None:
                hp_total += attributes.get("maxlife") * number
            slots.append([
                type_id, level, number, _json_num(_float(slot.get("def_percent"))),
                _int(slot.get("batch")), _json_num(_float(slot.get("coordinator_x"))),
                _json_num(_float(slot.get("coordinator_y"))),
            ])
        faction_name = (max(faction_counter,
                           key=lambda name: (faction_counter[name][0],
                                             faction_counter[name][1]))
                        if faction_counter else "其它")
        support_appearances = sorted(support_team_missions.get(team_id, ()))
        power = _int(team_row.get("effect_ext")) or manual_effects.get(team_id, 0)
        return {
            "id": team_id,
            "power": power,
            "power_known": power != 0,
            "units": len(slots),
            "hp_total": int(round(hp_total)),
            "faction": faction_name,
            "tags": (["BOSS"] if has_boss else []),
            "species": sorted(species),
            "members": slots,
            "appearances": [],
            "support_appearances": support_appearances,
            "roles": ["support"],
            "collectable": False,
            "gray_zone": any(_is_gray_mission(mid) for mid in support_appearances),
            "orphan": False,
            "rep_stage": None,
            "fight_type": _int(team_row.get("fight_type")),
            "use_building": str(team_row.get("use_building") or ""),
            "batch_max": 0,
        }

    for team_id in sorted(set(support_team_missions) - collectable):
        support_only_records.append(build_support_only_record(team_id))

    # ---- 类型标签 + 图标（成员/怪种展示用；不含任何技能信息） ----------
    icon_file_set = _icon_files()
    type_info: dict[str, dict] = {}
    for type_id in used_type_ids:
        row = type_rows.get(type_id) or {}
        code = str(row.get("code") or "")
        icon = _icon_filename(code)
        type_info[str(type_id)] = {
            "code": code,
            "name": _type_display_name(row, text) if row else str(type_id),
            "codex_no": type_codex.get(type_id, 0),
            "faction": type_faction.get(type_id) or "",
            "boss": 1 if type_boss.get(type_id) else 0,
            "icon": icon if icon and icon in icon_file_set else None,
        }

    # ---- 怪种（264 个可收藏 codex；v1.2 非互斥 flag） ------------------
    codex_types: dict[int, set[int]] = defaultdict(set)
    for type_id, codex in type_codex.items():
        if type_id in used_type_ids:
            codex_types[codex].add(type_id)

    species_items: list[dict] = []
    codex_rep_type: dict[int, int] = {}
    for codex_no in sorted(codex_types):
        member_teams = sorted(team_id for team_id in collectable
                              if codex_no in team_species.get(team_id, ()))
        if not member_teams:
            continue
        used_types = sorted(codex_types[codex_no])
        # 代表类型 = 该 codex 在可收藏队伍里出现次数（槽位数）最多的 type
        rep_type = max(used_types, key=lambda tid: (type_slot_counts.get(tid, 0), -tid))
        codex_rep_type[codex_no] = rep_type
        illu_rows = illustration_by_id.get(codex_no) or []
        illu = illu_rows[0] if illu_rows else None
        if illu is not None:
            name = _clean_text(text.get(str(illu.get("name") or ""), ""))
            species_type = _int(illu.get("type"))
        else:
            name = ""
            species_type = _int((type_rows.get(rep_type) or {}).get("type"))
        if not name:
            # 少数灰域 BOSS codex 在 enemy_illustration 里没有行：退化用类型名
            fallback = ""
            for type_id in used_types:
                row = type_rows.get(type_id) or {}
                fallback = _clean_text(text.get(str(row.get("name") or ""), ""))
                if fallback:
                    break
            if fallback:
                info = " ".join(str((type_rows.get(type_id) or {}).get("enemy_info") or "")
                                for type_id in used_types)
                name = f"{fallback}（灰域Boss）" if "灰域" in info else f"{fallback}（图鉴 {codex_no}）"
            else:
                name = f"图鉴 {codex_no}"
        faction_counter: dict[str, int] = defaultdict(int)
        for type_id in used_types:
            faction = type_faction.get(type_id) or ""
            if faction:
                faction_counter[faction] += 1
        faction = (max(faction_counter, key=lambda key: faction_counter[key])
                   if faction_counter else "")
        capturable = any(type_capturable.get(type_id) for type_id in used_types)

        has_normal = any(team_flags[tid]["fixed"] for tid in member_teams)
        has_grayzone = any(team_flags[tid]["gray"] for tid in member_teams)
        has_orphan = any(team_flags[tid]["orphan"] for tid in member_teams)
        category = "normal" if has_normal else ("grayzone" if has_grayzone else
                                              ("orphan" if has_orphan else "normal"))
        rep_code = str((type_rows.get(rep_type) or {}).get("code") or "")
        icon = _icon_filename(rep_code)
        species_items.append({
            "codex_no": codex_no,
            "name": name,
            "faction": faction,
            "type": species_type,
            "capturable": bool(capturable),
            "tags": ["契约捕获"] if capturable else [],
            "category": category,
            "has_normal": bool(has_normal),
            "has_grayzone": bool(has_grayzone),
            "has_orphan": bool(has_orphan),
            "team_count": len(member_teams),
            "normal_team_count": sum(1 for tid in member_teams if team_flags[tid]["fixed"]),
            "gray_zone_team_count": sum(1 for tid in member_teams if team_flags[tid]["gray"]),
            "orphan_team_count": sum(1 for tid in member_teams if team_flags[tid]["orphan"]),
            "icon": icon if icon and icon in icon_file_set else None,
            "teams": member_teams,
        })
    species_by_codex = {item["codex_no"]: item for item in species_items}

    # ---- 关卡记录 ------------------------------------------------------
    stage_records: list[dict] = []
    stage_by_id: dict[int, dict] = {}
    for mission_id, team_ids in mission_teams.items():
        mission = missions.get(mission_id)
        if mission is not None:
            campaign = _int(mission.get("campaign"))
            title = _mission_title(mission_id, mission, text)
            code = _stage_code(mission)
            difficulty = _int(mission.get("difficulty"))
            recommend_level = _int(mission.get("recommend_gun_level"))
            order = _int(mission.get("order"))
            tags = _stage_tags(mission)
        else:
            title = f"未知节点 {mission_id}"
            code = str(mission_id)
            difficulty = 0
            recommend_level = 0
            order = 0
            tags = ["普通"]
        species_union: set[int] = set()
        for team_id in team_ids:
            species_union |= team_species.get(team_id, set())
        # 结算形式结构化（v1.3）：score=event_score 结算，normal=普通结算
        event_score = _parse_event_score((mission or {}).get("event_score"))
        settlement = {
            "type": "score" if event_score else "normal",
            "event_score": event_score,
            "score_prize": _parse_score_prize((mission or {}).get("score_prize")),
            "rank": mission_rank.get(mission_id),
        }
        record = {
            "id": mission_id,
            "chapter_id": mid_chapter.get(mission_id, ""),
            "title": title,
            "code": code,
            "difficulty": difficulty,
            "recommend_level": recommend_level,
            "team_count": len(team_ids),
            "support_team_count": len(support_mission_teams.get(mission_id, [])),
            "reserve_team_count": len(stage_reserve_teams.get(mission_id, [])),
            "species_count": len(species_union),
            "tags": tags,
            "order": order,
            "gray_zone": _int((mission or {}).get("campaign")) == -404,
            "settlement": settlement,
        }
        stage_records.append(record)
        stage_by_id[mission_id] = record

    # ---- 灰域区域层级（region = 沙尘带/风暴带/硅状带/结晶带/特殊区域） --------
    # daily_mission_group：mission id 逗号列表 → difficulty_group；
    # daily_mission_difficulty_group 的 1..4 有客户端名称，5/6/未映射归「特殊区域」。
    mission_difficulty_groups: dict[int, set[int]] = defaultdict(set)
    for row in tables["daily_mission_group"]:
        group_no = _int(row.get("difficulty_group"))
        if group_no <= 0:
            continue
        for token in str(row.get("mission_group") or "").split(","):
            token = token.strip()
            if token.isdigit():
                mission_difficulty_groups[int(token)].add(group_no)
    difficulty_rows = {_int(row.get("id")): row
                       for row in tables["daily_mission_difficulty_group"]}
    region_meta: dict[int, dict] = {}
    for group_no, region_id in GRAY_REGION_DEFS:
        row = difficulty_rows.get(group_no) or {}
        source_key = str(row.get("name") or "")
        title = (_clean_text(text.get(source_key, ""))
                 or GRAY_REGION_FALLBACK_TITLES[group_no])
        region_meta[group_no] = {"id": region_id, "title": title,
                                 "source": source_key or None}

    def gray_stage_region(mission_id: int) -> str:
        groups = mission_difficulty_groups.get(mission_id) or set()
        for group_no, region_id in GRAY_REGION_DEFS:
            if group_no in groups:
                return region_id
        return SPECIAL_REGION_ID

    # ---- 灰域节点 / 区域（v1.8：区域→节点；装甲突击单独爬塔模式） ----------
    all_gray_missions = [mid for mid, mission in missions.items()
                         if _int(mission.get("campaign")) == -404]
    gray_set_for_teams = set(gray_stage_ids)
    area_stage_ids: dict[str, list[int]] = defaultdict(list)   # 地点 → 有可收藏队伍的节点
    area_all_count: Counter = Counter()                        # 地点 → 全部灰域节点数
    area_team_ids: dict[str, set[int]] = defaultdict(set)
    area_region_ids: dict[str, set[str]] = defaultdict(set)
    region_stage_ids: dict[str, list[int]] = defaultdict(list)
    region_team_ids: dict[str, set[int]] = defaultdict(set)
    for mission_id in all_gray_missions:
        mission = missions.get(mission_id) or {}
        location = _gray_area(_mission_title(mission_id, mission, text)) or "未分类"
        area_all_count[location] += 1
        mission_region_id = gray_stage_region(mission_id)
        if location == ARMOR_ASSAULT_TITLE:
            mission_region_id = ARMOR_ASSAULT_REGION_ID   # 爬塔单独成区
        if mission_id in gray_set_for_teams:
            area_stage_ids[location].append(mission_id)
            area_team_ids[location] |= mission_teams.get(mission_id, set())
            area_region_ids[location].add(mission_region_id)
            region_stage_ids[mission_region_id].append(mission_id)
            region_team_ids[mission_region_id] |= mission_teams.get(mission_id, set())
    # 没有可收藏队伍的地点（庇护所旧址 / 坍缩狭缝）也按 mission 的 difficulty_group 标 region_ids
    for mission_id in all_gray_missions:
        mission = missions.get(mission_id) or {}
        location = _gray_area(_mission_title(mission_id, mission, text)) or "未分类"
        if area_stage_ids.get(location):
            continue
        area_region_ids[location].add(gray_stage_region(mission_id))
    areas: list[dict] = []
    for area in sorted(area_all_count,
                       key=lambda key: (-len(area_stage_ids.get(key, [])),
                                        -len(area_team_ids.get(key, set())),
                                        -area_all_count[key], key)):
        area_species: set[int] = set()
        for team_id in area_team_ids.get(area, set()):
            area_species |= team_species.get(team_id, set())
        areas.append({
            "id": area,
            "title": area,
            "region_ids": [region_id for region_id in GRAY_REGION_ORDER
                           if region_id in area_region_ids.get(area, set())],
            "stage_count": len(area_stage_ids.get(area, [])),
            "team_count": len(area_team_ids.get(area, set())),
            "species_count": len(area_species),
        })
    # 节点（= 有可收藏队伍的 mission），按区域归组；top_species 最多 4 个
    nodes: list[dict] = []
    for region_id in GRAY_REGION_ORDER:
        for mission_id in sorted(region_stage_ids.get(region_id, [])):
            mission = missions.get(mission_id) or {}
            stage = stage_by_id.get(mission_id) or {}
            title = _mission_title(mission_id, mission, text)
            location = _gray_area(title) or "未分类"
            team_ids = mission_teams.get(mission_id, set())
            codex_counts: Counter = Counter()
            for team_id in team_ids:
                for codex_no in team_species.get(team_id, set()):
                    codex_counts[codex_no] += 1
            top_species = [codex_no for codex_no, _count in
                           sorted(codex_counts.items(),
                                  key=lambda item: (-item[1], item[0]))[:4]]
            nodes.append({
                "mission_id": mission_id,
                "title": title,
                "location": location,
                "region_id": region_id,
                "difficulty": _int(stage.get("difficulty")),
                "team_count": len(team_ids),
                "species_count": len(codex_counts),
                "top_species": top_species,
                "tags": list(stage.get("tags") or []),
            })
    # 真实区域（6 个：4 个区域 + 装甲突击爬塔 + 特殊区域）
    regions: list[dict] = []
    for region_id in GRAY_REGION_ORDER:
        stage_ids = region_stage_ids.get(region_id, [])
        region_species: set[int] = set()
        for team_id in region_team_ids.get(region_id, set()):
            region_species |= team_species.get(team_id, set())
        if region_id == ARMOR_ASSAULT_REGION_ID:
            groups = [5, 6]
            title = ARMOR_ASSAULT_TITLE
            kind = "tower"
            source = None
            note = ARMOR_ASSAULT_NOTE
        elif region_id == SPECIAL_REGION_ID:
            groups = [5, 6]
            title = SPECIAL_REGION_TITLE
            kind = "special"
            source = None
            note = SPECIAL_REGION_NOTE
        else:
            group_no = next(group for group, rid in GRAY_REGION_DEFS
                            if rid == region_id)
            meta = region_meta[group_no]
            groups = [group_no]
            title = meta["title"]
            kind = "region"
            source = meta["source"]
            note = ""
        regions.append({
            "id": region_id,
            "title": title,
            "kind": kind,
            "groups": groups,
            "stage_count": len(stage_ids),
            "team_count": len(region_team_ids.get(region_id, set())),
            "species_count": len(region_species),
            "source": source,
            "note": note,
        })
    grayzone_team_ids = sorted({team_id for ids in area_team_ids.values() for team_id in ids})
    gray_stage_count = len(gray_stage_ids)

    # ---- 章节标题/副标题/标签（活动按 campaign 一章，不合并） ----------
    mission_by_id = missions

    def _sorted_stage_ids(stage_ids: Iterable[int]) -> list[int]:
        return sorted(stage_ids, key=lambda mid: (
            _int((mission_by_id.get(mid) or {}).get("order")), mid))

    def _first_stage_title(stage_ids: Iterable[int]) -> str:
        ordered = _sorted_stage_ids(stage_ids)
        if not ordered:
            return ""
        record = stage_by_id.get(ordered[0])
        return str(record.get("title") or "") if record else ""

    for chapter_id, chapter in chapters.items():
        stage_ids = _sorted_stage_ids(chapter.get("stage_ids") or [])
        chapter["stage_ids"] = stage_ids
        category = chapter["category"]
        campaign = chapter_campaign.get(chapter_id)
        first_title = _first_stage_title(stage_ids)
        activity = campaign_to_act.get(campaign, {}) if campaign is not None else {}
        event_name = campaign_to_event.get(campaign, "") if campaign is not None else ""
        chapter_name = _clean_text(activity.get("chapter_name"))
        activity_name = _clean_text(activity.get("name"))
        kind = "normal"
        title = ""
        subtitle = ""
        tags = list(GROUP_TAGS.get(category, []))
        if category == "main":
            title = "序章" if campaign == 0 else f"第{campaign}章"
            subtitle = ""
        elif category == "tutorial":
            head = re.split(r"[:：]", first_title)[0].strip() if first_title else ""
            title = head or "教学关卡"
        elif category == "simulation":
            title = "模拟作战·靶场"
        elif category == "score":
            kind = "score"
            if campaign in SCORE_SPECIAL_CAMPAIGNS:
                # -404xx：章节名可能被大活动名占用（-40403 = 慢休克 / 自画像），优先 event_name
                base_title = event_name or chapter_name or first_title or f"积分关卡 {campaign}"
            else:
                # 其它积分关卡：优先活动内章节名（如 终焉花海+ / 混沌落幕+ / 思域迷航）
                base_title = chapter_name or event_name or first_title
            # 混合活动（同 campaign 还有非积分关卡任务）会同时存在 event 章，标题加后缀区分
            mixed = campaign is not None and f"event-{campaign}" in chapters
            title = f"{base_title} · 积分关卡" if mixed and base_title else base_title
            parent = activity_name or event_name
            subtitle = f"{parent} · 积分关卡" if parent else "积分关卡"
            tags = ["积分关卡"]
        elif category == "event":
            if chapter.get("kind") == "unknown":
                kind = "unknown"
                title = "特殊作战·未知"
                subtitle = "mission 表缺失的节点"
                tags = ["特殊作战"]
            elif campaign is not None and campaign >= 0:
                # 旧 rerun：id >= 90000 的往期活动复刻
                kind = "rerun"
                title = event_name or first_title
                subtitle = f"往期复刻 · 第{campaign}章"
                tags = ["往期复刻"]
            elif campaign is not None and campaign in plus_campaigns:
                # 多关的「+」活动（如 魔方行动+ -6/-7）：常驻/复刻活动，不是积分关卡
                kind = "rerun"
                title = chapter_name or event_name or first_title
                parent = activity_name or event_name
                subtitle = f"{parent} · 往期复刻" if parent else "往期复刻"
                tags = ["往期复刻"]
            elif activity or event_name:
                title = chapter_name or event_name or first_title
                subtitle = activity_name or "往期活动"
                tags = ["活动"]
            else:
                # 旧 special：没有任何活动表映射的负 campaign
                kind = "special"
                title = first_title or f"特殊作战 {campaign}"
                subtitle = f"特殊作战 {campaign}" if campaign is not None else "特殊作战"
                tags = ["特殊作战"]
        chapter["title"] = title or first_title or chapter_id
        chapter["subtitle"] = subtitle
        chapter["tags"] = tags
        chapter["kind"] = kind

    # 灰域章节（不产关卡列表，只产 regions + areas；v1.7：5 区域 / 14 地点）
    gray_team_species: set[int] = set()
    for team_id in grayzone_team_ids:
        gray_team_species |= team_species.get(team_id, set())
    gray_difficulties = [stage_by_id[mid]["difficulty"] for mid in gray_stage_ids
                         if mid in stage_by_id]
    grayzone_chapter = {
        "id": "grayzone",
        "category": "grayzone",
        "kind": "grayzone",
        "title": "灰域探查",
        "subtitle": f"{len(regions)} 个区域 · {gray_stage_count} 个节点",
        "tags": list(GROUP_TAGS["grayzone"]),
        "stage_count": gray_stage_count,
        "team_count": len(grayzone_team_ids),
        "species_count": len(gray_team_species),
        "difficulty_min": min(gray_difficulties) if gray_difficulties else 0,
        "difficulty_max": max(gray_difficulties) if gray_difficulties else 0,
        "regions": regions,
        "areas": areas,
    }
    chapters["grayzone"] = grayzone_chapter
    chapter_campaign["grayzone"] = -404

    # 无固定关卡章节（按队伍列出）
    orphan_team_ids = sorted(team_id for team_id in collectable
                             if team_flags[team_id]["orphan"])
    orphan_species: set[int] = set()
    for team_id in orphan_team_ids:
        orphan_species |= team_species.get(team_id, set())
    chapters["orphan"] = {
        "id": "orphan",
        "category": "orphan",
        "kind": "orphan",
        "title": "无固定关卡",
        "subtitle": f"{len(orphan_team_ids)} 支队伍",
        "tags": list(GROUP_TAGS["orphan"]),
        "stage_count": 0,
        "team_count": len(orphan_team_ids),
        "species_count": len(orphan_species),
        "difficulty_min": 0,
        "difficulty_max": 0,
    }

    # ---- 章节聚合（关卡数/队伍数/怪种数/难度） -------------------------
    for chapter_id, chapter in chapters.items():
        if chapter.get("kind") in ("grayzone", "orphan"):
            continue
        stage_ids = chapter.get("stage_ids") or []
        team_union: set[int] = set()
        species_union: set[int] = set()
        difficulties: list[int] = []
        for mission_id in stage_ids:
            record = stage_by_id.get(mission_id)
            if record is None:
                continue
            team_union |= mission_teams.get(mission_id, set())
            species_union |= {codex for team_id in mission_teams.get(mission_id, set())
                              for codex in team_species.get(team_id, set())}
            difficulties.append(record["difficulty"])
        chapter["stage_count"] = len(stage_ids)
        chapter["team_count"] = len(team_union)
        chapter["species_count"] = len(species_union)
        chapter["difficulty_min"] = min(difficulties) if difficulties else 0
        chapter["difficulty_max"] = max(difficulties) if difficulties else 0

    # ---- 章节排序 / 分组 ------------------------------------------------
    group_chapter_ids: dict[str, list[str]] = {group_id: [] for group_id, _ in GROUPS}
    for chapter_id, chapter in chapters.items():
        group_chapter_ids.setdefault(chapter["category"], []).append(chapter_id)

    def _chapter_sort_key(chapter_id: str):
        chapter = chapters[chapter_id]
        stage_ids = chapter.get("stage_ids") or []
        if stage_ids:
            return (0, min((_int((mission_by_id.get(mid) or {}).get("order")), mid)
                           for mid in stage_ids))
        return (1, (0, 0))

    ordered_chapter_ids: list[str] = []
    groups_payload: list[dict] = []
    for group_id, group_title in GROUPS:
        ids = sorted(group_chapter_ids.get(group_id, []), key=_chapter_sort_key)
        groups_payload.append({"id": group_id, "title": group_title, "chapter_ids": ids})
        ordered_chapter_ids.extend(ids)

    chapter_stage_ids: dict[str, list[int]] = {}
    chapters_payload: list[dict] = []
    for chapter_id in ordered_chapter_ids:
        chapter = chapters[chapter_id]
        stage_ids = list(chapter.pop("stage_ids", []))
        chapter.pop("campaign", None)
        chapter_stage_ids[chapter_id] = stage_ids
        payload_chapter = {
            "id": chapter_id,
            "category": chapter.get("category"),
            "kind": chapter.get("kind", "normal"),
            "title": chapter.get("title") or "",
            "subtitle": chapter.get("subtitle") or "",
            "stage_count": chapter.get("stage_count", 0),
            "team_count": chapter.get("team_count", 0),
            "species_count": chapter.get("species_count", 0),
            "difficulty_min": chapter.get("difficulty_min", 0),
            "difficulty_max": chapter.get("difficulty_max", 0),
            "tags": list(chapter.get("tags") or []),
        }
        if chapter.get("areas") is not None:
            payload_chapter["areas"] = chapter["areas"]
        if chapter.get("regions") is not None:
            payload_chapter["regions"] = chapter["regions"]
        chapters_payload.append(payload_chapter)

    # 关卡列表顺序：章节顺序内按 (order, id)
    listed_stage_ids: list[int] = []
    for chapter_id in ordered_chapter_ids:
        listed_stage_ids.extend(chapter_stage_ids.get(chapter_id, []))

    # ---- 汇总 counts / meta --------------------------------------------
    counts = {
        "chapters": len(chapters_payload),
        "stages": len(mission_teams),
        "teams": len(team_records),
        "support_teams": len(support_team_missions),
        "species": len(species_items),
        "missions": len(missions),
    }

    codes_needed = sorted({
        str((type_rows.get(type_id) or {}).get("code") or "")
        for type_id in used_type_ids
        if str((type_rows.get(type_id) or {}).get("code") or "")
    })
    codes_covered = [code for code in codes_needed
                     if _icon_filename(code) in icon_file_set]
    species_with_icon = [item for item in species_items if item.get("icon")]
    icons_meta = {
        "files": len(icon_file_set),
        "codes_needed": len(codes_needed),
        "codes_covered": len(codes_covered),
        "species_total": len(species_items),
        "species_covered": len(species_with_icon),
        "missing_codes": [code for code in codes_needed
                          if _icon_filename(code) not in icon_file_set][:40],
    }

    sources = {
        "stc_version": str(getattr(tables["stc_module"], "MAPPING_VERSION", "")),
        "tables": {
            "enemy_team": len(tables["enemy_team"]),
            "enemy_in_team": len(tables["enemy_in_team"]),
            "enemy_character_type": len(tables["enemy_character_type"]),
            "enemy_illustration": len(tables["enemy_illustration"]),
            "mission": len(tables["mission"]),
            "spot": len(tables["spot"]),
            "mission_event": len(tables["mission_event"]),
            "normal_activity": len(tables["normal_activity"]),
            "rank": len(tables["rank"]),
        },
        "settlement": {
            "score_stages": len(score_mission_ids),
            "rank_matched_stages": sum(1 for mid in score_mission_ids
                                       if mid in mission_rank),
        },
        "support": {
            "team_ids": len(all_support_team_ids),
            "with_slots": len(support_team_missions),
            "collectable": sum(1 for team_id in support_team_missions
                               if team_id in collectable),
            "missions_with_support": len(support_mission_teams),
            "stage_support_links": sum(len(tids) for mid, tids in
                                       support_mission_teams.items()
                                       if mid in stage_mission_ids),
        },
        "reserve": {
            "stages_with_reserve": len(stage_reserve_teams),
            "links": sum(len(ids) for ids in stage_reserve_teams.values()),
            "teams": len(reserve_team_missions),
            "prefix_stages": sum(1 for meta in stage_reserve_meta.values()
                                 if meta.get("method") == "prefix"),
            "neighbor_stages": sum(1 for meta in stage_reserve_meta.values()
                                   if meta.get("method") == "neighbor"),
            "manual_stages": sum(1 for meta in stage_reserve_meta.values()
                                 if meta.get("method") == "manual"),
            "inherited_stages": sum(1 for meta in stage_reserve_meta.values()
                                    if meta.get("inherited")),
            "reason": RESERVE_REASON,
        },
        "client_text": _source_file_info(TEXT_FILE),
        "enemy_full_model": _source_file_info(MODEL_FILE),
        "icons": icons_meta,
        "elapsed_internal_s": round(time.time() - started, 2),
    }

    payload = {
        "schema": SCHEMA_VERSION,
        "built_at": _now_iso(),
        "elapsed_s": round(time.time() - started, 2),
        "counts": counts,
        "sources": sources,
        "groups": groups_payload,
        "chapters": chapters_payload,
        "chapter_stage_ids": chapter_stage_ids,
        "stage_ids": listed_stage_ids,
        "stages": stage_records,
        "stage_teams": {str(mid): sorted(tids) for mid, tids in mission_teams.items()},
        "stage_support_teams": {
            str(mid): [[team_id, support_row_counts[mid][team_id]] for team_id in tids]
            for mid, tids in support_mission_teams.items()
            if mid in stage_mission_ids and tids
        },
        "stage_reserve_teams": {str(mid): ids
                                for mid, ids in stage_reserve_teams.items()},
        "stage_reserve_meta": {str(mid): meta
                               for mid, meta in stage_reserve_meta.items()},
        "grayzone": {
            "chapter_id": "grayzone",
            "regions": regions,
            "areas": areas,
            "nodes": nodes,
            "area_team_ids": {area: sorted(ids) for area, ids in area_team_ids.items()},
            "region_team_ids": {region_id: sorted(ids)
                                for region_id, ids in region_team_ids.items()},
            "team_ids": grayzone_team_ids,
        },
        "orphan_team_ids": orphan_team_ids,
        "teams": team_records,
        "support_team_records": support_only_records,
        "types": type_info,
        "species": species_items,
        "score_campaigns": sorted(score_campaigns),
    }
    return payload


def _source_file_info(path: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path.relative_to(ROOT)), "exists": False}
    return {
        "path": str(path.relative_to(ROOT)),
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# build / load
# ---------------------------------------------------------------------------
_BUILD_LOCK = threading.Lock()
_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, Any] = {"catalog": None, "mtime": None}


def build(force: bool = False) -> dict:
    """解析 STC + client_text + enemy_full_model.csv，写 catalog.json，返回 meta。

    ``force=False`` 且 catalog.json 比所有数据源（含 icons/）新时直接复用缓存。
    写文件是原子的（tmp + ``os.replace``），并用 ``catalog.lock`` 做跨进程互斥。
    """
    with _BUILD_LOCK:
        with _file_lock():
            cached = _cached_meta(force=force)
            if cached is not None:
                return cached
            started = time.time()
            payload = _build_payload()
            payload["built_at"] = _now_iso()
            payload["elapsed_s"] = round(time.time() - started, 2)
            json_size = _atomic_write(payload)
            meta = _meta_from_payload(payload, json_size=json_size)
            meta["counts"] = dict(payload["counts"])
            _invalidate_cache()
            return meta


def _invalidate_cache() -> None:
    with _CACHE_LOCK:
        _CACHE["catalog"] = None
        _CACHE["mtime"] = None


def reload() -> "Catalog":
    """强制重新读取 catalog.json（不存在/损坏时先 build）。"""
    if not CATALOG_FILE.is_file():
        build(force=True)
    try:
        payload = _read_payload()
    except (OSError, json.JSONDecodeError):
        build(force=True)
        payload = _read_payload()
    catalog = Catalog(payload)
    with _CACHE_LOCK:
        _CACHE["catalog"] = catalog
        _CACHE["mtime"] = _catalog_mtime_ns()
    return catalog


def load() -> "Catalog":
    """加载 catalog（单例 + 线程安全；catalog.json mtime 变化时自动重载）。"""
    with _CACHE_LOCK:
        catalog = _CACHE["catalog"]
        if catalog is not None and _CACHE["mtime"] == _catalog_mtime_ns():
            return catalog
    if not CATALOG_FILE.is_file():
        build(force=True)
        return reload()
    try:
        payload = _read_payload()
        mtime = _catalog_mtime_ns()
    except (OSError, json.JSONDecodeError):
        build(force=True)
        payload = _read_payload()
        mtime = _catalog_mtime_ns()
    catalog = Catalog(payload)
    with _CACHE_LOCK:
        _CACHE["catalog"] = catalog
        _CACHE["mtime"] = mtime
    return catalog


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------
class Catalog:
    """catalog.json 的只读查询层（进程内可被多线程共享）。"""

    def __init__(self, payload: dict):
        self.built_at: str = str(payload.get("built_at") or "")
        self.counts: dict = dict(payload.get("counts") or {})
        self.sources: dict = dict(payload.get("sources") or {})
        self.elapsed_s = payload.get("elapsed_s")
        self.schema = payload.get("schema")

        self._chapters: dict[str, dict] = {
            str(chapter.get("id")): chapter for chapter in payload.get("chapters") or []
        }
        self._chapter_stage_ids: dict[str, list[int]] = {
            str(key): [int(mid) for mid in value]
            for key, value in (payload.get("chapter_stage_ids") or {}).items()
        }
        self._stage_list: list[dict] = list(payload.get("stages") or [])
        self._stages: dict[int, dict] = {int(stage["id"]): stage for stage in self._stage_list}
        self._stage_ids: list[int] = [int(mid) for mid in payload.get("stage_ids") or []]
        self._stage_teams: dict[int, list[int]] = {
            int(key): [int(team) for team in value]
            for key, value in (payload.get("stage_teams") or {}).items()
        }
        # v1.4 支援队伍：stage → [(team_id, support_count)]
        self._stage_support_teams: dict[int, list[tuple[int, int]]] = {
            int(key): [(int(pair[0]), int(pair[1])) for pair in value]
            for key, value in (payload.get("stage_support_teams") or {}).items()
        }
        # v1.5 机场/后续刷新候选（推断）：stage → [team_id]
        self._stage_reserve_teams: dict[int, list[int]] = {
            int(key): [int(team_id) for team_id in value]
            for key, value in (payload.get("stage_reserve_teams") or {}).items()
        }
        # v1.8.1 reserve 推断元信息：stage → {prefix, prefix_length, refs, method, count}
        self._stage_reserve_meta: dict[int, dict] = {
            int(key): dict(value)
            for key, value in (payload.get("stage_reserve_meta") or {}).items()
        }
        self._teams: dict[int, dict] = {
            int(team["id"]): team for team in payload.get("teams") or []
        }
        # 不可收藏的支援队伍只用于 stage.support_teams 展示（不进 team() 查询）
        self._support_records: dict[int, dict] = {
            int(team["id"]): team
            for team in payload.get("support_team_records") or []
        }
        self._team_ids: list[int] = sorted(self._teams)
        self._types: dict[int, dict] = {
            int(key): value for key, value in (payload.get("types") or {}).items()
        }
        self._species_items: list[dict] = list(payload.get("species") or [])
        self._species_by_codex: dict[int, dict] = {
            int(item["codex_no"]): item for item in self._species_items
        }
        grayzone = payload.get("grayzone") or {}
        self._regions: list[dict] = list(grayzone.get("regions") or [])
        self._region_by_id: dict[str, dict] = {
            str(region.get("id") or ""): region for region in self._regions
        }
        self._areas: list[dict] = list(grayzone.get("areas") or [])
        self._grayzone_nodes: list[dict] = list(grayzone.get("nodes") or [])
        self._area_team_ids: dict[str, list[int]] = {
            str(key): [int(team) for team in value]
            for key, value in (grayzone.get("area_team_ids") or {}).items()
        }
        self._region_team_ids: dict[str, list[int]] = {
            str(key): [int(team) for team in value]
            for key, value in (grayzone.get("region_team_ids") or {}).items()
        }
        # region 参数兼容：id（sand/armor_assault/…）、标题（沙尘带/装甲突击）、组号（"1".."6"）
        self._region_lookup: dict[str, str] = {}
        for region in self._regions:
            region_id = str(region.get("id") or "")
            if not region_id:
                continue
            self._region_lookup[region_id.lower()] = region_id
            title = str(region.get("title") or "")
            if title:
                self._region_lookup[title.lower()] = region_id
            if region_id in (ARMOR_ASSAULT_REGION_ID,):
                continue  # 爬塔不按组号映射（组号留给特殊区域）
            for group_no in region.get("groups") or []:
                self._region_lookup.setdefault(str(group_no), region_id)
        self._grayzone_team_ids: list[int] = [int(team) for team in
                                              grayzone.get("team_ids") or []]
        self._orphan_team_ids: list[int] = [int(team) for team in
                                            payload.get("orphan_team_ids") or []]
        self._groups: list[dict] = []
        for group in payload.get("groups") or []:
            chapter_ids = [str(cid) for cid in group.get("chapter_ids") or []]
            self._groups.append({
                "id": str(group.get("id")),
                "title": str(group.get("title") or ""),
                "chapters": [self._chapters[cid] for cid in chapter_ids
                             if cid in self._chapters],
            })

        # v1.6 全怪组总表索引（加载时预计算，team_list 单次查询 <100ms）：
        # 每支队伍 → 怪种 codex 集合 / 出现过的章节 id 集合（敌方+支援+reserve 推断）。
        self._team_species_sets: dict[int, set[int]] = {
            team_id: set(record.get("species") or [])
            for team_id, record in self._teams.items()
        }
        self._team_chapters: dict[int, set[str]] = {}
        for family in (self._teams, self._support_records):
            for team_id, record in family.items():
                chapter_ids: set[str] = set()
                for key in ("appearances", "support_appearances", "reserve_appearances"):
                    for mission_id in record.get(key) or []:
                        stage = self._stages.get(int(mission_id))
                        if stage is None:
                            continue
                        chapter_id = str(stage.get("chapter_id") or "")
                        if chapter_id:
                            chapter_ids.add(chapter_id)
                self._team_chapters[team_id] = chapter_ids
        # 每队搜索快照（id/阵营/tags/怪种名/成员 code·name 拼接小写），让 q 查询也 <100ms
        self._team_search_text: dict[int, str] = {}
        for family in (self._teams, self._support_records):
            for team_id, record in family.items():
                parts = [str(team_id), str(record.get("faction") or "")]
                parts.extend(str(tag) for tag in record.get("tags") or [])
                for codex_no in record.get("species") or []:
                    parts.append(str(codex_no))
                    item = self._species_by_codex.get(codex_no)
                    if item:
                        parts.append(str(item.get("name") or ""))
                for slot in record.get("members") or []:
                    info = self._types.get(_int(slot[0])) or {}
                    parts.append(str(info.get("code") or ""))
                    parts.append(str(info.get("name") or ""))
                self._team_search_text[team_id] = " ".join(parts).lower()

    # -- 基础 ---------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Catalog {self.built_at} teams={self.counts.get('teams')}>"

    def chapters(self) -> dict:
        counts = {key: self.counts.get(key, 0)
                  for key in ("chapters", "stages", "teams", "species")}
        return {"built_at": self.built_at, "counts": counts, "groups": self._groups}

    def chapter(self, chapter_id: str) -> dict | None:
        chapter_id = str(chapter_id)
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            return None
        category = chapter.get("category")
        if category == "grayzone":
            return {"chapter": chapter, "stages": [],
                    "regions": self._regions, "areas": self._areas}
        if category == "orphan":
            teams = [summary for summary in
                     (self._team_summary(team_id) for team_id in self._orphan_team_ids)
                     if summary is not None]
            return {"chapter": chapter, "stages": [], "teams": teams,
                    "teams_total": len(teams)}
        stages = [self._stage_list_item(mission_id)
                  for mission_id in self._chapter_stage_ids.get(chapter_id, [])]
        return {"chapter": chapter, "stages": stages}

    def stage(self, mission_id: int) -> dict | None:
        try:
            mission_id = int(mission_id)
        except (TypeError, ValueError):
            return None
        stage = self._stages.get(mission_id)
        if stage is None:
            return None
        chapter = self._chapters.get(stage.get("chapter_id") or "")
        payload = dict(stage)
        payload["chapter_title"] = chapter.get("title") if chapter else ""
        payload["category"] = chapter.get("category") if chapter else ""
        support_links = self._stage_support_teams.get(mission_id, [])
        support_items: list[dict] = []
        for team_id, support_count in support_links:
            summary = self._team_summary(team_id)
            if summary is None:
                continue
            item = dict(summary)
            item["role"] = "support"
            item["support_count"] = support_count
            support_items.append(item)
        reserve_links = self._stage_reserve_teams.get(mission_id, [])
        reserve_meta = dict(self._stage_reserve_meta.get(mission_id) or {})
        manual = reserve_meta.get("method") == "manual"
        manual_entries = {_int(entry.get("team")): entry
                          for entry in (reserve_meta.get("entries") or [])
                          if isinstance(entry, dict)}
        reserve_items: list[dict] = []
        for team_id in reserve_links:
            summary = self._team_summary(team_id)
            if summary is None:
                continue
            item = dict(summary)
            item["role"] = "reserve"
            item["inferred"] = not manual
            item["reserve_source"] = "manual" if manual else "inferred"
            item["reserve_reason"] = (reserve_meta.get("title")
                                      if manual else RESERVE_REASON)
            entry = manual_entries.get(team_id)
            if manual:
                item["appeared"] = entry is not None
                item["appearance"] = "可能刷怪" if entry else "实际未出现"
                item["actual_kind"] = (entry or {}).get("kind") or ""
            if entry:
                item["reserve_area"] = entry.get("area") or ""
                item["reserve_turns"] = entry.get("turns") or ""
                item["reserve_logic"] = entry.get("logic") or ""
            reserve_items.append(item)
        # 场上已存在（enemy on map）；manual 关卡标注是否在固定/刷怪表内
        teams_items: list[dict] = []
        for team_id in self._stage_teams.get(mission_id, []):
            summary = self._team_summary(team_id)
            if summary is None:
                continue
            item = dict(summary)
            if manual:
                entry = manual_entries.get(_int(team_id))
                if entry is not None:
                    item["appearance"] = "场上已存在"
                    item["actual_kind"] = entry.get("kind") or ""
            teams_items.append(item)
        return {
            "stage": payload,
            "teams": teams_items,
            "support_teams": support_items,
            "support_team_count": len(support_links),
            "reserve_teams": reserve_items,
            "reserve_team_count": len(reserve_links),
            "reserve_meta": reserve_meta,
        }

    # -- 灰域 ---------------------------------------------------------
    def grayzone_areas(self) -> dict:
        """灰域层级：``regions``（6 个：沙尘带/风暴带/硅状带/结晶带/装甲突击爬塔/特殊区域）
        + ``areas``（14 个地点，仅兼容保留，不作为主结构）。"""
        return {"regions": self._regions, "areas": self._areas}

    def grayzone_nodes(self, region: str = "", *, q: str = "", offset: int = 0,
                       limit: int = 50, sort: str = "id_asc") -> dict:
        """灰域节点列表（区域 → 节点 → 节点内小怪）。

        * ``region``：sand/storm/silicon/crystal/armor_assault/special 或中文标题
          （沙尘带/…/装甲突击/特殊区域）；空 = 全部节点
        * ``q``：匹配节点 id / 标题 / 地点（不区分大小写）
        * ``sort``：id_asc（默认）/ id_desc / difficulty_asc / difficulty_desc /
          team_count_desc / species_count_desc
        * 返回 ``{region_id, region_title, total, offset, limit, sort, items}``，
          每项 = ``{mission_id,title,location,region_id,region_title,difficulty,
          team_count,species_count,top_species:[{codex_no,name,icon},≤4],tags}``
        """
        region = str(region or "").strip()
        query = str(q or "").strip().lower()
        sort = str(sort or "id_asc").strip().lower()
        offset = max(0, _int(offset))
        limit = min(200, max(1, _int(limit, 50)))
        region_id = ""
        region_title = ""
        if region:
            region_id = self._region_lookup.get(region.lower(), "")
            if not region_id:
                return {"region_id": region, "region_title": "", "total": 0,
                        "offset": offset, "limit": limit, "sort": sort, "items": []}
            region_title = str(self._region_by_id.get(region_id, {}).get("title") or "")
        selected: list[dict] = []
        for node in self._grayzone_nodes:
            if region_id and str(node.get("region_id")) != region_id:
                continue
            if query:
                haystack = (f"{node.get('mission_id')} {node.get('title') or ''} "
                            f"{node.get('location') or ''}").lower()
                if query not in haystack:
                    continue
            selected.append(node)
        if sort == "id_desc":
            selected.sort(key=lambda node: -_int(node.get("mission_id")))
        elif sort == "difficulty_asc":
            selected.sort(key=lambda node: (_int(node.get("difficulty")),
                                            _int(node.get("mission_id"))))
        elif sort == "difficulty_desc":
            selected.sort(key=lambda node: (-_int(node.get("difficulty")),
                                            _int(node.get("mission_id"))))
        elif sort in ("team_count_desc", "teams_desc"):
            selected.sort(key=lambda node: (-_int(node.get("team_count")),
                                            _int(node.get("mission_id"))))
        elif sort in ("species_count_desc", "species_desc"):
            selected.sort(key=lambda node: (-_int(node.get("species_count")),
                                            _int(node.get("mission_id"))))
        else:
            selected.sort(key=lambda node: _int(node.get("mission_id")))
        total = len(selected)
        page = selected[offset:offset + limit]
        items: list[dict] = []
        for node in page:
            node_region_id = str(node.get("region_id") or "")
            top_species = []
            for codex_no in (node.get("top_species") or [])[:4]:
                codex_no = _int(codex_no)
                item = self._species_by_codex.get(codex_no)
                top_species.append({
                    "codex_no": codex_no,
                    "name": item.get("name") if item else f"图鉴 {codex_no}",
                    "icon": item.get("icon") if item else None,
                })
            items.append({
                "mission_id": _int(node.get("mission_id")),
                "title": node.get("title") or "",
                "location": node.get("location") or "",
                "region_id": node_region_id,
                "region_title": str(self._region_by_id.get(
                    node_region_id, {}).get("title") or ""),
                "difficulty": _int(node.get("difficulty")),
                "team_count": _int(node.get("team_count")),
                "species_count": _int(node.get("species_count")),
                "top_species": top_species,
                "tags": list(node.get("tags") or []),
            })
        return {"region_id": region_id, "region_title": region_title,
                "total": total, "offset": offset, "limit": limit, "sort": sort,
                "items": items}

    def grayzone_teams(self, area: str = "", offset: int = 0, limit: int = 60,
                       q: str = "", region: str = "", *,
                       area_id: str | None = None,
                       power_min: float | None = None,
                       power_max: float | None = None,
                       power_known: Any = None,
                       sort: str = "default") -> dict:
        """灰域队伍：按地点（area）和/或真实区域（region）筛选，再 q/power/排序/分页。

        * ``area``：14 个地点之一（如 共生净土）；传空 = 全部灰域队伍（3352 支）
        * ``region``：沙尘带/风暴带/硅状带/结晶带/特殊区域（也接受 sand/storm/silicon/
          crystal/special、组号 "1".."6"）；special 含组5/6/未映射
        * 契约里地点参数名是 ``area_id``（app.py 用 ``area=``），两种都支持
        """
        if area_id is not None:
            area = area_id
        area = str(area or "").strip()
        region = str(region or "").strip()
        if area:
            team_ids: list[int] = list(self._area_team_ids.get(area, []))
        else:
            team_ids = list(self._grayzone_team_ids)
        region_id = ""
        if region:
            region_id = self._region_lookup.get(region.lower(), "")
            if not region_id:
                return {"total": 0, "offset": max(0, _int(offset)),
                        "limit": max(1, _int(limit, 60)),
                        "sort": str(sort or "default"), "region": region,
                        "items": [], **({"area": area} if area else {})}
            region_set = set(self._region_team_ids.get(region_id, []))
            team_ids = [team_id for team_id in team_ids if team_id in region_set]
        total, page = self._query_team_ids(
            team_ids, offset=offset, limit=limit, q=q,
            power_min=power_min, power_max=power_max, power_known=power_known,
            sort=sort,
        )
        items = [summary for summary in (self._team_summary(team_id) for team_id in page)
                 if summary is not None]
        payload = {
            "total": total,
            "offset": max(0, _int(offset)),
            "limit": max(1, _int(limit, 60)),
            "sort": str(sort or "default"),
            "items": items,
        }
        if area:
            payload["area"] = area
        if region_id:
            payload["region"] = region_id
        return payload

    # -- reserve 审计（v1.8.1） ----------------------------------------
    def _legacy_reserve_teams(self, mission_id: int) -> list[int]:
        """旧版 reserve 规则（只尝试 4 位前缀），用于审计「改进前」对比。"""
        referenced = set(self._stage_teams.get(mission_id, []))
        referenced |= {team_id for team_id, _count in
                       self._stage_support_teams.get(mission_id, [])}
        tally: Counter = Counter(str(team_id)[:4]
                                 for team_id in referenced if team_id > 1000)
        if not tally:
            return []
        prefix, count = sorted(tally.items(), key=lambda item: (-item[1], item[0]))[0]
        if count < 3:
            return []
        candidates = [team_id for team_id in self._team_ids
                      if str(team_id).startswith(prefix) and team_id not in referenced]
        return candidates[:RESERVE_CAP]

    def reserve_audit(self, *, write: bool = True) -> dict:
        """全量 score 章节 reserve 审计：逐关新旧数量/prefix/引用数 + 仍为 0 的原因。

        完整报告写入 ``DATA_DIR/reserve_audit.json``（write=True 时），返回同一 dict。
        """
        score_chapters = [chapter for chapter in self._chapters.values()
                          if chapter.get("category") == "score"]
        rows: list[dict] = []
        for chapter in sorted(score_chapters, key=lambda item: str(item.get("id"))):
            chapter_id = str(chapter.get("id"))
            chapter_title = str(chapter.get("title") or "")
            for mission_id in self._chapter_stage_ids.get(chapter_id, []):
                stage = self._stages.get(mission_id) or {}
                new_ids = list(self._stage_reserve_teams.get(mission_id, []))
                old_ids = self._legacy_reserve_teams(mission_id)
                meta = self._stage_reserve_meta.get(mission_id) or {}
                referenced = set(self._stage_teams.get(mission_id, []))
                referenced |= {team_id for team_id, _count in
                               self._stage_support_teams.get(mission_id, [])}
                ref_ids = [team_id for team_id in referenced if team_id > 1000]
                reason = ""
                if not new_ids:
                    if not referenced:
                        reason = "no_referenced_teams"
                    elif not ref_ids:
                        reason = "referenced_ids_le_1000"
                    else:
                        reason = "no_candidates"
                rows.append({
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "stage_id": mission_id,
                    "title": stage.get("title") or "",
                    "difficulty": _int(stage.get("difficulty")),
                    "team_count": len(self._stage_teams.get(mission_id, [])),
                    "referenced_count": len(referenced),
                    "referenced_gt_1000": len(ref_ids),
                    "prefix": str(meta.get("prefix") or ""),
                    "prefix_length": _int(meta.get("prefix_length")),
                    "prefix_ref_count": _int(meta.get("refs")),
                    "method": str(meta.get("method") or ""),
                    "reserve_count": len(new_ids),
                    "reserve_legacy_count": len(old_ids),
                    "reserve_team_ids": new_ids,
                    "still_zero_reason": reason,
                })
        improved = [row for row in rows
                    if row["reserve_legacy_count"] == 0 and row["reserve_count"] > 0]
        still_zero = [row for row in rows if row["reserve_count"] == 0]
        methods: Counter = Counter(row["method"] for row in rows if row["reserve_count"])
        summary = {
            "score_chapters": len(score_chapters),
            "score_stages": len(rows),
            "stages_with_reserve": len(rows) - len(still_zero),
            "still_zero_stages": len(still_zero),
            "improved_from_zero": len(improved),
            "legacy_stages_with_reserve": sum(1 for row in rows
                                              if row["reserve_legacy_count"] > 0),
            "prefix_stages": methods.get("prefix", 0),
            "neighbor_stages": methods.get("neighbor", 0),
            "manual_stages": methods.get("manual", 0),
            "inherited_stages": sum(
                1 for row in rows
                if (self._stage_reserve_meta.get(row["stage_id"]) or {}).get("inherited")),
        }
        report = {
            "generated_at": self.built_at,
            "kind": "reserve_audit_score",
            "summary": summary,
            "improved": improved,
            "still_zero": still_zero,
            "stages": rows,
        }
        if write:
            path = CATALOG_FILE.parent / "reserve_audit.json"
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
                os.replace(tmp_path, path)
            finally:
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
        return report

    # -- 队伍 ---------------------------------------------------------
    def team(self, team_id: int) -> dict | None:
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            return None
        record = self._teams.get(team_id)
        if record is None:
            return None
        appearances = self._appearances(record)
        return {
            "id": record["id"],
            "power": record["power"],
            "power_known": record.get("power_known", False),
            "units": record["units"],
            "hp_total": record["hp_total"],
            "faction": record["faction"],
            "tags": list(record.get("tags") or []),
            "roles": list(record.get("roles") or []),
            "collectable": bool(record.get("collectable", True)),
            "gray_zone": record["gray_zone"],
            "orphan": record["orphan"],
            "params": {
                "effect_ext": record["power"],
                "power_known": record.get("power_known", False),
                "fight_type": record.get("fight_type", 0),
                "use_building": record.get("use_building", ""),
                "batch_max": record.get("batch_max", 0),
                "gray_zone_missions": sum(1 for entry in appearances if entry["gray_zone"]),
                "mission_count": len(appearances),
                "note": "数值按队伍等级缩放（单位实测口径）；effect_ext=0 表示客户端未标注效能",
            },
            "appearances": appearances[:24],
            "species": self._team_species_detail(record),
            "members": self._members_detail(record),
        }

    def team_summaries(self, team_ids: list[int]) -> list[dict]:
        summaries: list[dict] = []
        for raw in team_ids or []:
            summary = self._team_summary(raw)
            if summary is not None:
                summaries.append(summary)
        return summaries

    # -- 全怪组总表（v1.6） -------------------------------------------
    def team_list(self, *, q: str = "", chapter: str = "", species: Any = None,
                  role: str = "any", collectable: Any = True,
                  power_known: Any = None, power_min: Any = None,
                  power_max: Any = None, units_min: Any = None,
                  units_max: Any = None, sort: str = "id_asc",
                  offset: int = 0, limit: int = 50) -> dict:
        """全怪组总表：多条件筛选 + 稳定排序 + 分页（13,700 队单查询 <100ms）。

        * ``q``：id 子串 / 阵营 / 怪种名称 / 成员 code·name / tags（不区分大小写）
        * ``chapter``：章节 id 精确匹配；队伍在该章节有**任意 role**（敌方/支援/推断候选）
          出现即命中；``orphan`` 表示无固定关卡章节
        * ``species``：codex_no 列表（list 或逗号串），**AND**（队伍包含全部指定怪种）
        * ``role``：enemy / support / reserve / any
        * ``collectable``：默认 True（只返回可收藏队伍）；False 时返回不可收藏的支援队伍
        * ``power_known`` / ``power_min`` / ``power_max`` / ``units_min`` / ``units_max``
        * ``sort``：id_asc / id_desc / power_desc / power_asc / units_desc / units_asc /
          hp_desc / species_desc（稳定排序，同值按 id 升序；效能未知在效能排序时排最后）
        * ``offset`` / ``limit``（默认 0/50，limit 上限 200）
        """
        query = str(q or "").strip().lower()
        chapter = str(chapter or "").strip()
        role = str(role or "any").strip().lower()
        if role not in ("any", "enemy", "support", "reserve"):
            role = "any"
        sort = str(sort or "id_asc").strip().lower()
        species_needed = self._normalize_species(species)
        known = _optional_bool(power_known)
        collectable_flag = _optional_bool(collectable)
        low = None if power_min is None or str(power_min).strip() == "" else _float(power_min)
        high = None if power_max is None or str(power_max).strip() == "" else _float(power_max)
        units_low = None if units_min is None or str(units_min).strip() == "" else _int(units_min)
        units_high = None if units_max is None or str(units_max).strip() == "" else _int(units_max)
        offset = max(0, _int(offset))
        limit = min(200, max(1, _int(limit, 50)))

        if collectable_flag is False:
            base: dict[int, dict] = self._support_records
            candidates: list[int] = sorted(base)
        else:
            base = self._teams
            candidates = self._team_ids

        filtered: list[int] = []
        for team_id in candidates:
            record = base[team_id]
            if (collectable_flag is not None
                    and bool(record.get("collectable", True)) != collectable_flag):
                continue
            if chapter:
                if chapter == "orphan":
                    if not record.get("orphan"):
                        continue
                elif chapter not in self._team_chapters.get(team_id, ()):
                    continue
            roles = record.get("roles") or []
            if role == "enemy" and "enemy" not in roles:
                continue
            if role == "support" and "support" not in roles:
                continue
            if role == "reserve" and not record.get("reserve_appearances"):
                continue
            if known is not None and bool(record.get("power_known")) != known:
                continue
            power = _int(record.get("power"))
            if low is not None and power < low:
                continue
            if high is not None and power > high:
                continue
            units = _int(record.get("units"))
            if units_low is not None and units < units_low:
                continue
            if units_high is not None and units > units_high:
                continue
            if species_needed and not species_needed.issubset(
                    self._team_species_sets.get(team_id, ())):
                continue
            if query and not self._team_matches_query(team_id, query):
                continue
            filtered.append(team_id)

        total = len(filtered)
        self._sort_team_ids(filtered, sort)
        page = filtered[offset:offset + limit]
        items = [self._team_list_item(team_id, base) for team_id in page]
        return {"total": total, "offset": offset, "limit": limit,
                "sort": sort, "items": items}

    @staticmethod
    def _normalize_species(species: Any) -> set[int]:
        if species is None:
            return set()
        if isinstance(species, (list, tuple, set)):
            raw_values = list(species)
        else:
            raw_values = str(species).replace(";", ",").split(",")
        out: set[int] = set()
        for value in raw_values:
            try:
                out.add(int(str(value).strip()))
            except (TypeError, ValueError):
                continue
        return out

    def _team_sort_record(self, team_id: int) -> dict:
        return self._teams.get(team_id) or self._support_records[team_id]

    def _sort_team_ids(self, team_ids: list[int], sort: str) -> None:
        """稳定排序：同值一律按 id 升序；效能未知排在效能排序最后。"""
        if sort == "id_desc":
            team_ids.sort(reverse=True)
            return
        if sort in ("power_desc", "power_asc"):
            reverse = sort == "power_desc"
            team_ids.sort(key=lambda team_id: (
                not bool(self._team_sort_record(team_id).get("power_known")),
                -_int(self._team_sort_record(team_id).get("power")) if reverse
                else _int(self._team_sort_record(team_id).get("power")),
                team_id,
            ))
            return
        if sort in ("units_desc", "units_asc"):
            reverse = sort == "units_desc"
            team_ids.sort(key=lambda team_id: (
                -_int(self._team_sort_record(team_id).get("units")) if reverse
                else _int(self._team_sort_record(team_id).get("units")),
                team_id,
            ))
            return
        if sort == "hp_desc":
            team_ids.sort(key=lambda team_id: (
                -_int(self._team_sort_record(team_id).get("hp_total")), team_id))
            return
        if sort == "species_desc":
            team_ids.sort(key=lambda team_id: (
                -len(self._team_sort_record(team_id).get("species") or []), team_id))
            return
        team_ids.sort()  # id_asc（默认）

    def _team_list_item(self, team_id: int, base: dict[int, dict]) -> dict:
        record = base[team_id]
        species = []
        for codex_no in record.get("species") or []:
            item = self._species_by_codex.get(codex_no)
            species.append({
                "codex_no": codex_no,
                "name": item.get("name") if item else f"图鉴 {codex_no}",
                "icon": item.get("icon") if item else None,
            })
        appearances, chapter_titles, appearance_count = self._team_list_appearances(record)
        return {
            "id": record["id"],
            "power": record["power"],
            "power_known": record.get("power_known", False),
            "units": record["units"],
            "hp_total": record["hp_total"],
            "faction": record["faction"],
            "roles": list(record.get("roles") or []),
            "collectable": bool(record.get("collectable", True)),
            "orphan": bool(record.get("orphan", False)),
            "species": species,
            "appearances": appearances,
            "appearance_count": appearance_count,
            "chapter_titles": chapter_titles,
        }

    def _team_list_appearances(self, record: dict) -> tuple[list[dict], list[str], int]:
        """总表里的出处：敌方/支援/推断候选合并（真实在前），最多 60 条。"""
        role_map: dict[int, set[str]] = defaultdict(set)
        for mission_id in record.get("appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("enemy")
        for mission_id in record.get("support_appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("support")
        for mission_id in record.get("reserve_appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("reserve")
        entries = []
        for mission_id, roles in role_map.items():
            stage = self._stages[mission_id]
            primary = 0 if "enemy" in roles else (1 if "support" in roles else 2)
            entries.append((primary, _int(stage.get("order")), mission_id, roles))
        entries.sort()
        appearances: list[dict] = []
        chapter_titles: list[str] = []
        seen_chapters: set[str] = set()
        for primary, _order, mission_id, roles in entries:
            stage = self._stages[mission_id]
            chapter_id = str(stage.get("chapter_id") or "")
            chapter = self._chapters.get(chapter_id) or {}
            title = str(chapter.get("title") or "")
            if chapter_id and chapter_id not in seen_chapters:
                seen_chapters.add(chapter_id)
                if title:
                    chapter_titles.append(title)
            if len(appearances) < 60:
                role = "enemy" if primary == 0 else ("support" if primary == 1 else "reserve")
                appearances.append({
                    "mission_id": mission_id,
                    "chapter_id": chapter_id,
                    "chapter_title": title,
                    "stage_title": stage.get("title") or "",
                    "role": role,
                    "inferred": role == "reserve",
                })
        return appearances, chapter_titles, len(role_map)

    # -- 怪种 ---------------------------------------------------------
    def species_list(self, *, q: str = "", faction: str = "", category: str = "",
                     offset: int = 0, limit: int = 60) -> dict:
        query = str(q or "").strip().lower()
        faction = str(faction or "").strip()
        category = str(category or "").strip().lower()
        if category == "all":
            category = ""
        flag_name = {
            "normal": "has_normal",
            "grayzone": "has_grayzone",
            "orphan": "has_orphan",
        }.get(category)
        items = []
        for item in self._species_items:
            if flag_name and not item.get(flag_name):
                continue
            if faction and item.get("faction") != faction:
                continue
            if query:
                haystack = f"{item.get('codex_no')} {item.get('name')} {item.get('faction')}".lower()
                if query not in haystack:
                    continue
            items.append(self._species_public(item))
        total = len(items)
        offset = max(0, _int(offset))
        limit = max(1, _int(limit, 60))
        return {"total": total, "offset": offset, "limit": limit,
                "items": items[offset:offset + limit]}

    def species(self, codex_no: int, offset: int | None = None,
                limit: int | None = None, q: str | None = None,
                power_min: float | None = None, power_max: float | None = None,
                power_known: Any = None, sort: str | None = None) -> dict | None:
        """怪种详情 + 队伍。

        兼容两种调用：

        * ``species(codex_no)``（无参）→ 返回**全量** teams（app.py 内存筛选/分页用）；
        * 显式传入 ``offset/limit/q/power_min/power_max/power_known/sort`` 中任意一个
          → 走 catalog 内部筛选 + 排序 + 分页（``sort`` 默认 ``"default"``，
          ``offset`` 默认 0，``limit`` 默认 60）。
        """
        try:
            codex_no = int(codex_no)
        except (TypeError, ValueError):
            return None
        item = self._species_by_codex.get(codex_no)
        if item is None:
            return None
        public = self._species_public(item)
        team_ids = list(item.get("teams") or [])
        paged = any(value is not None for value in
                    (offset, limit, q, power_min, power_max, power_known, sort))
        if not paged:
            teams = [summary for summary in
                     (self._team_summary(team_id) for team_id in team_ids)
                     if summary is not None]
            return {
                "species": public,
                "total": len(teams),
                "teams_total": len(teams),
                "offset": 0,
                "limit": len(teams),
                "teams": teams,
            }
        total, page = self._query_team_ids(
            team_ids,
            offset=_int(offset, 0),
            limit=_int(limit, 60),
            q=q or "",
            power_min=power_min,
            power_max=power_max,
            power_known=power_known,
            sort=sort or "default",
        )
        teams = [summary for summary in (self._team_summary(team_id) for team_id in page)
                 if summary is not None]
        return {
            "species": public,
            "total": total,
            "teams_total": total,
            "offset": max(0, _int(offset, 0)),
            "limit": max(1, _int(limit, 60)),
            "sort": str(sort or "default"),
            "teams": teams,
        }

    # -- 搜索 ---------------------------------------------------------
    def search(self, q: str, limit: int = 30) -> dict:
        query = str(q or "").strip()
        limit = max(1, _int(limit, 30))
        if not query:
            return {"teams": [], "stages": [], "species": []}
        lowered = query.lower()

        team_hits: list[tuple[int, dict]] = []
        for team_id in self._team_ids:
            if not self._team_matches_query(team_id, lowered):
                continue
            summary = self._team_summary(team_id)
            if summary is not None:
                score = 0 if str(team_id) == query else 1
                team_hits.append((score, summary))
            if len(team_hits) >= limit * 4:
                break
        team_hits.sort(key=lambda pair: pair[0])
        teams = [summary for _, summary in team_hits[:limit]]

        # 关卡搜索也命中章节标题/副标题/标签（活动名、自画像、积分关卡等可搜）
        chapters_haystack: dict[str, str] = {}
        stages = []
        for mission_id in self._stage_ids:
            stage = self._stages.get(mission_id)
            if stage is None:
                continue
            chapter_id = stage.get("chapter_id") or ""
            chapter_hay = chapters_haystack.get(chapter_id)
            if chapter_hay is None:
                chapter = self._chapters.get(chapter_id) or {}
                chapter_hay = " ".join([
                    str(chapter.get("title") or ""),
                    str(chapter.get("subtitle") or ""),
                    " ".join(str(tag) for tag in chapter.get("tags") or []),
                    str(chapter.get("category") or ""),
                ]).lower()
                chapters_haystack[chapter_id] = chapter_hay
            haystack = (f"{stage.get('title')} {stage.get('code')} "
                        f"{mission_id} {chapter_hay}").lower()
            if lowered in haystack:
                chapter = self._chapters.get(chapter_id) or {}
                stages.append({
                    "id": mission_id,
                    "title": stage.get("title"),
                    "code": stage.get("code"),
                    "chapter_id": chapter_id,
                    "chapter_title": chapter.get("title") or "",
                })
                if len(stages) >= limit:
                    break

        species = []
        for item in self._species_items:
            haystack = f"{item.get('codex_no')} {item.get('name')} {item.get('faction')}".lower()
            if lowered in haystack:
                species.append(self._species_public(item))
                if len(species) >= limit:
                    break

        return {"teams": teams, "stages": stages, "species": species}

    # -- 内部：列表筛选/排序 ------------------------------------------
    def _query_team_ids(self, team_ids: Iterable[int], *, offset: int = 0,
                        limit: int = 60, q: str = "",
                        power_min: Any = None, power_max: Any = None,
                        power_known: Any = None,
                        sort: str = "default") -> tuple[int, list[int]]:
        """按 q / power 条件筛选并排序，返回 ``(过滤后总数, 当前页 id)``。"""
        query = str(q or "").strip().lower()
        known = _optional_bool(power_known)
        low = None if power_min is None or str(power_min).strip() == "" else _float(power_min)
        high = None if power_max is None or str(power_max).strip() == "" else _float(power_max)
        filtered: list[int] = []
        for team_id in team_ids:
            record = self._teams.get(int(team_id))
            if record is None:
                continue
            if query and not self._team_matches_query(int(team_id), query):
                continue
            if known is not None and bool(record.get("power_known")) != known:
                continue
            power = _int(record.get("power"))
            if low is not None and power < low:
                continue
            if high is not None and power > high:
                continue
            filtered.append(int(team_id))
        sort = str(sort or "default")
        if sort in ("power_desc", "power_asc"):
            reverse = sort == "power_desc"
            filtered.sort(key=lambda tid: (
                not self._teams[tid].get("power_known"),
                -self._teams[tid]["power"] if reverse else self._teams[tid]["power"],
                tid,
            ))
        elif sort == "hp_desc":
            filtered.sort(key=lambda tid: (-_int(self._teams[tid].get("hp_total")), tid))
        elif sort == "units_desc":
            filtered.sort(key=lambda tid: (-_int(self._teams[tid].get("units")), tid))
        total = len(filtered)
        offset = max(0, _int(offset))
        limit = max(1, _int(limit, 60))
        return total, filtered[offset:offset + limit]

    # -- 内部：摘要 / 详情 --------------------------------------------
    def _stage_list_item(self, mission_id: int) -> dict | None:
        stage = self._stages.get(int(mission_id))
        if stage is None:
            return None
        return {key: stage.get(key) for key in STAGE_LIST_KEYS}

    def _species_public(self, item: dict) -> dict:
        return {key: value for key, value in item.items() if key != "teams"}

    def _team_members_groups(self, record: dict) -> list[dict]:
        groups: list[dict] = []
        by_code: dict[str, dict] = {}
        for slot in record.get("members") or []:
            type_id = _int(slot[0])
            number = _int(slot[2])
            info = self._types.get(type_id) or {}
            code = str(info.get("code") or type_id)
            group = by_code.get(code)
            if group is None:
                group = {
                    "code": code,
                    "name": str(info.get("name") or code),
                    "number": number,
                    "count": 0,
                    "icon": info.get("icon"),
                }
                by_code[code] = group
                groups.append(group)
            group["count"] += 1
            if number > group["number"]:
                group["number"] = number
        return groups

    def _team_species_detail(self, record: dict) -> list[dict]:
        out: list[dict] = []
        for codex_no in record.get("species") or []:
            item = self._species_by_codex.get(codex_no)
            if item is None:
                out.append({"codex_no": codex_no, "name": f"图鉴 {codex_no}",
                            "faction": "", "type": 0, "icon": None})
                continue
            out.append({
                "codex_no": codex_no,
                "name": item.get("name"),
                "faction": item.get("faction"),
                "type": item.get("type", 0),
                "icon": item.get("icon"),
            })
        return out

    def _team_summary(self, team_id: int) -> dict | None:
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            return None
        record = self._teams.get(team_id) or self._support_records.get(team_id)
        if record is None:
            return None
        species = []
        for codex_no in (record.get("species") or [])[:8]:
            item = self._species_by_codex.get(codex_no)
            species.append({
                "codex_no": codex_no,
                "name": item.get("name") if item else f"图鉴 {codex_no}",
                "icon": item.get("icon") if item else None,
            })
        stage = None
        rep_stage = record.get("rep_stage")
        if rep_stage is not None:
            stage_info = self._stages.get(int(rep_stage))
            if stage_info is not None:
                chapter = self._chapters.get(stage_info.get("chapter_id") or "")
                stage = {
                    "chapter_id": stage_info.get("chapter_id"),
                    "title": chapter.get("title") if chapter else "",
                    "stage_title": stage_info.get("title"),
                    "code": stage_info.get("code"),
                }
        return {
            "id": record["id"],
            "power": record["power"],
            "power_known": record.get("power_known", False),
            "units": record["units"],
            "hp_total": record["hp_total"],
            "faction": record["faction"],
            "tags": list(record.get("tags") or []),
            "roles": list(record.get("roles") or []),
            "collectable": bool(record.get("collectable", True)),
            "species": species,
            "members": self._team_members_groups(record)[:6],
            "gray_zone": record["gray_zone"],
            "orphan": record["orphan"],
            "stage": stage,
        }

    def _appearances(self, record: dict) -> list[dict]:
        """真实出处（敌方/支援）+ 推断出处（reserve，机场/后续刷新候选）。

        每条带 ``role``（enemy/support/reserve）与 ``roles`` 列表；reserve 条目带
        ``inferred: true``，只是"可能刷新"，不影响 orphan/roles 真实状态。
        """
        role_map: dict[int, set[str]] = defaultdict(set)
        for mission_id in record.get("appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("enemy")
        for mission_id in record.get("support_appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("support")
        for mission_id in record.get("reserve_appearances") or []:
            if mission_id in self._stages:
                role_map[mission_id].add("reserve")
        entries = []
        for mission_id, roles in role_map.items():
            stage = self._stages[mission_id]
            gray = bool(stage.get("gray_zone")) or stage.get("chapter_id") == "grayzone"
            primary = 0 if "enemy" in roles else (1 if "support" in roles else 2)
            entries.append((1 if gray else 0, _int(stage.get("order")), primary, mission_id))
        entries.sort()
        out: list[dict] = []
        for _, _, _, mission_id in entries:
            stage = self._stages[mission_id]
            chapter = self._chapters.get(stage.get("chapter_id") or "")
            roles = sorted(role_map[mission_id],
                           key=lambda value: {"enemy": 0, "support": 1,
                                              "reserve": 2}.get(value, 9))
            primary_role = ("enemy" if "enemy" in roles else
                            ("support" if "support" in roles else "reserve"))
            out.append({
                "mission_id": mission_id,
                "chapter_id": stage.get("chapter_id"),
                "chapter_title": chapter.get("title") if chapter else "",
                "stage_title": stage.get("title"),
                "code": stage.get("code"),
                "difficulty": stage.get("difficulty", 0),
                "gray_zone": bool(stage.get("gray_zone")),
                "role": primary_role,
                "roles": roles,
                "inferred": primary_role == "reserve",
            })
        return out

    def _members_detail(self, record: dict) -> list[dict]:
        from unit_model.core import enemy as enemy_mod

        slots = record.get("members") or []
        counts: dict[int, int] = defaultdict(int)
        for slot in slots:
            counts[_int(slot[0])] += 1
        members: list[dict] = []
        for slot in slots:
            type_id = _int(slot[0])
            level = _int(slot[1])
            number = _int(slot[2])
            def_percent = slot[3]
            batch = _int(slot[4])
            x = slot[5]
            y = slot[6]
            info = self._types.get(type_id) or {}
            try:
                scaled = enemy_mod.enemy_attributes(type_id, level, scale_by_level=True)
                base = enemy_mod.enemy_attributes(type_id, None)
                stats = {key: _stat_num(scaled.get(key)) for key in STAT_KEYS}
                base_stats = {key: _stat_num(base.get(key)) for key in STAT_KEYS}
                # def=99999 是"无防护"哨兵值（不是真实力场值），不参与等级缩放展示
                if _float(base.get("def")) >= 99999:
                    stats["def"] = 99999
            except (KeyError, ValueError):  # pragma: no cover - 缺失类型兜底
                stats = {key: 0 for key in STAT_KEYS}
                base_stats = {key: 0 for key in STAT_KEYS}
            members.append({
                "type_id": type_id,
                "code": str(info.get("code") or ""),
                "name": str(info.get("name") or type_id),
                "codex_no": _int(info.get("codex_no")),
                "icon": info.get("icon"),
                "level": level,
                "number": number,
                "count": counts[type_id],
                "def_percent": def_percent,
                "batch": batch,
                "x": x,
                "y": y,
                "stats": stats,
                "base_stats": base_stats,
            })
        return members

    # -- 内部：搜索匹配 ------------------------------------------------
    def _team_matches_query(self, team_id: int, lowered: str) -> bool:
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            return False
        haystack = self._team_search_text.get(team_id)
        if haystack is None:  # 兼容旧 catalog（无预计算快照）
            record = self._teams.get(team_id) or self._support_records.get(team_id)
            if record is None:
                return False
            haystack = " ".join([
                str(record.get("id")),
                str(record.get("faction") or ""),
                " ".join(str(tag) for tag in record.get("tags") or []),
            ]).lower()
        return lowered in haystack


__all__ = [
    "CATALOG_FILE",
    "DATA_DIR",
    "GROUPS",
    "ICON_DIR",
    "LOCK_FILE",
    "MODEL_FILE",
    "SORT_MODES",
    "Catalog",
    "TEXT_FILE",
    "build",
    "load",
    "reload",
]
