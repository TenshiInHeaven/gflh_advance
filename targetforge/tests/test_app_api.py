"""app.py 的接口/状态/序列/job 自检（catalog、gflh 用 fake 模块，不依赖真实数据）。

跑法（仓库根目录）：
    python -m unittest targetforge.tests.test_app_api -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
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
        return {
            "regions": [{"id": "sand", "title": "沙尘带", "groups": [1],
                         "stage_count": 1, "team_count": 1, "species_count": 1,
                         "source": "daily_mission_difficulty_group-10000001"}],
            "areas": [{"id": "旅团商道", "title": "旅团商道", "region_ids": ["sand"],
                       "stage_count": 1, "team_count": 1, "species_count": 1}],
        }

    def grayzone_teams(self, area, region="", offset=0, limit=60, q="", power_min=None, power_max=None,
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
                                     headers={"Content-Type": "application/json",
                                              "X-TargetForge-Client": "1"})
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

    def test_security_headers_and_csrf_guard(self):
        # 正常 GET 带安全响应头
        with urllib.request.urlopen(self.base + "/api/health", timeout=10) as resp:
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
            self.assertIn("default-src 'self'", resp.headers.get("Content-Security-Policy") or "")
        # POST 缺少自定义安全头 → 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(urllib.request.Request(
                self.base + "/api/sequence", data=b"{}", method="POST",
                headers={"Content-Type": "application/json"}), timeout=10)
        self.assertEqual(ctx.exception.code, 403)
        # Host 非 loopback → 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(urllib.request.Request(
                self.base + "/api/health", headers={"Host": "evil.example"}), timeout=10)
        self.assertEqual(ctx.exception.code, 403)

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


# ---------------------------------------------------------------------------
# 游戏客户端目录（v1.9，gamepath）
# ---------------------------------------------------------------------------
def make_game_dir(root: Path, *, exe: bool = True, data: bool = True,
                  stc: bool = True) -> Path:
    """构造假的少前客户端目录树。"""
    root.mkdir(parents=True, exist_ok=True)
    if exe:
        (root / "GrilsFrontLine.exe").write_bytes(b"fake-exe")
    if data:
        res_dir = root / "GrilsFrontLine_Data" / "StreamingAssets" / "Res" / "Pc"
        res_dir.mkdir(parents=True, exist_ok=True)
        if stc:
            stc_dir = res_dir / "stc"
            stc_dir.mkdir(parents=True, exist_ok=True)
            (stc_dir / "catchdata.dat").write_bytes(b"fake")
    return root


class GamePathUnitTest(unittest.TestCase):
    """gamepath.validate/apply/bootstrap/status/pick 的单元测试（不弹窗）。"""

    def setUp(self):
        from targetforge import gamepath as gamepath_module
        self.gamepath = gamepath_module
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.local_paths = self.tmp_path / "local_paths.json"
        patch = mock.patch.object(self.gamepath, "LOCAL_PATHS_FILE", self.local_paths)
        patch.start()
        self.addCleanup(patch.stop)
        env_patch = mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        clear_patch = mock.patch.object(self.gamepath, "clear_game_caches", lambda: [])
        clear_patch.start()
        self.addCleanup(clear_patch.stop)
        self.valid_dir = make_game_dir(self.tmp_path / "game")

    def test_validate_cases(self):
        self.assertEqual(self.gamepath.validate(""),
                         (False, ["missing_path"]))
        self.assertEqual(self.gamepath.validate(self.tmp_path / "nope"),
                         (False, ["missing_dir"]))
        empty = self.tmp_path / "empty"
        empty.mkdir()
        valid, missing = self.gamepath.validate(empty)
        self.assertFalse(valid)
        self.assertIn("missing_exe", missing)
        self.assertIn("missing_data", missing)
        exe_only = make_game_dir(self.tmp_path / "exe_only", data=False)
        self.assertEqual(self.gamepath.validate(exe_only),
                         (False, ["missing_data"]))
        no_stc = make_game_dir(self.tmp_path / "no_stc", stc=False)
        self.assertEqual(self.gamepath.validate(no_stc),
                         (False, ["missing_stc"]))
        # 大小写不敏感
        upper = make_game_dir(self.tmp_path / "upper")
        (upper / "GrilsFrontLine.exe").unlink()
        (upper / "GRILSFRONTLINE.EXE").write_bytes(b"x")
        self.assertEqual(self.gamepath.validate(upper), (True, []))
        self.assertEqual(self.gamepath.validate(self.valid_dir), (True, []))
        self.assertEqual(self.gamepath.missing_messages(["missing_exe"])[0],
                         "未找到 GrilsFrontLine.exe")
        self.assertIn("StreamingAssets", self.gamepath.describe_missing(["missing_stc"]))
        self.assertTrue(self.gamepath.find_exe(self.valid_dir))
        self.assertTrue(self.gamepath.find_stc_dir(self.valid_dir))

    def test_apply_writes_local_paths_env(self):
        result = self.gamepath.apply(self.valid_dir)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["saved"])
        self.assertEqual(result["path"], str(self.valid_dir.resolve()))
        data = json.loads(self.local_paths.read_text(encoding="utf-8"))
        self.assertEqual(data["gf1_game_root"], str(self.valid_dir.resolve()))
        import os as _os
        self.assertEqual(_os.environ.get("GF1_GAME_ROOT"), str(self.valid_dir.resolve()))
        # 校验失败不写文件
        bad = self.gamepath.apply(self.tmp_path / "nope")
        self.assertFalse(bad["ok"])
        self.assertIn("目录不存在", bad["error"])
        self.assertIn("missing_dir", bad["missing_codes"])
        # persist=False 也不写文件
        self.local_paths.unlink()
        result = self.gamepath.apply(self.valid_dir, persist=False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["saved"])
        self.assertFalse(self.local_paths.exists())

    def test_bootstrap_priority(self):
        valid = str(self.valid_dir)
        # settings 优先级最高
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""}):
            result = self.gamepath.bootstrap({"game_root": valid},
                                             auto_detect=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "settings")
        # settings 无效、env 为空 → 自动检测关闭时失败
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""}):
            result = self.gamepath.bootstrap({"game_root": str(self.tmp_path / "bad")},
                                             auto_detect=False)
        self.assertFalse(result["ok"])
        # settings 无效 → 落到 env
        env_valid = str(make_game_dir(self.tmp_path / "env_game"))
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": env_valid}):
            result = self.gamepath.bootstrap({"game_root": ""}, auto_detect=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "env")
        # env 无效 → local_paths
        local_valid = make_game_dir(self.tmp_path / "local_game")
        self.local_paths.write_text(json.dumps(
            {"gf1_game_root": str(local_valid)}), encoding="utf-8")
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": str(self.tmp_path / "bad")}):
            result = self.gamepath.bootstrap({"game_root": ""}, auto_detect=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "local_paths")
        # 都无效 → 自动检测（不保存）
        detected = make_game_dir(self.tmp_path / "detected_game")
        self.local_paths.unlink()
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""}):
            with mock.patch.object(self.gamepath, "detect_best",
                                   lambda: {"path": str(detected),
                                            "source": "process"}):
                result = self.gamepath.bootstrap({"game_root": ""},
                                                 auto_detect=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "detected")
        self.assertTrue(result["detected"])
        self.assertFalse(result["saved"])
        # 全部失败
        with mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""}):
            with mock.patch.object(self.gamepath, "detect_best", lambda: None):
                result = self.gamepath.bootstrap({"game_root": ""},
                                                 auto_detect=True)
        self.assertFalse(result["ok"])
        self.assertIn("未找到", result["error"])

    def test_status_and_quick_mode(self):
        valid = str(self.valid_dir)
        status = self.gamepath.status({"game_root": valid}, include_detected=False,
                                      include_process=False)
        self.assertTrue(status["configured"])
        self.assertTrue(status["valid"])
        self.assertFalse(status["needs_setup"])
        self.assertEqual(status["source"], "settings")
        missing = self.gamepath.status(
            {"game_root": str(self.tmp_path / "nope")},
            include_detected=False, include_process=False)
        self.assertFalse(missing["valid"])
        self.assertTrue(missing["needs_setup"])
        self.assertTrue(missing["missing"])
        self.assertIn("目录不存在", missing["missing"][0])
        empty = self.gamepath.status({}, include_detected=False, include_process=False)
        self.assertFalse(empty["configured"])
        self.assertFalse(empty["valid"])

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_pick_folder_cancel_timeout_and_success(self):
        from types import SimpleNamespace
        fake_ok = SimpleNamespace(stdout=b"C:\\Games\\GIRLS FRONTLINE\r\n")
        with mock.patch.object(self.gamepath.subprocess, "run", return_value=fake_ok):
            self.assertEqual(self.gamepath.pick_folder(timeout=1),
                             "C:\\Games\\GIRLS FRONTLINE")
        fake_empty = SimpleNamespace(stdout=b"")
        with mock.patch.object(self.gamepath.subprocess, "run", return_value=fake_empty):
            with self.assertRaises(self.gamepath.GamePathError) as ctx:
                self.gamepath.pick_folder(timeout=1)
            self.assertEqual(ctx.exception.message, "已取消")
        with mock.patch.object(self.gamepath.subprocess, "run",
                               side_effect=__import__("subprocess").TimeoutExpired(
                                   "powershell", 1)):
            with self.assertRaises(self.gamepath.GamePathError) as ctx:
                self.gamepath.pick_folder(timeout=1)
            self.assertEqual(ctx.exception.message, "选择目录超时")
        with mock.patch.object(self.gamepath.subprocess, "run",
                               side_effect=OSError("no desktop")):
            with self.assertRaises(self.gamepath.GamePathError) as ctx:
                self.gamepath.pick_folder(timeout=1)
            self.assertIn("无法打开", ctx.exception.message)


class GameRoutesTest(AppTestBase):
    """GET /api/game/status 与 POST /api/game/{detect,pick,confirm}。"""

    def setUp(self):
        super().setUp()
        from targetforge import gamepath as gamepath_module
        self.gamepath = gamepath_module
        self.game_dir = make_game_dir(self.tmp_path / "game")
        self.bad_dir = self.tmp_path / "bad_game"
        self.bad_dir.mkdir()
        self.local_paths = self.tmp_path / "local_paths.json"
        self.candidates = [
            {"path": str(self.game_dir), "source": "process", "valid": True,
             "missing": []},
            {"path": str(self.bad_dir), "source": "steam", "valid": False,
             "missing": ["missing_exe", "missing_data"]},
        ]
        extra = [
            mock.patch.object(app, "_gamepath_module", lambda: self.gamepath),
            mock.patch.object(self.gamepath, "LOCAL_PATHS_FILE", self.local_paths),
            mock.patch.object(self.gamepath, "detect",
                              lambda **kwargs: self.candidates),
            mock.patch.object(self.gamepath, "detect_best",
                              lambda: {"path": str(self.game_dir), "source": "process"}),
            mock.patch.object(self.gamepath, "running_game_root",
                              lambda: ("", "")),
            mock.patch.object(self.gamepath, "clear_game_caches", lambda: []),
        ]
        for patch in extra:
            patch.start()
            self.addCleanup(patch.stop)
        env_patch = mock.patch.dict("os.environ", {"GF1_GAME_ROOT": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
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
                                     headers={"Content-Type": "application/json",
                                              "X-TargetForge-Client": "1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def set_game_root(self, path: str) -> None:
        state = app.state_load()
        settings = state.get("settings") or {}
        settings["game_root"] = path
        settings["game_selected_at"] = "2026-11-07T00:00:00+08:00"
        state["settings"] = settings
        app.state_save(state)

    def test_game_status(self):
        status, payload = self.request("GET", "/api/game/status")
        self.assertEqual(status, 200)
        for key in ("configured", "path", "source", "exists", "valid", "missing",
                    "game_running", "process_path", "detected", "catalog_ready",
                    "needs_setup"):
            self.assertIn(key, payload)
        self.assertFalse(payload["valid"])
        self.assertTrue(payload["needs_setup"])
        self.assertEqual(payload["detected"]["path"], str(self.game_dir))
        # 设置里有有效目录后 status.valid=True
        self.set_game_root(str(self.game_dir))
        status, payload = self.request("GET", "/api/game/status")
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["valid"])
        self.assertFalse(payload["needs_setup"])
        self.assertEqual(payload["source"], "settings")
        # health 带轻量 game_setup 摘要
        status, health = self.request("GET", "/api/health")
        self.assertIn("game_setup", health)
        self.assertTrue(health["game_setup"]["valid"])

    def test_game_confirm_errors(self):
        status, payload = self.request("POST", "/api/game/confirm", {})
        self.assertEqual(status, 400)
        self.assertIn("缺少游戏目录路径", payload["error"])
        self.assertIn("missing", payload)
        # 目录不存在
        status, payload = self.request("POST", "/api/game/confirm",
                                       {"path": str(self.tmp_path / "nope")})
        self.assertEqual(status, 400)
        self.assertIn("目录不存在", payload["error"])
        self.assertIn("missing", payload)
        # 目录存在但没有 exe
        empty = self.tmp_path / "only_dir"
        empty.mkdir()
        status, payload = self.request("POST", "/api/game/confirm",
                                       {"path": str(empty)})
        self.assertEqual(status, 400)
        self.assertIn("GrilsFrontLine.exe", payload["error"])
        self.assertIn("missing", payload)
        # 有 exe 但没有 *_Data
        exe_only = make_game_dir(self.tmp_path / "exe_only", data=False)
        status, payload = self.request("POST", "/api/game/confirm",
                                       {"path": str(exe_only)})
        self.assertEqual(status, 400)
        self.assertIn("*_Data", payload["error"])
        # 有 *_Data 但没有 stc
        no_stc = make_game_dir(self.tmp_path / "no_stc", stc=False)
        status, payload = self.request("POST", "/api/game/confirm",
                                       {"path": str(no_stc)})
        self.assertEqual(status, 400)
        self.assertIn("StreamingAssets", payload["error"])
        self.assertIn("missing", payload)
        self.assertFalse(self.local_paths.exists())  # 失败不写 local_paths

    def test_game_confirm_success_and_settings(self):
        status, payload = self.request("POST", "/api/game/confirm",
                                       {"path": str(self.game_dir)})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["status"]["valid"])
        self.assertTrue(payload["status"]["configured"])
        self.assertTrue(self.local_paths.is_file())
        data = json.loads(self.local_paths.read_text(encoding="utf-8"))
        self.assertEqual(data["gf1_game_root"], str(self.game_dir.resolve()))
        settings = app.state_load()["settings"]
        self.assertEqual(settings["game_root"], str(self.game_dir.resolve()))
        self.assertTrue(settings["game_selected_at"])
        status, settings_resp = self.request("POST", "/api/settings",
                                             {"game_root": ""})
        self.assertIn("game_root", settings_resp)

    def test_game_detect_and_pick(self):
        status, payload = self.request("POST", "/api/game/detect", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["detected"]["path"], str(self.game_dir))
        self.assertGreaterEqual(len(payload["candidates"]), 1)
        # pick 取消 → 400「已取消」
        with mock.patch.object(self.gamepath, "pick_folder",
                               side_effect=self.gamepath.GamePathError(
                                   "已取消", hint="可重试", code="pick_cancelled")):
            status, payload = self.request("POST", "/api/game/pick", {})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "已取消")
        # pick 成功 → {path}
        with mock.patch.object(self.gamepath, "pick_folder",
                               return_value=str(self.game_dir)):
            status, payload = self.request("POST", "/api/game/pick", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["path"], str(self.game_dir))


if __name__ == "__main__":
    unittest.main()
