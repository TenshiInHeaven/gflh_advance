"""靶机工坊 TargetForge —— GFLH 登录抓取 / 序列规划 / 靶机注入 / 游戏控制。

对应 GUI 工具 GFLH-TargetTrain 的能力，接口见 ``targetforge/contract.md`` §3：

* **capture**：``GFLProxy`` 监听可配置端口（默认 18080，勿用 8080）抓
  ``SYS_KEY_UPGRADE``（uid + sign）和
  ``Index/index`` 的 ``targettrain_collect_user_info``（当前收藏标靶 enemies/orders），
  落 ``<datapaths.DATA_DIR>/creds_latest.json``（默认
  ``dataMiner/derived/targetforge/``，可用环境变量 ``TARGETFORGE_DATA_DIR`` 覆盖）；
  抓齐后可自动停抓并恢复系统代理。
* **plan**：纯函数。按 ``append / replace / rebuild / clear`` 四种语义算出
  ``Targettrain/addCollect`` / ``delCollect`` 的 payload（含 order_id），不联网。
* **execute**：先 DEL 再 ADD（间隔 0.5~0.6s），逐条 log、单条失败继续，
  成功的条目同步到本地 ``dataMiner/derived/target_injection_state.json``。
* **player_status / restart_game / set_system_proxy**：tasklist / steam / winreg 的游戏控制。

设计约定（很重要）：

1. 模块顶层**不 import gflzirc、不起线程、不读游戏状态、不联网**；
   gflzirc 与 ``scripts/gflh_target_train.py`` 都是**懒加载**，只在显式函数调用时加载。
2. 编号规划直接复用 ``scripts/gflh_target_train.py`` 的
   ``plan_add / add_payload / del_payload / update_state / load_state / save_state``，
   不重复实现。
3. 日志/状态里**不出现 sign**（``capture_status()`` 只给 ``sign_set``；写 creds 文件才落 sign）。
4. 所有会碰游戏进程 / 系统代理 / 网络的动作都只在对应函数被调用时发生；
   unittest 全部 mock，禁止真启动代理、改系统代理、杀游戏。
5. 需要落盘的数据目录统一走 ``targetforge.datapaths``（``TARGETFORGE_DATA_DIR``
   可覆盖）：``DATA_DIR`` / ``DEFAULT_CREDS`` 来自 datapaths；``STATE_FILE``
   （``dataMiner/derived/target_injection_state.json``）为兼容老脚本固定在仓库根。

用法（app.py 里懒加载调用）::

    from targetforge import gflh
    current = gflh.current_targets("auto")
    plan = gflh.plan("replace", [6549244, 6630136], current=current)
    result = gflh.execute("replace", [6549244, 6630136], dry_run=True)
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import random
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from targetforge.datapaths import CREDS_LATEST as DEFAULT_CREDS
from targetforge import creds_store
from targetforge.datapaths import DATA_DIR

# ---------------------------------------------------------------------------
# 常量（contract §3）
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DERIVED = ROOT / "dataMiner" / "derived"
# 兼容原 gf_forge 脚本的既有路径：本地注入状态固定写仓库根
# dataMiner/derived/target_injection_state.json，**不跟** TARGETFORGE_DATA_DIR 走
# （scripts/gflh_target_train.py 等老脚本也读这个位置）。
# 只有 creds / catalog / app 的 state.json 走 datapaths 的 DATA_DIR
# （默认 dataMiner/derived/targetforge，可用 TARGETFORGE_DATA_DIR 覆盖）。
STATE_FILE = DERIVED / "target_injection_state.json"

CAPTURE_PORT = 18080          # 默认抓包端口（capture_start(port=...) 可配；别用 8080）
PORT_MIN, PORT_MAX = 1, 65535
RESERVED_CAPTURE_PORTS = {8080}   # 本机另一个 bot 占用，禁止用于抓包
STATIC_KEY = "yundoudou"
API_ADD = "Targettrain/addCollect"
API_DEL = "Targettrain/delCollect"
MAX_TARGETS = 35

STEAM_APPID = 3347970
GAME_PROCESS = "GrilsFrontLine.exe"
GAME_WINDOW_TITLE = "少女前线"
STEAM_URL = f"steam://rungameid/{STEAM_APPID}"

SIGN_STALE_SECONDS = 6 * 3600     # sign 通常每次登录都换；超过 6h 提示重新抓取
CAPTURE_LOG_LIMIT = 200           # 状态里日志环形缓存上限
CAPTURE_URL_LIMIT = 60            # 记录/去重多少条 URL
CAPTURE_AUTO_STOP_DELAY = 3.0     # 抓齐后延迟几秒自动停（先让游戏把响应收完）
CAPTURE_WATCH_INTERVAL = 0.5
SLEEP_RANGE = (0.5, 0.6)          # 注入每条之间的间隔

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_TRAIN_MODULE = None
_TRAIN_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 小工具：时间 / JSON / 懒加载
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """本地时区的 ISO 时间（带 offset，前端可直接 new Date()）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _fmt_age(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return f"{seconds:.0f} 秒"
    if seconds < 90 * 60:
        return f"{seconds / 60:.1f} 分钟"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} 小时"
    return f"{seconds / 86400:.1f} 天"


