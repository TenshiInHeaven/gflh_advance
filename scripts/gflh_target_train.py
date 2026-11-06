"""GFLH 靶机的命令行版：抓 sign_key / 规划编号 / 增删靶机（支持任意服务器 URL）。

对应 GUI 工具 GFLH-TargetTrain（https://github.com/MaaGF1/GFLH）：
  - 代理监听 18080，游戏登录时从流量里拿 uid + sign
  - **不要用 8080**：8080 是另一个 bot（uvicorn）的端口，抓包和它抢端口会把
    系统代理流量全打进 bot，产生 404 / Invalid HTTP 日志
  - 再用 uid/sign 调 Targettrain/addCollect / delCollect 增删靶机

## 编号（order_id）为什么必须管

收藏标靶界面按 ``order_id`` 显示「收藏標靶1、收藏標靶2…」。曾经的坑：

* ``add`` 每次调用都从 1 开始编号 → 分两段注入后列表里出现**多个「收藏標靶1」**；
* 删掉中间几个再补，服务器不会帮你重排 → 编号出现空洞，界面顺序和预期不一致。

现在的做法：

1. **先 plan 再 add**。``plan`` 离线算出"每条要用的 order_id"，不联网；
2. 默认**接着已有的最大编号往后排**（不会撞号），并跳过已经在列表里的队伍；
3. ``--renumber`` 一次性清空再按 CSV 的 1..N 重排（推荐：拿到的就是干净连续的 35 个）；
4. 本地状态文件 ``dataMiner/derived/target_injection_state.json`` 记录"哪个号给了哪支队伍"，
   下次运行可以续号；``--creds`` 里的 ``enemies/orders``（capture --mode full 抓到的）优先。

## 用法

```powershell
# 0) 只看计划，不联网（先跑这个确认编号）
python scripts\\gflh_target_train.py plan --csv dataMiner\\derived\\target35_selection.csv

# 1) 抓 sign（把系统/模拟器代理指向本机 18080，然后重启游戏登录）
python scripts\\gflh_target_train.py capture --port 18080 --seconds 180 --mode full --out dataMiner\\derived\\creds.json

# 2) 按 CSV 的 order 1..35 重排（先清空再按顺序加；最稳，不会出现重复编号）
python scripts\\gflh_target_train.py add --creds dataMiner\\derived\\creds.json ^
    --csv dataMiner\\derived\\target35_selection.csv --renumber

# 3) 追加（不清空，接着现有最大编号往后排；已在列表里的会跳过）
python scripts\\gflh_target_train.py add --creds dataMiner\\derived\\creds.json --teams 444705,444805

# 4) 删除 / 清空
python scripts\\gflh_target_train.py del --creds dataMiner\\derived\\creds.json --teams 444705
python scripts\\gflh_target_train.py clear --creds dataMiner\\derived\\creds.json
```

改完靶机要重登游戏同步；清空靶机后要强退，否则进靶机界面卡死。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STATIC_KEY = "yundoudou"
API_ADD = "Targettrain/addCollect"
API_DEL = "Targettrain/delCollect"
MAX_TARGETS = 35
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / "dataMiner" / "derived" / "target_injection_state.json"


# ---------------------------------------------------------------------------
# 纯逻辑（不联网，可单测）
# ---------------------------------------------------------------------------
def read_target_csv(path: str | Path) -> list[dict]:
    """读靶机清单：``order`` 必须 1..N 连续唯一，``team`` 必须唯一且 > 0。"""
    rows = []
    with Path(path).open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append({"order": int(row["order"]), "team": int(row["team"]),
                         "members": row.get("members", "")})
    problems = validate_order_rows(rows)
    if problems:
        raise SystemExit("靶机清单编号有问题：\n  " + "\n  ".join(problems))
    return rows


def validate_order_rows(rows: list[dict]) -> list[str]:
    """编号连续唯一 + 队伍不重复 + 不超上限。"""
    problems: list[str] = []
    orders = [int(row["order"]) for row in rows]
    teams = [int(row["team"]) for row in rows]
    if len(orders) != len(set(orders)):
        dup = sorted({o for o in orders if orders.count(o) > 1})
        problems.append(f"order 重复：{dup}")
    if len(teams) != len(set(teams)):
        dup = sorted({t for t in teams if teams.count(t) > 1})
        problems.append(f"team 重复：{dup}")
    if orders and sorted(orders) != list(range(1, len(orders) + 1)):
        problems.append(f"order 不是 1..{len(orders)} 连续：{sorted(orders)}")
    if len(rows) > MAX_TARGETS:
        problems.append(f"共 {len(rows)} 个，超过上限 {MAX_TARGETS}")
    if any(t <= 0 for t in teams):
        problems.append(f"team 必须为正：{sorted({t for t in teams if t <= 0})}")
    return problems


def existing_targets(creds: dict | None = None, state_path: str | Path | None = None) -> list[dict]:
    """已有靶机（order, team）。``creds`` 优先于本地状态文件。"""
    if creds:
        enemies = [int(t) for t in creds.get("enemies") or []]
        orders = [int(o) for o in creds.get("orders") or []]
        if enemies:
            return [{"order": orders[i] if i < len(orders) else 0, "team": team}
                    for i, team in enumerate(enemies)]
    path = Path(state_path) if state_path else DEFAULT_STATE
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        return [{"order": int(item.get("order") or 0), "team": int(item.get("team") or 0)}
                for item in payload.get("targets") or []]
    return []


def duplicate_orders(existing: list[dict]) -> dict[int, list[int]]:
    """已撞号的 order → 占用了它的队伍列表（``len > 1`` 就是重复编号）。"""
    out: dict[int, list[int]] = {}
    for item in existing:
        out.setdefault(int(item.get("order") or 0), []).append(int(item.get("team") or 0))
    return {order: teams for order, teams in out.items() if order > 0 and len(teams) > 1}


def plan_add(existing: list[dict], wanted: list[dict], *,
             start_order: int | None = None, renumber: bool = False) -> dict:
    """算出一批 addCollect 的 order_id 分配（不联网）。

    * ``renumber``：先把已有全部删掉，再按 ``wanted`` 顺序从 1 开始编号；
    * 默认：跳过已有队伍，接着 ``max(已有编号)+1``（或 ``start_order``）往后排。

    返回 ``{"delete": [team...], "add": [{"order","team"}...], "skipped": [...],
    "duplicates": {...}, "renumber": bool}``。
    """
    existing_teams = {int(item["team"]) for item in existing if item.get("team")}
    dup = duplicate_orders(existing)
    delete: list[int] = []
    add: list[dict] = []
    skipped: list[dict] = []

    if renumber:
        delete = [int(item["team"]) for item in existing if item.get("team")]
        delete_map = {int(item["team"]): int(item.get("order") or 0)
                      for item in existing if item.get("team")}
        for index, row in enumerate(wanted, 1):
            add.append({"order": index, "team": int(row["team"])})
        return {"delete": delete, "delete_map": delete_map, "add": add, "skipped": skipped,
                "duplicates": dup, "renumber": True}

    occupy = {int(item["order"]) for item in existing if int(item.get("order") or 0) > 0}
    next_order = max([start_order or 1, (max(occupy) + 1) if occupy else 1])
    for row in wanted:
        team = int(row["team"])
        if team in existing_teams:
            skipped.append({"team": team, "reason": "已在收藏列表里"})
            continue
        while next_order in occupy:
            next_order += 1
        if next_order > MAX_TARGETS:
            skipped.append({"team": team, "reason": f"编号超过上限 {MAX_TARGETS}"})
            continue
        add.append({"order": next_order, "team": team})
        occupy.add(next_order)
        next_order += 1
    delete_teams = [int(item["team"]) for item in existing if item.get("team")]
    delete_map = {int(item["team"]): int(item.get("order") or 0)
                  for item in existing if item.get("team")}
    return {"delete": delete_teams, "delete_map": delete_map, "add": add, "skipped": skipped,
            "duplicates": dup, "renumber": False}


def add_payload(order: int, team: int) -> dict:
    return {
        "enemy_team_id": int(team),
        "fight_type": 0,
        "fight_coef": "",
        "fight_environment_group": "",
        "order_id": int(order),
    }


def del_payload(team: int, order: int | None = None) -> dict:
    payload = {"enemy_team_id": int(team), "fight_type": 0,
               "fight_coef": "", "fight_environment_group": ""}
    # 国服 delCollect 需要 order_id：不带会返回 error:300（实测）
    if order:
        payload["order_id"] = int(order)
    return payload


def load_state(path: str | Path = DEFAULT_STATE) -> dict:
    path = Path(path)
    if not path.is_file():
        return {"targets": []}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"targets": []}


def save_state(payload: dict, path: str | Path = DEFAULT_STATE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def update_state(payload: dict, *, add: list[dict] | None = None,
                 delete: list[int] | None = None,
                 uid: str | None = None, base_url: str | None = None) -> dict:
    """在内存状态上做增删（``targets`` 永远保持 order 升序、team 唯一）。"""
    targets = {int(item["team"]): {"order": int(item["order"]), "team": int(item["team"])}
               for item in payload.get("targets") or []}
    for team in delete or ():
        targets.pop(int(team), None)
    for item in add or ():
        targets[int(item["team"])] = {"order": int(item["order"]), "team": int(item["team"])}
    payload["targets"] = sorted(targets.values(), key=lambda item: item["order"])
    if uid:
        payload["uid"] = str(uid)
    if base_url:
        payload["base_url"] = str(base_url)
    return payload


# ---------------------------------------------------------------------------
# 联网部分（需要 gflzirc）
# ---------------------------------------------------------------------------
def _require_gflzirc():
    try:
        from gflzirc import GFLClient, GFLProxy
    except ModuleNotFoundError:
        raise SystemExit(
            "需要先安装 gflzirc：\n"
            "  .\\.sim\\Scripts\\python.exe -m pip install gflzirc==0.4.4\n"
            "（plan / 校验编号不需要联网，也不装 gflzirc）")
    return GFLClient, GFLProxy


def capture(args) -> int:
    GFLClient, GFLProxy = _require_gflzirc()
    captured = {"uid": None, "sign": None, "base_url": None, "enemies": [], "orders": [], "urls": []}
    done = threading.Event()

    def on_traffic(event_type, url, payload):
        if url:
            if url not in captured["urls"]:
                captured["urls"].append(url)
                print(f"[URL] {url}", flush=True)
            if captured["base_url"] is None and "index.php/" in url:
                head = url.split("index.php/")[0] + "index.php/"
                tail = url.split("index.php/")[1].split("/")[0]
                if tail.isdigit():
                    captured["base_url"] = head + tail + "/"
                    print(f"[BASE] {captured['base_url']}", flush=True)
        if event_type == "SYS_KEY_UPGRADE":
            captured["uid"] = payload.get("uid")
            captured["sign"] = payload.get("sign")
            print(f"[KEY] uid={captured['uid']} sign={captured['sign']}", flush=True)
            if args.mode == "auth":
                done.set()
        if args.mode == "full" and event_type == "S2C" and "Index/index" in str(url):
            info = (payload or {}).get("targettrain_collect_user_info") if isinstance(payload, dict) else None
            if isinstance(info, list):
                captured["enemies"] = [str(item.get("enemy_team_id")) for item in info
                                       if item.get("enemy_team_id") is not None]
                captured["orders"] = [str(item.get("order_id")) for item in info
                                      if item.get("order_id") is not None]
                print(f"[TARGETS] {len(captured['enemies'])} 个：{captured['enemies'][:10]}", flush=True)
                if captured["uid"] and captured["sign"]:
                    done.set()

    proxy = GFLProxy(args.port, STATIC_KEY, on_traffic)
    proxy.start()
    print(f"[PROXY] 监听 0.0.0.0:{args.port}（把游戏/模拟器的 HTTP 代理指到本机这个端口）", flush=True)
    deadline = time.time() + args.seconds
    while time.time() < deadline and not done.is_set():
        time.sleep(0.5)
    proxy.stop()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[DONE] 写入 {out}", flush=True)
    return 0 if captured["uid"] and captured["sign"] else 1


def _client(creds, base_url: str | None):
    GFLClient, _ = _require_gflzirc()
    base = base_url or creds.get("base_url")
    if not base:
        raise SystemExit("没有服务器地址：请用 --base 指定，或先用 capture 抓到 base_url")
    client = GFLClient(str(creds["uid"]), str(creds["sign"]), base)
    client.session.trust_env = False
    client.session.proxies.clear()
    return client


def _load_creds(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _existing_from_args(args, creds: dict | None) -> list[dict]:
    state = load_state(args.state)
    if creds and (creds.get("enemies") or []):
        return existing_targets(creds)
    if state.get("targets"):
        return existing_targets(None, args.state)
    return existing_targets(creds)


def plan(args) -> int:
    """离线打印编号分配（不联网）。"""
    creds = _load_creds(args.creds) if args.creds and Path(args.creds).is_file() else None
    existing = _existing_from_args(args, creds)
    wanted = read_target_csv(args.csv) if args.csv else [
        {"order": i + 1, "team": int(t)} for i, t in enumerate(
            [x for x in str(args.teams or "").split(",") if x.strip()])]
    result = plan_add(existing, wanted, start_order=args.start_order,
                      renumber=args.renumber)
    print(f"已有靶机：{len(existing)} 个")
    for item in existing:
        print(f"  收藏標靶{item['order']}: {item['team']}")
    if result["duplicates"]:
        print(f"[WARN] 已有列表里编号重复：{result['duplicates']}（建议 --renumber）")
    if result["renumber"]:
        print(f"\n--renumber：先删 {len(result['delete'])} 个，再加 {len(result['add'])} 个")
    print(f"\n计划 add {len(result['add'])} 个（order_id 唯一）：")
    for item in result["add"]:
        print(f"  收藏標靶{item['order']:>2}  team={item['team']}  "
              f"payload={json.dumps(add_payload(item['order'], item['team']), ensure_ascii=False)}")
    for item in result["skipped"]:
        print(f"  [SKIP] team={item['team']}：{item['reason']}")
    print(f"\n结果：编号 {[i['order'] for i in result['add']]}")
    if args.json:
        Path(args.json).write_text(json.dumps({"existing": existing, **result},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"写入 {args.json}")
    return 0


def add(args) -> int:
    creds = _load_creds(args.creds)
    existing = _existing_from_args(args, creds)
    wanted = read_target_csv(args.csv) if args.csv else [
        {"order": i + 1, "team": int(t)} for i, t in enumerate(
            [x for x in str(args.teams or "").split(",") if x.strip()])]
    if not wanted:
        raise SystemExit("没有要加的队伍：给 --csv 或 --teams")
    result = plan_add(existing, wanted, start_order=args.start_order,
                      renumber=args.renumber)
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    client = _client(creds, args.base)
    state = load_state(args.state)
    if result["duplicates"] and not args.renumber:
        print(f"[WARN] 已有编号重复 {result['duplicates']}；继续追加会保留这些重复项，"
              f"建议用 --renumber 重排")
    if result["renumber"]:
        delete_map = result.get("delete_map") or {}
        for team in result["delete"]:
            try:
                res = client.send_request(API_DEL, del_payload(team, delete_map.get(team)))
                print(f"[DEL] {team} order={delete_map.get(team)} -> {res}")
            except Exception as exc:  # noqa: BLE001 - 网络错误要继续删下一个
                print(f"[DEL] {team} 失败：{exc}")
            time.sleep(0.5)
        update_state(state, delete=result["delete"])
    for item in result["add"]:
        try:
            res = client.send_request(API_ADD, add_payload(item["order"], item["team"]))
            print(f"[ADD] 收藏標靶{item['order']} {item['team']} -> {res}")
            update_state(state, add=[item])
            save_state(state, args.state)
        except Exception as exc:  # noqa: BLE001
            print(f"[ADD] {item['team']} 失败：{exc}")
        time.sleep(0.6)
    for item in result["skipped"]:
        print(f"[SKIP] {item['team']}：{item['reason']}")
    update_state(state, uid=creds.get("uid"), base_url=creds.get("base_url"))
    save_state(state, args.state)
    print(f"\n本地状态：{Path(args.state)}（{len(state.get('targets') or [])} 个靶机）")
    return 0


def delete(args) -> int:
    creds = _load_creds(args.creds)
    client = _client(creds, args.base)
    items = _existing_from_args(args, creds) or []
    order_map = {int(item["team"]): int(item.get("order") or 0)
                 for item in items if item.get("team")}
    teams = [int(t) for t in args.teams.split(",") if t.strip()] if args.teams else []
    if not teams:
        teams = [int(item["team"]) for item in items if item.get("team")]
    for team in teams:
        try:
            res = client.send_request(API_DEL, del_payload(team, order_map.get(team)))
            print(f"[DEL] {team} order={order_map.get(team)} -> {res}")
        except Exception as exc:  # noqa: BLE001
            print(f"[DEL] {team} 失败：{exc}")
        time.sleep(0.6)
    state = load_state(args.state)
    update_state(state, delete=teams)
    save_state(state, args.state)
    return 0


def clear(args) -> int:
    args.teams = ""
    return delete(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(node):
        node.add_argument("--creds", default="dataMiner/derived/creds.json")
        node.add_argument("--base", default=None, help="服务器根地址，如 http://host/index.php/1000/")
        node.add_argument("--csv", default=None,
                          help="靶机清单（order/team 列，order 必须 1..N 连续唯一）")
        node.add_argument("--teams", default="", help="enemy_team_id，逗号分隔")
        node.add_argument("--start-order", type=int, default=None,
                          help="起始编号（默认接着已有最大编号往后排）")
        node.add_argument("--renumber", action="store_true",
                          help="先清空已有靶机，再按 CSV 顺序从 1 编号（推荐）")
        node.add_argument("--state", default=str(DEFAULT_STATE), help="本地状态文件")

    cap = sub.add_parser("capture", help="起代理抓 uid/sign（可选抓靶机列表）")
    cap.add_argument("--port", type=int, default=18080)
    cap.add_argument("--seconds", type=int, default=120)
    cap.add_argument("--mode", choices=("auth", "full"), default="auth")
    cap.add_argument("--out", default="dataMiner/derived/creds.json")
    cap.set_defaults(func=capture)

    node = sub.add_parser("plan", help="离线打印编号分配（不联网）")
    common(node)
    node.add_argument("--json", default=None, help="把计划写成 JSON")
    node.set_defaults(func=plan)

    node = sub.add_parser("add", help="注入靶机（按 order_id 顺序编号）")
    common(node)
    node.add_argument("--dry-run", action="store_true", help="只打印不发送")
    node.set_defaults(func=add)

    node = sub.add_parser("del", help="删除靶机")
    common(node)
    node.set_defaults(func=delete)

    node = sub.add_parser("clear", help="清空靶机")
    common(node)
    node.set_defaults(func=clear)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
