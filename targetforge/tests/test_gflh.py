"""targetforge.gflh 单测。

原则：**全部 mock**，不联网 / 不启动真实代理 / 不改系统代理 / 不杀游戏进程 /
不读写真实 dataMiner（落盘路径全部指到临时目录）。

运行：``python -m unittest targetforge.tests.test_gflh -v``
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from targetforge import gflh


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
def current(*pairs) -> dict:
    """构造 current_targets() 形状的当前列表（pairs: (order, team)）。"""
    return {"targets": [{"order": order, "team": team} for order, team in pairs]}


def pairs(items) -> list[tuple[int, int]]:
    return [(item["order"], item["team"]) for item in items]


def now_iso(hours_ago: float = 0.0) -> str:
    moment = datetime.now().astimezone() - timedelta(hours=hours_ago)
    return moment.isoformat(timespec="seconds")


class TempPathsMixin:
    """把 gflh 的文件路径常量指到临时目录。"""

    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)
        self.derived = self.tmp / "derived"
        self.data_dir = self.derived / "targetforge"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.derived / "target_injection_state.json"
        self.creds_file = self.data_dir / "creds_latest.json"
        for name, value in (
            ("DERIVED", self.derived),
            ("DATA_DIR", self.data_dir),
            ("STATE_FILE", self.state_file),
            ("DEFAULT_CREDS", self.creds_file),
        ):
            patcher = mock.patch.object(gflh, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_creds(self, payload: dict, path: Path | None = None) -> Path:
        path = path or self.creds_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def write_state(self, payload: dict) -> Path:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self.state_file

    def read_state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))


class FakeGflzirc:
    """模拟 gflzirc 模块（只实现 capture 用到的 GFLProxy / set_windows_proxy）。"""

    def __init__(self, start_error: Exception | None = None):
        self.proxies: list = []
        self.set_proxy_calls: list[tuple[bool, str]] = []
        self.start_error = start_error
        outer = self

        class FakeProxy:
            def __init__(self, port, static_key, callback=None):
                self.port = port
                self.static_key = static_key
                self.callback = callback
                self.started = False
                self.stopped = False
                outer.proxies.append(self)

            def start(self):
                if outer.start_error is not None:
                    raise outer.start_error
                self.started = True

            def stop(self):
                self.stopped = True

        def set_windows_proxy(enable, proxy_addr="127.0.0.1:8080"):
            outer.set_proxy_calls.append((bool(enable), proxy_addr))
            return True

        self.GFLProxy = FakeProxy
        self.set_windows_proxy = set_windows_proxy


class FakeClient:
    """模拟 GFLClient.send_request（不联网，记录调用）。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    def send_request(self, endpoint, payload):
        self.calls.append((endpoint, dict(payload)))
        if self.responses:
            return self.responses.pop(0)
        return {"success": True}


