"""靶机工坊 TargetForge —— STC → 章节/关卡/怪种/怪组 数据层。

职责（见 ``contract.md`` §2）：

* :func:`build` 解析本机 STC（game 定长表）+ ``client_text.json`` +
  ``enemy_full_model.csv``，生成 :data:`CATALOG_FILE`（原子写 + 跨进程锁）；
* :func:`load` 单例加载（线程安全、检测 catalog.json mtime 自动重载）；
* :class:`Catalog` 提供 ``/api/chapters``、``/api/stages``、``/api/teams``、
  ``/api/species``、``/api/grayzone/*``、``/api/search`` 需要的查询。

设计取舍
--------
catalog.json 不存"前端完整详情"，而是存**查询所需的紧凑索引**：

* 每支队伍只存槽位（type_id / level / number / def_percent / batch / x / y）
  和汇总字段，队伍详情（成员数值、出处）在 ``Catalog.team()`` 里按需计算，
  展示数值统一走 ``unit_model.core.enemy.enemy_attributes(..., scale_by_level=True)``
  （660011 实测口径：总血 359,580）。这样 JSON 只有 ~5MB，load 远低于 5s。
* 怪种图鉴、类型索引只保留名称/阵营/图鉴号等标签，**不写任何技能字段**
  （skill / trigger / action / buff 等一律不进 JSON）。

数据口径（与 Lead 侦查一致）
----------------------------
* 可收藏有效队伍 = ``enemy_team.targettrain_cancollect == "1"`` 且 ``enemy_in_team``
  有编制 → 13700；
* 队伍↔关卡 = ``spot.enemy_team_id`` ∪ ``mission.boss_team_id``；
* 有可收藏队伍的关卡 → 2345（灰域 1288 / 活动 743 / 主线 140 / 特殊 84 /
  往期复刻 40 / 教学 40 / 模拟作战 9 / 未知 1）；
* 灰域 = ``campaign == -404``，按标题前缀（如「共生净土-I」→ 共生净土）分 12 个区域；
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
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: catalog 缓存文件（整个 dataMiner/derived/targetforge/ 不入 git，可重建）
DATA_DIR = ROOT / "dataMiner" / "derived" / "targetforge"
CATALOG_FILE = DATA_DIR / "catalog.json"
LOCK_FILE = DATA_DIR / "catalog.lock"

#: 只读数据源
TEXT_FILE = ROOT / "dataMiner" / "derived" / "client_text.json"
MODEL_FILE = ROOT / "dataMiner" / "derived" / "enemy_full_model.csv"

#: JSON schema 版本（结构变更时 +1）
SCHEMA_VERSION = 1

#: mission 文本 key 前缀：``mission-{10000000 + mission_id}``
MISSION_TEXT_BASE = 10_000_000

#: 章节组顺序与标题（contract §2.2 排序）
GROUPS: tuple[tuple[str, str], ...] = (
    ("main", "主线"),
    ("event", "活动"),
    ("rerun", "往期复刻"),
    ("tutorial", "教学"),
    ("special", "特殊作战"),
    ("simulation", "模拟作战"),
    ("grayzone", "灰域探查"),
    ("orphan", "无固定关卡"),
)
GROUP_TITLES = dict(GROUPS)

#: 章节/组的标签文案
GROUP_TAGS = {
    "main": ["主线"],
    "event": ["活动"],
    "rerun": ["往期复刻"],
    "tutorial": ["教学"],
    "special": ["特殊作战"],
    "simulation": ["模拟作战"],
    "grayzone": ["打灰"],
    "orphan": ["无固定关卡"],
}

#: 章节列表里关卡摘要的字段（contract §2.3）
STAGE_LIST_KEYS = (
    "id", "title", "code", "difficulty", "recommend_level",
    "team_count", "species_count", "tags", "order",
)

#: 队伍详情里展示的数值键（contract §2.3 示例；只展示参数，不含技能）
STAT_KEYS = (
    "maxlife", "pow", "hit", "dodge", "armor", "armor_piercing",
    "range", "speed", "shield", "def", "crit", "crit_dmg", "tenacity",
)

#: 图鉴类别（contract §2.4）
SPECIES_CATEGORIES = ("normal", "grayzone", "orphan")

_TAG_RE = re.compile(r"<[^>]*>")


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


def _source_mtime_ns() -> int:
    """所有数据源里最新的 mtime（用于 build 的缓存新鲜度判断）。"""
    latest = 0
    for path in (TEXT_FILE, MODEL_FILE, Path(__file__)):
        try:
            latest = max(latest, path.stat().st_mtime_ns)
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
    """灰域区域 = 标题里第一个 ``-`` 之前的前缀（兼容全角/不换行空格）。"""
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


def _classify_mission(
    mid: int,
    mission: dict,
    *,
    campaign_to_act: dict[int, dict],
    campaign_to_event: dict[int, str],
) -> tuple[str | None, str | None, str, str]:
    """返回 ``(category, chapter_id, title, subtitle)``。

    ``category`` 为 None 表示该关卡不产生章节（contract §2.2 规则 7）；
    活动章节按 (标题, 副标题) 归并后再分配 ``chapter_id``，因此这里 chapter_id 为 None。
    """
    campaign = _int(mission.get("campaign"))
    map_res = str(mission.get("map_res_name") or "")

    # 1. 灰域（不产关卡列表，单独成章）
    if campaign == -404:
        return ("grayzone", "grayzone", "灰域探查", "")

    # 2. 教学：按 campaign 一章
    if -10006 <= campaign <= -10000:
        return ("tutorial", f"tutorial-{campaign}", "", "")

    # 3. 模拟作战/靶场：map_res_name 以 Moni 开头（经验特训 / 模拟作战），
    #    外加固定 id 段 1101..1106（经验/特种特训，其中 1104..1106 的 map 是 OPS5_Y）
    #    与 1701..1745（模拟作战系列，campaign 6）。
    if map_res.startswith("Moni") or 1101 <= mid <= 1106 or 1701 <= mid <= 1745:
        return ("simulation", "simulation", "模拟作战·靶场", "")

    # 4. 主线：campaign 0..13、id < 90000、非模拟作战地图
    if 0 <= campaign <= 13 and mid < 90000 and not map_res.startswith("Moni"):
        title = "序章" if campaign == 0 else f"第{campaign}章"
        return ("main", f"main-{campaign}", title, "")

    # 5. 往期活动复刻：id >= 90000 且 campaign >= 0
    if mid >= 90000 and campaign >= 0:
        event_name = str(campaign_to_event.get(campaign) or "")
        return ("rerun", f"rerun-{campaign}", f"往期活动·第{campaign}章", event_name)

    # 6. 其它负 campaign：活动 / 特殊作战
    if campaign < 0:
        activity = campaign_to_act.get(campaign)
        event_name = str(campaign_to_event.get(campaign) or "")
        if activity:
            title = (_clean_text(activity.get("chapter_name"))
                     or _clean_text(activity.get("name"))
                     or event_name or f"活动 {campaign}")
            subtitle = _clean_text(activity.get("name")) or event_name
            return ("event", None, title, subtitle)
        if event_name:
            return ("event", None, event_name, "")
        return ("special", f"special-{campaign}", f"特殊作战 {campaign}", "")

    # 7. 其余（campaign 14+ 等）不产生章节
    return (None, None, "", "")

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
    illustration_by_code: dict[str, list[dict]] = defaultdict(list)
    for row in tables["enemy_illustration"]:
        illustration_by_id[_int(row.get("id"))].append(row)
        illustration_by_code[str(row.get("code") or "")].append(row)
    for rows in illustration_by_id.values():
        rows.sort(key=lambda item: _int(item.get("sub_id")))
    for rows in illustration_by_code.values():
        rows.sort(key=lambda item: _int(item.get("sub_id")))

    # 活动 / 复刻名映射
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
            "name": text.get(str(row.get("name") or ""), ""),
            "chapter_name": text.get(str(row.get("chapter_name") or ""), ""),
            "tag": text.get(str(row.get("tag") or ""), ""),
        }

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

    # ---- 关卡归类 → 章节骨架 -------------------------------------------
    gray_stage_ids: list[int] = []
    mid_chapter: dict[int, str] = {}
    chapters: dict[str, dict] = {}
    event_groups: dict[tuple[str, str], dict] = {}
    event_campaigns: dict[tuple[str, str], list[int]] = defaultdict(list)

    for mission_id in mission_teams:
        mission = missions.get(mission_id)
        if mission is None:
            # spot 里有 mission_id 不在 mission 表（例 404101）→ 归「特殊作战·未知」
            chapter = chapters.setdefault("special-unknown", {
                "category": "special",
                "title": "特殊作战·未知",
                "subtitle": "",
                "stage_ids": [],
                "campaign": None,
            })
            chapter["stage_ids"].append(mission_id)
            mid_chapter[mission_id] = "special-unknown"
            continue
        category, chapter_id, title, subtitle = _classify_mission(
            mission_id, mission,
            campaign_to_act=campaign_to_act,
            campaign_to_event=campaign_to_event,
        )
        if category is None:
            continue
        if category == "grayzone":
            gray_stage_ids.append(mission_id)
            mid_chapter[mission_id] = "grayzone"
            continue
        if category == "event":
            key = (title, subtitle)
            group = event_groups.setdefault(key, {
                "category": "event",
                "title": title,
                "subtitle": subtitle,
                "stage_ids": [],
            })
            group["stage_ids"].append(mission_id)
            event_campaigns[key].append(_int(mission.get("campaign")))
            mid_chapter[mission_id] = ""  # 活动章节 id 归并后回填
            continue
        chapter = chapters.setdefault(chapter_id, {
            "category": category,
            "title": title,
            "subtitle": subtitle,
            "stage_ids": [],
        })
        chapter["stage_ids"].append(mission_id)
        mid_chapter[mission_id] = chapter_id

    # 活动章节：同 (标题, 副标题) 的不同 campaign 合成一章，id 取最小 campaign
    for key, group in event_groups.items():
        chapter_id = f"event-{min(event_campaigns[key])}"
        chapters[chapter_id] = group
        for mission_id in group["stage_ids"]:
            mid_chapter[mission_id] = chapter_id

    # ---- 队伍记录（详情数值按需计算，这里只存紧凑索引） ----------------
    team_records: list[dict] = []
    team_species: dict[int, set[int]] = {}
    team_flags: dict[int, dict] = {}
    team_gray_mission_count: dict[int, int] = {}
    used_type_ids: set[int] = set()

    def scaled_attributes(type_id: int, level: int):
        try:
            return enemy_mod.enemy_attributes(type_id, level, scale_by_level=True)
        except (KeyError, ValueError):
            return None

    for team_id in sorted(collectable):
        team_row = teams_by_id[team_id]
        raw_slots = sorted(
            slots_by_team[team_id],
            key=lambda item: (_float(item.get("coordinator_x")), -_float(item.get("coordinator_y"))),
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
            batch_max = max(batch_max, batch)
            codex = type_codex.get(type_id, 0)
            if codex:
                species.add(codex)
            faction = type_faction.get(type_id) or ""
            if faction:
                faction_counter[faction][0] += 1
                faction_counter[faction][1] += max(1.0, _float((type_rows.get(type_id) or {}).get("maxlife")))
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
                type_id, level, number, _json_num(def_percent), batch, _json_num(x), _json_num(y),
            ])

        appearances = sorted(team_missions.get(team_id, ()))
        gray_missions = [mid for mid in appearances
                         if _int((missions.get(mid) or {}).get("campaign")) == -404]
        non_gray = [mid for mid in appearances if mid not in set(gray_missions)]
        rep_stage = None
        if non_gray:
            rep_stage = min(
                non_gray,
                key=lambda mid: (_int((missions.get(mid) or {}).get("order")), mid),
            )
        is_gray = bool(gray_missions)
        is_orphan = not appearances
        team_flags[team_id] = {"fixed": bool(non_gray), "gray": is_gray, "orphan": is_orphan}
        team_gray_mission_count[team_id] = len(gray_missions)
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

        team_records.append({
            "id": team_id,
            "power": _int(team_row.get("effect_ext")),
            "units": len(slots),
            "hp_total": int(round(hp_total)),
            "faction": faction_name,
            "tags": tags,
            "species": sorted(species),
            "members": slots,
            "appearances": appearances,
            "gray_zone": is_gray,
            "orphan": is_orphan,
            "rep_stage": rep_stage,
            "fight_type": _int(team_row.get("fight_type")),
            "use_building": str(team_row.get("use_building") or ""),
            "batch_max": batch_max,
        })

    # ---- 类型标签（成员/怪种展示用；不含任何技能信息） ----------------
    type_info: dict[str, dict] = {}
    for type_id in used_type_ids:
        row = type_rows.get(type_id) or {}
        type_info[str(type_id)] = {
            "code": str(row.get("code") or ""),
            "name": _type_display_name(row, text) if row else str(type_id),
            "codex_no": type_codex.get(type_id, 0),
            "faction": type_faction.get(type_id) or "",
            "boss": 1 if type_boss.get(type_id) else 0,
        }

    # ---- 怪种（264 个可收藏 codex） ------------------------------------
    codex_types: dict[int, set[int]] = defaultdict(set)
    for type_id, codex in type_codex.items():
        if type_id in used_type_ids:
            codex_types[codex].add(type_id)

    species_items: list[dict] = []
    for codex_no in sorted(codex_types):
        member_teams = sorted(team_id for team_id in collectable
                              if codex_no in team_species.get(team_id, ()))
        if not member_teams:
            continue
        used_types = sorted(codex_types[codex_no])
        illu_rows = illustration_by_id.get(codex_no) or []
        illu = illu_rows[0] if illu_rows else None
        if illu is not None:
            name = _clean_text(text.get(str(illu.get("name") or ""), ""))
            species_type = _int(illu.get("type"))
        else:
            name = ""
            species_type = _int((type_rows.get(used_types[0]) or {}).get("type"))
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
        faction = max(faction_counter, key=lambda key: faction_counter[key]) if faction_counter else ""
        capturable = any(type_capturable.get(type_id) for type_id in used_types)

        has_fixed = any(team_flags[tid]["fixed"] for tid in member_teams)
        has_gray_only = any(team_flags[tid]["gray"] and not team_flags[tid]["fixed"]
                            for tid in member_teams)
        has_orphan = any(team_flags[tid]["orphan"] for tid in member_teams)
        category = "normal" if has_fixed else ("grayzone" if has_gray_only else
                                              ("orphan" if has_orphan else "normal"))
        species_items.append({
            "codex_no": codex_no,
            "name": name,
            "faction": faction,
            "type": species_type,
            "capturable": bool(capturable),
            "tags": ["契约捕获"] if capturable else [],
            "category": category,
            "team_count": len(member_teams),
            "gray_zone_team_count": sum(1 for tid in member_teams if team_flags[tid]["gray"]),
            "orphan_team_count": sum(1 for tid in member_teams if team_flags[tid]["orphan"]),
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
        record = {
            "id": mission_id,
            "chapter_id": mid_chapter.get(mission_id, ""),
            "title": title,
            "code": code,
            "difficulty": difficulty,
            "recommend_level": recommend_level,
            "team_count": len(team_ids),
            "species_count": len(species_union),
            "tags": tags,
            "order": order,
            "gray_zone": _int((mission or {}).get("campaign")) == -404,
        }
        stage_records.append(record)
        stage_by_id[mission_id] = record

    # ---- 灰域区域 ------------------------------------------------------
    area_stage_ids: dict[str, list[int]] = defaultdict(list)
    area_team_ids: dict[str, set[int]] = defaultdict(set)
    for mission_id in gray_stage_ids:
        mission = missions.get(mission_id) or {}
        area = _gray_area(_mission_title(mission_id, mission, text))
        if not area:
            area = "未分类"
        area_stage_ids[area].append(mission_id)
        area_team_ids[area] |= mission_teams.get(mission_id, set())
    areas: list[dict] = []
    for area in sorted(area_stage_ids,
                       key=lambda key: (-len(area_stage_ids[key]),
                                        -len(area_team_ids[key]), key)):
        area_species: set[int] = set()
        for team_id in area_team_ids[area]:
            area_species |= team_species.get(team_id, set())
        areas.append({
            "id": area,
            "title": area,
            "stage_count": len(area_stage_ids[area]),
            "team_count": len(area_team_ids[area]),
            "species_count": len(area_species),
        })
    grayzone_team_ids = sorted({team_id for ids in area_team_ids.values() for team_id in ids})
    gray_stage_count = len(gray_stage_ids)

    # ---- 章节聚合 ------------------------------------------------------
    mission_by_id = missions

    def _first_stage(chapter: dict) -> dict | None:
        stage_ids = chapter.get("stage_ids") or []
        if not stage_ids:
            return None
        ordered = sorted(stage_ids, key=lambda mid: (
            _int((mission_by_id.get(mid) or {}).get("order")), mid))
        return stage_by_id.get(ordered[0])

    for chapter in chapters.values():
        stage_ids = chapter.get("stage_ids") or []
        chapter["stage_ids"] = sorted(
            stage_ids,
            key=lambda mid: (_int((mission_by_id.get(mid) or {}).get("order")), mid),
        )
        chapter["stage_count"] = len(stage_ids)
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
        chapter["team_count"] = len(team_union)
        chapter["species_count"] = len(species_union)
        chapter["difficulty_min"] = min(difficulties) if difficulties else 0
        chapter["difficulty_max"] = max(difficulties) if difficulties else 0
        chapter["tags"] = list(GROUP_TAGS.get(chapter["category"], []))
        category = chapter["category"]
        if category == "tutorial":
            first = _first_stage(chapter)
            first_title = first["title"] if first else ""
            head = re.split(r"[:：]", first_title)[0].strip() if first_title else ""
            chapter["title"] = head or "教学关卡"
            chapter["subtitle"] = ""
        elif category == "special":
            if chapter.get("title") == "特殊作战·未知":
                chapter["subtitle"] = "mission 表缺失的节点"
            else:
                first = _first_stage(chapter)
                chapter["subtitle"] = first["title"] if first else ""

    # 灰域章节（不产关卡列表，只产 areas）
    gray_team_species: set[int] = set()
    for team_id in grayzone_team_ids:
        gray_team_species |= team_species.get(team_id, set())
    gray_difficulties = [stage_by_id[mid]["difficulty"] for mid in gray_stage_ids
                         if mid in stage_by_id]
    chapters["grayzone"] = {
        "id": "grayzone",
        "category": "grayzone",
        "title": "灰域探查",
        "subtitle": f"{len(areas)} 个区域 · {gray_stage_count} 个节点",
        "stage_count": gray_stage_count,
        "team_count": len(grayzone_team_ids),
        "species_count": len(gray_team_species),
        "difficulty_min": min(gray_difficulties) if gray_difficulties else 0,
        "difficulty_max": max(gray_difficulties) if gray_difficulties else 0,
        "tags": list(GROUP_TAGS["grayzone"]),
        "areas": areas,
    }

    # 无固定关卡章节（按队伍列出）
    orphan_team_ids = sorted(team_id for team_id in collectable
                             if team_flags[team_id]["orphan"])
    orphan_species: set[int] = set()
    for team_id in orphan_team_ids:
        orphan_species |= team_species.get(team_id, set())
    chapters["orphan"] = {
        "id": "orphan",
        "category": "orphan",
        "title": "无固定关卡",
        "subtitle": f"{len(orphan_team_ids)} 支队伍",
        "stage_count": 0,
        "team_count": len(orphan_team_ids),
        "species_count": len(orphan_species),
        "difficulty_min": 0,
        "difficulty_max": 0,
        "tags": list(GROUP_TAGS["orphan"]),
    }

    # 补齐 id / stage_ids 之外的展示字段
    for chapter_id, chapter in chapters.items():
        chapter.setdefault("id", chapter_id)
        chapter["id"] = chapter_id
        chapter.setdefault("subtitle", "")

    # ---- 章节排序 / 分组 ------------------------------------------------
    group_chapter_ids: dict[str, list[str]] = {group_id: [] for group_id, _ in GROUPS}
    for chapter_id, chapter in chapters.items():
        group_chapter_ids.setdefault(chapter["category"], []).append(chapter_id)

    def _chapter_sort_key(chapter_id: str):
        chapter = chapters[chapter_id]
        stage_ids = chapter.get("stage_ids") or []
        if stage_ids:
            return min((_int((mission_by_id.get(mid) or {}).get("order")), mid)
                       for mid in stage_ids)
        return (0, 0)

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
        "species": len(species_items),
        "missions": len(missions),
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
        },
        "client_text": _source_file_info(TEXT_FILE),
        "enemy_full_model": _source_file_info(MODEL_FILE),
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
        "grayzone": {
            "chapter_id": "grayzone",
            "areas": areas,
            "area_team_ids": {area: sorted(ids) for area, ids in area_team_ids.items()},
            "team_ids": grayzone_team_ids,
        },
        "orphan_team_ids": orphan_team_ids,
        "teams": team_records,
        "types": type_info,
        "species": species_items,
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

    ``force=False`` 且 catalog.json 比所有数据源新时直接复用缓存。
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
        self._teams: dict[int, dict] = {
            int(team["id"]): team for team in payload.get("teams") or []
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
        self._areas: list[dict] = list(grayzone.get("areas") or [])
        self._area_team_ids: dict[str, list[int]] = {
            str(key): [int(team) for team in value]
            for key, value in (grayzone.get("area_team_ids") or {}).items()
        }
        self._grayzone_team_ids: list[int] = [int(team) for team in grayzone.get("team_ids") or []]
        self._orphan_team_ids: list[int] = [int(team) for team in payload.get("orphan_team_ids") or []]
        self._groups: list[dict] = []
        for group in payload.get("groups") or []:
            chapter_ids = [str(cid) for cid in group.get("chapter_ids") or []]
            self._groups.append({
                "id": str(group.get("id")),
                "title": str(group.get("title") or ""),
                "chapters": [self._chapters[cid] for cid in chapter_ids if cid in self._chapters],
            })

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
            return {"chapter": chapter, "stages": [], "areas": self._areas}
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
        return {
            "stage": payload,
            "teams": [summary for summary in
                      (self._team_summary(team_id)
                       for team_id in self._stage_teams.get(mission_id, []))
                      if summary is not None],
        }

    # -- 灰域 ---------------------------------------------------------
    def grayzone_areas(self) -> list[dict]:
        return self._areas

    def grayzone_teams(self, area: str = "", offset: int = 0, limit: int = 60,
                       q: str = "", *, area_id: str | None = None) -> dict:
        """灰域区域队伍分页。

        契约里参数名是 ``area_id``，app.py 实际用 ``area=`` 调用；两种都支持。
        传空 area 则返回全部灰域队伍（3352 支）。
        """
        if area_id is not None:
            area = area_id
        area = str(area or "").strip()
        if area:
            team_ids = self._area_team_ids.get(area, [])
        else:
            team_ids = self._grayzone_team_ids
        query = str(q or "").strip().lower()
        if query:
            team_ids = [team_id for team_id in team_ids
                        if self._team_matches_query(team_id, query)]
        total = len(team_ids)
        offset = max(0, _int(offset))
        limit = max(1, _int(limit, 60))
        page = team_ids[offset:offset + limit]
        items = [summary for summary in (self._team_summary(team_id) for team_id in page)
                 if summary is not None]
        payload = {"total": total, "offset": offset, "limit": limit, "items": items}
        if area:
            payload["area"] = area
        return payload

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
            "units": record["units"],
            "hp_total": record["hp_total"],
            "faction": record["faction"],
            "tags": list(record.get("tags") or []),
            "gray_zone": record["gray_zone"],
            "orphan": record["orphan"],
            "params": {
                "effect_ext": record["power"],
                "fight_type": record.get("fight_type", 0),
                "use_building": record.get("use_building", ""),
                "batch_max": record.get("batch_max", 0),
                "gray_zone_missions": sum(1 for entry in appearances if entry["gray_zone"]),
                "mission_count": len(record.get("appearances") or []),
                "note": "数值按队伍等级缩放（单位实测口径）",
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

    # -- 怪种 ---------------------------------------------------------
    def species_list(self, *, q: str = "", faction: str = "", category: str = "",
                     offset: int = 0, limit: int = 60) -> dict:
        query = str(q or "").strip().lower()
        faction = str(faction or "").strip()
        category = str(category or "").strip().lower()
        if category == "all":
            category = ""
        items = []
        for item in self._species_items:
            if category and item.get("category") != category:
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

    def species(self, codex_no: int) -> dict | None:
        try:
            codex_no = int(codex_no)
        except (TypeError, ValueError):
            return None
        item = self._species_by_codex.get(codex_no)
        if item is None:
            return None
        teams = [summary for summary in
                 (self._team_summary(team_id) for team_id in item.get("teams") or [])
                 if summary is not None]
        return {
            "species": self._species_public(item),
            "total": len(teams),
            "teams_total": len(teams),
            "offset": 0,
            "limit": len(teams),
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

        stages = []
        for mission_id in self._stage_ids:
            stage = self._stages.get(mission_id)
            if stage is None:
                continue
            haystack = f"{stage.get('title')} {stage.get('code')} {mission_id}".lower()
            if lowered in haystack:
                chapter = self._chapters.get(stage.get("chapter_id") or "")
                stages.append({
                    "id": mission_id,
                    "title": stage.get("title"),
                    "code": stage.get("code"),
                    "chapter_title": chapter.get("title") if chapter else "",
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
                out.append({"codex_no": codex_no, "name": f"图鉴 {codex_no}", "faction": "", "type": 0})
                continue
            out.append({
                "codex_no": codex_no,
                "name": item.get("name"),
                "faction": item.get("faction"),
                "type": item.get("type", 0),
            })
        return out

    def _team_summary(self, team_id: int) -> dict | None:
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            return None
        record = self._teams.get(team_id)
        if record is None:
            return None
        species = []
        for codex_no in (record.get("species") or [])[:8]:
            item = self._species_by_codex.get(codex_no)
            species.append({"codex_no": codex_no,
                            "name": item.get("name") if item else f"图鉴 {codex_no}"})
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
            "units": record["units"],
            "hp_total": record["hp_total"],
            "faction": record["faction"],
            "tags": list(record.get("tags") or []),
            "species": species,
            "members": self._team_members_groups(record)[:6],
            "gray_zone": record["gray_zone"],
            "orphan": record["orphan"],
            "stage": stage,
        }

    def _appearances(self, record: dict) -> list[dict]:
        entries = []
        for mission_id in record.get("appearances") or []:
            stage = self._stages.get(mission_id)
            if stage is None:
                continue
            gray = bool(stage.get("gray_zone")) or stage.get("chapter_id") == "grayzone"
            entries.append((1 if gray else 0, _int(stage.get("order")), mission_id))
        entries.sort()
        out: list[dict] = []
        for _, _, mission_id in entries:
            stage = self._stages[mission_id]
            chapter = self._chapters.get(stage.get("chapter_id") or "")
            out.append({
                "mission_id": mission_id,
                "chapter_id": stage.get("chapter_id"),
                "chapter_title": chapter.get("title") if chapter else "",
                "stage_title": stage.get("title"),
                "code": stage.get("code"),
                "difficulty": stage.get("difficulty", 0),
                "gray_zone": bool(stage.get("gray_zone")),
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
        record = self._teams.get(int(team_id))
        if record is None:
            return False
        if lowered in str(record["id"]):
            return True
        if lowered in str(record.get("faction") or "").lower():
            return True
        for tag in record.get("tags") or []:
            if lowered in str(tag).lower():
                return True
        for codex_no in record.get("species") or []:
            item = self._species_by_codex.get(codex_no)
            if item and lowered in str(item.get("name") or "").lower():
                return True
        for slot in record.get("members") or []:
            info = self._types.get(_int(slot[0])) or {}
            if lowered in str(info.get("code") or "").lower():
                return True
            if lowered in str(info.get("name") or "").lower():
                return True
        return False


__all__ = [
    "CATALOG_FILE",
    "DATA_DIR",
    "GROUPS",
    "LOCK_FILE",
    "MODEL_FILE",
    "Catalog",
    "TEXT_FILE",
    "build",
    "load",
    "reload",
]