def _read_json(path) -> dict | None:
    """读 JSON 对象；文件不存在/损坏/不是对象都返回 None（不抛）。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def _require_gflzirc():
    """懒加载 gflzirc（顶层不 import，保证纯逻辑/单测不依赖它）。"""
    try:
        import gflzirc  # noqa: WPS433 - 必须懒加载
        return gflzirc
    except Exception as exc:  # noqa: BLE001 - 缺包/装坏都按不可用处理
        raise RuntimeError(
            f"gflzirc 不可用（{type(exc).__name__}: {exc}）；"
            "请在仓库根用系统 python 安装 gflzirc==0.4.4") from exc


def _gflzirc_ok() -> bool:
    try:
        import gflzirc  # noqa: F401,WPS433
        return True
    except Exception:  # noqa: BLE001
        return False


def _train():
    """懒加载 scripts/gflh_target_train.py（复用 plan_add/add_payload/...）。"""
    global _TRAIN_MODULE
    if _TRAIN_MODULE is not None:
        return _TRAIN_MODULE
    with _TRAIN_LOCK:
        if _TRAIN_MODULE is not None:
            return _TRAIN_MODULE
        script = ROOT / "scripts" / "gflh_target_train.py"
        if not script.is_file():
            # 工作区整理后脚本可能被归到 simBattle/scripts；按常见位置回退查找。
            for candidate in (ROOT / "simBattle" / "scripts" / "gflh_target_train.py",
                              ROOT / "misc" / "scripts" / "gflh_target_train.py"):
                if candidate.is_file():
                    script = candidate
                    break
        if not script.is_file():
            raise RuntimeError(f"缺少 {script}：靶机编号规划依赖它")
        spec = importlib.util.spec_from_file_location("targetforge._gflh_target_train", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载 {script}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _TRAIN_MODULE = module
        return module


# ---------------------------------------------------------------------------
# plan 内部工具
# ---------------------------------------------------------------------------
def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_current(current) -> list[dict]:
    """current（current_targets 的 dict 或 targets 列表）→ [{order, team}]，按 order 升序。

    * team <= 0 的条目丢弃；order 缺失按 0 处理（排在最后）。
    * 完全相同的 (order, team) 只保留一条（避免重复发 del）。
    """
    if current is None:
        return []
    items = current.get("targets") if isinstance(current, dict) else current
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for raw in items or []:
        if isinstance(raw, dict):
            order = _as_int(raw.get("order"), 0)
            team = _as_int(raw.get("team"), 0)
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            order, team = _as_int(raw[0], 0), _as_int(raw[1], 0)
        else:
            continue
        if team <= 0:
            continue
        key = (order, team)
        if key in seen:
            continue
        seen.add(key)
        out.append({"order": order, "team": team})
    out.sort(key=lambda item: item["order"] if item["order"] > 0 else 10 ** 9)
    return out


def _dedupe_draft(draft_team_ids) -> tuple[list[int], list[int]]:
    """草稿去重（保留第一次出现），返回 (unique, duplicated)。"""
    unique: list[int] = []
    dup: list[int] = []
    seen: set[int] = set()
    for raw in draft_team_ids or []:
        team = _as_int(raw, 0)
        if team <= 0:
            continue
        if team in seen:
            dup.append(team)
            continue
        seen.add(team)
        unique.append(team)
    return unique, dup


def _duplicate_orders(targets: list[dict]) -> dict[int, list[int]]:
    buckets: dict[int, list[int]] = {}
    for item in targets:
        order = _as_int(item.get("order"), 0)
        team = _as_int(item.get("team"), 0)
        if order <= 0 or team <= 0:
            continue
        buckets.setdefault(order, []).append(team)
    return {order: teams for order, teams in buckets.items() if len(teams) > 1}


def _entries(pairs) -> list[dict]:
    """把 [(order, team)] 规范成 [{"order","team"}]（去重、按 order 排序）。"""
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for order, team in pairs:
        key = (int(order), int(team))
        if key in seen:
            continue
        seen.add(key)
        out.append({"order": int(order), "team": int(team)})
    out.sort(key=lambda item: item["order"] if item["order"] > 0 else 10 ** 9)
    return out


def _merge_final(kept: list[dict], adds: list[dict]) -> list[dict]:
    merged = list(kept) + list(adds)
    merged.sort(key=lambda item: item["order"] if item["order"] > 0 else 10 ** 9)
    return merged


def _finalize_plan(mode: str, *, deletes: list[dict], adds: list[dict], kept: list[dict],
                   skipped: list[dict], warnings: list[str], valid: bool,
                   max_targets: int) -> dict:
    """统一收口：去重、排序、final、payload、合法性检查。"""
    train = _train()
    max_targets = int(max_targets or MAX_TARGETS)
    deletes = _entries((item["order"], item["team"]) for item in deletes)
    adds = _entries((item["order"], item["team"]) for item in adds)
    kept = _entries((item["order"], item["team"]) for item in kept)
    final = _merge_final(kept, adds)

    if len(adds) > max_targets:
        valid = False
        warnings.append(f"计划新增 {len(adds)} 个，超过上限 {max_targets}")
    if len(final) > max_targets:
        valid = False
        warnings.append(f"最终 {len(final)} 个靶机，超过上限 {max_targets}")
    from_add = [item for item in adds if item["order"] < 1]
    if from_add:
        valid = False
        warnings.append(f"有 {len(from_add)} 条新增没有合法 order_id")
    over = [item for item in final if item["order"] > max_targets]
    if over:
        valid = False
        warnings.append(f"有 {len(over)} 条编号超过上限 {max_targets}："
                        f"{[item['order'] for item in over]}")
    final_orders = [item["order"] for item in final if item["order"] > 0]
    if len(final_orders) != len(set(final_orders)):
        dup_orders = sorted({order for order in final_orders if final_orders.count(order) > 1})
        warnings.append(f"最终列表编号重复：{dup_orders}（当前列表本身已有重复编号，"
                        "append/replace 无法消除，建议 rebuild）")
    final_teams = [item["team"] for item in final]
    dup_teams = sorted({team for team in final_teams if final_teams.count(team) > 1})
    if dup_teams:
        warnings.append(f"最终列表里有重复队伍：{dup_teams}（注入可能报 error:300，建议 rebuild）")
    missing_order = [item for item in deletes if item["order"] <= 0]
    if missing_order:
        warnings.append(f"有 {len(missing_order)} 条删除没有 order_id（国服会报 error:300）："
                        f"{[item['team'] for item in missing_order]}")

    payloads = {
        "add": [train.add_payload(item["order"], item["team"]) for item in adds],
        "del": [train.del_payload(item["team"], item["order"]) for item in deletes],
    }
    if not valid and not any("不合法" in text for text in warnings):
        warnings.append("执行计划不合法，请修正后再执行（可先 dry_run 预览 payload）")
    return {
        "mode": mode,
        "deletes": deletes,
        "adds": adds,
        "kept": kept,
        "skipped": skipped,
        "final": final,
        "warnings": warnings,
        "valid": bool(valid),
        "payloads": payloads,
    }


# ---------------------------------------------------------------------------
# plan（纯函数，不联网）
# ---------------------------------------------------------------------------
PLAN_MODES = ("append", "replace", "rebuild", "clear")


def plan(mode: str, draft_team_ids: list[int], *, current: dict | list | None = None,
         max_targets: int = MAX_TARGETS) -> dict:
    """离线规划注入顺序（纯函数，不联网、不读文件）。

    * ``append``：接在现有靶机后面（跳过已有队伍，编号接 max+1）
    * ``replace``：草稿第 i 个替换当前第 i 号靶机（i=1..N）；当前多出来的保留；
      草稿队伍若已存在于当前其它编号，先删旧项；草稿重复队伍 → valid=False
    * ``rebuild``：清空当前全部，再按草稿 1..N 全量填充
    * ``clear``：只清空当前全部（adds 为空）

    返回 ``{mode, deletes, adds, kept, skipped, final, warnings, valid, payloads}``；
    ``payloads.add`` / ``payloads.del`` 直接就是 addCollect / delCollect 的请求体。
    """
    mode = str(mode or "").strip().lower()
    if mode not in PLAN_MODES:
        raise ValueError(f"未知执行模式：{mode!r}（可用：append / replace / rebuild / clear）")
    try:
        max_targets = int(max_targets or MAX_TARGETS)
    except (TypeError, ValueError):
        max_targets = MAX_TARGETS
    if max_targets < 1:
        max_targets = MAX_TARGETS

    existing = _normalize_current(current)
    draft, dup_draft = _dedupe_draft(draft_team_ids)
    warnings: list[str] = []
    skipped: list[dict] = [{"team": team, "reason": "草稿里重复出现，已忽略"}
                           for team in dup_draft]
    if dup_draft:
        warnings.append(f"草稿里有重复队伍：{dup_draft}（已按第一次出现去重）")

    if len(draft) > max_targets:
        warnings.append(f"草稿 {len(draft)} 个，超过上限 {max_targets}")

    if mode == "clear":
        deletes = list(existing)
        if not deletes:
            warnings.append("当前没有靶机，无需清空")
        return _finalize_plan(mode, deletes=deletes, adds=[], kept=[], skipped=[],
                              warnings=warnings, valid=True, max_targets=max_targets)

    if not draft:
        if mode == "replace":
            warnings.append("草稿是空的，replace 什么都不会替换（当前列表保留）")
        elif mode == "rebuild":
            warnings.append("草稿是空的，rebuild 会清空当前全部靶机")
        return _finalize_plan(mode, deletes=list(existing) if mode == "rebuild" else [],
                              adds=[], kept=[] if mode == "rebuild" else list(existing),
                              skipped=skipped, warnings=warnings, valid=True,
                              max_targets=max_targets)

    train = _train()
    wanted = [{"order": index, "team": team} for index, team in enumerate(draft, 1)]

    if mode == "append":
        result = train.plan_add(existing, wanted, renumber=False)
        adds = [{"order": item["order"], "team": int(item["team"])}
                for item in result.get("add") or []]
        skipped.extend(result.get("skipped") or [])
        if result.get("duplicates"):
            warnings.append(f"当前列表里编号重复：{result['duplicates']}"
                            "（append 只往后接号，不会修复重复）")
        if result.get("skipped"):
            warnings.append(f"有 {len(result['skipped'])} 个队伍因已在列表/超过上限被跳过")
        return _finalize_plan(mode, deletes=[], adds=adds, kept=list(existing),
                              skipped=skipped, warnings=warnings, valid=True,
                              max_targets=max_targets)

    if mode == "rebuild":
        result = train.plan_add(existing, wanted, renumber=True)
        adds = [{"order": item["order"], "team": int(item["team"])}
                for item in result.get("add") or []]
        if existing:
            warnings.append(f"rebuild 会先删除当前全部 {len(existing)} 个靶机，再按 1..{len(adds)} 重排")
        return _finalize_plan(mode, deletes=list(existing), adds=adds, kept=[],
                              skipped=skipped, warnings=warnings, valid=True,
                              max_targets=max_targets)

    # mode == "replace"
    draft_teams = set(draft)
    count = len(draft)
    deleted_keys: set[tuple[int, int]] = set()
    deletes: list[dict] = []
    kept: list[dict] = []

    def _delete(item: dict) -> None:
        key = (item["order"], item["team"])
        if key in deleted_keys:
            return
        deleted_keys.add(key)
        deletes.append(dict(item))

    replaced = [item for item in existing if 1 <= item["order"] <= count]
    for item in replaced:
        _delete(item)
    # 草稿队伍若已存在于当前其它编号（含 order>N 的保留区），先删旧项避免重复
    for item in existing:
        if item in replaced:
            continue
        if item["team"] in draft_teams:
            _delete(item)
            warnings.append(f"队伍 {item['team']} 已在当前编号 {item['order']}，"
                            f"先删除旧项再放到新编号")
    for item in existing:
        if item in replaced:
            continue
        if any(entry["order"] == item["order"] and entry["team"] == item["team"]
               for entry in deletes):
            continue
        kept.append(item)
    adds = [{"order": order, "team": team} for order, team in enumerate(draft, 1)]

    if dup_draft:
        warnings.append("replace 模式下草稿有重复队伍，只能保留第一个（计划不合法）")
        valid = False
    else:
        valid = True
    if count > max_targets:
        valid = False
    if existing and any(item["order"] <= 0 for item in existing):
        warnings.append("当前列表有靶机缺少 order_id，删除时可能失败（error:300）")
    duplicate_current = _duplicate_orders(existing)
    if duplicate_current:
        warnings.append(f"当前列表编号重复：{duplicate_current}（replace 只会删除 1..{count} 号）")
    return _finalize_plan("replace", deletes=deletes, adds=adds, kept=kept,
                          skipped=skipped, warnings=warnings, valid=valid,
                          max_targets=max_targets)


# ---------------------------------------------------------------------------
# current_targets / list_creds / load_creds_file（只读本地文件）
# ---------------------------------------------------------------------------
def _stale_warning(captured_at) -> str | None:
    moment = _parse_iso(captured_at)
    if moment is None:
        return None
    if moment.tzinfo is None:
        now = datetime.now()
        moment = moment.replace(tzinfo=now.astimezone().tzinfo)
    else:
        now = datetime.now(moment.tzinfo)
    age = (now - moment).total_seconds()
    if age > SIGN_STALE_SECONDS:
        return (f"凭证抓取于 {_fmt_age(age)}前（{captured_at}），sign 可能已过期；"
                "建议重新登录抓取")
    return None


def _build_current(*, source: str, targets: list[dict], uid=None, base_url=None,
                   captured_at=None, creds_file=None, state_file=None,
                   extra_warnings: list[str] | None = None) -> dict:
    warnings = list(extra_warnings or [])
    duplicates = _duplicate_orders(targets)
    if duplicates:
        text = "；".join(f"编号 {order} 被 {len(teams)} 个队伍占用 {teams}"
                        for order, teams in sorted(duplicates.items()))
        warnings.append(f"当前列表编号重复：{text}。建议用 rebuild 重排。")
    missing = [item for item in targets if _as_int(item.get("order"), 0) <= 0]
    if missing:
        warnings.append(f"有 {len(missing)} 个靶机没有编号（order_id=0），"
                        "删除可能失败（error:300），建议 rebuild")
    if len(targets) > MAX_TARGETS:
        warnings.append(f"当前 {len(targets)} 个靶机，超过上限 {MAX_TARGETS}")
    if not targets and source != "none":
        warnings.append("当前没有收藏标靶")
    stale = _stale_warning(captured_at)
    if stale:
        warnings.append(stale)
    if source == "creds" and not captured_at:
        warnings.append("creds 缺少 captured_at，无法判断 sign 新鲜度")
    out = {
        "source": source,
        "creds_file": creds_file,
        "uid": str(uid) if uid else None,
        "base_url": base_url or None,
        "captured_at": captured_at,
        "targets": targets,
        "duplicate_orders": duplicates,
        "max_targets": MAX_TARGETS,
        "warnings": warnings,
    }
    if state_file:
        out["state_file"] = state_file
    return out


def _targets_from_enemies(enemies, orders) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    enemy_list = list(enemies or []) if isinstance(enemies, (list, tuple)) else []
    order_list = list(orders or []) if isinstance(orders, (list, tuple)) else []
    if order_list and len(order_list) != len(enemy_list):
        warnings.append(f"creds 里 enemies({len(enemy_list)}) 与 orders({len(order_list)}) "
                        "数量不一致，缺失编号按 0 处理")
    if enemy_list and not order_list:
        warnings.append("creds 缺少 orders（编号），建议重新登录抓取")
    targets: list[dict] = []
    for index, raw in enumerate(enemy_list):
        team = _as_int(raw, 0)
        if team <= 0:
            warnings.append(f"忽略非法队伍 id：{raw!r}")
            continue
        order = _as_int(order_list[index], 0) if index < len(order_list) else 0
        targets.append({"order": order, "team": team})
    targets.sort(key=lambda item: item["order"] if item["order"] > 0 else 10 ** 9)
    return targets, warnings


def _current_from_creds(creds: dict, path=None) -> dict:
    creds = creds or {}
    extra: list[str] = []
    if "enemies" not in creds:
        extra.append("creds 里没有当前收藏标靶列表（可能没抓到 Index/index）；建议重新登录抓取")
    targets, warnings = _targets_from_enemies(creds.get("enemies"), creds.get("orders"))
    extra.extend(warnings)
    name = Path(path).name if path else DEFAULT_CREDS.name
    return _build_current(source="creds", targets=targets, uid=creds.get("uid"),
                          base_url=creds.get("base_url"),
                          captured_at=creds.get("captured_at"),
                          creds_file=name, extra_warnings=extra)


def _current_from_state() -> dict:
    state_path = Path(STATE_FILE)
    if not state_path.is_file():
        return _build_current(
            source="state", targets=[], state_file=state_path.name,
            extra_warnings=[f"没有本地状态文件 {state_path.name}"
                            "（先执行一次注入，或从凭证列表加载）"])
    payload = _read_json(state_path)
    if payload is None:
        return _build_current(source="state", targets=[], state_file=state_path.name,
                              extra_warnings=[f"本地状态文件读取失败：{state_path.name}"])
    targets: list[dict] = []
    for item in payload.get("targets") or []:
        if not isinstance(item, dict):
            continue
        order = _as_int(item.get("order"), 0)
        team = _as_int(item.get("team"), 0)
        if team <= 0:
            continue
        targets.append({"order": order, "team": team})
    targets.sort(key=lambda item: item["order"] if item["order"] > 0 else 10 ** 9)
    if not targets:
        extra = [f"本地状态文件里没有靶机：{state_path.name}"]
    else:
        extra = []
    return _build_current(source="state", targets=targets, uid=payload.get("uid"),
                          base_url=payload.get("base_url"),
                          captured_at=payload.get("updated_at"),
                          state_file=state_path.name, extra_warnings=extra)


def current_targets(source: str = "auto") -> dict:
    """当前收藏标靶（真实列表）。

    ``source``：``auto``（creds 优先，缺 targets 时回退本地状态） / ``creds`` / ``state``。
    返回结构见 contract §3；``warnings`` 会提示 sign 较旧、编号重复、数量为 0 等。
    不会返回 sign。
    """
    source = str(source or "auto").strip().lower()
    if source not in ("auto", "creds", "state"):
        raise ValueError(f"未知数据源：{source!r}（可用：auto / creds / state）")

    creds_path = Path(DEFAULT_CREDS)
    creds = creds_store.read_creds(creds_path) if creds_path.is_file() else None

    if source == "state":
        return _current_from_state()

    if source == "creds":
        if creds is None:
            return _build_current(
                source="creds", targets=[], creds_file=creds_path.name,
                extra_warnings=[f"没有凭证文件 {creds_path.name}：请先登录抓取，"
                                "或从凭证列表加载一个"])
        return _current_from_creds(creds, creds_path)

    # auto：capture 抓到的 creds（服务端真值）优先
    if creds is not None:
        if "enemies" in creds:
            return _current_from_creds(creds, creds_path)
        state_current = _current_from_state()
        if state_current["targets"]:
            return state_current
        return _current_from_creds(creds, creds_path)
    state_current = _current_from_state()
    if state_current["targets"]:
        return state_current
    return _build_current(
        source="none", targets=[],
        extra_warnings=["没有可用的当前靶机数据：请先用登录抓取拿到 uid/sign，"
                        "或先执行一次注入生成本地状态"])


def migrate_creds_encryption() -> bool:
    """启动时把历史明文 creds_latest.json 迁移为 DPAPI 加密（失败静默）。"""
    try:
        return creds_store.migrate_plain(DEFAULT_CREDS)
    except OSError:
        return False


def _creds_summary(path: Path) -> dict | None:
    payload = creds_store.read_creds(path)
    if payload is None:
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(
            timespec="seconds")
    except OSError:
        mtime = None
    enemies = payload.get("enemies")
    targets_count = len(enemies) if isinstance(enemies, (list, tuple)) else 0
    uid = payload.get("uid")
    return {
        "name": path.name,
        "path": str(path),
        "updated_at": payload.get("captured_at") or mtime,
        "uid": str(uid) if uid not in (None, "") else None,
        "base_url": payload.get("base_url") or None,
        "targets_count": targets_count,
    }


def list_creds() -> list[dict]:
    """扫描可用的凭证文件（不返回 sign），按更新时间倒序。"""
    out: list[dict] = []
    seen: set[str] = set()
    patterns = (
        (Path(DATA_DIR), "creds_*.json"),
        (Path(DERIVED), "cn_creds*.json"),
        (Path(DERIVED), "tw_creds*.json"),
    )
    for directory, pattern in patterns:
        try:
            if not directory.is_dir():
                continue
            paths = sorted(directory.glob(pattern))
        except OSError:
            continue
        for path in paths:
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            info = _creds_summary(path)
            if info is not None:
                out.append(info)
    out.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return out


def load_creds_file(name: str) -> dict:
    """把指定凭证文件复制成 ``creds_latest.json``，返回 ``current_targets("creds")``。

    文件不存在 / 不是合法 JSON / 缺 uid+sign 时抛 ValueError（app.py 可包成 4xx）。
    """
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("缺少凭证文件名")
    base_name = Path(raw).name
    target: Path | None = None
    for entry in list_creds():
        if entry["name"] == base_name or entry["path"] == raw:
            target = Path(entry["path"])
            break
    if target is None:
        candidate = Path(raw)
        try:
            resolved = candidate.resolve()
            allowed = {Path(DATA_DIR).resolve(), Path(DERIVED).resolve()}
            if (resolved.is_file() and resolved.parent in allowed
                    and resolved.suffix.lower() == ".json"):
                target = candidate
        except OSError:
            target = None
    if target is None or not target.is_file():
        raise ValueError(f"没有这个凭证文件：{base_name}")
    payload = creds_store.read_creds(target)
    if payload is None:
        raise ValueError(f"凭证文件不是合法 JSON：{base_name}")
    if not payload.get("uid") or not payload.get("sign"):
        raise ValueError(f"凭证文件不完整（缺少 uid/sign）：{base_name}")
    creds_store.write_creds(DEFAULT_CREDS, payload)
    result = current_targets(source="creds")
    result["ok"] = True
    result["loaded_from"] = base_name
    result["loaded_at"] = _now_iso()
    return result


# ---------------------------------------------------------------------------
# capture：GFLProxy 抓 uid/sign + 当前收藏标靶
# ---------------------------------------------------------------------------
def _new_capture_state() -> dict:
    return {
        "state": "idle",              # idle|starting|running|stopped|error
        "port": CAPTURE_PORT,
        "proxy_active": False,
        "system_proxy_on": False,
        "auto_restore_proxy": True,
        "uid": None,
        "sign": None,
        "base_url": None,
        "enemies": [],
        "orders": [],
        "urls": [],
        "login_captured": False,
        "targets_captured": False,
        "started_at": None,
        "started_mono": None,
        "stopped_at": None,
        "elapsed_s": 0.0,
        "creds_path": None,
        "error": None,
        "logs": [],
        "proxy": None,
        "watchdog": None,
        "auto_stop_at": None,
        "stopping": False,
    }


_CAPTURE = _new_capture_state()
_CAPTURE_LOCK = threading.RLock()
_CAPTURE_GENERATION = 0          # 每次 start 自增；旧 watchdog 看到代数变化自行退出


# ---------------------------------------------------------------------------
# 端口工具：抓包端口可配置，系统代理地址一律由「当前会话端口」推导
# ---------------------------------------------------------------------------
def _validate_capture_port(port) -> tuple[int, str | None]:
    """校验抓包端口：None / "" / 0 视为未指定 → 默认 18080。返回 (port, error)。"""
    if port is None or (isinstance(port, str) and not port.strip()):
        return CAPTURE_PORT, None
    try:
        value = int(str(port).strip())
    except (TypeError, ValueError):
        return CAPTURE_PORT, (f"端口不是整数：{port!r}"
                              f"（请用 {PORT_MIN}~{PORT_MAX} 之间的数字，默认 {CAPTURE_PORT}）")
    if value == 0:
        return CAPTURE_PORT, None
    if value in RESERVED_CAPTURE_PORTS:
        return value, (f"端口 {value} 被本机另一个 bot 占用，不能用于抓包；"
                       f"请用默认 {CAPTURE_PORT} 或其它未占用端口")
    if not (PORT_MIN <= value <= PORT_MAX):
        return value, (f"端口 {value} 越界（必须在 {PORT_MIN}~{PORT_MAX} 之间，"
                       f"常用 {CAPTURE_PORT}）")
    return value, None


def _as_valid_port(port) -> int:
    """把任意输入转成合法端口（不合法 → 默认 18080）。"""
    value = _as_int(port, 0)
    return value if PORT_MIN <= value <= PORT_MAX else CAPTURE_PORT


def _recent_capture_port() -> int:
    """最近一次抓包会话端口；没有会话时用默认 18080。保留端口 8080 不参与。"""
    with _CAPTURE_LOCK:
        port = _as_int(_CAPTURE.get("port"), 0)
    if PORT_MIN <= port <= PORT_MAX and port not in RESERVED_CAPTURE_PORTS:
        return port
    return CAPTURE_PORT


def _has_capture_session() -> bool:
    """是否已经有过抓包会话（running / stopped / error 都算）。"""
    with _CAPTURE_LOCK:
        return _CAPTURE.get("state") in ("starting", "running", "stopped", "error")


def _proxy_addr(port: int | None = None) -> str:
    """系统代理地址：显式端口优先，否则最近会话端口 / 默认 18080。"""
    return f"127.0.0.1:{_as_valid_port(port) if port is not None else _recent_capture_port()}"


def _port_available(port: int) -> tuple[bool, str]:
    """检查 127.0.0.1:port 能否 bind（bind 后立刻释放；单测会 mock）。"""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:  # pragma: no cover - 极端环境
        return False, f"无法创建 socket 检查端口 {port}：{exc}"
    try:
        probe.settimeout(1.0)
        probe.bind(("127.0.0.1", int(port)))
        return True, ""
    except OSError as exc:
        return False, (f"端口 {port} 无法监听：{exc}；可能被其它程序占用，"
                       f"请换一个端口（默认 {CAPTURE_PORT}）")
    finally:
        try:
            probe.close()
        except OSError:  # pragma: no cover
            pass


def _cap_log(level: str, text: str) -> None:
    """写抓包日志（环形缓存 ≤200；自动把 sign 打码，避免泄漏）。"""
    level = str(level or "info").strip().lower()
    if level not in ("info", "warn", "error"):
        level = "info"
    text = str(text)
    with _CAPTURE_LOCK:
        sign = _CAPTURE.get("sign")
        if sign:
            text = text.replace(str(sign), "***")
        entry = {"t": _now_iso(), "level": level, "text": text}
        logs = _CAPTURE.setdefault("logs", [])
        logs.append(entry)
        if len(logs) > CAPTURE_LOG_LIMIT:
            del logs[: len(logs) - CAPTURE_LOG_LIMIT]


def capture_status() -> dict:
    """抓包状态（不含 sign；logs ≤200）。"""
    with _CAPTURE_LOCK:
        elapsed = _CAPTURE.get("elapsed_s") or 0.0
        started = _CAPTURE.get("started_mono")
        if _CAPTURE.get("state") == "running" and started is not None:
            elapsed = round(time.monotonic() - started, 1)
        else:
            elapsed = round(float(elapsed or 0.0), 1)
        return {
            "state": _CAPTURE.get("state") or "idle",
            "port": int(_CAPTURE.get("port") or CAPTURE_PORT),
            "proxy_active": bool(_CAPTURE.get("proxy_active")),
            "system_proxy_on": bool(_CAPTURE.get("system_proxy_on")),
            "auto_restore_proxy": bool(_CAPTURE.get("auto_restore_proxy")),
            "uid": _CAPTURE.get("uid") or None,
            "sign_set": bool(_CAPTURE.get("sign")),
            "base_url": _CAPTURE.get("base_url") or None,
            "targets_count": len(_CAPTURE.get("enemies") or []),
            "login_captured": bool(_CAPTURE.get("login_captured")),
            "targets_captured": bool(_CAPTURE.get("targets_captured")),
            "started_at": _CAPTURE.get("started_at"),
            "elapsed_s": elapsed,
            "creds_path": _CAPTURE.get("creds_path"),
            "error": _CAPTURE.get("error"),
            "logs": [dict(item) for item in (_CAPTURE.get("logs") or [])[-CAPTURE_LOG_LIMIT:]],
        }


def _capture_fail(message: str) -> dict:
    """把抓包状态置为 error 并返回 status（错误同时写 logs，方便前端展示）。"""
    with _CAPTURE_LOCK:
        _CAPTURE["state"] = "error"
        _CAPTURE["error"] = str(message)
        _CAPTURE["proxy_active"] = False
    _cap_log("error", message)
    return capture_status()


def _derive_base_url(url: str) -> str | None:
    """从 ``http://host/index.php/1000/Index/index`` 还原 base_url。

    相对路径（``/index.php/1000/...``）没有 host，无法还原 → 返回 None。
    """
    if not url:
        return None
    marker = "index.php/"
    if marker not in url:
        return None
    head, tail = url.split(marker, 1)
    segment = tail.split("/", 1)[0]
    if not segment.isdigit():
        return None
    if not head.lower().startswith(("http://", "https://")):
        return None  # 相对路径没有 host，无法还原 base_url
    return f"{head}{marker}{segment}/"


def _remember_url(url: str) -> None:
    if not url:
        return
    with _CAPTURE_LOCK:
        urls = _CAPTURE.setdefault("urls", [])
        if url in urls:
            return
        if len(urls) >= CAPTURE_URL_LIMIT:
            return
        urls.append(url)
        base = _derive_base_url(url)
        set_base = None
        if base and not _CAPTURE.get("base_url"):
            _CAPTURE["base_url"] = base
            set_base = base
    _cap_log("info", f"流量：{url}")
    if set_base:
        _cap_log("info", f"服务器地址：{set_base}")


def _on_capture_traffic(event_type, url, payload) -> None:
    """GFLProxy 回调：解析 SYS_KEY_UPGRADE / Index/index 的 targettrain_collect_user_info。"""
    try:
        with _CAPTURE_LOCK:
            if _CAPTURE.get("state") != "running":
                return
        if url:
            _remember_url(str(url))
        if event_type == "SYS_KEY_UPGRADE" and isinstance(payload, dict):
            uid = payload.get("uid")
            sign = payload.get("sign")
            if uid and sign:
                with _CAPTURE_LOCK:
                    _CAPTURE["uid"] = str(uid)
                    _CAPTURE["sign"] = str(sign)
                    _CAPTURE["login_captured"] = True
                _cap_log("info", f"抓到登录凭证：uid={uid}（sign 已获取，不写入日志）")
        if event_type == "S2C" and url and "Index/index" in str(url) \
                and isinstance(payload, dict):
            info = payload.get("targettrain_collect_user_info")
            if isinstance(info, list):
                enemies: list[str] = []
                orders: list[str] = []
                for item in info:
                    if not isinstance(item, dict):
                        continue
                    team = item.get("enemy_team_id")
                    order = item.get("order_id")
                    if team is not None:
                        enemies.append(str(team))
                    if order is not None:
                        orders.append(str(order))
                with _CAPTURE_LOCK:
                    _CAPTURE["enemies"] = enemies
                    _CAPTURE["orders"] = orders
                    _CAPTURE["targets_captured"] = True
                _cap_log("info", f"抓到当前收藏标靶：{len(enemies)} 个")
    except Exception:  # noqa: BLE001 - 回调绝不能把代理搞崩
        pass


def _call_set_windows_proxy(enable: bool, addr: str | None = None) -> bool:
    """包装 gflzirc.set_windows_proxy；任何异常都吞掉返回 False。

    ``enable=True`` 且没给 ``addr`` 时用最近会话端口（没有会话用默认 18080），
    绝不把端口写死成 18080。
    """
    try:
        gflzirc = _require_gflzirc()
    except RuntimeError:
        return False
    try:
        if enable:
            return bool(gflzirc.set_windows_proxy(True, addr or _proxy_addr()))
        return bool(gflzirc.set_windows_proxy(False))
    except Exception:  # noqa: BLE001
        return False


def _restore_system_proxy() -> bool:
    ok = _call_set_windows_proxy(False)
    with _CAPTURE_LOCK:
        _CAPTURE["system_proxy_on"] = False
    if ok:
        _cap_log("info", "已恢复系统代理（关闭）")
    else:
        _cap_log("warn", "恢复系统代理失败，请手动关闭系统代理")
    return ok


def _write_capture_creds() -> str | None:
    """把已抓到的 uid/sign/enemies/orders 写到 creds_latest.json；返回路径（失败 None）。"""
    with _CAPTURE_LOCK:
        uid = _CAPTURE.get("uid")
        sign = _CAPTURE.get("sign")
        if not uid or not sign:
            return None
        payload = {
            "uid": str(uid),
            "sign": str(sign),
            "base_url": _CAPTURE.get("base_url") or None,
            "enemies": list(_CAPTURE.get("enemies") or []),
            "orders": list(_CAPTURE.get("orders") or []),
            "urls": list(_CAPTURE.get("urls") or []),
            "captured_at": _now_iso(),
        }
    try:
        path = creds_store.write_creds(DEFAULT_CREDS, payload)
    except OSError as exc:
        _cap_log("error", f"写入凭证失败：{type(exc).__name__}: {exc}")
        return None
    return str(path)


def _capture_watchdog(generation: int | None = None) -> None:
    """auto_restore_proxy：抓齐后延迟 CAPTURE_AUTO_STOP_DELAY 秒自动停抓 + 恢复代理。"""
    while True:
        time.sleep(CAPTURE_WATCH_INTERVAL)
        if generation is not None and generation != _CAPTURE_GENERATION:
            return  # 已被新一轮 capture_start 取代
        should_stop = False
        with _CAPTURE_LOCK:
            if generation is not None and generation != _CAPTURE_GENERATION:
                return
            if _CAPTURE.get("state") != "running":
                return
            if not (_CAPTURE.get("login_captured") and _CAPTURE.get("targets_captured")):
                continue
            stop_at = _CAPTURE.get("auto_stop_at")
            if stop_at is None:
                _CAPTURE["auto_stop_at"] = time.monotonic() + CAPTURE_AUTO_STOP_DELAY
                _cap_log("info", f"登录凭证与靶机列表都已抓到，"
                                 f"{CAPTURE_AUTO_STOP_DELAY:.0f} 秒后自动停止抓包并恢复系统代理")
                continue
            should_stop = time.monotonic() >= stop_at
        if should_stop:
            capture_stop()
            return


def capture_start(*, port: int = CAPTURE_PORT, set_proxy: bool = True,
                  auto_restore_proxy: bool = True) -> dict:
    """启动抓包代理（端口可配置，默认 18080；立即返回 status，不阻塞）。

    * ``port``：监听端口。监听、系统代理地址、``status.port``、
      ``capture_restart_game()`` 设置的系统代理、``capture_stop()`` 恢复代理，
      全部用这一个端口（不会退回写死的 18080）。
    * ``set_proxy``：把系统代理指到 ``127.0.0.1:<port>``
    * ``auto_restore_proxy``：uid/sign + 靶机列表都抓到后，延迟几秒自动停并恢复系统代理

    端口非法（越界 / 8080 保留）或被占用时返回 ``state="error"`` 且 ``error``
    里有可操作提示，不会去改系统代理。
    """
    global _CAPTURE_GENERATION
    port, port_error = _validate_capture_port(port)
    generation = _CAPTURE_GENERATION
    with _CAPTURE_LOCK:
        if _CAPTURE.get("state") in ("starting", "running"):
            _cap_log("warn", "抓包已经在运行，忽略重复启动")
            return capture_status()
        fresh = _new_capture_state()
        fresh["port"] = port if PORT_MIN <= port <= PORT_MAX else CAPTURE_PORT
        fresh["auto_restore_proxy"] = bool(auto_restore_proxy)
        fresh["state"] = "starting"
        _CAPTURE.clear()
        _CAPTURE.update(fresh)
        _CAPTURE_GENERATION += 1
        generation = _CAPTURE_GENERATION
    if port_error:
        return _capture_fail(port_error)

    _cap_log("info", f"启动抓包代理，监听 127.0.0.1:{port}")
    available, reason = _port_available(port)
    if not available:
        return _capture_fail(reason)

    try:
        gflzirc = _require_gflzirc()
    except RuntimeError as exc:
        return _capture_fail(str(exc))

    proxy_addr = _proxy_addr(port)
    if set_proxy:
        proxy_ok = _call_set_windows_proxy(True, proxy_addr)
        with _CAPTURE_LOCK:
            _CAPTURE["system_proxy_on"] = bool(proxy_ok)
        if proxy_ok:
            _cap_log("info", f"系统代理已指向 {proxy_addr}")
        else:
            _cap_log("warn", f"设置系统代理失败，请手动把系统代理指到 {proxy_addr}")

    proxy = gflzirc.GFLProxy(port, STATIC_KEY, _on_capture_traffic)
    try:
        proxy.start()
    except Exception as exc:  # noqa: BLE001
        if set_proxy:
            _restore_system_proxy()
        return _capture_fail(f"抓包代理启动失败：{type(exc).__name__}: {exc}"
                             f"（端口 {port} 可能被占用）")

    with _CAPTURE_LOCK:
        _CAPTURE["proxy"] = proxy
        _CAPTURE["proxy_active"] = True
        _CAPTURE["state"] = "running"
        _CAPTURE["started_at"] = _now_iso()
        _CAPTURE["started_mono"] = time.monotonic()
    _cap_log("info", f"抓包已启动（端口 {port}）：请强制重启游戏并登录"
                     "（在登录/主界面会抓到 uid、sign 和当前收藏标靶）")

    if auto_restore_proxy:
        watchdog = threading.Thread(target=_capture_watchdog, args=(generation,),
                                    name="gflh-capture-watchdog", daemon=True)
        with _CAPTURE_LOCK:
            _CAPTURE["watchdog"] = watchdog
        watchdog.start()
    return capture_status()


def capture_stop() -> dict:
    """停止抓包：停代理 → 恢复系统代理 → 写 creds_latest.json。未启动时安全返回。

    恢复系统代理是「关闭系统代理」（与本次会话用的端口无关，不需要端口）。
    """
    with _CAPTURE_LOCK:
        state = _CAPTURE.get("state") or "idle"
        port = _as_int(_CAPTURE.get("port"), CAPTURE_PORT)
        if state in ("idle", "stopped"):
            _cap_log("warn", "抓包未在运行，无需停止")
            return capture_status()
        if _CAPTURE.get("stopping"):
            return capture_status()
        _CAPTURE["stopping"] = True
        proxy = _CAPTURE.get("proxy")
        started = _CAPTURE.get("started_mono")
        if started is not None:
            _CAPTURE["elapsed_s"] = round(time.monotonic() - started, 1)
            _CAPTURE["started_mono"] = None
        _CAPTURE["proxy"] = None
        _CAPTURE["proxy_active"] = False

    if proxy is not None:
        try:
            proxy.stop()
        except Exception as exc:  # noqa: BLE001
            _cap_log("warn", f"停止抓包代理时出错：{type(exc).__name__}: {exc}")
    if _CAPTURE.get("system_proxy_on"):
        _restore_system_proxy()
    creds_path = _write_capture_creds()
    with _CAPTURE_LOCK:
        _CAPTURE["state"] = "stopped"
        _CAPTURE["stopped_at"] = _now_iso()
        if creds_path:
            _CAPTURE["creds_path"] = creds_path
        _CAPTURE["stopping"] = False
    if creds_path:
        _cap_log("info", f"抓包已停止（端口 {port}），凭证写入 {creds_path}")
    else:
        _cap_log("warn", f"抓包已停止（端口 {port}），但没抓到完整凭证"
                         "（uid/sign），未写 creds_latest.json")
    return capture_status()


def capture_restart_game() -> dict:
    """抓包运行时：设系统代理 → 强杀游戏 → steam 重启游戏（让流量走代理登录）。

    必须已有活跃抓包会话（``state == "running"``），否则返回清晰错误；
    系统代理地址用当前会话端口（``capture_start(port=X)`` 的 X）。
    """
    with _CAPTURE_LOCK:
        state = _CAPTURE.get("state") or "idle"
        port = _as_int(_CAPTURE.get("port"), CAPTURE_PORT)
    if state != "running":
        return {
            "ok": False,
            "state": state,
            "error": "没有活跃的抓包会话（未启动或已停止）",
            "steps": [],
            "hint": f"先用端口 {port} 点「开始抓取」，再点「设置代理并重启游戏」",
        }
    addr = _proxy_addr(port)
    steps: list[str] = []
    proxy_ok = _call_set_windows_proxy(True, addr)
    with _CAPTURE_LOCK:
        _CAPTURE["system_proxy_on"] = bool(proxy_ok)
    steps.append(f"设置系统代理 {addr}")
    _cap_log("info" if proxy_ok else "warn",
             f"系统代理已指向 {addr}" if proxy_ok else f"设置系统代理失败，请手动指到 {addr}")

    pids = _game_pids()
    killed = _kill_game(pids)
    if killed:
        _wait_game_gone()
        steps.append("强杀游戏")
        _cap_log("info", "已强制退出游戏")
    else:
        steps.append("游戏未运行，跳过强杀")
        _cap_log("info", "游戏未在运行，跳过强杀")

    launched = _launch_game()
    if launched:
        steps.append("重新启动游戏")
        _cap_log("info", "已通过 Steam 启动游戏，等待登录…")
    else:
        _cap_log("error", "启动游戏失败：请手动打开 Steam 启动游戏")
    return {
        "ok": bool(launched),
        "steps": steps,
        "system_proxy": addr if proxy_ok else None,
        "hint": "游戏启动后请登录并进入主界面；抓到 uid/sign + 收藏标靶后会自动停止抓包并恢复系统代理",
    }


# ---------------------------------------------------------------------------
# execute：真正发 addCollect / delCollect
# ---------------------------------------------------------------------------
def _pace() -> None:
    """注入间隔 0.5~0.6s（单测会 patch 掉）。"""
    try:
        time.sleep(random.uniform(*SLEEP_RANGE))
    except Exception:  # noqa: BLE001
        pass


def _response_error(response) -> str | None:
    """从 GFLClient.send_request 的返回里判断失败（返回错误文本，成功 None）。"""
    if not isinstance(response, dict):
        return None
    error = response.get("error")
    if error not in (None, "", 0, "0"):
        return str(error)
    if response.get("error_local"):
        return str(response.get("error_local"))
    if response.get("success") is False:
        return str(response.get("msg") or response.get("message") or "服务器返回 success=false")
    return None


def _error_hint(error: str) -> str:
    text = str(error or "").lower()
    if "300" in text:
        return "队伍不可收藏或重复；删除时还可能是 order_id 不正确"
    if any(key in text for key in ("sign", "auth", "401", "403", "key")):
        return "sign 可能已过期，请重新登录抓取"
    if any(key in text for key in ("network", "timeout", "connection", "ssl", "proxy")):
        return "网络异常，检查网络/服务器地址；也确认抓包代理已停止"
    return "可重试；若持续失败请重新登录抓取凭证"


def _resolve_creds_path(creds_file) -> Path:
    """creds_file 可以是绝对路径、相对路径、或 dataMiner/derived 下的文件名。"""
    if not creds_file:
        return Path(DEFAULT_CREDS)
    raw = str(creds_file).strip()
    candidate = Path(raw)
    options: list[Path] = []
    if candidate.is_absolute():
        options.append(candidate)
    else:
        options.extend([
            candidate,
            Path(ROOT) / candidate,
            Path(DERIVED) / candidate,
            Path(DERIVED) / candidate.name,
            Path(DATA_DIR) / candidate.name,
        ])
    for option in options:
        try:
            if option.is_file():
                return option
        except OSError:
            continue
    if candidate.name:
        for entry in list_creds():
            if entry["name"] == candidate.name or entry["path"] == raw:
                return Path(entry["path"])
    return candidate if candidate.is_absolute() else Path(DATA_DIR) / candidate.name


def _exec_creds(creds_file):
    path = _resolve_creds_path(creds_file)
    creds = creds_store.read_creds(path) if path.is_file() else None
    return path, creds


def _exec_current(creds: dict | None, creds_path: Path, explicit: bool) -> dict:
    if creds is not None and "enemies" in creds:
        return _current_from_creds(creds, creds_path)
    if explicit:
        return _current_from_creds(creds or {}, creds_path)
    return current_targets(source="auto")


def _make_client(uid: str, sign: str, base_url: str):
    """创建 GFLClient，并强制绕过系统代理（否则请求会打进抓包代理）。"""
    gflzirc = _require_gflzirc()
    client = gflzirc.GFLClient(str(uid), str(sign), str(base_url))
    try:
        session = getattr(client, "session", None)
        if session is not None:
            session.trust_env = False
            session.proxies.clear()
    except Exception:  # noqa: BLE001
        pass
    return client


def execute(mode: str, draft_team_ids: list[int], *, creds_file: str | None = None,
            dry_run: bool = False, log=None, cancel=None) -> dict:
    """执行注入（同步，app.py 放线程池跑）。

    * ``dry_run=True``：只返回 payload，**不联网**（不构造 GFLClient）；
    * 真跑：先 DEL 再 ADD，每条间隔 0.5~0.6s，逐条 ``log(level, text)``；
      单条失败继续，成功的条目同步到本地 ``target_injection_state.json``；
    * ``cancel()`` 返回 True 时在下一步前停下。

    返回 ``{ok, mode, deleted, added, failed, final, creds_file, restart_required, ...}``。
    """
    def _log(level: str, text: str) -> None:
        if callable(log):
            try:
                log(level, text)
            except Exception:  # noqa: BLE001 - 日志失败不能影响执行
                pass

    def _canceled() -> bool:
        if callable(cancel):
            try:
                return bool(cancel())
            except Exception:  # noqa: BLE001
                return False
        return False

    mode = str(mode or "").strip().lower()
    try:
        draft = [_as_int(item, 0) for item in (draft_team_ids or [])]
        draft = [team for team in draft if team > 0]
    except (TypeError, ValueError):
        return {"ok": False, "mode": mode, "error": "draft_team_ids 里有非整数",
                "deleted": 0, "added": 0, "failed": [], "final": [],
                "creds_file": None, "restart_required": False}

    creds_path, creds = _exec_creds(creds_file)
    current = _exec_current(creds, creds_path, explicit=bool(creds_file))
    try:
        plan_result = plan(mode, draft, current=current)
    except ValueError as exc:
        return {"ok": False, "mode": mode, "error": str(exc), "deleted": 0,
                "added": 0, "failed": [], "final": [], "creds_file": str(creds_path),
                "restart_required": False}

    if dry_run:
        _log("info", f"[dry_run] 模式 {mode}：删除 {len(plan_result['deletes'])}，"
                     f"新增 {len(plan_result['adds'])}，保留 {len(plan_result['kept'])}")
        for item in plan_result["deletes"]:
            _log("info", f"[dry_run] del 收藏標靶{item['order']} team={item['team']}")
        for item in plan_result["adds"]:
            _log("info", f"[dry_run] add 收藏標靶{item['order']} team={item['team']}")
        for warning in plan_result["warnings"]:
            _log("warn", f"[dry_run] {warning}")
        return {
            "ok": True,
            "mode": mode,
            "dry_run": True,
            "deleted": 0,
            "added": 0,
            "failed": [],
            "final": plan_result["final"],
            "warnings": plan_result["warnings"],
            "payloads": plan_result["payloads"],
            "plan": plan_result,
            "creds_file": str(creds_path),
            "restart_required": False,
        }

    if not plan_result["valid"]:
        _log("error", "执行计划不合法：" + "；".join(plan_result["warnings"][-4:]))
        return {
            "ok": False,
            "mode": mode,
            "dry_run": False,
            "error": "执行计划不合法",
            "warnings": plan_result["warnings"],
            "deleted": 0,
            "added": 0,
            "failed": [],
            "final": plan_result["final"],
            "payloads": plan_result["payloads"],
            "creds_file": str(creds_path),
            "restart_required": False,
        }

    if creds is None:
        return {
            "ok": False, "mode": mode, "dry_run": False,
            "error": f"没有凭证文件：{creds_path}",
            "hint": "先做登录抓取（uid/sign），或从凭证列表加载一个",
            "deleted": 0, "added": 0, "failed": [], "final": plan_result["final"],
            "creds_file": str(creds_path), "restart_required": False,
        }
    uid = str(creds.get("uid") or "").strip()
    sign = str(creds.get("sign") or "").strip()
    base_url = str(creds.get("base_url") or "").strip()
    missing = [name for name, value in (("uid", uid), ("sign", sign),
                                        ("base_url", base_url)) if not value]
    if missing:
        return {
            "ok": False, "mode": mode, "dry_run": False,
            "error": f"凭证不完整（缺少 {'/'.join(missing)}）：{creds_path.name}",
            "hint": "重新登录抓取（sign 每次登录都会变）",
            "deleted": 0, "added": 0, "failed": [], "final": plan_result["final"],
            "creds_file": str(creds_path), "restart_required": False,
        }

    try:
        client = _make_client(uid, sign, base_url)
    except RuntimeError as exc:
        return {
            "ok": False, "mode": mode, "dry_run": False, "error": str(exc),
            "hint": "在仓库根用系统 python 安装 gflzirc==0.4.4",
            "deleted": 0, "added": 0, "failed": [], "final": plan_result["final"],
            "creds_file": str(creds_path), "restart_required": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "mode": mode, "dry_run": False,
            "error": f"创建 GFLClient 失败：{type(exc).__name__}: {exc}",
            "deleted": 0, "added": 0, "failed": [], "final": plan_result["final"],
            "creds_file": str(creds_path), "restart_required": False,
        }

    train = _train()
    try:
        state = train.load_state(STATE_FILE)
    except Exception:  # noqa: BLE001
        state = {"targets": []}

    def _save_state() -> None:
        try:
            train.save_state(state, STATE_FILE)
        except Exception as exc:  # noqa: BLE001
            _log("warn", f"写本地状态失败：{type(exc).__name__}: {exc}")

    deleted: list[dict] = []
    added: list[dict] = []
    failed: list[dict] = []
    canceled = False

    _log("info", f"凭证 uid={uid} @ {base_url}；模式 {mode}："
                 f"删除 {len(plan_result['deletes'])} 条，新增 {len(plan_result['adds'])} 条")

    for item in plan_result["deletes"]:
        if _canceled():
            canceled = True
            _log("warn", "收到取消请求：停止执行（已完成的部分生效）")
            break
        team = int(item["team"])
        order = int(item.get("order") or 0)
        try:
            response = client.send_request(API_DEL, train.del_payload(team, order))
            error = _response_error(response)
            if error:
                failed.append({"step": "del", "team": team, "order": order,
                               "error": error, "hint": _error_hint(error)})
                _log("error", f"删除收藏標靶{order} team={team} 失败：{error}"
                              f"（{_error_hint(error)}）")
            else:
                deleted.append({"order": order, "team": team})
                train.update_state(state, delete=[team])
                _save_state()
                _log("info", f"删除收藏標靶{order} team={team} 成功")
        except Exception as exc:  # noqa: BLE001 - 单条失败继续
            failed.append({"step": "del", "team": team, "order": order,
                           "error": f"{type(exc).__name__}: {exc}",
                           "hint": "网络/接口异常，可重试；若持续失败请重新登录抓取"})
            _log("error", f"删除收藏標靶{order} team={team} 异常：{exc}")
        _pace()

    for item in plan_result["adds"]:
        if canceled or _canceled():
            canceled = True
            _log("warn", "收到取消请求：停止执行（已完成的部分生效）")
            break
        team = int(item["team"])
        order = int(item["order"])
        try:
            response = client.send_request(API_ADD, train.add_payload(order, team))
            error = _response_error(response)
            if error:
                failed.append({"step": "add", "team": team, "order": order,
                               "error": error, "hint": _error_hint(error)})
                _log("error", f"新增收藏標靶{order} team={team} 失败：{error}"
                              f"（{_error_hint(error)}）")
            else:
                added.append({"order": order, "team": team})
                train.update_state(state, add=[{"order": order, "team": team}])
                _save_state()
                _log("info", f"新增收藏標靶{order} team={team} 成功")
        except Exception as exc:  # noqa: BLE001 - 单条失败继续
            failed.append({"step": "add", "team": team, "order": order,
                           "error": f"{type(exc).__name__}: {exc}",
                           "hint": "网络/接口异常，可重试；若持续失败请重新登录抓取"})
            _log("error", f"新增收藏標靶{order} team={team} 异常：{exc}")
        _pace()

    try:
        train.update_state(state, uid=uid, base_url=base_url)
        _save_state()
    except Exception as exc:  # noqa: BLE001
        _log("warn", f"写本地状态失败：{type(exc).__name__}: {exc}")

    ok = not failed and not canceled
    restart_required = bool(deleted or added)
    result = {
        "ok": ok,
        "mode": mode,
        "dry_run": False,
        "deleted": len(deleted),
        "added": len(added),
        "failed": failed,
        "final": plan_result["final"],
        "creds_file": str(creds_path),
        "state_file": str(STATE_FILE),
        "restart_required": restart_required,
        "canceled": canceled,
        "deleted_items": deleted,
        "added_items": added,
        "warnings": plan_result["warnings"],
    }
    if failed:
        _log("warn", f"执行完成：成功删除 {len(deleted)} / 新增 {len(added)}，失败 {len(failed)} 条")
    elif canceled:
        _log("warn", f"已取消：成功删除 {len(deleted)} / 新增 {len(added)}")
    else:
        _log("info", f"执行完成：删除 {len(deleted)}，新增 {len(added)}")
    if restart_required:
        _log("info", "请大退重登游戏同步靶机列表；清空靶机后必须强退，"
                     "否则进靶机界面可能卡死")
    return result


# ---------------------------------------------------------------------------
# 游戏控制：player_status / restart_game / set_system_proxy
# ---------------------------------------------------------------------------
def _run(cmd: list[str], *, timeout: float = 15.0):
    """跑一条系统命令（创建时不弹窗；单测里 mock 掉 subprocess.run）。"""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          errors="replace", creationflags=CREATE_NO_WINDOW)


def _parse_tasklist_pids(text: str, process: str = GAME_PROCESS) -> list[int]:
    """解析 ``tasklist /FO CSV /NH`` 输出，拿进程 pid 列表。"""
    pids: list[int] = []
    target = process.lower()
    for row in csv.reader(io.StringIO(text or "")):
        if len(row) >= 2 and row[0].strip().lower() == target:
            try:
                pids.append(int(row[1].strip()))
            except (TypeError, ValueError):
                continue
    return pids


def _game_pids() -> list[int]:
    """tasklist 查游戏进程（只读，不杀）。失败按未运行处理。"""
    try:
        proc = _run(["tasklist", "/FI", f"IMAGENAME eq {GAME_PROCESS}",
                     "/FO", "CSV", "/NH"], timeout=10.0)
    except Exception:  # noqa: BLE001
        return []
    return _parse_tasklist_pids(getattr(proc, "stdout", "") or "")


def _kill_game(pids: list[int] | None = None) -> bool:
    """taskkill 强杀游戏；游戏没在跑返回 False（避免无意义调用）。"""
    if pids is None:
        pids = _game_pids()
    if not pids:
        return False
    try:
        proc = _run(["taskkill", "/IM", GAME_PROCESS, "/F"], timeout=15.0)
    except Exception:  # noqa: BLE001
        return False
    if int(getattr(proc, "returncode", 0) or 0) == 0:
        return True
    return not _game_pids()


def _wait_game_gone(timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout))
    while time.monotonic() < deadline:
        if not _game_pids():
            return True
        time.sleep(0.25)
    return not _game_pids()


def _launch_game() -> bool:
    """通过 Steam 启动游戏（steam://rungameid/3347970）。"""
    try:
        proc = _run(["cmd", "/c", "start", "", STEAM_URL], timeout=15.0)
    except Exception:  # noqa: BLE001
        return False
    return int(getattr(proc, "returncode", 0) or 0) == 0