# ---------------------------------------------------------------------------
# plan：纯函数语义
# ---------------------------------------------------------------------------
class PlanTests(unittest.TestCase):
    def test_append_appends_after_max(self):
        result = gflh.plan("append", [300, 400], current=current((1, 100), (2, 200)))
        self.assertEqual(pairs(result["adds"]), [(3, 300), (4, 400)])
        self.assertEqual(result["deletes"], [])
        self.assertEqual(pairs(result["kept"]), [(1, 100), (2, 200)])
        self.assertEqual(pairs(result["final"]), [(1, 100), (2, 200), (3, 300), (4, 400)])
        self.assertTrue(result["valid"])
        self.assertEqual([item["order_id"] for item in result["payloads"]["add"]], [3, 4])
        self.assertEqual(result["payloads"]["del"], [])

    def test_append_skips_existing_and_duplicate_draft(self):
        result = gflh.plan("append", [100, 200, 200], current=current((1, 100)))
        self.assertEqual(pairs(result["adds"]), [(2, 200)])
        skipped_teams = [item["team"] for item in result["skipped"]]
        self.assertIn(100, skipped_teams)
        self.assertIn(200, skipped_teams)
        self.assertTrue(result["valid"])
        self.assertTrue(result["warnings"])

    def test_append_stops_at_35(self):
        current_items = [(index, 1000 + index) for index in range(1, 34)]  # 1..33
        result = gflh.plan("append", [5000, 5001, 5002], current=current(*(current_items)))
        self.assertEqual(pairs(result["adds"]), [(34, 5000), (35, 5001)])
        self.assertEqual(len(result["final"]), 35)
        self.assertTrue(result["valid"])
        self.assertEqual([item["team"] for item in result["skipped"]], [5002])
        self.assertIn("超过上限", " ".join(result["warnings"]) + " ".join(
            item["reason"] for item in result["skipped"]))

    def test_append_duplicate_current_orders_only_warns(self):
        result = gflh.plan("append", [400], current=current((1, 100), (1, 200), (3, 300)))
        self.assertEqual(pairs(result["adds"]), [(4, 400)])
        self.assertTrue(result["valid"])
        self.assertTrue(any("编号重复" in warning for warning in result["warnings"]))

    def test_append_empty_draft_noop(self):
        result = gflh.plan("append", [], current=current((1, 100)))
        self.assertEqual(result["adds"], [])
        self.assertEqual(pairs(result["final"]), [(1, 100)])
        self.assertTrue(result["valid"])

    def test_rebuild_clears_and_renumbers(self):
        result = gflh.plan("rebuild", [300, 400, 500],
                           current=current((1, 100), (2, 200)))
        self.assertEqual(pairs(result["deletes"]), [(1, 100), (2, 200)])
        self.assertEqual(pairs(result["adds"]), [(1, 300), (2, 400), (3, 500)])
        self.assertEqual(result["kept"], [])
        self.assertEqual(pairs(result["final"]), [(1, 300), (2, 400), (3, 500)])
        self.assertTrue(result["valid"])
        self.assertEqual([item["order_id"] for item in result["payloads"]["del"]], [1, 2])

    def test_rebuild_empty_current(self):
        result = gflh.plan("rebuild", [300, 400], current=current())
        self.assertEqual(result["deletes"], [])
        self.assertEqual(pairs(result["adds"]), [(1, 300), (2, 400)])
        self.assertEqual(result["final"], result["adds"])
        self.assertTrue(result["valid"])

    def test_rebuild_over_limit_invalid(self):
        draft = list(range(5000, 5036))  # 36 个
        result = gflh.plan("rebuild", draft, current=current())
        self.assertFalse(result["valid"])
        self.assertTrue(any("上限" in warning for warning in result["warnings"]))

    def test_rebuild_dedupes_draft(self):
        result = gflh.plan("rebuild", [300, 300, 400], current=current())
        self.assertEqual(pairs(result["adds"]), [(1, 300), (2, 400)])
        self.assertTrue(any("重复" in warning for warning in result["warnings"]))
        self.assertEqual([item["team"] for item in result["skipped"]], [300])
        self.assertTrue(result["valid"])

    def test_replace_basic(self):
        result = gflh.plan(
            "replace", [900, 800, 700],
            current=current((1, 100), (2, 200), (3, 300), (4, 400), (5, 500)))
        self.assertEqual(pairs(result["deletes"]), [(1, 100), (2, 200), (3, 300)])
        self.assertEqual(pairs(result["adds"]), [(1, 900), (2, 800), (3, 700)])
        self.assertEqual(pairs(result["kept"]), [(4, 400), (5, 500)])
        self.assertEqual(pairs(result["final"]),
                         [(1, 900), (2, 800), (3, 700), (4, 400), (5, 500)])
        self.assertTrue(result["valid"])

    def test_replace_removes_old_order_of_draft_team(self):
        result = gflh.plan("replace", [700],
                           current=current((1, 100), (2, 200), (6, 700)))
        # order 1 被替换；700 原来在 order 6（保留区）→ 先删旧项
        self.assertIn((6, 700), pairs(result["deletes"]))
        self.assertEqual(pairs(result["adds"]), [(1, 700)])
        self.assertEqual(pairs(result["kept"]), [(2, 200)])
        self.assertEqual(pairs(result["final"]), [(1, 700), (2, 200)])
        self.assertTrue(result["valid"])

    def test_replace_longer_than_current(self):
        result = gflh.plan("replace", [900, 800, 700], current=current((1, 100)))
        self.assertEqual(pairs(result["deletes"]), [(1, 100)])
        self.assertEqual(pairs(result["adds"]), [(1, 900), (2, 800), (3, 700)])
        self.assertEqual(result["kept"], [])
        self.assertEqual(len(result["final"]), 3)
        self.assertTrue(result["valid"])

    def test_replace_duplicate_draft_invalid(self):
        result = gflh.plan("replace", [900, 900], current=current())
        self.assertFalse(result["valid"])
        self.assertTrue(any("重复" in warning for warning in result["warnings"]))
        self.assertEqual(pairs(result["adds"]), [(1, 900)])

    def test_replace_over_limit_invalid(self):
        draft = list(range(5000, 5036))
        result = gflh.plan("replace", draft, current=current())
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["adds"]), 36)
        self.assertTrue(any("上限" in warning for warning in result["warnings"]))

    def test_replace_deletes_all_entries_at_replaced_order(self):
        result = gflh.plan("replace", [900, 800],
                           current=current((2, 100), (2, 200)))
        self.assertEqual(pairs(result["deletes"]), [(2, 100), (2, 200)])
        self.assertEqual(pairs(result["final"]), [(1, 900), (2, 800)])
        self.assertTrue(result["valid"])

    def test_clear(self):
        result = gflh.plan("clear", [], current=current((1, 100), (2, 200)))
        self.assertEqual(pairs(result["deletes"]), [(1, 100), (2, 200)])
        self.assertEqual(result["adds"], [])
        self.assertEqual(result["kept"], [])
        self.assertEqual(result["final"], [])
        self.assertTrue(result["valid"])
        self.assertEqual([item["order_id"] for item in result["payloads"]["del"]], [1, 2])
        self.assertEqual(result["payloads"]["add"], [])

    def test_clear_with_empty_current(self):
        result = gflh.plan("clear", [], current=current())
        self.assertEqual(result["deletes"], [])
        self.assertTrue(result["valid"])
        self.assertTrue(result["warnings"])

    def test_payload_shape(self):
        result = gflh.plan("rebuild", [100], current=current((2, 200)))
        self.assertEqual(result["payloads"]["add"][0], {
            "enemy_team_id": 100,
            "fight_type": 0,
            "fight_coef": "",
            "fight_environment_group": "",
            "order_id": 1,
        })
        self.assertEqual(result["payloads"]["del"][0], {
            "enemy_team_id": 200,
            "fight_type": 0,
            "fight_coef": "",
            "fight_environment_group": "",
            "order_id": 2,
        })

    def test_plan_accepts_plain_target_list(self):
        result = gflh.plan("append", [300], current=[{"order": 1, "team": 100}])
        self.assertEqual(pairs(result["adds"]), [(2, 300)])

    def test_plan_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            gflh.plan("nope", [100], current=current())

    def test_plan_ignores_invalid_current_entries(self):
        result = gflh.plan("append", [300], current={"targets": [
            {"order": 1, "team": 100}, {"order": 2, "team": 0}, "bad",
        ]})
        self.assertEqual(pairs(result["adds"]), [(2, 300)])

    def test_constants(self):
        self.assertEqual(gflh.MAX_TARGETS, 35)
        self.assertEqual(gflh.CAPTURE_PORT, 18080)
        self.assertEqual(gflh.API_ADD, "Targettrain/addCollect")
        self.assertEqual(gflh.API_DEL, "Targettrain/delCollect")


