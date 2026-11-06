"""真实 catalog 的 API 冒烟（Lead 验收用，不碰游戏/网络注入）。

跑法（仓库根目录，catalog.json 已生成）：
    python targetforge/tools/api_smoke.py
    python targetforge/tools/api_smoke.py --url http://127.0.0.1:8765
不带 --url 时自己起一个临时端口的内嵌服务（真实 catalog/gflh 模块）。
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS: list[str] = []
FAILS: list[str] = []


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
        body = exc.read().decode(errors="replace")
        return exc.code, {"_raw": body[:500]}


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return exc.code, {"_raw": body[:500]}


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


def run_checks(base: str) -> None:
    status, health = get(base, "/api/health")
    check("health 200", status == 200 and health.get("ok"), str(status))
    status, meta = get(base, "/api/meta")
    counts = (meta or {}).get("counts") or {}
    print("  counts:", counts)
    check("teams=13700", counts.get("teams") == 13700, str(counts.get("teams")))
    check("species=264", counts.get("species") == 264, str(counts.get("species")))
    check("stages=2345", counts.get("stages") == 2345, str(counts.get("stages")))

    status, chapters = get(base, "/api/chapters")
    groups = (chapters or {}).get("groups") or []
    check("chapters 8 组", len(groups) == 8, str([g.get("id") for g in groups]))
    check("章节数 ~107", 95 <= sum(len(g.get("chapters") or []) for g in groups) <= 120,
          str(sum(len(g.get("chapters") or []) for g in groups)))
    chapter_ids = [c["id"] for g in groups for c in (g.get("chapters") or [])]
    main1 = next((cid for cid in chapter_ids if cid == "main-1"), None)
    check("有 main-1", main1 is not None, str(chapter_ids[:6]))

    status, chapter = get(base, "/api/chapters/main-1")
    stages = (chapter or {}).get("stages") or []
    check("main-1 有 10 关", len(stages) == 10, str(len(stages)))
    stage_id = stages[0]["id"] if stages else 5

    status, stage = get(base, f"/api/stages/{stage_id}")
    teams = (stage or {}).get("teams") or []
    check(f"stage {stage_id} 有队伍", len(teams) > 0, str(len(teams)))
    team_id = teams[0]["id"] if teams else 6549244
    team_id2 = teams[1]["id"] if len(teams) > 1 else 6549244

    status, team = get(base, f"/api/teams/{team_id}")
    check(f"team {team_id} 详情字段", status == 200 and team.get("members") and team.get("species"),
          str(status))
    check("队伍详情无技能字段", not any(k in json.dumps(team, ensure_ascii=False)[:200000]
                                       for k in ("battle_skill", "skill_group", "\"skill\"")),
          "found skill field")

    status, species = get(base, "/api/species?limit=100")
    items = (species or {}).get("items") or []
    total = (species or {}).get("total")
    check("species 264", total == 264, str(total))
    check("species 分页 100", len(items) == 100, str(len(items)))
    codex = items[0]["codex_no"] if items else 5
    status, sp = get(base, f"/api/species/{codex}")
    check(f"species {codex} 有队伍", status == 200 and len((sp or {}).get("teams") or []) > 0, str(status))

    status, areas = get(base, "/api/grayzone/areas")
    area_list = (areas or {}).get("areas") or []
    check("灰域 12 区域", len(area_list) == 12, str(len(area_list)))
    if area_list:
        area = area_list[0]["id"]
        status, gz = get(base, "/api/grayzone/teams?area=" + urllib.parse.quote(area) + "&limit=30")
        check("灰域队伍分页", status == 200 and (gz or {}).get("total", 0) > 0, str(status))

    status, search = get(base, "/api/search?q=" + urllib.parse.quote("稻草人"))
    check("搜索有结果", status == 200 and (len(search.get("teams") or []) + len(search.get("species") or [])) > 0,
          str(status))

    status, creds = get(base, "/api/creds")
    check("creds 列表", status == 200, str(status))
    status, current = get(base, "/api/current?source=auto")
    check("current 当前靶机", status == 200 and "targets" in current, str(status))

    status, seq = get(base, "/api/sequence")
    check("sequence 初始", status == 200 and "draft" in seq, str(status))
    status, seq = post(base, "/api/sequence", {"action": "set", "team_ids": [team_id, team_id2]})
    check("sequence set 2（预览前）", status == 200 and seq.get("count") == 2, str(seq.get("count")))
    status, preview = post(base, "/api/execute/preview", {"mode": "append", "source": "state"})
    check("preview append", status == 200 and "adds" in preview and "final" in preview, str(status))
    status, preview = post(base, "/api/execute/preview", {"mode": "replace", "source": "state"})
    check("preview replace", status == 200 and "deletes" in preview, str(status))
    status, preview = post(base, "/api/execute/preview", {"mode": "rebuild", "source": "state"})
    check("preview rebuild", status == 200 and "adds" in preview, str(status))

    # 加两个队、预览、dry-run 执行（绝不联网）
    status, seq = post(base, "/api/sequence", {"action": "set", "team_ids": [team_id, team_id2]})
    check("sequence set 2", status == 200 and seq.get("count") == 2, str(seq.get("count")))
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
    logs = (job or {}).get("logs") or []
    check("dry-run 有日志", len(logs) > 0, str(len(logs)))
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
    run_checks(base)
    if server:
        server.shutdown()
    print(f"\n== 结果：{len(CHECKS)} 项通过，{len(FAILS)} 项失败 ==")
    for fail in FAILS:
        print("  FAIL:", fail)
    return 1 if FAILS else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: F401 - 延迟导入避免子进程启动慢
    sys.exit(main())
