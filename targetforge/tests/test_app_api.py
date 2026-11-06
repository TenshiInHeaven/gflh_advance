"""app.py 的接口/状态/序列/job 自检（catalog、gflh 用 fake 模块，不依赖真实数据）。

跑法（仓库根目录）：
    python -m unittest targetforge.tests.test_app_api -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from targetforge import app  # noqa: E402


# ---------------------------------------------------------------------------
# fake catalog / gflh
# ---------------------------------------------------------------------------
TEAMS = {
    101: {
        "id": 101, "power": 50000, "power_known": True, "units": 3, "hp_total": 12000, "faction": "铁血",
        "tags": ["测试"], "gray_zone": False, "orphan": False,
        "species": [{"codex_no": 5, "name": "稻草人"}],
        "members": [{"code": "Scarecrow", "name": "稻草人", "number": 1, "count": 1}],
        "stage": {"chapter_id": "main-1", "title": "第1章", "stage_title": "演习训练", "code": "1-1"},
    },
    102: {
        "id": 102, "power": 0, "power_known": False, "units": 5, "hp_total": 20000, "faction": "军方",
        "tags": ["BOSS"], "gray_zone": False, "orphan": False,
        "species": [{"codex_no": 15, "name": "圣盾"}],
        "members": [{"code": "Aegis", "name": "圣盾", "number": 5, "count": 1}],
        "stage": None,
    },
}


class FakeCatalog:
    built_at = "2026-11-06T00:00:00+08:00"
    counts = {"chapters": 2, "stages": 3, "teams": len(TEAMS), "species": 2}

    def chapters(self):
        return {"built_at": self.built_at, "counts": self.counts, "groups": [
            {"id": "main", "title": "主线", "chapters": [
                {"id": "main-1", "category": "main", "title": "第1章", "subtitle": "",
                 "stage_count": 2, "team_count": 2, "species_count": 2,
                 "difficulty_min": 200, "difficulty_max": 34000, "tags": ["主线"]}]},
            {"id": "grayzone", "title": "灰域探查", "chapters": [
                {"id": "grayzone", "category": "grayzone", "title": "灰域探查", "subtitle": "1 个区域",
                 "stage_count": 1, "team_count": 1, "species_count": 1,
                 "areas": [{"id": "旅团商道", "title": "旅团商道", "stage_count": 1,
                            "team_count": 1, "species_count": 1}], "tags": ["打灰"]}]},
        ]}

    def chapter(self, chapter_id):
        if chapter_id == "main-1":
            return {"chapter": self.chapters()["groups"][0]["chapters"][0],
                    "stages": [{"id": 5, "title": "演习训练", "code": "1-1", "difficulty": 200,
                                "recommend_level": 0, "team_count": 1, "species_count": 1,
                                "tags": [], "order": 0}]}
        if chapter_id == "grayzone":
            return {"chapter": self.chapters()["groups"][1]["chapters"][0], "stages": [],
                    "areas": [{"id": "旅团商道", "title": "旅团商道", "stage_count": 1,
                               "team_count": 1, "species_count": 1}]}
        return None

    def stage(self, mission_id):
        if mission_id != 5:
            return None
        return {"stage": {"id": 5, "title": "演习训练", "code": "1-1", "difficulty": 200},
                "teams": [TEAMS[101]]}

    def team(self, team_id):
        return TEAMS.get(int(team_id))

    def team_summaries(self, team_ids):
        return [TEAMS[int(t)] for t in team_ids if int(t) in TEAMS]

    def grayzone_areas(self):
        return [{"id": "旅团商道", "title": "旅团商道", "stage_count": 1,
                 "team_count": 1, "species_count": 1}]

    def grayzone_teams(self, area, offset, limit, q="", power_min=None, power_max=None,
                       power_known=None, sort="default"):
        items = [TEAMS[101]] if not q else []
        if power_known:
            items = [item for item in items if item.get("power_known")]
        return {"total": len(items), "offset": 0, "items": items}

    def species_list(self, *, q="", faction="", category="", offset=0, limit=60):
        items = [{"codex_no": 5, "name": "稻草人", "faction": "铁血", "type": 1,
                  "team_count": 20, "gray_zone_team_count": 3, "orphan_team_count": 1,
                  "capturable": True, "tags": ["契约捕获"]}]
        return {"total": 1, "items": items}

    def species(self, codex_no):
        if codex_no != 5:
            return None
        return {"species": {"codex_no": 5, "name": "稻草人"}, "total": 1, "offset": 0,
                "limit": 60, "teams": [TEAMS[101]]}

    def search(self, q, limit=30):
        return {"teams": [TEAMS[101]], "stages": [{"id": 5, "title": "演习训练"}],
                "species": [{"codex_no": 5, "name": "稻草人"}]}


class FakeGflh:
    MAX_TARGETS = 35

    def player_status(self):
        return {"game_running": True, "pid": 1234, "gflzirc_ok": True, "system_proxy": None}

    def current_targets(self, source="auto"):
        return {"source": "state", "targets": [{"order": 1, "team": 101}],
                "uid": "1", "base_url": "", "captured_at": None,
                "duplicate_orders": {}, "max_targets": 35, "warnings": []}

    def plan(self, mode, draft, *, current, max_targets=35):
        return {"mode": mode, "deletes": [{"order": 1, "team": 101}],
                "adds": [{"order": i, "team": t} for i, t in enumerate(draft, 1)],
                "kept": [], "skipped": [], "final": [{"order": i, "team": t}
                                                     for i, t in enumerate(draft, 1)],
                "warnings": [], "valid": True, "payloads": {"add": [], "del": []}}

    def execute(self, mode, draft, *, creds_file=None, dry_run=False, log=None, cancel=None):
        if log:
            log("info", f"fake execute {mode} dry_run={dry_run}")
        return {"ok": True, "mode": mode, "dry_run": dry_run, "deleted": 1, "added": len(draft),
                "failed": [], "final": [{"order": i, "team": t} for i, t in enumerate(draft, 1)],
                "creds_file": creds_file, "restart_required": True}

    def list_creds(self):
        return [{"name": "creds_latest.json", "updated_at": None, "uid": "1",
                 "base_url": "", "targets_count": 1}]

    def capture_status(self):
        return {"state": "idle", "port": 18080, "logs": []}

    def capture_start(self, *, port=18080, set_proxy=True, auto_restore_proxy=True):
        return {"state": "running", "port": port, "logs": []}

    def capture_stop(self):
        return {"state": "stopped", "logs": []}

    def capture_restart_game(self):
        return {"ok": True, "steps": ["a", "b"]}

    def load_creds_file(self, name):
        return {"loaded": name, **self.current_targets()}

    def restart_game(self, *, wait_ready=True):
        return {"ok": True}

    def set_system_proxy(self, enable, addr="127.0.0.1:18080"):
        return {"enabled": enable, "addr": addr}


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------
class AppTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.icon_dir = self.tmp_path / "icons"
        self.icon_dir.mkdir(parents=True, exist_ok=True)
        (self.icon_dir / "test.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        self.patches = [
            mock.patch.object(app, "STATE_FILE", self.tmp_path / "state.json"),
            mock.patch.object(app, "DATA_DIR", self.tmp_path),
            mock.patch.object(app, "ICON_DIR", self.icon_dir),
            mock.patch.object(app, "_JOBS", {}),
            mock.patch.object(app, "_catalog_module", lambda: SimpleNamespace(
                load=lambda: FakeCatalog(), build=lambda force=False: {"counts": FakeCatalog.counts,
                                                                        "built_at": FakeCatalog.built_at},
                reload=lambda: FakeCatalog())),
            mock.patch.object(app, "_gflh_module", lambda: FakeGflh()),
            mock.patch.object(app, "_CATALOG_STATE",
                              {"state": "ready", "built_at": FakeCatalog.built_at,
                               "counts": FakeCatalog.counts, "error": None,
                               "started_at": None, "detail": ""}),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)


class StateAndHelpersTest(AppTestBase):
    def test_state_roundtrip(self):
        state = app.state_load()
        self.assertEqual(state["draft"], [])
        state["draft"] = [101, 102]
        state["tutorial"] = {"completed": ["welcome"], "dismissed": True}
        app.state_save(state)
        loaded = app.state_load()
        self.assertEqual(loaded["draft"], [101, 102])
        self.assertEqual(loaded["tutorial"]["completed"], ["welcome"])
        self.assertTrue((self.tmp_path / "state.json").is_file())

    def test_sequence_add_dedup_and_cap(self):
        resp = app.api_sequence_post({"action": "add", "team_id": 101})
        self.assertEqual([t["id"] for t in resp["draft"]], [101])
        resp = app.api_sequence_post({"action": "add", "team_ids": [101, 102]})
        self.assertEqual([t["id"] for t in resp["draft"]], [101, 102])
        with self.assertRaises(app.HttpError) as ctx:
            app.api_sequence_post({"action": "add", "team_ids": [999]})
        self.assertEqual(ctx.exception.status, 400)

    def test_sequence_move_remove_clear(self):
        app.api_sequence_post({"action": "set", "team_ids": [101, 102]})
        resp = app.api_sequence_post({"action": "move", "from": 0, "to": 1})
        self.assertEqual([t["id"] for t in resp["draft"]], [102, 101])
        resp = app.api_sequence_post({"action": "remove", "team_id": 102})
        self.assertEqual([t["id"] for t in resp["draft"]], [101])
        resp = app.api_sequence_post({"action": "clear"})
        self.assertEqual(resp["draft"], [])

    def test_exec_request_validation(self):
        with self.assertRaises(app.HttpError):
            app._exec_request({"mode": "nope"})
        with self.assertRaises(app.HttpError):
            app._exec_request({"mode": "append"})
        mode, draft, source = app._exec_request({"mode": "clear"})
        self.assertEqual((mode, draft, source), ("clear", [], "auto"))

    def test_preview_append(self):
        app.api_sequence_post({"action": "set", "team_ids": [101, 102]})
        preview = app.api_execute_preview({"mode": "append", "source": "state"})
        self.assertEqual(preview["mode"], "append")
        self.assertEqual(len(preview["adds"]), 2)
        self.assertEqual(len(preview["draft"]), 2)

    def test_jsonable_path_and_set(self):
        self.assertEqual(app._jsonable(self.tmp_path), str(self.tmp_path))
        self.assertEqual(app._jsonable({"b", "a"}), ["a", "b"])

    def test_team_query_filters_and_sort(self):
        teams = [
            {"id": 1, "power": 100, "power_known": True, "hp_total": 10, "units": 1},
            {"id": 2, "power": 0, "power_known": False, "hp_total": 30, "units": 3},
            {"id": 3, "power": -50, "power_known": True, "hp_total": 20, "units": 2},
        ]
        page = app._apply_team_query(teams, {"power_known": ["1"]})
        self.assertEqual([t["id"] for t in page["items"]], [1, 3])
        page = app._apply_team_query(teams, {"sort": ["hp_desc"]})
        self.assertEqual([t["id"] for t in page["items"]], [2, 3, 1])
        page = app._apply_team_query(teams, {"sort": ["power_desc"]})
        self.assertEqual([t["id"] for t in page["items"]], [1, 3, 2])
        page = app._apply_team_query(teams, {"power_min": ["0"], "power_max": ["200"]})
        self.assertEqual([t["id"] for t in page["items"]], [1])
        with self.assertRaises(app.HttpError):
            app._team_filters({"sort": ["bad"]})


class HttpRoutesTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def request(self, method, path, payload=None, timeout=20):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())

    def test_health_and_meta(self):
        status, payload = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["catalog"]["state"], "ready")
        status, meta = self.request("GET", "/api/meta")
        self.assertEqual(meta["counts"]["teams"], 2)

    def test_catalog_routes(self):
        status, chapters = self.request("GET", "/api/chapters")
        self.assertEqual(len(chapters["groups"]), 2)
        status, chapter = self.request("GET", "/api/chapters/main-1")
        self.assertEqual(chapter["stages"][0]["id"], 5)
        status, stage = self.request("GET", "/api/stages/5")
        self.assertEqual(stage["teams"][0]["id"], 101)
        status, team = self.request("GET", "/api/teams/101")
        self.assertEqual(team["power"], 50000)
        status, species = self.request("GET", "/api/species")
        self.assertEqual(species["total"], 1)
        status, species_detail = self.request("GET", "/api/species/5")
        self.assertEqual(species_detail["teams"][0]["id"], 101)
        status, areas = self.request("GET", "/api/grayzone/areas")
        self.assertEqual(areas["areas"][0]["id"], "旅团商道")
        status, gz = self.request("GET", "/api/grayzone/teams?area=%E6%97%85%E5%9B%A2%E5%95%86%E9%81%93&offset=0&limit=30")
        self.assertEqual(gz["total"], 1)
        status, search = self.request("GET", "/api/search?q=5")
        self.assertEqual(len(search["teams"]), 1)

    def test_sequence_and_preview_and_execute_job(self):
        status, seq = self.request("GET", "/api/sequence")
        self.assertEqual(seq["count"], 0)
        status, seq = self.request("POST", "/api/sequence",
                                   {"action": "add", "team_ids": [101, 102]})
        self.assertEqual(seq["count"], 2)
        status, preview = self.request("POST", "/api/execute/preview",
                                       {"mode": "rebuild", "source": "state"})
        self.assertTrue(preview["valid"])
        status, started = self.request("POST", "/api/execute",
                                       {"mode": "rebuild", "source": "state", "dry_run": True})
        self.assertIn("job_id", started)
        job = None
        for _ in range(100):
            status, job = self.request("GET", f"/api/jobs/{started['job_id']}")
            if job["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertTrue(job["result"]["execution"]["ok"])
        self.assertTrue(any("fake execute" in entry["text"] for entry in job["logs"]))

        status, state = self.request("POST", "/api/tutorial",
                                     {"completed": ["welcome", "chapters"], "dismissed": False})
        self.assertEqual(state["completed"], ["welcome", "chapters"])
        status, settings = self.request("POST", "/api/settings", {"capture_port": 18080})
        self.assertEqual(settings["capture_port"], 18080)

    def test_unknown_api_returns_json_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("GET", "/api/nope")
        self.assertEqual(ctx.exception.code, 404)
        payload = json.loads(ctx.exception.read().decode())
        self.assertIn("error", payload)

    def test_static_index(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as resp:
            html = resp.read().decode()
        self.assertIn("TargetForge", html)

    def test_icon_route_and_traversal_guard(self):
        with urllib.request.urlopen(self.base + "/api/icons/test.png", timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/png")
            self.assertEqual(resp.read(), b"\x89PNG\r\n\x1a\nfake")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/api/icons/..%2Fstate.json", timeout=10)
        self.assertIn(ctx.exception.code, (403, 404))


if __name__ == "__main__":
    unittest.main()