# ---------------------------------------------------------------------------
# current_targets / list_creds / load_creds_file
# ---------------------------------------------------------------------------
class CurrentTargetsTests(TempPathsMixin, unittest.TestCase):
    def test_creds_source_pairs_enemies_orders(self):
        self.write_creds({
            "uid": "100000001", "sign": "SECRET_SIGN",
            "base_url": "http://gf.example/index.php/1000/",
            "enemies": ["111", "222"], "orders": ["1", "2"],
            "captured_at": now_iso(),
        })
        result = gflh.current_targets("creds")
        self.assertEqual(result["source"], "creds")
        self.assertEqual(result["creds_file"], "creds_latest.json")
        self.assertEqual(result["uid"], "100000001")
        self.assertEqual(result["base_url"], "http://gf.example/index.php/1000/")
        self.assertEqual(pairs(result["targets"]), [(1, 111), (2, 222)])
        self.assertEqual(result["duplicate_orders"], {})
        self.assertEqual(result["max_targets"], gflh.MAX_TARGETS)
        self.assertNotIn("SECRET_SIGN", json.dumps(result, ensure_ascii=False))

    def test_duplicate_orders_warning(self):
        self.write_creds({
            "uid": "1", "sign": "s", "base_url": "http://gf.example/index.php/1000/",
            "enemies": ["11", "22", "33"], "orders": ["2", "2", "3"],
            "captured_at": now_iso(),
        })
        result = gflh.current_targets("creds")
        self.assertEqual(result["duplicate_orders"], {2: [11, 22]})
        self.assertTrue(any("编号重复" in warning for warning in result["warnings"]))

    def test_empty_targets_warning(self):
        self.write_creds({
            "uid": "1", "sign": "s", "base_url": "http://gf.example/index.php/1000/",
            "enemies": [], "orders": [], "captured_at": now_iso(),
        })
        result = gflh.current_targets("creds")
        self.assertEqual(result["targets"], [])
        self.assertTrue(any("没有" in warning for warning in result["warnings"]))

    def test_stale_creds_warning(self):
        self.write_creds({
            "uid": "1", "sign": "s", "base_url": "http://gf.example/index.php/1000/",
            "enemies": ["11"], "orders": ["1"],
            "captured_at": now_iso(hours_ago=30),
        })
        result = gflh.current_targets("creds")
        self.assertTrue(any("过期" in warning and "重新登录" in warning
                            for warning in result["warnings"]))

    def test_auto_prefers_creds(self):
        self.write_creds({
            "uid": "cred_uid", "sign": "s",
            "base_url": "http://gf.example/index.php/1000/",
            "enemies": ["11"], "orders": ["1"], "captured_at": now_iso(),
        })
        self.write_state({"targets": [{"order": 1, "team": 999}]})
        result = gflh.current_targets("auto")
        self.assertEqual(result["source"], "creds")
        self.assertEqual(pairs(result["targets"]), [(1, 11)])

    def test_state_source_when_no_creds(self):
        self.write_state({
            "targets": [{"order": 1, "team": 100}, {"order": 2, "team": 200}],
            "uid": "100000001",
            "base_url": "http://gf.example/index.php/1000/",
            "updated_at": now_iso(),
        })
        result = gflh.current_targets("auto")
        self.assertEqual(result["source"], "state")
        self.assertEqual(result["uid"], "100000001")
        self.assertEqual(pairs(result["targets"]), [(1, 100), (2, 200)])
        self.assertEqual(result["state_file"], "target_injection_state.json")

    def test_no_data_at_all(self):
        result = gflh.current_targets("auto")
        self.assertEqual(result["source"], "none")
        self.assertEqual(result["targets"], [])
        self.assertTrue(result["warnings"])

    def test_creds_missing_raises_only_for_bad_source(self):
        with self.assertRaises(ValueError):
            gflh.current_targets("nope")

    def test_creds_source_without_file(self):
        result = gflh.current_targets("creds")
        self.assertEqual(result["source"], "creds")
        self.assertEqual(result["targets"], [])
        self.assertTrue(any("没有凭证文件" in warning for warning in result["warnings"]))

    def test_mismatched_enemies_and_orders(self):
        self.write_creds({
            "uid": "1", "sign": "s", "base_url": "http://gf.example/index.php/1000/",
            "enemies": ["11", "22"], "orders": ["1"], "captured_at": now_iso(),
        })
        result = gflh.current_targets("creds")
        self.assertEqual(pairs(result["targets"]), [(1, 11), (0, 22)])
        self.assertTrue(any("数量不一致" in warning for warning in result["warnings"]))


class CredsFileTests(TempPathsMixin, unittest.TestCase):
    def test_list_creds_scans_all_locations_without_sign(self):
        self.write_creds({"uid": "a", "sign": "SIGN_A", "base_url": "http://a/",
                          "enemies": ["1", "2"], "orders": ["1", "2"],
                          "captured_at": now_iso(1)}, self.data_dir / "creds_old.json")
        self.write_creds({"uid": "b", "sign": "SIGN_B", "base_url": "http://b/",
                          "enemies": ["3"], "orders": ["1"],
                          "captured_at": now_iso()}, self.derived / "cn_creds_x.json")
        self.write_creds({"uid": "c", "sign": "SIGN_C", "base_url": "http://c/",
                          "enemies": [], "orders": [],
                          "captured_at": now_iso(2)}, self.derived / "tw_creds.json")
        entries = gflh.list_creds()
        names = {entry["name"] for entry in entries}
        self.assertEqual(names, {"creds_old.json", "cn_creds_x.json", "tw_creds.json"})
        self.assertEqual([entry for entry in entries if entry["name"] == "cn_creds_x.json"][0]
                         ["targets_count"], 1)
        dumped = json.dumps(entries, ensure_ascii=False)
        self.assertNotIn("SIGN_A", dumped)
        self.assertNotIn("SIGN_B", dumped)
        self.assertNotIn("SIGN_C", dumped)
        for entry in entries:
            self.assertNotIn("sign", entry)

    def test_load_creds_file_copies_to_latest(self):
        source = self.write_creds(
            {"uid": "100000001", "sign": "SIGN_X", "base_url": "http://gf.example/index.php/1000/",
             "enemies": ["111", "222"], "orders": ["1", "2"],
             "captured_at": now_iso()},
            self.derived / "cn_creds_pick.json")
        result = gflh.load_creds_file("cn_creds_pick.json")
        self.assertTrue(result["ok"])
        self.assertEqual(result["loaded_from"], "cn_creds_pick.json")
        self.assertEqual([item["name"] for item in gflh.list_creds()
                          if item["name"] == "creds_latest.json"], ["creds_latest.json"])
        copied = json.loads(self.creds_file.read_text(encoding="utf-8"))
        self.assertEqual(copied["sign"], "SIGN_X")
        self.assertEqual(copied["enemies"], ["111", "222"])
        self.assertEqual(pairs(result["targets"]), [(1, 111), (2, 222)])
        self.assertNotIn("SIGN_X", json.dumps(result, ensure_ascii=False))
        self.assertTrue(source.is_file())

    def test_load_creds_file_missing_raises(self):
        with self.assertRaises(ValueError):
            gflh.load_creds_file("creds_不存在.json")

    def test_load_creds_file_incomplete_raises(self):
        self.write_creds({"uid": "1"}, self.derived / "cn_creds_broken.json")
        with self.assertRaises(ValueError):
            gflh.load_creds_file("cn_creds_broken.json")

    def test_load_creds_file_rejects_outside_path(self):
        outside = self.write_creds({"uid": "1", "sign": "S"}, self.tmp / "outside.json")
        with self.assertRaises(ValueError):
            gflh.load_creds_file(str(outside))