def _window_title(pid: int) -> str | None:
    """用 EnumWindows 找该进程的可见窗口标题（只读；失败 None）。"""
    if not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # noqa: BLE001
        return None
    try:
        user32 = ctypes.windll.user32
        titles: list[str] = []

        def _callback(hwnd, _lparam):  # noqa: ANN001
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                process_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                if process_id.value == pid and buffer.value:
                    titles.append(buffer.value)
            except Exception:  # noqa: BLE001
                pass
            return True

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(enum_proc(_callback), 0)
        return titles[0] if titles else None
    except Exception:  # noqa: BLE001
        return None


def _read_system_proxy() -> str | None:
    """读 Windows 系统代理（HKCU Internet Settings）；未开启/失败返回 None。"""
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return None
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            try:
                enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except OSError:
                return None
            if not enabled:
                return None
            try:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except OSError:
                return None
            return str(server) if server else None
    except OSError:
        return None


def player_status() -> dict:
    """游戏进程 / 系统代理 / gflzirc 状态（只读，不动游戏）。"""
    pids = _game_pids()
    pid = pids[0] if pids else None
    return {
        "game_running": bool(pids),
        "pid": pid,
        "game_window_title": _window_title(pid) if pid else None,
        "system_proxy": _read_system_proxy(),
        "gflzirc_ok": _gflzirc_ok(),
    }


