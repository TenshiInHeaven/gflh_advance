"""分析「积分关卡」的结算形式：event_score / score_prize / rank 积分榜。

背景：以前判断积分关卡靠活动名里有没有「+」，不靠谱。权威字段是
``mission.event_score``（积分结算配置）。本工具把整条**结算链**结构化输出，
方便复查分类、给前端/文档提供依据，也用于回归（关键数字：53 个有队伍积分关卡 /
25 个 campaign / 76 条 score_prize / rank 命中 25 个 mission）。

数据源（只读本机 STC，不联网）：

* ``mission``：event_score / score_prize / campaign / name
* ``rank``：``type=10`` 常驻积分榜、``type=6`` 活动积分榜；``sub_type`` 逗号列表 = mission id
* ``event_rank``：秃洞/静默沙盘等总榜（辅助信息）
* ``enemy_team`` / ``enemy_in_team`` / ``spot`` + ``mission.boss_team_id``：判断 mission 有没有可收藏队伍
* ``dataMiner/derived/client_text.json``：活动名/关卡名/rank 名文本解析

用法（系统 python 或 .sim python 均可）::

    python targetforge\\tools\\analyze_score_stages.py
    python targetforge\\tools\\analyze_score_stages.py --json
    .\\.sim\\Scripts\\python.exe targetforge\\tools\\analyze_score_stages.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEXT_FILE = ROOT / "dataMiner" / "derived" / "client_text.json"

#: 总榜/常驻榜优先级（同 mission 多行时 type=10 优先，其次 type=6）
RANK_PRIORITY = {10: 0, 6: 1}


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------
def _int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _plain_text(text: dict, key) -> str:
    raw = str((text or {}).get(str(key or ""), ""))
    return " ".join(raw.replace("\u00a0", " ").split()).strip()


def _mission_title(mid: int, mission: dict, text: dict) -> str:
    raw = str(text.get(str((mission or {}).get("name") or ""), ""))
    clean = " ".join(raw.replace("//n", " ").split())
    clean = clean.split("|")[0].strip()
    return clean or f"关卡 {mid}"


def _parse_event_score(raw) -> dict | None:
    raw = str(raw or "").strip()
    if not raw:
        return None
    head, sep, tail = raw.partition("|")
    params = len([part for part in tail.split(",") if part.strip()]) if sep else 0
    return {"mode": head.strip(), "params": params}


def _parse_score_prize(raw) -> dict | None:
    raw = str(raw or "").strip()
    if not raw:
        return None
    _, sep, tail = raw.partition("|")
    tiers = len([part for part in tail.split(",") if part.strip()]) if sep else 0
    return {"raw": raw, "tiers": tiers}


def _load_client_text() -> dict:
    if not TEXT_FILE.is_file():
        return {}
    try:
        payload = json.loads(TEXT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_tables() -> dict:
    try:
        from unit_model.core import stc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"[error] 无法导入 unit_model.core.stc：{exc}\n"
            "        请在仓库根目录运行，并确认 local_paths.json 指向本机游戏目录。") from exc

    def table(name: str) -> list[dict]:
        try:
            return stc.table(name)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"[error] 解析 STC 表 {name} 失败：{exc}") from exc

    return {
        "mission": table("mission"),
        "rank": table("rank"),
        "event_rank": table("event_rank"),
        "spot": table("spot"),
        "enemy_team": table("enemy_team"),
        "enemy_in_team": table("enemy_in_team"),
    }


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------
def build_report() -> dict:
    """返回完整分析数据（人读报告和 --json 共用）。"""
    tables = _load_tables()
    text = _load_client_text()

    missions: dict[int, dict] = {}
    for row in tables["mission"]:
        missions[_int(row.get("id"))] = row

    # 可收藏且有编制的队伍（与 catalog 同口径）
    slots = defaultdict(int)
    for row in tables["enemy_in_team"]:
        team_id = _int(row.get("enemy_team_id"))
        if team_id:
            slots[team_id] += 1
    teams = {_int(row.get("id")): row for row in tables["enemy_team"]}
    collectable = {
        team_id for team_id, row in teams.items()
        if str(row.get("targettrain_cancollect")).strip() == "1" and slots.get(team_id)
    }
    mission_teams: dict[int, set[int]] = defaultdict(set)
    for row in tables["spot"]:
        team_id = _int(row.get("enemy_team_id"))
        mission_id = _int(row.get("mission_id"))
        if team_id > 0 and mission_id > 0 and team_id in collectable:
            mission_teams[mission_id].add(team_id)
    for mission_id, mission in missions.items():
        for token in str(mission.get("boss_team_id") or "").replace(";", ",").split(","):
            token = token.strip()
            if token.lstrip("-").isdigit() and _int(token) in collectable:
                mission_teams[mission_id].add(_int(token))

    # rank 映射：sub_type 逗号列表里的 mission id；type=10 优先，其次 type=6
    mission_rank: dict[int, dict] = {}
    rank_rows = tables["rank"]
    rank_type_counts = Counter(_int(row.get("type")) for row in rank_rows)
    for row in rank_rows:
        rank_type = _int(row.get("type"))
        priority = RANK_PRIORITY.get(rank_type)
        if priority is None:
            continue
        payload = {
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
            if current is None or priority < RANK_PRIORITY.get(current["type"], 99):
                mission_rank[mission_id] = dict(payload)

    # event_score / score_prize 全量统计（含灰域）
    event_score_rows: list[tuple[int, dict, dict]] = []
    for mission_id, mission in missions.items():
        parsed = _parse_event_score(mission.get("event_score"))
        if parsed:
            event_score_rows.append((mission_id, mission, parsed))
    gray_event = [(mid, m) for mid, m, _ in event_score_rows
                  if _int(m.get("campaign")) == -404]
    non_gray_event = [(mid, m) for mid, m, _ in event_score_rows
                      if _int(m.get("campaign")) != -404]

    mode_counts = Counter(parsed["mode"] for _, _, parsed in event_score_rows)
    params_counts = Counter(parsed["params"] for _, _, parsed in event_score_rows)

    score_prize_rows = []
    for mission_id, mission in missions.items():
        parsed = _parse_score_prize(mission.get("score_prize"))
        if parsed:
            score_prize_rows.append((mission_id, mission, parsed))
    prize_tiers = Counter(parsed["tiers"] for _, _, parsed in score_prize_rows)
    prize_without_event = [mid for mid, m, _ in score_prize_rows
                           if not _parse_event_score(m.get("event_score"))]

    # 积分关卡（有可收藏队伍、非灰域）= score 章的实际来源
    score_missions = [(mid, mission) for mid, mission in non_gray_event
                      if mid in mission_teams]
    campaigns: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for mid, mission in score_missions:
        campaigns[_int(mission.get("campaign"))].append((mid, mission))

    rank_matched = [(mid, mission, mission_rank[mid]) for mid, mission in score_missions
                    if mid in mission_rank]
    rank_examples = []
    for mid, mission, rank in rank_matched[:12]:
        rank_examples.append({
            "mission_id": mid,
            "mission_title": _mission_title(mid, mission, text),
            "rank_id": rank["id"],
            "rank_name": rank["name"],
            "rank_title": rank["title"],
            "rank_type": rank["type"],
        })

    campaign_rows = []
    for campaign in sorted(campaigns, key=lambda value: (value >= 0, abs(value))):
        mission_list = sorted(campaigns[campaign])
        campaign_rows.append({
            "campaign": campaign,
            "count": len(mission_list),
            "missions": [{
                "id": mid,
                "title": _mission_title(mid, mission, text),
                "event_score": _parse_event_score(mission.get("event_score")),
                "score_prize": _parse_score_prize(mission.get("score_prize")),
                "rank_id": mission_rank.get(mid, {}).get("id"),
            } for mid, mission in mission_list],
        })

    # 普通 EX 反例：标题带 EX 但没有 event_score（有可收藏队伍）
    normal_ex = []
    for mission_id, mission in missions.items():
        if _int(mission.get("campaign")) == -404:
            continue
        title = _mission_title(mission_id, mission, text)
        if "EX" not in title.upper():
            continue
        if _parse_event_score(mission.get("event_score")):
            continue
        if mission_id not in mission_teams:
            continue
        normal_ex.append({"id": mission_id, "title": title,
                          "campaign": _int(mission.get("campaign"))})
    normal_ex.sort(key=lambda item: item["id"])

    # event_rank（秃洞/静默沙盘等总榜，辅助信息）
    event_rank_rows = [{
        "id": _int(row.get("id")),
        "title": _plain_text(text, row.get("title")) or str(row.get("title") or ""),
        "remake_id": _int(row.get("remake_id")),
    } for row in tables["event_rank"]]

    checks = {
        "event_score_total": len(event_score_rows),
        "event_score_non_gray": len(non_gray_event),
        "event_score_gray": len(gray_event),
        "score_missions_with_teams": len(score_missions),
        "score_campaigns": len(campaigns),
        "score_prize_total": len(score_prize_rows),
        "score_prize_without_event_score": len(prize_without_event),
        "rank_matched_score_missions": len(rank_matched),
        "rank_type10_rows": rank_type_counts.get(10, 0),
        "rank_type6_rows": rank_type_counts.get(6, 0),
        "normal_ex_without_event_score": len(normal_ex),
    }
    expected = {
        "event_score_total": 102,
        "event_score_non_gray": 58,
        "event_score_gray": 44,
        "score_missions_with_teams": 53,
        "score_campaigns": 25,
        "score_prize_total": 76,
        "score_prize_without_event_score": 0,
        "rank_matched_score_missions": 25,
        "rank_type10_rows": 16,
        "rank_type6_rows": 2,
    }
    mismatches = {key: (checks[key], want) for key, want in expected.items()
                  if checks[key] != want}

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checks": checks,
        "expected": expected,
        "ok": not mismatches,
        "mismatches": mismatches,
        "event_score": {
            "total": len(event_score_rows),
            "non_gray": len(non_gray_event),
            "gray": len(gray_event),
            "mode_counts": dict(sorted(mode_counts.items())),
            "params_counts": {str(key): value
                              for key, value in sorted(params_counts.items())},
            "gray_sample": [{"id": mid, "title": _mission_title(mid, m, text)}
                            for mid, m in sorted(gray_event)[:10]],
        },
        "score_prize": {
            "total": len(score_prize_rows),
            "tiers_counts": {str(key): value
                             for key, value in sorted(prize_tiers.items())},
            "examples": [{"id": mid,
                          "raw": parsed["raw"],
                          "tiers": parsed["tiers"]}
                         for mid, _, parsed in score_prize_rows[:8]],
        },
        "rank": {
            "type10_rows": rank_type_counts.get(10, 0),
            "type6_rows": rank_type_counts.get(6, 0),
            "matched_score_missions": len(rank_matched),
            "examples": rank_examples,
            "event_rank_rows": len(event_rank_rows),
            "event_rank_sample": [row["title"] for row in event_rank_rows[:10]],
        },
        "campaigns": campaign_rows,
        "normal_ex": {
            "count": len(normal_ex),
            "examples": normal_ex[:12],
        },
    }


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def print_report(report: dict) -> None:
    checks = report["checks"]
    print("==" * 32)
    print("TargetForge 积分关卡结算分析（mission.event_score / score_prize / rank）")
    print("==" * 32)

    event_score = report["event_score"]
    print("\n[1] event_score 分布")
    print(f"    总计 {event_score['total']} 条 = 非灰域 {event_score['non_gray']} + "
          f"灰域 {event_score['gray']}")
    print(f"    mode: {event_score['mode_counts']}")
    print(f"    params 个数分布: {event_score['params_counts']}")
    print(f"    灰域样例: {[item['title'] for item in event_score['gray_sample'][:5]]}")

    prize = report["score_prize"]
    print("\n[2] score_prize 覆盖")
    print(f"    总计 {prize['total']} 条；tiers 分布: {prize['tiers_counts']}")
    for item in prize["examples"][:5]:
        print(f"    {item['id']}: {item['raw']} (tiers={item['tiers']})")

    rank = report["rank"]
    print("\n[3] rank 积分榜映射")
    print(f"    rank 行: type=10 常驻 {rank['type10_rows']} / type=6 活动 {rank['type6_rows']}")
    print(f"    命中积分关卡 mission: {rank['matched_score_missions']} 个")
    for item in rank["examples"][:8]:
        print(f"    mission {item['mission_id']} {item['mission_title']!r} → "
              f"rank {item['rank_id']} {item['rank_name']!r} ({item['rank_title']!r})")
    print(f"    event_rank 行: {rank['event_rank_rows']}，样例: "
          f"{rank['event_rank_sample'][:5]}")

    print("\n[4] 按 campaign 的积分关卡（有可收藏队伍，共 "
          f"{checks['score_missions_with_teams']} 关 / {checks['score_campaigns']} 个 campaign）")
    for row in report["campaigns"]:
        titles = "、".join(mission["title"] for mission in row["missions"][:6])
        suffix = "…" if row["count"] > 6 else ""
        print(f"    campaign {row['campaign']:>8}  n={row['count']:<2} {titles}{suffix}")

    print("\n[5] 普通 EX 反例（标题含 EX 但无 event_score，不算积分关卡）")
    normal_ex = report["normal_ex"]
    print(f"    共 {normal_ex['count']} 个；样例: "
          f"{[(item['id'], item['title']) for item in normal_ex['examples'][:6]]}")

    print("\n[6] 校验结论")
    for key, value in checks.items():
        print(f"    {key} = {value}")
    if report["ok"]:
        print("    [OK] 与侦查基线完全一致"
              "（102/58/44、53、25、76、rank 25、type10 16、type6 2）")
    else:
        print(f"    [WARN] 与基线不一致: {report['mismatches']}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="分析少前1积分关卡的结算形式（event_score/score_prize/rank）")
    parser.add_argument("--json", action="store_true",
                        help="输出机器可读 JSON（不打印人读报告）")
    args = parser.parse_args(argv)

    try:
        report = build_report()
    except SystemExit as exc:  # 表/data 缺失时保留可读提示
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