# ---------------------------------------------------------------------------
# execute：dry_run 不联网 / 真跑 mock client
# ---------------------------------------------------------------------------
class ExecuteTests(TempPathsMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        pace = mock.patch.object(gflh, "_pace")
        self.pace = pace.start()
        self.addCleanup(pace.stop)

    def _creds(self, enemies=(), orders=(), uid="100000001", sign="SECRET_SIGN"):
        return {
            "uid": uid, "sign": sign,
            "base_url": "http://gf.example/index.php/1000/",
            "enemies": list(enemies), "orders": list(orders),
            "captured_at": now_iso(),
        }

    def test_dry_run_returns_payloads_without_network(self):
        self.write_creds(self._creds())
        with mock.patch.object(gflh, "_make_client",
                               side_effect=AssertionError("dry_run 不能联网")), \
                mock.patch.object(gflh, "_require_gflzirc",
                                  side_effect=AssertionError("dry_run 不需要 gflzirc")):
            result = gflh.execute("rebuild", [300, 400], dry_run=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["added"], 0)
        self.assertEqual([item["order_id"] for item in result["payloads"]["add"]], [1, 2])
        self.assertEqual([item["enemy_team_id"] for item in result["payloads"]["add"]],
                         [300, 400])
        self.assertFalse(result["restart_required"])

    def test_dry_run_works_without_creds_file(self):
        result = gflh.execute("rebuild", [300], dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual([item["order_id"] for item in result["payloads"]["add"]], [1])

    def test_dry_run_replace_has_del_payloads_with_order_id(self):
        self.write_creds(self._creds(enemies=["111", "222"], orders=["1", "2"]))
        result = gflh.execute("replace", [900], dry_run=True)
        self.assertEqual(result["payloads"]["del"],
                         [{"enemy_team_id": 111, "fight_type": 0, "fight_coef": "",
                           "fight_environment_group": "", "order_id": 1}])
        self.assertEqual([(item["order"], item["team"]) for item in result["plan"]["adds"]],
                         [(1, 900)])

    def test_execute_invalid_plan_does_not_connect(self):
        with mock.patch.object(gflh, "_make_client",
                               side_effect=AssertionError("不合法计划不该联网")):
            result = gflh.execute("replace", [900, 900])
        self.assertFalse(result["ok"])
        self.assertIn("不合法", result["error"])

    def test_execute_missing_creds(self):
        with mock.patch.object(gflh, "_make_client",
                               side_effect=AssertionError("缺凭证不该建 client")):
            result = gflh.execute("rebuild", [300])
        self.assertFalse(result["ok"])
        self.assertIn("没有凭证", result["error"])
        self.assertIn("hint", result)

    def test_execute_incomplete_creds(self):
        self.write_creds(self._creds(sign=""))
        with mock.patch.object(gflh, "_make_client",
                               side_effect=AssertionError("缺 sign 不该建 client")):
            result = gflh.execute("rebuild", [300])
        self.assertFalse(result["ok"])
        self.assertIn("sign", result["error"])

    def test_execute_happy_path_calls_add_and_updates_state(self):
        self.write_creds(self._creds())
        client = FakeClient()
        logs: list[tuple[str, str]] = []
        with mock.patch.object(gflh, "_make_client", return_value=client) as make:
            result = gflh.execute("rebuild", [300, 400], log=lambda level, text: logs.append(
                (level, text)))
        make.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["failed"], [])
        self.assertEqual(client.calls, [
            (gflh.API_ADD, {"enemy_team_id": 300, "fight_type": 0, "fight_coef": "",
                            "fight_environment_group": "", "order_id": 1}),
            (gflh.API_ADD, {"enemy_team_id": 400, "fight_type": 0, "fight_coef": "",
                            "fight_environment_group": "", "order_id": 2}),
        ])
        self.assertEqual(self.pace.call_count, 2)
        state = self.read_state()
        self.assertEqual(pairs(state["targets"]), [(1, 300), (2, 400)])
        self.assertEqual(state["uid"], "100000001")
        self.assertTrue(result["restart_required"])
        self.assertTrue(any("新增收藏標靶1" in text for _level, text in logs))

    def test_execute_deletes_before_adds(self):
        self.write_creds(self._creds(enemies=["111", "222"], orders=["1", "2"]))
        client = FakeClient()
        with mock.patch.object(gflh, "_make_client", return_value=client):
            result = gflh.execute("replace", [900, 800])
        self.assertTrue(result["ok"])
        self.assertEqual([call[0] for call in client.calls],
                         [gflh.API_DEL, gflh.API_DEL, gflh.API_ADD, gflh.API_ADD])
        self.assertEqual([call[1]["order_id"] for call in client.calls], [1, 2, 1, 2])
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["added"], 2)
        state = self.read_state()
        self.assertEqual(pairs(state["targets"]), [(1, 900), (2, 800)])

    def test_execute_single_failure_continues(self):
        self.write_creds(self._creds())
        client = FakeClient(responses=[{"error": 300}, {"success": True}])
        with mock.patch.object(gflh, "_make_client", return_value=client):
            result = gflh.execute("rebuild", [300, 400])
        self.assertFalse(result["ok"])
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(result["failed"]), 1)
        failed = result["failed"][0]
        self.assertEqual((failed["step"], failed["team"], failed["order"]), ("add", 300, 1))
        self.assertEqual(failed["error"], "300")
        self.assertIn("order_id", failed["hint"])
        state = self.read_state()
        self.assertEqual(pairs(state["targets"]), [(2, 400)])

    def test_execute_cancel_stops_early(self):
        self.write_creds(self._creds())
        client = FakeClient()
        counter = {"n": 0}

        def cancel():
            counter["n"] += 1
            return counter["n"] > 1

        with mock.patch.object(gflh, "_make_client", return_value=client):
            result = gflh.execute("rebuild", [300, 400, 500], cancel=cancel)
        self.assertFalse(result["ok"])
        self.assertTrue(result["canceled"])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["added"], 1)

    def test_execute_explicit_creds_file(self):
        path = self.write_creds(self._creds(enemies=["111"], orders=["1"]),
                                self.derived / "cn_creds_special.json")
        client = FakeClient()
        with mock.patch.object(gflh, "_make_client", return_value=client):
            result = gflh.execute("append", [300], creds_file=str(path), dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["creds_file"], str(path))
        self.assertEqual([item["order"] for item in result["plan"]["adds"]], [2])

    def test_response_error_parsing(self):
        self.assertEqual(gflh._response_error({"error": 300}), "300")
        self.assertIsNone(gflh._response_error({"success": True}))
        self.assertIsNone(gflh._response_error(None))
        self.assertTrue(gflh._response_error({"error_local": "boom"}))
        self.assertTrue(gflh._response_error({"success": False, "msg": "no"}))

    def test_error_hint(self):
        self.assertIn("order_id", gflh._error_hint("300"))
        self.assertIn("sign", gflh._error_hint("sign expired"))
        self.assertIn("网络", gflh._error_hint("network timeout"))

    def test_derive_base_url(self):
        self.assertEqual(
            gflh._derive_base_url("http://gf.example/index.php/1000/Index/index"),
            "http://gf.example/index.php/1000/")
        self.assertIsNone(gflh._derive_base_url("/index.php/1000/Index/index"))
        self.assertIsNone(gflh._derive_base_url("http://gf.example/other"))