def restart_game(*, wait_ready: bool = True) -> dict:
    """大退重登：强杀游戏 → Steam 启动（无代理；注入完同步靶机列表用）。"""
    steps: list[str] = []
    pids = _game_pids()
    killed = _kill_game(pids)
    if killed:
        _wait_game_gone()
        steps.append("强杀游戏")
    else:
        steps.append("游戏未运行，跳过强杀")
    launched = _launch_game()
    steps.append("启动游戏" if launched else "启动游戏失败")
    waited = 0.0
    if wait_ready and launched:
        started = time.monotonic()
        deadline = started + 30.0
        while time.monotonic() < deadline:
            if _game_pids():
                break
            time.sleep(0.5)
        waited = round(time.monotonic() - started, 1)
    return {
        "ok": bool(launched),
        "steps": steps,
        "killed": bool(killed),
        "launched": bool(launched),
        "waited_s": waited,
        "hint": ("靶机改动需要大退重登才会同步；清空靶机后必须强退，"
                 "否则进靶机界面可能卡死"),
    }


def set_system_proxy(enable: bool, addr: str | None = None) -> dict:
    """开关 Windows 系统代理（包装 gflzirc.set_windows_proxy）。

    ``addr`` **显式优先**（例如 ``capture_start(port=18093)`` 后传
    ``127.0.0.1:18093``）；没给 addr 时用最近一次抓包会话端口，没有会话时用
    默认 ``CAPTURE_PORT``（18080）——不会无条件写死 18080。
    """
    if enable:
        explicit = str(addr).strip() if addr is not None else ""
        if explicit:
            address, source = explicit, "explicit"
        else:
            address = _proxy_addr()
            source = "session" if _has_capture_session() else "default"
        ok = _call_set_windows_proxy(True, address)
        port = _as_int(address.rsplit(":", 1)[-1], 0)
        return {
            "ok": bool(ok),
            "enabled": bool(ok),
            "addr": address,
            "port": port if PORT_MIN <= port <= PORT_MAX else None,
            "source": source,
            "system_proxy": _read_system_proxy(),
            "hint": "" if ok else "设置失败：确认 gflzirc 可用；也可以手动改系统代理",
        }
    ok = _call_set_windows_proxy(False)
    return {
        "ok": bool(ok),
        "enabled": False,
        "addr": None,
        "port": None,
        "source": "disable",
        "system_proxy": _read_system_proxy(),
        "hint": "" if ok else "关闭失败：请手动关闭系统代理",
    }
