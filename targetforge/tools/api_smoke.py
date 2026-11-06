"""真实 catalog 的 API 冒烟（v1.3，Lead 验收用，不碰游戏/网络注入）。

跑法（catalog.json + icons 已生成）：
    python targetforge/tools/api_smoke.py
    python targetforge/tools/api_smoke.py --url http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS: list[str] = []
FAILS: list[str] = []
GROUP_IDS = ["main", "event", "score", "tutorial", "simulation", "grayzone", "orphan"]


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        CHECKS.append(name)
        print(f"  OK   {name}")
    else:
        FAILS.append(f"{name} {detail}")
        print(f"  FAIL {name} {detail}")


def get(base: str, path: str) -> tuple[int, dict | list]:
    try:
        with urllib.request.urlopen(base + path, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, {"_raw": exc.read().decode(errors="replace")[:500]}


def get_bytes(base: str, path: str) -> tuple[int, str, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=60) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, "", b""


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, {"_raw": exc.read().decode(errors="replace")[:500]}


def wait_ready(base: str, timeout: float = 240.0) -> dict:
    started = time.time()
    while time.time() - started < timeout:
        try:
            status, health = get(base, "/api/health")
        except Exception as exc:  # noqa: BLE001
            print("  ... 服务未就绪", exc)
            time.sleep(2)
            continue
        state = (health.get("catalog") or {}).get("state")
        print(f"  ... catalog={state} elapsed={time.time() - started:.0f}s")
        if state == "ready":
            return health
        if state == "error":
            print("catalog 构建失败：", (health.get("catalog") or {}).get("detail", "")[:800])
            return health
        time.sleep(2)
    return {}


def run_checks(base: str, health: dict) -> None:
    check("health 200", bool(health.get("ok")), "")
    check("version 1.5.x", str(health.get("version", "")).startswith("1.5"), str(health.get("version")))
    check("health.data_dir", bool(health.get("data_dir")), "")
    status, meta = get(base, "/api/meta")
    counts = (meta or {}).get("counts") or {}
    print("  counts:", counts)
    check("teams=13700", counts.get("teams") == 13700, str(counts.get("teams")))
    check("species=264", counts.get("species") == 264, str(counts.get("species")))
    check("stages=2345", counts.get("stages") == 2345, str(counts.get("stages")))

    status, chapters = get(base, "/api/chapters")
    groups = (chapters or {}).get("groups") or []
    ids = [g.get("id") for g in groups]
    check("groups 7 个", len(groups) == 7, str(ids))
    check("groups 顺序/ID", ids == GROUP_IDS, str(ids))
    by_id = {g.get("id"): g for g in groups}
    check("score 分组存在且有章节", len(by_id.get("score", {}).get("chapters") or []) >= 10,
          str(len(by_id.get("score", {}).get("chapters") or [])))
    event_chapters = by_id.get("event", {}).get("chapters") or []
    check("event 分组存在", len(event_chapters) >= 30, str(len(event_chapters)))

    # 自画像搜索/章节
    status, search = get(base, "/api/search?q=" + urllib.parse.quote("自画像"))
    found_self = [c for c in (search.get("stages") or []) if "自画像" in (c.get("title") or "")]
    titles = [c.get("title") or "" for g in groups for c in (g.get("chapters") or [])]
    check("自画像章节存在/可搜", any("自画像" in t for t in titles) or bool(found_self),
          f"titles_hit={[t for t in titles if '自画像' in t][:3]} search={len(found_self)}")

    # 灰域 14 区域
    status, areas = get(base, "/api/grayzone/areas")
    area_list = (areas or {}).get("areas") or []
    check("灰域 14 区域", len(area_list) == 14, str([a.get("id") for a in area_list]))
    names = [a.get("id") for a in area_list]
    check("灰域含 庇护所旧址/坍缩狭缝", "庇护所旧址" in names and "坍缩狭缝" in names, str(names))

    # 物种：灰域过滤 66 含法官
    status, gray_species = get(base, "/api/species?category=grayzone&limit=200")
    gray_items = (gray_species or {}).get("items") or []
    gray_total = (gray_species or {}).get("total")
    check("灰域怪种 66（±2）", 64 <= (gray_total or 0) <= 68, str(gray_total))
    judge = [s for s in gray_items if "法官" in (s.get("name") or "") or s.get("codex_no") == 35]
    check("灰域过滤含法官(35)", bool(judge), str([(s.get("codex_no"), s.get("name")) for s in gray_items[:5]]))
    flags = [s for s in gray_items if s.get("has_grayzone")]
    check("species flags has_grayzone", len(flags) == len(gray_items), f"{len(flags)}/{len(gray_items)}")

    # 图标
    icon_items = [s for s in gray_items if s.get("icon")]
    if icon_items:
        status, ctype, body = get_bytes(base, "/api/icons/" + urllib.parse.quote(icon_items[0]["icon"]))
        check("图标接口可用", status == 200 and "image/png" in ctype and body[:4] == b"\x89PNG",
              f"{status} {ctype} {len(body)}")
    else:
        print("  ... 无 icon 数据，跳过图标接口检查")

    # 章节/关卡/队伍
    chapter_ids = [c["id"] for g in groups for c in (g.get("chapters") or [])]
    main1 = "main-1" if "main-1" in chapter_ids else (chapter_ids[0] if chapter_ids else "")
    status, chapter = get(base, "/api/chapters/" + urllib.parse.quote(main1))
    stages = (chapter or {}).get("stages") or []
    check("章节详情有 stages", len(stages) > 0, str(len(stages)))
    stage_id = stages[0]["id"] if stages else 5
    status, stage = get(base, f"/api/stages/{stage_id}")
    teams = (stage or {}).get("teams") or []
    check(f"stage {stage_id} 有队伍", len(teams) > 0, str(len(teams)))
    team_id = teams[0]["id"] if teams else 6549244
    team_id2 = teams[1]["id"] if len(teams) > 1 else team_id
    status, team = get(base, f"/api/teams/{team_id}")
    check("队伍详情字段", status == 200 and team.get("members") and "power_known" in team, str(status))

    # 效能筛选（灰域队伍）
    area = (area_list[0]["id"] if area_list else "")
    status, gz_all = get(base, "/api/grayzone/teams?area=" + urllib.parse.quote(area) + "&limit=5")
    check("灰域队伍分页", status == 200 and (gz_all or {}).get("total", 0) > 0, str(status))
    status, gz_known = get(base, "/api/grayzone/teams?area=" + urllib.parse.quote(area)
                           + "&limit=5&power_known=1&sort=power_desc")
    check("灰域效能筛选接口", status == 200 and "items" in (gz_known or {}), str(status))
    known_items = (gz_known or {}).get("items") or []
    check("效能筛选结果 power_known", all(item.get("power_known") for item in known_items),
          str([item.get("power") for item in known_items[:3]]))

    # 物种详情 + 筛选
    status, species = get(base, "/api/species?limit=200")
    items = (species or {}).get("items") or []
    check("species 264 全量", (species or {}).get("total") == 264, str((species or {}).get("total")))
    codex = (judge[0]["codex_no"] if judge else (items[0]["codex_no"] if items else 5))
    status, sp = get(base, f"/api/species/{codex}?limit=10&power_known=1&sort=power_desc")
    check(f"species {codex} 详情/筛选", status == 200 and "teams" in (sp or {}), str(status))

    # 序列/执行 dry-run
    status, seq = post(base, "/api/sequence", {"action": "set", "team_ids": [team_id, team_id2]})
    check("sequence set 2", status == 200 and seq.get("count") == 2, str(status))
    status, preview = post(base, "/api/execute/preview", {"mode": "rebuild", "source": "state"})
    check("preview rebuild", status == 200 and "adds" in preview, str(status))
    status, started = post(base, "/api/execute", {"mode": "rebuild", "source": "state", "dry_run": True})
    job_id = (started or {}).get("job_id")
    check("execute 启动 job", status == 200 and bool(job_id), str(status))
    job = {}
    for _ in range(200):
        status, job = get(base, f"/api/jobs/{job_id}")
        if job.get("state") in ("done", "error"):
            break
        time.sleep(0.2)
    check("dry-run job done", job.get("state") == "done", job.get("error") or "")
    post(base, "/api/sequence", {"action": "clear"})


def start_embedded() -> tuple[object, str]:
    from http.server import ThreadingHTTPServer
    from targetforge import app

    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.warm_catalog()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=None)
    args = parser.parse_args()
    server = None
    if args.url:
        base = args.url.rstrip("/")
    else:
        if not (ROOT / "dataMiner/derived/targetforge/catalog.json").is_file():
            print("缺 catalog.json：先跑 python -c \"from targetforge import catalog; catalog.build()\"")
            return 2
        server, base = start_embedded()
        print(f"内嵌服务 {base}")
    health = wait_ready(base)
    if not health or (health.get("catalog") or {}).get("state") != "ready":
        print("catalog 未就绪，终止")
        return 2
    run_checks(base, health)
    if server:
        server.shutdown()
    print(f"\n== 结果：{len(CHECKS)} 项通过，{len(FAILS)} 项失败 ==")
    for fail in FAILS:
        print("  FAIL:", fail)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