# ---------------------------------------------------------------------------
# capture：状态机（GFLProxy / 系统代理全部 fake）
# ---------------------------------------------------------------------------
class CaptureTests(TempPathsMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.capture = gflh._new_capture_state()
        patcher = mock.patch.object(gflh, "_CAPTURE", self.capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 端口可用性检查 mock 掉（真实 bind 会碰系统端口，单测禁止）
        self.port_available = mock.patch.object(gflh, "_port_available",
                                                return_value=(True, ""))
        self.port_available.start()
        self.addCleanup(self.port_available.stop)

    def test_status_initial_idle(self):
        status = gflh.capture_status()
        self.assertEqual(status["state"], "idle")
        self.assertEqual(status["port"], gflh.CAPTURE_PORT)
        self.assertFalse(status["sign_set"])
        self.assertFalse(status["login_captured"])
        self.assertFalse(status["targets_captured"])
        self.assertEqual(status["targets_count"], 0)
        self.assertEqual(status["logs"], [])
        self.assertNotIn("sign", status)

    def test_stop_without_start_is_safe(self):
        status = gflh.capture_stop()
        self.assertEqual(status["state"], "idle")
        self.assertFalse(self.creds_file.exists())
        self.assertTrue(status["logs"])  # 有一条 warn 日志
        self.assertEqual(status["logs"][-1]["level"], "warn")

    def test_start_requires_gflzirc(self):
        with mock.patch.object(gflh, "_require_gflzirc",
                               side_effect=RuntimeError("缺少 gflzirc")), \
                mock.patch.object(gflh, "_call_set_windows_proxy") as set_proxy:
            status = gflh.capture_start(set_proxy=True, auto_restore_proxy=False)
        self.assertEqual(status["state"], "error")
        self.assertIn("gflzirc", status["error"])
        set_proxy.assert_not_called()

    def test_start_proxy_error_restores_system_proxy(self):
        fake = FakeGflzirc(start_error=OSError("port in use"))
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            status = gflh.capture_start(set_proxy=True, auto_restore_proxy=False)
        self.assertEqual(status["state"], "error")
        self.assertIn("port in use", status["error"])
        self.assertEqual(fake.set_proxy_calls[0][0], True)
        self.assertEqual(fake.set_proxy_calls[-1][0], False)
        self.assertFalse(status["proxy_active"])

    def test_capture_start_capture_stop_full_flow(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            status = gflh.capture_start(port=gflh.CAPTURE_PORT, set_proxy=True,
                                        auto_restore_proxy=False)
            self.assertEqual(status["state"], "running")
            self.assertEqual(status["port"], gflh.CAPTURE_PORT)
            self.assertTrue(status["proxy_active"])
            self.assertTrue(status["system_proxy_on"])
            self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:18080"))
            self.assertEqual(len(fake.proxies), 1)
            proxy = fake.proxies[0]
            self.assertEqual(proxy.port, gflh.CAPTURE_PORT)
            self.assertEqual(proxy.static_key, gflh.STATIC_KEY)
            self.assertTrue(proxy.started)

            # 登录流量：SYS_KEY_UPGRADE
            proxy.callback("SYS_KEY_UPGRADE",
                           "http://gf.example/index.php/1000/Index/getUidPC",
                           {"uid": "100000001", "sign": "SECRET_SIGN"})
            status = gflh.capture_status()
            self.assertEqual(status["uid"], "100000001")
            self.assertTrue(status["sign_set"])
            self.assertTrue(status["login_captured"])
            self.assertEqual(status["base_url"], "http://gf.example/index.php/1000/")
            self.assertNotIn("SECRET_SIGN", json.dumps(status, ensure_ascii=False))

            # 靶机列表：S2C Index/index 的 targettrain_collect_user_info
            proxy.callback("S2C", "http://gf.example/index.php/1000/Index/index", {
                "targettrain_collect_user_info": [
                    {"enemy_team_id": "111", "order_id": "1"},
                    {"enemy_team_id": "222", "order_id": "2"},
                ],
            })
            status = gflh.capture_status()
            self.assertEqual(status["targets_count"], 2)
            self.assertTrue(status["targets_captured"])

            status = gflh.capture_stop()
        self.assertEqual(status["state"], "stopped")
        self.assertTrue(proxy.stopped)
        self.assertEqual(fake.set_proxy_calls[-1][0], False)
        self.assertTrue(status["creds_path"].endswith("creds_latest.json"))
        creds = json.loads(self.creds_file.read_text(encoding="utf-8"))
        self.assertEqual(creds["uid"], "100000001")
        self.assertEqual(creds["sign"], "SECRET_SIGN")
        self.assertEqual(creds["base_url"], "http://gf.example/index.php/1000/")
        self.assertEqual(creds["enemies"], ["111", "222"])
        self.assertEqual(creds["orders"], ["1", "2"])
        self.assertIn("captured_at", creds)
        self.assertNotIn("SECRET_SIGN", json.dumps(status, ensure_ascii=False))

        # 抓到的 creds 能被 current_targets 读到
        result = gflh.current_targets("creds")
        self.assertEqual(pairs(result["targets"]), [(1, 111), (2, 222)])

    def test_custom_port_full_chain_uses_configured_port(self):
        """capture_start(port=18093) 后：监听/系统代理/status/restart_game/stop 全用 18093。"""
        fake = FakeGflzirc()
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_game_pids", side_effect=[[111], []]), \
                mock.patch.object(gflh.subprocess, "run", return_value=completed) as run:
            start = gflh.capture_start(port=18093, set_proxy=True,
                                       auto_restore_proxy=False)
            self.assertEqual(start["state"], "running")
            self.assertEqual(start["port"], 18093)
            self.assertTrue(start["proxy_active"])
            self.assertTrue(start["system_proxy_on"])
            self.assertEqual(len(fake.proxies), 1)
            self.assertEqual(fake.proxies[0].port, 18093)
            self.assertEqual(fake.proxies[0].static_key, gflh.STATIC_KEY)
            self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:18093"))
            self.assertEqual(gflh.capture_status()["port"], 18093)

            # restart_game 用当前会话端口，不是默认 18080
            restart = gflh.capture_restart_game()
            self.assertTrue(restart["ok"])
            self.assertEqual(restart["system_proxy"], "127.0.0.1:18093")
            self.assertIn("127.0.0.1:18093", restart["steps"][0])
            self.assertEqual(fake.set_proxy_calls[-1], (True, "127.0.0.1:18093"))

            # stop：停代理 + 恢复系统代理，status.port 仍是 18093
            stop = gflh.capture_stop()
        self.assertEqual(stop["state"], "stopped")
        self.assertEqual(stop["port"], 18093)
        self.assertTrue(fake.proxies[0].stopped)
        self.assertEqual(fake.set_proxy_calls[-1][0], False)
        logs_text = " ".join(entry["text"] for entry in stop["logs"])
        self.assertIn("18093", logs_text)
        self.assertNotIn("18080", logs_text)  # 全链路不能回落到默认端口
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["taskkill", "/IM", gflh.GAME_PROCESS, "/F"], commands)
        self.assertIn(["cmd", "/c", "start", "", gflh.STEAM_URL], commands)
        # 停掉后系统代理地址仍可从最近会话端口推导
        self.assertEqual(gflh._recent_capture_port(), 18093)

    def test_capture_start_rejects_out_of_range_port(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            status = gflh.capture_start(port=70000, set_proxy=True,
                                        auto_restore_proxy=False)
        self.assertEqual(status["state"], "error")
        self.assertIn("越界", status["error"])
        # 越界端口不会成为 status.port / 最近会话端口
        self.assertEqual(status["port"], gflh.CAPTURE_PORT)
        self.assertEqual(gflh._recent_capture_port(), gflh.CAPTURE_PORT)
        self.assertEqual(fake.proxies, [])
        self.assertEqual(fake.set_proxy_calls, [])

    def test_capture_start_rejects_reserved_8080(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            status = gflh.capture_start(port=8080, set_proxy=True,
                                        auto_restore_proxy=False)
        self.assertEqual(status["state"], "error")
        self.assertIn("8080", status["error"])
        self.assertIn("占用", status["error"])
        # 8080 即使被尝试过，也不会成为「最近会话端口」被自动拿去做系统代理
        self.assertEqual(gflh._recent_capture_port(), gflh.CAPTURE_PORT)
        self.assertEqual(gflh._proxy_addr(), f"127.0.0.1:{gflh.CAPTURE_PORT}")
        self.assertEqual(fake.proxies, [])
        self.assertEqual(fake.set_proxy_calls, [])

    def test_capture_start_occupied_port_error_is_readable(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_port_available",
                               return_value=(False, "端口 18093 无法监听："
                                                     "可能被其它程序占用")), \
                mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            status = gflh.capture_start(port=18093, set_proxy=True,
                                        auto_restore_proxy=False)
        self.assertEqual(status["state"], "error")
        self.assertIn("无法监听", status["error"])
        self.assertIn("18093", status["error"])
        # 端口不可用时不改系统代理、不创建代理
        self.assertEqual(fake.proxies, [])
        self.assertEqual(fake.set_proxy_calls, [])

    def test_repeated_start_is_ignored(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake):
            gflh.capture_start(auto_restore_proxy=False)
            second = gflh.capture_start(auto_restore_proxy=False)
        self.assertEqual(second["state"], "running")
        self.assertEqual(second["port"], gflh.CAPTURE_PORT)  # 不传 port 用默认 18080
        self.assertEqual(len(fake.proxies), 1)

    def test_auto_restore_watchdog_stops_when_ready(self):
        self.capture.update({"state": "running", "login_captured": True,
                             "targets_captured": True})
        with mock.patch.object(gflh, "CAPTURE_AUTO_STOP_DELAY", 0.0), \
                mock.patch.object(gflh.time, "sleep"), \
                mock.patch.object(gflh, "capture_stop") as stop:
            gflh._capture_watchdog()
        stop.assert_called_once()
        self.assertIsNotNone(self.capture["auto_stop_at"])

    def test_watchdog_does_nothing_before_ready(self):
        self.capture.update({"state": "running", "login_captured": True,
                             "targets_captured": False})
        calls = {"n": 0}

        def sleep_once(_seconds):
            calls["n"] += 1
            if calls["n"] > 2:
                self.capture["state"] = "stopped"  # 让 watchdog 退出

        with mock.patch.object(gflh.time, "sleep", side_effect=sleep_once), \
                mock.patch.object(gflh, "capture_stop") as stop:
            gflh._capture_watchdog()
        stop.assert_not_called()

    def test_old_watchdog_exits_after_restart(self):
        self.capture.update({"state": "running", "login_captured": True,
                             "targets_captured": True})
        stale_generation = gflh._CAPTURE_GENERATION - 1
        with mock.patch.object(gflh.time, "sleep"), \
                mock.patch.object(gflh, "capture_stop") as stop:
            gflh._capture_watchdog(generation=stale_generation)
        stop.assert_not_called()

    def test_capture_restart_game_requires_running(self):
        with mock.patch.object(gflh, "_call_set_windows_proxy") as set_proxy, \
                mock.patch.object(gflh.subprocess, "run") as run:
            result = gflh.capture_restart_game()
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "idle")
        self.assertIn("没有活跃", result["error"])
        self.assertIn(str(gflh.CAPTURE_PORT), result["hint"])
        self.assertEqual(result["steps"], [])
        set_proxy.assert_not_called()
        run.assert_not_called()

    def test_capture_restart_game_sets_proxy_and_launches(self):
        self.capture.update({"state": "running", "port": 18080})
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(gflh, "_call_set_windows_proxy", return_value=True) as set_proxy, \
                mock.patch.object(gflh, "_game_pids", side_effect=[[111], []]), \
                mock.patch.object(gflh.subprocess, "run", return_value=completed) as run:
            result = gflh.capture_restart_game()
        self.assertTrue(result["ok"])
        self.assertEqual(result["system_proxy"], "127.0.0.1:18080")
        self.assertEqual(len(result["steps"]), 3)
        self.assertTrue(result["hint"])
        set_proxy.assert_called_with(True, "127.0.0.1:18080")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["taskkill", "/IM", gflh.GAME_PROCESS, "/F"], commands)
        self.assertIn(["cmd", "/c", "start", "", gflh.STEAM_URL], commands)


# ---------------------------------------------------------------------------
# 端口可配置：校验 / set_system_proxy 的 addr 优先级
# ---------------------------------------------------------------------------
class PortConfigTests(unittest.TestCase):
    def test_validate_capture_port(self):
        self.assertEqual(gflh._validate_capture_port(18093), (18093, None))
        self.assertEqual(gflh._validate_capture_port("18093"), (18093, None))
        # 未指定 → 默认 18080
        self.assertEqual(gflh._validate_capture_port(None), (gflh.CAPTURE_PORT, None))
        self.assertEqual(gflh._validate_capture_port(""), (gflh.CAPTURE_PORT, None))
        self.assertEqual(gflh._validate_capture_port(0), (gflh.CAPTURE_PORT, None))
        # 越界
        for bad in (-1, 70000, 65536):
            port, error = gflh._validate_capture_port(bad)
            self.assertEqual(port, bad)
            self.assertIsNotNone(error)
            self.assertIn("越界", error)
        # 非整数
        port, error = gflh._validate_capture_port("abc")
        self.assertEqual(port, gflh.CAPTURE_PORT)
        self.assertIsNotNone(error)
        self.assertIn("不是整数", error)
        # 8080 保留（另一个 bot）
        port, error = gflh._validate_capture_port(8080)
        self.assertEqual(port, 8080)
        self.assertIsNotNone(error)
        self.assertIn("占用", error)
        self.assertEqual(gflh._validate_capture_port(1024), (1024, None))
        self.assertEqual(gflh._validate_capture_port(65535), (65535, None))

    def test_proxy_addr_uses_explicit_then_recent_port(self):
        self.assertEqual(gflh._proxy_addr(18093), "127.0.0.1:18093")
        self.assertEqual(gflh._proxy_addr(gflh.CAPTURE_PORT),
                         f"127.0.0.1:{gflh.CAPTURE_PORT}")
        capture = gflh._new_capture_state()
        capture.update({"state": "stopped", "port": 18093})
        with mock.patch.object(gflh, "_CAPTURE", capture):
            self.assertEqual(gflh._proxy_addr(), "127.0.0.1:18093")
            self.assertTrue(gflh._has_capture_session())
            self.assertEqual(gflh._recent_capture_port(), 18093)
        with mock.patch.object(gflh, "_CAPTURE", gflh._new_capture_state()):
            self.assertEqual(gflh._proxy_addr(), f"127.0.0.1:{gflh.CAPTURE_PORT}")
            self.assertFalse(gflh._has_capture_session())

    def test_set_system_proxy_default_is_18080_without_session(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_CAPTURE", gflh._new_capture_state()), \
                mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_read_system_proxy", return_value=None):
            result = gflh.set_system_proxy(True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["addr"], "127.0.0.1:18080")
        self.assertEqual(result["port"], 18080)
        self.assertEqual(result["source"], "default")
        self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:18080"))

    def test_set_system_proxy_uses_recent_session_port(self):
        capture = gflh._new_capture_state()
        capture.update({"state": "stopped", "port": 18093})
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_CAPTURE", capture), \
                mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_read_system_proxy",
                                  return_value="127.0.0.1:18093"):
            result = gflh.set_system_proxy(True)
        self.assertEqual(result["addr"], "127.0.0.1:18093")
        self.assertEqual(result["port"], 18093)
        self.assertEqual(result["source"], "session")
        self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:18093"))
        # 空白 addr 视同未给 → 仍用会话端口
        with mock.patch.object(gflh, "_CAPTURE", capture), \
                mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_read_system_proxy", return_value=None):
            blank = gflh.set_system_proxy(True, "  ")
        self.assertEqual(blank["addr"], "127.0.0.1:18093")
        self.assertEqual(blank["source"], "session")

    def test_set_system_proxy_explicit_addr_wins(self):
        capture = gflh._new_capture_state()
        capture.update({"state": "running", "port": 18093})
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_CAPTURE", capture), \
                mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_read_system_proxy",
                                  return_value="127.0.0.1:19001"):
            result = gflh.set_system_proxy(True, "127.0.0.1:19001")
        self.assertEqual(result["addr"], "127.0.0.1:19001")
        self.assertEqual(result["port"], 19001)
        self.assertEqual(result["source"], "explicit")
        self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:19001"))


