"""靶机工坊 TargetForge —— 本地 Web 服务（Lead 维护）。

启动：``python -m targetforge``（默认 http://127.0.0.1:8765）。

这里只做 HTTP/路由/前端状态/job 管理；数据与 GFLH 逻辑分别在
``targetforge.catalog`` / ``targetforge.gflh``（见 contract.md）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
MAX_TARGETS = 35
VERSION = "1.6.0"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from targetforge.datapaths import DATA_DIR, ICON_DIR, STATE_FILE, ensure_dirs  # noqa: E402

# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_CATALOG_STATE = {"state": "cold", "detail": "", "started_at": None, "error": None}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class HttpError(Exception):
    def __init__(self, status: int, error: str, detail: str | None = None, hint: str | None = None):
        super().__init__(error)
        self.status = status
        self.payload = {"error": error}
        if detail:
            self.payload["detail"] = detail
        if hint:
            self.payload["hint"] = hint


def _jsonable(value):
    """把 Path / set 之类转成 JSON 可序列化。"""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


# ---------------------------------------------------------------------------
# 前端状态（draft / tutorial / settings）
# ---------------------------------------------------------------------------
DEFAULT_STATE = {
    "draft": [],
    "tutorial": {"completed": [], "dismissed": False},
    "settings": {
        "capture_port": 18080,
        "auto_restore_proxy": True,
        "preferred_creds": "creds_latest.json",
        "append_skip_existing": True,
    },
    "last_execution": None,
    "updated_at": None,
}


def state_load() -> dict:
    with _LOCK:
        state = json.loads(json.dumps(DEFAULT_STATE))
        if STATE_FILE.is_file():
            try:
                payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    state.update({k: v for k, v in payload.items() if k in state})
            except (OSError, json.JSONDecodeError):
                pass
        state["draft"] = [int(t) for t in (state.get("draft") or [])
                          if isinstance(t, (int, float, str)) and str(t).lstrip("-").isdigit()]
        return state


def state_save(state: dict) -> dict:
    with _LOCK:
        state["updated_at"] = now_iso()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE_FILE)
        return state


# ---------------------------------------------------------------------------
# catalog / gflh 懒加载
# ---------------------------------------------------------------------------
def _catalog_module():
    from targetforge import catalog  # noqa: WPS433 - 延迟导入
    return catalog


def catalog_status() -> dict:
    with _LOCK:
        return dict(_CATALOG_STATE)


def warm_catalog(*, rebuild: bool = False) -> None:
    """后台重建/加载 catalog（启动时与 /api/catalog/refresh 用）。"""
    with _LOCK:
        if _CATALOG_STATE["state"] == "building":
            return
        _CATALOG_STATE.update({"state": "building", "started_at": now_iso(), "error": None})
    started = time.time()

    def work():
        try:
            catalog = _catalog_module()
            if rebuild:
                catalog.build(force=True)
                if hasattr(catalog, "reload"):
                    catalog.reload()
            cat = catalog.load()
            info = {"state": "ready", "built_at": getattr(cat, "built_at", None),
                    "counts": getattr(cat, "counts", {}), "elapsed_s": round(time.time() - started, 1),
                    "error": None, "detail": ""}
        except Exception as exc:  # noqa: BLE001 - 后台线程必须兜住
            info = {"state": "error", "error": f"{type(exc).__name__}: {exc}",
                    "detail": traceback.format_exc()[-2000:], "elapsed_s": round(time.time() - started, 1)}
        with _LOCK:
            _CATALOG_STATE.update(info)

    threading.Thread(target=work, name="catalog-warm", daemon=True).start()


def get_catalog():
    catalog = _catalog_module()
    with _LOCK:
        state = _CATALOG_STATE["state"]
    if state == "ready":
        return catalog.load()
    if state in ("cold", "error"):
        warm_catalog()
    status = catalog_status()
    raise HttpError(503, "数据正在构建，请稍候",
                    detail=status.get("error") or status.get("state"),
                    hint="首次启动/重建大约需要 20~60 秒，页面会自动重试。")


def _gflh_module():
    try:
        from targetforge import gflh
    except ModuleNotFoundError as exc:
        raise HttpError(503, "GFLH 模块未安装 / 依赖缺失", detail=str(exc),
                        hint="确认已安装 gflzirc，并在仓库根目录运行 python -m targetforge。")
    return gflh


# ---------------------------------------------------------------------------
# job 管理
# ---------------------------------------------------------------------------
def start_job(kind: str, fn) -> dict:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "kind": kind,
        "state": "running",
        "created_at": now_iso(),
        "finished_at": None,
        "logs": [],
        "result": None,
        "error": None,
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job
    cancel_event = threading.Event()
    job["_cancel"] = cancel_event

    def log(level: str, text: str) -> None:
        with _JOBS_LOCK:
            entry = {"t": now_iso(), "level": level, "text": str(text)}
            job["logs"].append(entry)
            if len(job["logs"]) > 800:
                del job["logs"][: len(job["logs"]) - 800]

    job["log"] = log

    def run():
        try:
            job["result"] = fn(job)
            job["state"] = "done"
        except HttpError as exc:
            job["state"] = "error"
            job["error"] = exc.payload.get("error") or str(exc)
            log("error", job["error"])
        except Exception as exc:  # noqa: BLE001
            job["state"] = "error"
            job["error"] = f"{type(exc).__name__}: {exc}"
            log("error", job["error"])
            log("error", traceback.format_exc()[-1200:])
        finally:
            job["finished_at"] = now_iso()

    threading.Thread(target=run, name=f"job-{kind}-{job_id}", daemon=True).start()
    return job


def job_public(job: dict) -> dict:
    with _JOBS_LOCK:
        return {
            "id": job["id"],
            "kind": job["kind"],
            "state": job["state"],
            "created_at": job["created_at"],
            "finished_at": job["finished_at"],
            "logs": list(job["logs"]),
            "result": job["result"],
            "error": job["error"],
        }


# ---------------------------------------------------------------------------
# 序列
# ---------------------------------------------------------------------------
def _team_summaries(team_ids: list[int]) -> list[dict]:
    catalog = get_catalog()
    return catalog.team_summaries([int(t) for t in team_ids])


def sequence_payload() -> dict:
    state = state_load()
    draft_ids = state.get("draft") or []
    summaries = _team_summaries(draft_ids) if draft_ids else []
    by_id = {int(item["id"]): item for item in summaries}
    ordered = [by_id[t] for t in draft_ids if t in by_id]
    missing = [t for t in draft_ids if t not in by_id]
    return {
        "draft": ordered,
        "count": len(ordered),
        "max": MAX_TARGETS,
        "missing": missing,
        "updated_at": state.get("updated_at"),
    }


def _resolve_team_ids(team_ids) -> list[int]:
    catalog = get_catalog()
    out: list[int] = []
    for raw in team_ids or []:
        try:
            team_id = int(raw)
        except (TypeError, ValueError):
            raise HttpError(400, "team 参数不是整数", detail=repr(raw))
        if catalog.team(team_id) is None:
            raise HttpError(400, f"队伍 {team_id} 不在可收藏队伍里",
                            hint="只能加入「可收藏」队伍；刷新数据后重试。")
        out.append(team_id)
    return out


def api_sequence_get() -> dict:
    return sequence_payload()


def api_sequence_post(body: dict) -> dict:
    action = str(body.get("action") or "").strip()
    state = state_load()
    draft = list(state.get("draft") or [])
    if action in ("add", "add_many"):
        team_ids = body.get("team_ids")
        if team_ids is None and body.get("team_id") is not None:
            team_ids = [body.get("team_id")]
        ids = _resolve_team_ids(team_ids)
        position = body.get("position")
        for team_id in ids:
            if team_id in draft:
                continue
            if isinstance(position, int) and 0 <= position <= len(draft):
                draft.insert(position, team_id)
                position += 1
            else:
                draft.append(team_id)
        if len(draft) > MAX_TARGETS:
            raise HttpError(400, f"序列超过上限 {MAX_TARGETS}",
                            detail=f"当前 {len(draft)}",
                            hint="先移除一部分队伍，或分批执行。")
    elif action == "remove":
        team_id = int(body.get("team_id"))
        draft = [t for t in draft if t != team_id]
    elif action == "move":
        try:
            src, dst = int(body.get("from")), int(body.get("to"))
        except (TypeError, ValueError):
            raise HttpError(400, "move 需要 from / to 下标")
        if not (0 <= src < len(draft) and 0 <= dst < len(draft)):
            raise HttpError(400, "move 下标越界", detail=f"from={src} to={dst} n={len(draft)}")
        item = draft.pop(src)
        draft.insert(dst, item)
    elif action == "set":
        draft = _resolve_team_ids(body.get("team_ids"))
        if len(draft) > MAX_TARGETS:
            raise HttpError(400, f"序列超过上限 {MAX_TARGETS}")
    elif action == "clear":
        draft = []
    elif action == "import_current":
        gflh = _gflh_module()
        current = gflh.current_targets(source=str(body.get("source") or "auto"))
        raw_ids = [int(t["team"]) for t in current.get("targets") or []]
        catalog = get_catalog()
        draft = [team_id for team_id in raw_ids if catalog.team(team_id) is not None]
        if not draft and raw_ids:
            raise HttpError(400, "当前靶机都不在本机数据里",
                            hint="可能服务器版本/数据缓存过旧，先刷新数据再导入。")
        draft = draft[:MAX_TARGETS]
    else:
        raise HttpError(400, f"未知 action: {action!r}")
    state["draft"] = draft
    state_save(state)
    return sequence_payload()


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
EXEC_MODES = {"append", "replace", "rebuild", "clear"}


def _exec_request(body: dict) -> tuple[str, list[int], str]:
    mode = str(body.get("mode") or "").strip()
    if mode not in EXEC_MODES:
        raise HttpError(400, f"未知执行模式：{mode!r}",
                        hint="可用模式：append（追加）/ replace（按序号替换）/ rebuild（清空重排）/ clear（清空）")
    state = state_load()
    draft = [int(t) for t in (state.get("draft") or [])]
    if mode != "clear" and not draft:
        raise HttpError(400, "序列是空的", hint="先从关卡/怪种里挑选队伍加入序列。")
    source = str(body.get("source") or "auto")
    if source not in ("auto", "creds", "state"):
        raise HttpError(400, f"未知数据源：{source!r}")
    return mode, draft, source


def api_execute_preview(body: dict) -> dict:
    mode, draft, source = _exec_request(body)
    gflh = _gflh_module()
    current = gflh.current_targets(source=source)
    result = dict(gflh.plan(mode, draft, current=current, max_targets=MAX_TARGETS))
    result["current"] = current
    result["mode"] = mode
    result["draft"] = _team_summaries(draft) if draft else []
    return result


def api_execute(body: dict) -> dict:
    mode, draft, source = _exec_request(body)
    dry_run = bool(body.get("dry_run"))
    creds_file = body.get("creds_file") or None
    gflh = _gflh_module()
    current = gflh.current_targets(source=source)
    plan = gflh.plan(mode, draft, current=current, max_targets=MAX_TARGETS)
    if not plan.get("valid", True) and not dry_run:
        raise HttpError(400, "执行计划不合法", detail="；".join(plan.get("warnings") or []),
                        hint="请先修正序列（重复队伍 / 超过 35 个 / 编号冲突）。")

    def fn(job: dict):
        job["log"]("info", f"模式 {mode}：删除 {len(plan.get('deletes') or [])}，"
                           f"新增 {len(plan.get('adds') or [])}，保留 {len(plan.get('kept') or [])}")
        result = gflh.execute(mode, draft, creds_file=creds_file, dry_run=dry_run,
                              log=job["log"], cancel=job["_cancel"].is_set)
        state = state_load()
        state["last_execution"] = {
            "mode": mode, "dry_run": dry_run, "at": now_iso(),
            "plan": {k: plan.get(k) for k in ("deletes", "adds", "kept", "final", "warnings", "valid")},
            "result": result,
        }
        state_save(state)
        return {"plan": plan, "execution": result}

    job = start_job("execute", fn)
    return {"job_id": job["id"], "plan": plan}


# ---------------------------------------------------------------------------
# 其他 API
# ---------------------------------------------------------------------------
def api_health() -> dict:
    catalog = catalog_status()
    gflzirc_ok = False
    try:
        import gflzirc  # noqa: F401
        gflzirc_ok = True
    except Exception:  # noqa: BLE001
        gflzirc_ok = False
    player = None
    try:
        player = _gflh_module().player_status()
    except Exception as exc:  # noqa: BLE001
        player = {"error": str(exc)}
    try:
        icon_count = len(list(ICON_DIR.glob("*.png"))) if ICON_DIR.is_dir() else 0
    except OSError:
        icon_count = 0
    return {
        "ok": True,
        "app": "TargetForge",
        "version": VERSION,
        "now": now_iso(),
        "catalog": catalog,
        "gflzirc_ok": gflzirc_ok,
        "game": player,
        "data_dir": str(DATA_DIR),
        "icon_dir": str(ICON_DIR),
        "icons": icon_count,
    }


def api_meta() -> dict:
    cat = get_catalog()
    return {"version": VERSION, "built_at": cat.built_at, "counts": cat.counts,
            "max_targets": MAX_TARGETS, "now": now_iso()}


def api_team(team_id: int) -> dict:
    detail = get_catalog().team(team_id)
    if detail is None:
        raise HttpError(404, f"没有队伍 {team_id}", hint="该队伍不可收藏或数据未收录。")
    return detail


def api_teams(qs: dict | None = None) -> dict:
    """全怪组总表：多条件筛选 / 排序 / 分页。"""
    def first(key: str, default: str = "") -> str:
        return ((qs or {}).get(key) or [default])[0]

    def opt_int(key: str):
        raw = first(key, "").strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            raise HttpError(400, f"{key} 不是数字", detail=raw)

    species: list[int] = []
    for chunk in (qs or {}).get("species") or []:
        for part in str(chunk).replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                species.append(int(part))
            except ValueError:
                raise HttpError(400, "species 不是编号", detail=part)

    role = first("role", "any").strip() or "any"
    if role not in ("any", "enemy", "support", "reserve"):
        raise HttpError(400, f"未知角色筛选 {role!r}",
                        hint="可用：any / enemy / support / reserve")
    sort = first("sort", "id_asc").strip() or "id_asc"
    if sort not in ("id_asc", "id_desc", "power_desc", "power_asc", "units_desc",
                    "units_asc", "hp_desc", "species_desc"):
        raise HttpError(400, f"未知排序 {sort!r}",
                        hint="可用：id_asc/id_desc/power_desc/power_asc/units_desc/units_asc/hp_desc/species_desc")
    offset = max(0, int(float(first("offset", "0") or 0)))
    limit = min(200, max(1, int(float(first("limit", "50") or 50))))
    collectable_raw = first("collectable", "1").strip().lower()
    power_known_raw = first("power_known", "").strip().lower()
    return get_catalog().team_list(
        q=first("q", ""),
        chapter=first("chapter", ""),
        species=species or None,
        role=role,
        collectable=collectable_raw not in ("0", "false", "no"),
        power_known=power_known_raw in ("1", "true", "yes") if power_known_raw else None,
        power_min=opt_int("power_min"),
        power_max=opt_int("power_max"),
        units_min=opt_int("units_min"),
        units_max=opt_int("units_max"),
        sort=sort,
        offset=offset,
        limit=limit,
    )


def api_stage(mission_id: int) -> dict:
    data = get_catalog().stage(mission_id)
    if data is None:
        raise HttpError(404, f"没有关卡 {mission_id}")
    return data


def _team_matches(team: dict, query: str) -> bool:
    if not query:
        return True
    haystack = [str(team.get("id")), str(team.get("power")), str(team.get("faction"))]
    for species in team.get("species") or []:
        haystack.extend([str(species.get("codex_no")), str(species.get("name"))])
    for member in team.get("members") or []:
        haystack.extend([str(member.get("code")), str(member.get("name"))])
    haystack.extend(str(tag) for tag in team.get("tags") or [])
    return query in " ".join(haystack).lower()


def _team_filters(qs: dict) -> dict:
    """从 query string 解析队伍筛选/排序参数（效能/排序）。"""
    def first(key: str, default: str = "") -> str:
        return ((qs or {}).get(key) or [default])[0]

    def maybe_float(key: str):
        raw = first(key, "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            raise HttpError(400, f"{key} 不是数字", detail=raw)

    power_known_raw = first("power_known", "").strip().lower()
    sort = first("sort", "default").strip() or "default"
    if sort not in ("default", "power_desc", "power_asc", "hp_desc", "units_desc"):
        raise HttpError(400, f"未知排序 {sort!r}",
                        hint="可用：default / power_desc / power_asc / hp_desc / units_desc")
    return {
        "power_min": maybe_float("power_min"),
        "power_max": maybe_float("power_max"),
        "power_known": power_known_raw in ("1", "true", "yes"),
        "sort": sort,
    }


def _apply_team_query(items: list[dict], qs: dict, *, default_limit: int = 60,
                      max_limit: int = 200) -> dict:
    """对队伍列表做 搜索 / 效能筛选 / 排序 / 分页（内存版，用于 orphan、species 等）。"""
    query = ((qs or {}).get("q") or [""])[0].strip().lower()
    offset = max(0, int(((qs or {}).get("offset") or ["0"])[0] or 0))
    limit = min(max_limit, max(1, int(((qs or {}).get("limit") or [str(default_limit)])[0] or default_limit)))
    filters = _team_filters(qs or {})
    filtered = [item for item in items if _team_matches(item, query)] if query else list(items)
    if filters["power_known"]:
        filtered = [item for item in filtered if item.get("power_known")]
    if filters["power_min"] is not None:
        filtered = [item for item in filtered
                    if item.get("power_known") and float(item.get("power") or 0) >= filters["power_min"]]
    if filters["power_max"] is not None:
        filtered = [item for item in filtered
                    if item.get("power_known") and float(item.get("power") or 0) <= filters["power_max"]]
    sort = filters["sort"]
    if sort == "power_desc":
        filtered.sort(key=lambda it: float(it.get("power") or 0) if it.get("power_known") else float("-inf"),
                      reverse=True)
    elif sort == "power_asc":
        filtered.sort(key=lambda it: float(it.get("power") or 0) if it.get("power_known") else float("inf"))
    elif sort == "hp_desc":
        filtered.sort(key=lambda it: float(it.get("hp_total") or 0), reverse=True)
    elif sort == "units_desc":
        filtered.sort(key=lambda it: float(it.get("units") or 0), reverse=True)
    return {"total": len(filtered), "offset": offset, "limit": limit,
            "items": filtered[offset:offset + limit]}


def _paginate(items: list, qs: dict, default_limit: int = 60, max_limit: int = 200) -> dict:
    return _apply_team_query(items, qs or {}, default_limit=default_limit, max_limit=max_limit)


def api_chapter(chapter_id: str, qs: dict | None = None) -> dict:
    data = get_catalog().chapter(chapter_id)
    if data is None:
        raise HttpError(404, f"没有章节 {chapter_id}")
    if isinstance(data.get("teams"), list):
        # orphan（无固定关卡）章节：直接按 q/offset/limit 分页
        page = _paginate(data["teams"], qs or {})
        data = dict(data)
        data["teams"] = page["items"]
        data["teams_total"] = page["total"]
        data["offset"] = page["offset"]
        data["limit"] = page["limit"]
    return data


def api_current(qs: dict) -> dict:
    source = (qs.get("source") or ["auto"])[0]
    return _gflh_module().current_targets(source=source)


def api_capture_start(body: dict) -> dict:
    gflh = _gflh_module()
    settings = state_load().get("settings") or {}
    port = int(body.get("port") or settings.get("capture_port") or gflh.CAPTURE_PORT)
    return gflh.capture_start(
        port=port,
        set_proxy=bool(body.get("set_proxy", True)),
        auto_restore_proxy=bool(body.get("auto_restore_proxy",
                                       settings.get("auto_restore_proxy", True))),
    )


def _system_proxy_body(body: dict) -> dict:
    """系统代理开关：addr 为空时交给 gflh 用「最近一次抓包端口」，避免写死 18080。"""
    gflh = _gflh_module()
    raw_addr = body.get("addr")
    addr = str(raw_addr).strip() if raw_addr else None
    return gflh.set_system_proxy(bool(body.get("enable")), addr)


def api_catalog_refresh() -> dict:
    def fn(job: dict):
        catalog = _catalog_module()
        meta = catalog.build(force=True)
        if hasattr(catalog, "reload"):
            catalog.reload()
        else:
            catalog.load()
        with _LOCK:
            _CATALOG_STATE.update({"state": "ready", "built_at": meta.get("built_at"),
                                   "counts": meta.get("counts"), "error": None,
                                   "started_at": now_iso(), "detail": ""})
        job["log"]("info", f"catalog 重建完成：{meta.get('counts')}")
        return meta

    job = start_job("catalog-refresh", fn)
    return {"job_id": job["id"]}


def api_tutorial_get() -> dict:
    state = state_load()
    return state.get("tutorial") or {"completed": [], "dismissed": False}


def api_tutorial_post(body: dict) -> dict:
    state = state_load()
    tutorial = state.get("tutorial") or {"completed": [], "dismissed": False}
    if "completed" in body:
        tutorial["completed"] = [str(x) for x in body.get("completed") or []]
    if "dismissed" in body:
        tutorial["dismissed"] = bool(body.get("dismissed"))
    state["tutorial"] = tutorial
    state_save(state)
    return tutorial


def api_settings_get() -> dict:
    return state_load().get("settings") or {}


def api_settings_post(body: dict) -> dict:
    state = state_load()
    settings = state.get("settings") or {}
    for key in ("capture_port", "auto_restore_proxy", "preferred_creds", "append_skip_existing"):
        if key in body:
            settings[key] = body[key]
    if "capture_port" in settings:
        settings["capture_port"] = int(settings["capture_port"])
    state["settings"] = settings
    state_save(state)
    return settings


def api_creds_load(body: dict) -> dict:
    name = str(body.get("name") or "").strip()
    if not name:
        raise HttpError(400, "缺少凭证文件名")
    gflh = _gflh_module()
    try:
        return gflh.load_creds_file(name)
    except ValueError as exc:
        raise HttpError(400, "凭证加载失败", detail=str(exc),
                        hint="从 /api/creds 返回的列表里选一个凭证文件。")


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------
def api_grayzone_teams(qs: dict) -> dict:
    filters = _team_filters(qs or {})
    return get_catalog().grayzone_teams(
        area=(qs.get("area") or [""])[0],
        offset=int((qs.get("offset") or ["0"])[0] or 0),
        limit=min(200, int((qs.get("limit") or ["60"])[0] or 60)),
        q=(qs.get("q") or [""])[0],
        **filters,
    )


GET_ROUTES = [
    (re.compile(r"^/api/health$"), lambda ctx: api_health()),
    (re.compile(r"^/api/meta$"), lambda ctx: api_meta()),
    (re.compile(r"^/api/chapters$"), lambda ctx: get_catalog().chapters()),
    (re.compile(r"^/api/chapters/(?P<cid>[^/]+)$"), lambda ctx: api_chapter(unquote(ctx["match"].group("cid")), ctx["qs"])),
    (re.compile(r"^/api/stages/(?P<mid>-?\d+)$"), lambda ctx: api_stage(int(ctx["match"].group("mid")))),
    (re.compile(r"^/api/teams$"), lambda ctx: api_teams(ctx["qs"])),
    (re.compile(r"^/api/teams/(?P<tid>-?\d+)$"), lambda ctx: api_team(int(ctx["match"].group("tid")))),
    (re.compile(r"^/api/grayzone/areas$"), lambda ctx: {"areas": get_catalog().grayzone_areas()}),
    (re.compile(r"^/api/grayzone/teams$"), lambda ctx: api_grayzone_teams(ctx["qs"])),
    (re.compile(r"^/api/species$"), lambda ctx: get_catalog().species_list(
        q=(ctx["qs"].get("q") or [""])[0],
        faction=(ctx["qs"].get("faction") or [""])[0],
        category=(ctx["qs"].get("category") or [""])[0],
        offset=int((ctx["qs"].get("offset") or ["0"])[0] or 0),
        limit=min(200, int((ctx["qs"].get("limit") or ["60"])[0] or 60)),
    )),
    (re.compile(r"^/api/species/(?P<codex>-?\d+)$"), lambda ctx: api_species_detail(int(ctx["match"].group("codex")), ctx["qs"])),
    (re.compile(r"^/api/search$"), lambda ctx: get_catalog().search(
        (ctx["qs"].get("q") or [""])[0], limit=min(60, int((ctx["qs"].get("limit") or ["20"])[0] or 20)))),
    (re.compile(r"^/api/current$"), lambda ctx: api_current(ctx["qs"])),
    (re.compile(r"^/api/creds$"), lambda ctx: {"creds": _gflh_module().list_creds()}),
    (re.compile(r"^/api/player$"), lambda ctx: _gflh_module().player_status()),
    (re.compile(r"^/api/sequence$"), lambda ctx: api_sequence_get()),
    (re.compile(r"^/api/execute/preview$"), lambda ctx: api_execute_preview(ctx["json"] if ctx["method"] == "POST" else {})),
    (re.compile(r"^/api/jobs/(?P<jid>[0-9a-f]+)$"), lambda ctx: _job_get(ctx["match"].group("jid"))),
    (re.compile(r"^/api/capture/status$"), lambda ctx: _gflh_module().capture_status()),
    (re.compile(r"^/api/tutorial$"), lambda ctx: api_tutorial_get()),
    (re.compile(r"^/api/settings$"), lambda ctx: api_settings_get()),
]

POST_ROUTES = [
    (re.compile(r"^/api/sequence$"), lambda ctx: api_sequence_post(ctx["json"])),
    (re.compile(r"^/api/execute/preview$"), lambda ctx: api_execute_preview(ctx["json"])),
    (re.compile(r"^/api/execute$"), lambda ctx: api_execute(ctx["json"])),
    (re.compile(r"^/api/jobs/(?P<jid>[0-9a-f]+)/cancel$"), lambda ctx: _job_cancel(ctx["match"].group("jid"))),
    (re.compile(r"^/api/capture/start$"), lambda ctx: api_capture_start(ctx["json"])),
    (re.compile(r"^/api/capture/stop$"), lambda ctx: _gflh_module().capture_stop()),
    (re.compile(r"^/api/capture/restart_game$"), lambda ctx: _gflh_module().capture_restart_game()),
    (re.compile(r"^/api/creds/load$"), lambda ctx: api_creds_load(ctx["json"])),
    (re.compile(r"^/api/game/restart$"), lambda ctx: _gflh_module().restart_game(
        wait_ready=bool(ctx["json"].get("wait_ready", True)))),
    (re.compile(r"^/api/system/proxy$"), lambda ctx: _system_proxy_body(ctx["json"])),
    (re.compile(r"^/api/catalog/refresh$"), lambda ctx: api_catalog_refresh()),
    (re.compile(r"^/api/tutorial$"), lambda ctx: api_tutorial_post(ctx["json"])),
    (re.compile(r"^/api/settings$"), lambda ctx: api_settings_post(ctx["json"])),
]


def api_species_detail(codex_no: int, qs: dict | None = None) -> dict:
    data = get_catalog().species(codex_no)
    if data is None:
        raise HttpError(404, f"没有怪种 {codex_no}")
    teams = data.get("teams")
    if isinstance(teams, list):
        page = _paginate(teams, qs or {}, default_limit=60)
        data = dict(data)
        data["teams"] = page["items"]
        data["teams_total"] = page["total"]
        data["total"] = page["total"]
        data["offset"] = page["offset"]
        data["limit"] = page["limit"]
    return data


def _job_get(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HttpError(404, f"没有 job {job_id}")
    return job_public(job)


def _job_cancel(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HttpError(404, f"没有 job {job_id}")
    job["_cancel"].set()
    job["log"]("warn", "收到取消请求，当前步骤结束后停止")
    return {"job_id": job_id, "cancel_requested": True}


STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}


class Handler(BaseHTTPRequestHandler):
    server_version = f"TargetForge/{VERSION}"
    protocol_version = "HTTP/1.1"

    # --- 输出 ---
    def _send(self, status: int, body: bytes, content_type: str, *, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if not cache else "public, max-age=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_jsonable).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, error: str, detail: str | None = None, hint: str | None = None):
        payload = {"error": error}
        if detail:
            payload["detail"] = detail
        if hint:
            payload["hint"] = hint
        self._json(status, payload)

    # --- 静态 ---
    def _static(self, path: str) -> None:
        relative = unquote(path)
        if relative.startswith("/static/"):
            relative = relative[len("/static/"):]
        else:
            relative = relative.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        candidate = (STATIC_DIR / relative).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._error(403, "非法路径")
            return
        if not candidate.is_file():
            if path in ("/favicon.ico",):
                self._send(204, b"", "image/x-icon")
                return
            # 前端是单页应用，未知路径回退 index.html
            candidate = STATIC_DIR / "index.html"
            if not candidate.is_file():
                self._error(404, "静态文件不存在", detail=str(relative))
                return
        content_type = STATIC_TYPES.get(candidate.suffix.lower(), "application/octet-stream")
        self._send(200, candidate.read_bytes(), content_type)

    def _icon(self, name: str) -> None:
        """敌人头像图标：从数据目录 icons/ 下按文件名读取（名称由 catalog 生成，已做白名单校验）。"""
        clean = unquote(name)
        if "/" in clean or "\\" in clean or clean.startswith("."):
            self._error(403, "非法图标名")
            return
        candidate = (ICON_DIR / clean).resolve()
        try:
            candidate.relative_to(ICON_DIR.resolve())
        except ValueError:
            self._error(403, "非法图标路径")
            return
        if not candidate.is_file():
            self._error(404, "图标不存在", detail=clean)
            return
        suffix = candidate.suffix.lower()
        content_type = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}.get(
            suffix, "application/octet-stream")
        self._send(200, candidate.read_bytes(), content_type, cache=True)

    # --- 分发 ---
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        started = time.time()
        try:
            if path.startswith("/api/icons/"):
                self._icon(path[len("/api/icons/"):])
                self._log(method, path, 200, started)
                return
            if path.startswith("/api/"):
                ctx = {
                    "method": method,
                    "match": None,
                    "qs": parse_qs(parsed.query),
                    "json": {},
                }
                routes = GET_ROUTES if method == "GET" else POST_ROUTES
                for pattern, fn in routes:
                    match = pattern.match(path)
                    if not match:
                        continue
                    ctx["match"] = match
                    if method == "POST":
                        length = int(self.headers.get("Content-Length") or 0)
                        if length > 2 * 1024 * 1024:
                            raise HttpError(413, "请求体太大")
                        raw = self.rfile.read(length) if length else b"{}"
                        try:
                            ctx["json"] = json.loads(raw.decode("utf-8") or "{}")
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise HttpError(400, "请求体不是合法 JSON", detail=str(exc))
                        if not isinstance(ctx["json"], dict):
                            raise HttpError(400, "请求体必须是 JSON 对象")
                    result = fn(ctx)
                    self._json(200, result)
                    self._log(method, path, 200, started)
                    return
                raise HttpError(404, f"没有接口 {path}")
            if method != "GET":
                raise HttpError(405, "静态资源只支持 GET")
            self._static(path)
            self._log(method, path, 200, started)
        except HttpError as exc:
            self._json(exc.status, exc.payload)
            self._log(method, path, exc.status, started)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            detail = traceback.format_exc()[-2000:]
            sys.stderr.write(detail + "\n")
            self._error(500, f"内部错误：{type(exc).__name__}", detail=detail)
            self._log(method, path, 500, started)

    def _log(self, method: str, path: str, status: int, started: float) -> None:
        if path.startswith("/static/") or path == "/":
            return
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {method} {path} -> {status} "
              f"({(time.time() - started) * 1000:.0f}ms)", flush=True)

    # --- HTTP 方法 ---
    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_HEAD(self):  # noqa: N802
        self._dispatch("GET")

    def log_message(self, fmt, *args):  # noqa: A003 - 关掉默认 access log（自己打的更短）
        return


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="靶机工坊 TargetForge 本地 Web 应用")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后在浏览器打开")
    parser.add_argument("--rebuild-catalog", action="store_true", help="启动时强制重建数据缓存")
    args = parser.parse_args(argv)

    ensure_dirs()
    warm_catalog(rebuild=args.rebuild_catalog)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    url = f"http://{args.host}:{args.port}/"
    print(f"== 靶机工坊 TargetForge v{VERSION} ==")
    print(f"   本地地址: {url}")
    print(f"   数据目录: {DATA_DIR}")
    print("   Ctrl+C 退出")
    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，退出。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
