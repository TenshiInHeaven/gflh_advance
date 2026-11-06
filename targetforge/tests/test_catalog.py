"""catalog.py 数据层自检（真数据，本机 STC；不 mock）。

跑法（仓库根目录，系统 python）::

    python -m unittest targetforge.tests.test_catalog -v

覆盖任务验收点：
* 规模断言：可收藏队伍 13700 / codex 264 / 关卡 2345 / 灰域 12 区域 1288 节点 3352 队；
* 结构字段断言：chapters / chapter / stage / team / team_summary / species / search；
* 无技能字段断言：catalog.json 里不得出现 skill / trigger / buff / action 等键；
* 灰域区域数 + 区域队伍分页；
* ``spot`` 里有 mission_id 不在 mission 表（404101）→ 构建与查询都不崩；
* 等级缩放口径：660011 总血 359,580（实测锚点）；
* 缓存性能：load < 5s、build(force=False) 走缓存。
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from targetforge import catalog  # noqa: E402

#: 任务给的数据规模（允许 ±小误差的项用范围断言）
EXPECT_TEAMS = 13700
EXPECT_SPECIES = 264
EXPECT_STAGES = 2345
EXPECT_GRAY_STAGES = 1288
EXPECT_GRAY_TEAMS = 3352
EXPECT_GRAY_AREAS = 12
EXPECT_MISSIONS_IN_TABLE = 3986

GROUP_ORDER = ["main", "event", "rerun", "tutorial", "special",
               "simulation", "grayzone", "orphan"]

CHAPTER_KEYS = {"id", "category", "title", "subtitle", "stage_count", "team_count",
                "species_count", "difficulty_min", "difficulty_max", "tags"}
STAGE_LIST_KEYS = {"id", "title", "code", "difficulty", "recommend_level",
                   "team_count", "species_count", "tags", "order"}
TEAM_SUMMARY_KEYS = {"id", "power", "units", "hp_total", "faction", "tags", "species",
                     "members", "gray_zone", "orphan", "stage"}
TEAM_DETAIL_KEYS = {"id", "power", "units", "hp_total", "faction", "tags", "gray_zone",
                    "orphan", "params", "appearances", "species", "members"}
STAT_KEYS = {"maxlife", "pow", "hit", "dodge", "armor", "armor_piercing", "range",
             "speed", "shield", "def", "crit", "crit_dmg", "tenacity"}
SPECIES_ITEM_KEYS = {"codex_no", "name", "faction", "type", "capturable", "tags",
                     "category", "team_count", "gray_zone_team_count",
                     "orphan_team_count"}
#: 任何带这些子串的键都视为"技能/触发器信息"，不得出现在 catalog 里
FORBIDDEN_KEY_PARTS = ("skill", "trigger", "buff", "action_", "guninfo",
                       "passive", "normal_attack", "special_attack", "cd_frames")


def _walk_keys(node, path=""):
    """递归产出 (path, key)。"""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from _walk_keys(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_keys(value, f"{path}[{index}]")


class CatalogDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # force=False：catalog.json 比数据源新时走缓存（0.x s），否则自动重建
        cls.meta = catalog.build(force=False)
        cls.catalog = catalog.load()
        cls.chapters_payload = cls.catalog.chapters()

    # -- 规模 ---------------------------------------------------------
    def test_counts(self):
        counts = self.catalog.counts
        self.assertEqual(counts["teams"], EXPECT_TEAMS)
        self.assertEqual(counts["species"], EXPECT_SPECIES)
        self.assertEqual(counts["stages"], EXPECT_STAGES)
        self.assertEqual(counts["missions"], EXPECT_MISSIONS_IN_TABLE)
        # 章节数：main14 + event61 + rerun10 + tutorial6 + special16 + sim1 + gray1 + orphan1
        self.assertEqual(counts["chapters"], 110)
        self.assertEqual(self.catalog.built_at, self.meta["built_at"])

    def test_meta_contract(self):
        for key in ("built_at", "counts", "sources", "elapsed_s"):
            self.assertIn(key, self.meta)
        self.assertLess(float(self.meta["elapsed_s"]), 90.0)
        self.assertIn("stc_version", self.meta["sources"])
        tables = self.meta["sources"]["tables"]
        self.assertEqual(tables["enemy_team"], 16944)
        self.assertEqual(tables["enemy_in_team"], 136198)

    def test_chapter_groups(self):
        groups = self.chapters_payload["groups"]
        self.assertEqual([group["id"] for group in groups], GROUP_ORDER)
        self.assertEqual([group["title"] for group in groups],
                         ["主线", "活动", "往期复刻", "教学", "特殊作战",
                          "模拟作战", "灰域探查", "无固定关卡"])
        expected = {"main": 14, "event": 61, "rerun": 10, "tutorial": 6,
                    "special": 16, "simulation": 1, "grayzone": 1, "orphan": 1}
        # 每组的"有关卡的章节"关卡数（main 140 = 143 − 1104/1105/1106 移到模拟作战）
        expected_stages = {"main": 140, "event": 743, "rerun": 40, "tutorial": 40,
                           "special": 85, "simulation": 9, "grayzone": 1288, "orphan": 0}
        total = 0
        for group in groups:
            self.assertEqual(len(group["chapters"]), expected[group["id"]],
                             f"组 {group['id']} 章节数变了，检查归类规则")
            total += len(group["chapters"])
            self.assertEqual(sum(chapter["stage_count"] for chapter in group["chapters"]),
                             expected_stages[group["id"]],
                             f"组 {group['id']} 关卡数变了")
        self.assertEqual(total, self.catalog.counts["chapters"])
        # 章节 id 全局唯一
        ids = [chapter["id"] for group in groups for chapter in group["chapters"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_chapter_payload_fields(self):
        for group in self.chapters_payload["groups"]:
            for chapter in group["chapters"]:
                self.assertEqual(set(chapter), CHAPTER_KEYS | ({"areas"} if
                                 chapter["category"] == "grayzone" else set()))
                self.assertEqual(chapter["category"], group["id"])
                self.assertIsInstance(chapter["tags"], list)
                self.assertIsInstance(chapter["subtitle"], str)

    def test_stage_counts_add_up(self):
        listed = 0
        for group in self.chapters_payload["groups"]:
            for chapter in group["chapters"]:
                detail = self.catalog.chapter(chapter["id"])
                self.assertIsNotNone(detail)
                if chapter["category"] == "grayzone":
                    self.assertEqual(detail["stages"], [])
                    self.assertEqual(len(detail["areas"]), EXPECT_GRAY_AREAS)
                    continue
                if chapter["category"] == "orphan":
                    self.assertEqual(detail["stages"], [])
                    self.assertEqual(len(detail["teams"]), chapter["team_count"])
                    continue
                self.assertEqual(len(detail["stages"]), chapter["stage_count"])
                listed += len(detail["stages"])
                for stage in detail["stages"]:
                    self.assertEqual(set(stage), STAGE_LIST_KEYS)
        grayzone_chapter = self.catalog.chapter("grayzone")["chapter"]
        self.assertEqual(grayzone_chapter["stage_count"], EXPECT_GRAY_STAGES)
        self.assertEqual(listed + EXPECT_GRAY_STAGES, EXPECT_STAGES)
        self.assertEqual(self.catalog.chapter("no-such-chapter"), None)

    def test_main_chapter_one(self):
        detail = self.catalog.chapter("main-1")
        self.assertIsNotNone(detail)
        chapter = detail["chapter"]
        self.assertEqual(chapter["title"], "第1章")
        self.assertEqual(chapter["category"], "main")
        self.assertEqual(chapter["tags"], ["主线"])
        # 10 关 = 1-1..1-6（普通）+ 1-1E..1-4E（紧急）；特训/模拟作战不混进主线
        self.assertEqual(chapter["stage_count"], 10)
        self.assertEqual(chapter["difficulty_min"], 200)
        self.assertEqual(chapter["difficulty_max"], 1400)
        self.assertEqual([stage["code"] for stage in detail["stages"]],
                         ["1-1", "1-2", "1-3", "1-4", "1-5", "1-6",
                          "1-1E", "1-2E", "1-3E", "1-4E"])
        self.assertEqual({stage["tags"][0] for stage in detail["stages"]},
                         {"普通", "紧急"})
        stage = next(item for item in detail["stages"] if item["id"] == 5)
        self.assertEqual(stage["title"], "演习训练")
        self.assertEqual(stage["code"], "1-1")
        self.assertEqual(stage["difficulty"], 200)
        self.assertEqual(stage["recommend_level"], 3)
        self.assertEqual(stage["tags"], ["普通"])
        self.assertEqual(self.catalog.chapter("main-0")["chapter"]["title"], "序章")

    def test_simulation_chapter(self):
        """模拟作战/靶场：Moni 图 + 1101~1106（特种特训 map 是 OPS5_Y 也要归进来）。"""
        detail = self.catalog.chapter("simulation")
        self.assertIsNotNone(detail)
        chapter = detail["chapter"]
        self.assertEqual(chapter["category"], "simulation")
        self.assertEqual(chapter["title"], "模拟作战·靶场")
        self.assertEqual(chapter["tags"], ["模拟作战"])
        self.assertEqual(chapter["stage_count"], 9)
        stage_ids = {stage["id"] for stage in detail["stages"]}
        for mission_id in (1101, 1102, 1103, 1104, 1105, 1106, 1201, 1202, 1203):
            self.assertIn(mission_id, stage_ids)
        for stage in detail["stages"]:
            self.assertEqual(stage["tags"], ["模拟作战"])
        self.assertEqual(self.catalog.stage(1104)["stage"]["chapter_id"], "simulation")
        self.assertEqual(self.catalog.stage(1105)["stage"]["chapter_id"], "simulation")
        self.assertEqual(self.catalog.stage(1106)["stage"]["chapter_id"], "simulation")

    # -- 灰域 ---------------------------------------------------------
    def test_grayzone_areas(self):
        areas = self.catalog.grayzone_areas()
        self.assertEqual(len(areas), EXPECT_GRAY_AREAS)
        self.assertEqual(sum(area["stage_count"] for area in areas), EXPECT_GRAY_STAGES)
        names = [area["id"] for area in areas]
        for expected in ("共生净土", "晶团挖掘点", "旅团商道", "放射区",
                         "人形复制工厂", "废弃居民区", "秘密通道", "交易地",
                         "最终贮藏地", "图腾圣所", "地坛遗迹", "装甲突击"):
            self.assertIn(expected, names)
        by_id = {area["id"]: area for area in areas}
        self.assertEqual(by_id["共生净土"]["stage_count"], 240)
        self.assertEqual(by_id["共生净土"]["team_count"], 1104)
        self.assertEqual(by_id["晶团挖掘点"]["team_count"], 872)
        for area in areas:
            self.assertEqual(set(area), {"id", "title", "stage_count",
                                         "team_count", "species_count"})

    def test_grayzone_chapter(self):
        detail = self.catalog.chapter("grayzone")
        chapter = detail["chapter"]
        self.assertEqual(chapter["stage_count"], EXPECT_GRAY_STAGES)
        self.assertEqual(chapter["team_count"], EXPECT_GRAY_TEAMS)
        self.assertEqual(chapter["subtitle"], "12 个区域 · 1288 个节点")
        self.assertEqual(chapter["tags"], ["打灰"])
        # 灰域不产关卡列表
        self.assertEqual(detail["stages"], [])
        self.assertEqual(len(detail["areas"]), EXPECT_GRAY_AREAS)

    def test_grayzone_teams_pagination(self):
        page = self.catalog.grayzone_teams("共生净土", 0, 10)
        self.assertEqual(page["total"], 1104)
        self.assertEqual(len(page["items"]), 10)
        second = self.catalog.grayzone_teams("共生净土", 10, 10)
        first_ids = {item["id"] for item in page["items"]}
        second_ids = {item["id"] for item in second["items"]}
        self.assertFalse(first_ids & second_ids)
        everything = self.catalog.grayzone_teams("", 0, 1)
        self.assertEqual(everything["total"], EXPECT_GRAY_TEAMS)
        empty_area = self.catalog.grayzone_teams("不存在的区域", 0, 10)
        self.assertEqual(empty_area["total"], 0)
        # q 支持队伍 id / 怪种名 / 阵营 / tag
        some_id = page["items"][0]["id"]
        matched = self.catalog.grayzone_teams("共生净土", 0, 5, q=str(some_id))
        self.assertEqual(matched["total"], 1)
        self.assertIsInstance(page["items"][0], dict)
        # 两种调用签名都要兼容：app.py 用 area=，contract 写的是 area_id=
        by_area = self.catalog.grayzone_teams(area="共生净土", offset=0, limit=2)
        by_area_id = self.catalog.grayzone_teams(area_id="共生净土", offset=0, limit=2)
        self.assertEqual(by_area["total"], 1104)
        self.assertEqual(by_area["area"], "共生净土")
        self.assertEqual(by_area["total"], by_area_id["total"])

    # -- 关卡 ---------------------------------------------------------
    def test_stage_detail(self):
        detail = self.catalog.stage(5)
        self.assertIsNotNone(detail)
        self.assertEqual(set(detail), {"stage", "teams"})
        stage = detail["stage"]
        self.assertEqual(stage["id"], 5)
        self.assertEqual(stage["title"], "演习训练")
        self.assertEqual(stage["chapter_id"], "main-1")
        self.assertEqual(stage["chapter_title"], "第1章")
        for team in detail["teams"]:
            self.assertEqual(set(team), TEAM_SUMMARY_KEYS)
        self.assertEqual(self.catalog.stage(999999999), None)

    def test_missing_mission_in_spot_does_not_crash(self):
        """spot 里有 mission_id 不在 mission 表（404101）→ 归特殊作战，查询不崩。"""
        detail = self.catalog.stage(404101)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["stage"]["chapter_id"], "special-unknown")
        self.assertEqual(detail["stage"]["team_count"], 4)
        self.assertEqual([team["id"] for team in detail["teams"]],
                         [9410101, 9410103, 9410106, 9410107])
        # 这 4 支队伍本身仍然可查（其中 9410106 只出现在这个缺失 mission 上）
        self.assertIsNotNone(self.catalog.team(9410106))
        unknown_chapter = self.catalog.chapter("special-unknown")
        self.assertEqual(unknown_chapter["chapter"]["stage_count"], 1)

    # -- 队伍 ---------------------------------------------------------
    def test_team_detail_660011_scaled_hp(self):
        team = self.catalog.team(660011)
        self.assertIsNotNone(team)
        self.assertEqual(set(team), TEAM_DETAIL_KEYS)
        # 实测锚点：660011 总血 359,580（等级缩放口径）
        self.assertAlmostEqual(team["hp_total"], 359580, delta=3)
        self.assertEqual(team["units"], 10)
        self.assertEqual(team["power"], -100085)
        self.assertFalse(team["gray_zone"])
        self.assertEqual(team["params"]["mission_count"], 1)
        self.assertIn("params", team)
        self.assertIn("note", team["params"])
        for member in team["members"]:
            self.assertEqual(set(member["stats"]), STAT_KEYS)
            self.assertEqual(set(member["base_stats"]), STAT_KEYS)
            for key in ("type_id", "code", "name", "codex_no", "level", "number",
                        "count", "def_percent", "batch", "x", "y"):
                self.assertIn(key, member)
        # 等级 150 > 锚点 100：缩放过 maxlife 应大于 base
        member = team["members"][0]
        self.assertEqual(member["count"], 3)  # 同 type 3 格
        self.assertGreater(member["stats"]["maxlife"], member["base_stats"]["maxlife"])
        # def=99999 是哨兵值，不缩放
        self.assertEqual(member["base_stats"]["def"], 99999)
        self.assertEqual(member["stats"]["def"], 99999)

    def test_team_detail_fields(self):
        team = self.catalog.team(6549244)
        self.assertIsNotNone(team)
        self.assertEqual(team["power"], 113600)
        self.assertEqual(team["units"], 9)
        self.assertEqual(team["faction"], "军方")
        # 按格展开：members 数 = units；count = 同 type 在队伍里的格数
        self.assertEqual(len(team["members"]), team["units"])
        type_counts: dict[int, int] = {}
        for member in team["members"]:
            type_counts[member["type_id"]] = type_counts.get(member["type_id"], 0) + 1
        for member in team["members"]:
            self.assertEqual(member["count"], type_counts[member["type_id"]])
        self.assertEqual(self.catalog.team(123456789), None)
        # 负数队伍 id 也存在（无固定关卡的旧队伍）
        self.assertIsNotNone(self.catalog.team(-2))
        for appearance in team["appearances"]:
            for key in ("mission_id", "chapter_id", "chapter_title", "stage_title",
                        "code", "difficulty", "gray_zone"):
                self.assertIn(key, appearance)
            self.assertLessEqual(len(team["appearances"]), 24)

    def test_team_summaries(self):
        summaries = self.catalog.team_summaries([6549244, 660011, 123456789])
        self.assertEqual([item["id"] for item in summaries], [6549244, 660011])
        for summary in summaries:
            self.assertEqual(set(summary), TEAM_SUMMARY_KEYS)
            self.assertLessEqual(len(summary["species"]), 8)
            self.assertLessEqual(len(summary["members"]), 6)
            if summary["stage"] is not None:
                self.assertEqual(set(summary["stage"]),
                                 {"chapter_id", "title", "stage_title", "code"})
            for member in summary["members"]:
                self.assertEqual(set(member), {"code", "name", "number", "count"})
        self.assertEqual(self.catalog.team_summaries([]), [])

    # -- 怪种 ---------------------------------------------------------
    def test_species_list(self):
        page = self.catalog.species_list(limit=10)
        self.assertEqual(page["total"], EXPECT_SPECIES)
        self.assertEqual(len(page["items"]), 10)
        item = page["items"][0]
        self.assertEqual(set(item), SPECIES_ITEM_KEYS)
        self.assertIn(item["category"], ("normal", "grayzone", "orphan"))
        by_category = {category: self.catalog.species_list(category=category)["total"]
                       for category in ("normal", "grayzone", "orphan")}
        self.assertEqual(sum(by_category.values()), EXPECT_SPECIES)
        all_page = self.catalog.species_list(category="all")
        self.assertEqual(all_page["total"], EXPECT_SPECIES)
        self.assertGreater(self.catalog.species_list(faction="铁血")["total"], 0)
        self.assertGreater(self.catalog.species_list(q="稻草人")["total"], 0)
        # 分页
        second = self.catalog.species_list(offset=10, limit=10)
        self.assertNotEqual(page["items"][0]["codex_no"], second["items"][0]["codex_no"])

    def test_species_detail(self):
        detail = self.catalog.species(5)
        self.assertIsNotNone(detail)
        species = detail["species"]
        self.assertEqual(species["codex_no"], 5)
        self.assertEqual(species["name"], "稻草人")
        self.assertEqual(species["category"], "normal")
        self.assertEqual(species["tags"], ["契约捕获"])
        self.assertGreater(species["team_count"], 0)
        self.assertEqual(len(detail["teams"]), species["team_count"])
        self.assertEqual(detail["teams_total"], species["team_count"])
        for team in detail["teams"]:
            self.assertEqual(set(team), TEAM_SUMMARY_KEYS)
        self.assertIsNone(self.catalog.species(99999999))
        # 灰域 BOSS 变体 codex 没有 illustration 行，名称走回退
        gray_species = self.catalog.species(195)
        self.assertIsNotNone(gray_species)
        self.assertEqual(gray_species["species"]["category"], "grayzone")
        self.assertIn("灰域Boss", gray_species["species"]["name"])

    # -- 搜索 / JSON / 缓存 --------------------------------------------
    def test_search(self):
        result = self.catalog.search("稻草人")
        self.assertEqual(set(result), {"teams", "stages", "species"})
        self.assertTrue(result["teams"])
        self.assertTrue(result["species"])
        result = self.catalog.search("演习训练")
        self.assertTrue(any(stage["id"] == 5 for stage in result["stages"]))
        for stage in result["stages"]:
            self.assertEqual(set(stage), {"id", "title", "code", "chapter_title"})
        self.assertTrue(self.catalog.search("660011")["teams"])
        empty = self.catalog.search("")
        self.assertEqual(empty, {"teams": [], "stages": [], "species": []})

    def test_catalog_json_has_no_skill_fields(self):
        payload = json.loads(catalog.CATALOG_FILE.read_text(encoding="utf-8"))
        offenders = []
        for path, key in _walk_keys(payload):
            lowered = key.lower()
            if any(part in lowered for part in FORBIDDEN_KEY_PARTS):
                offenders.append(f"{path}/{key}")
        self.assertEqual(offenders[:10], [], "catalog 里出现了技能/触发器字段")

    def test_catalog_json_strict_serializable(self):
        payload = json.loads(catalog.CATALOG_FILE.read_text(encoding="utf-8"))
        # allow_nan=False：不允许 NaN / Infinity（前端 JSON.parse 会崩）
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        self.assertGreater(len(text), 1_000_000)

    def test_load_is_fast(self):
        started = time.time()
        fresh = catalog.reload()
        elapsed = time.time() - started
        self.assertLess(elapsed, 5.0, f"catalog load 太慢：{elapsed:.2f}s")
        self.assertEqual(fresh.built_at, self.catalog.built_at)
        self.assertIsInstance(fresh.counts, dict)

    def test_build_cache_hit(self):
        started = time.time()
        meta = catalog.build(force=False)
        elapsed = time.time() - started
        self.assertEqual(meta["counts"]["teams"], EXPECT_TEAMS)
        self.assertLess(elapsed, 10.0, f"build(force=False) 未命中缓存：{elapsed:.2f}s")


class AppIntegrationTest(unittest.TestCase):
    """确认 Lead 的 app.py 调用签名与 catalog 实现一致（不起 HTTP 服务、不占 8765）。"""

    @classmethod
    def setUpClass(cls) -> None:
        from targetforge import app

        cls.app = app
        cls.catalog = catalog.load()

    def test_app_catalog_routes(self):
        app = self.app
        # app.get_catalog() 只在 _CATALOG_STATE=ready 时返回；直接标记 ready（不启服务）
        app._CATALOG_STATE.update({"state": "ready",
                                   "built_at": self.catalog.built_at,
                                   "counts": self.catalog.counts})
        cat = app.get_catalog()
        self.assertIs(cat, self.catalog)
        self.assertTrue(cat.chapters()["groups"])
        self.assertEqual(app.api_meta()["counts"]["teams"], EXPECT_TEAMS)
        self.assertEqual(app.api_chapter("grayzone")["chapter"]["id"], "grayzone")
        self.assertEqual(app.api_stage(5)["stage"]["id"], 5)
        self.assertEqual(app.api_team(660011)["id"], 660011)
        self.assertEqual(app.api_species_detail(5)["species"]["codex_no"], 5)
        # app.py 的实际调用方式：grayzone_teams(area=..., offset=..., limit=..., q=...)
        grayzone = cat.grayzone_teams(area="共生净土", offset=0, limit=2, q="")
        self.assertEqual(grayzone["total"], 1104)
        # 路由返回的 payload 必须能被 app 的 JSON 序列化器写出去
        body = json.dumps(app.api_chapter("main-1"), ensure_ascii=False, default=app._jsonable)
        self.assertIn("第1章", body)


if __name__ == "__main__":
    unittest.main()