# ---------------------------------------------------------------------------
# player_status / restart_game / set_system_proxy（tasklist / steam / winreg 全部 mock）
# ---------------------------------------------------------------------------
class GameControlTests(unittest.TestCase):
    def test_player_status_running(self):
        # 系统代理读真实注册表值，不能受 CAPTURE_PORT/会话端口默认值影响
        with mock.patch.object(gflh, "_game_pids", return_value=[12345]), \
                mock.patch.object(gflh, "_window_title", return_value="少女前线"), \
                mock.patch.object(gflh, "_read_system_proxy",
                                  return_value="127.0.0.1:19999"), \
                mock.patch.object(gflh, "_gflzirc_ok", return_value=True):
            status = gflh.player_status()
        self.assertEqual(status, {
            "game_running": True,
            "pid": 12345,
            "game_window_title": "少女前线",
            "system_proxy": "127.0.0.1:19999",
            "gflzirc_ok": True,
        })

    def test_player_status_not_running(self):
        with mock.patch.object(gflh, "_game_pids", return_value=[]), \
                mock.patch.object(gflh, "_window_title") as title, \
                mock.patch.object(gflh, "_read_system_proxy", return_value=None), \
                mock.patch.object(gflh, "_gflzirc_ok", return_value=False):
            status = gflh.player_status()
        self.assertFalse(status["game_running"])
        self.assertIsNone(status["pid"])
        self.assertIsNone(status["game_window_title"])
        self.assertIsNone(status["system_proxy"])
        title.assert_not_called()

    def test_parse_tasklist_pids(self):
        text = ('"GrilsFrontLine.exe","12345","Console","1","12,345 K"\r\n'
                '"other.exe","4242","Console","1","1,000 K"\r\n')
        self.assertEqual(gflh._parse_tasklist_pids(text), [12345])
        self.assertEqual(gflh._parse_tasklist_pids("信息: 没有运行的任务匹配指定标准。"), [])
        self.assertEqual(gflh._parse_tasklist_pids(""), [])

    def test_restart_game_flow(self):
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(gflh, "_game_pids", side_effect=[[111], []]), \
                mock.patch.object(gflh.subprocess, "run", return_value=completed) as run:
            result = gflh.restart_game(wait_ready=False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["killed"])
        self.assertTrue(result["launched"])
        self.assertEqual(result["waited_s"], 0.0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["taskkill", "/IM", gflh.GAME_PROCESS, "/F"], commands)
        self.assertIn(["cmd", "/c", "start", "", gflh.STEAM_URL], commands)

    def test_restart_game_when_not_running(self):
        completed = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(gflh, "_game_pids", return_value=[]), \
                mock.patch.object(gflh.subprocess, "run", return_value=completed) as run:
            result = gflh.restart_game(wait_ready=False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["killed"])
        self.assertTrue(result["launched"])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertNotIn(["taskkill", "/IM", gflh.GAME_PROCESS, "/F"], commands)

    def test_set_system_proxy_enable_and_disable(self):
        fake = FakeGflzirc()
        with mock.patch.object(gflh, "_require_gflzirc", return_value=fake), \
                mock.patch.object(gflh, "_read_system_proxy",
                                  return_value="127.0.0.1:18080"):
            enabled = gflh.set_system_proxy(True, "127.0.0.1:18080")
            disabled = gflh.set_system_proxy(False)
        self.assertTrue(enabled["ok"])
        self.assertTrue(enabled["enabled"])
        self.assertEqual(enabled["addr"], "127.0.0.1:18080")
        self.assertEqual(fake.set_proxy_calls[0], (True, "127.0.0.1:18080"))
        self.assertFalse(disabled["enabled"])
        self.assertEqual(fake.set_proxy_calls[-1][0], False)

    def test_set_system_proxy_without_gflzirc(self):
        with mock.patch.object(gflh, "_require_gflzirc",
                               side_effect=RuntimeError("no gflzirc")), \
                mock.patch.object(gflh, "_read_system_proxy", return_value=None):
            result = gflh.set_system_proxy(True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["hint"])


# ---------------------------------------------------------------------------
# 模块级约束：顶层懒加载、不起线程
# ---------------------------------------------------------------------------
class ModuleContractTests(unittest.TestCase):
    def test_import_is_lazy(self):
        code = (
            "import sys;"
            "sys.path.insert(0, sys.argv[1]);"
            "import targetforge.gflh;"
            "print('gflzirc' in sys.modules);"
            "print(bool([t for t in __import__('threading').enumerate()"
            " if t.name.startswith('gflh')]))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(gflh.ROOT)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.split(), ["False", "False"])

    def test_no_capture_threads_started(self):
        leaks = [thread.name for thread in threading.enumerate()
                 if thread.name.startswith("gflh")]
        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
