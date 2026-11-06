"""catalog.py 数据层自检（v1.2，真数据，本机 STC；不 mock）。

跑法（仓库根目录，系统 python）::

    python -m unittest targetforge.tests.test_catalog -v

覆盖任务验收点（task-7）：
* 章节 7 组（main/event/score/tutorial/simulation/grayzone/orphan），活动/往期复刻/
  特殊作战合并进 event，积分关卡独立成组，自画像可搜；
* 灰域 14 个区域（含 庇护所旧址 / 坍缩狭缝）；
* 物种非互斥 flag：normal/grayzone/orphan 过滤数 = 244/66/211（±2），灰域过滤含
  法官（灰域Boss）变体；
* 效能 power / power_known + power_min/power_max/power_known/sort 筛选排序；
* 队伍/物种列表分页；species() 无参仍返回全量 teams（app.py 兼容）；
* 小怪图标：icon 字段（species / team_summary.species / detail members）+ 覆盖率；
* 规模/结构/无技能字段/spot 缺失 mission（404101）/JSON 严格可序列化/性能。
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
from targetforge.datapaths import CATALOG_FILE as DATA_CATALOG_FILE  # noqa: E402
from targetforge.datapaths import ICON_DIR as DATA_ICON_DIR  # noqa: E402

EXPECT_TEAMS = 13700
EXPECT_SPECIES = 264
EXPECT_STAGES = 2345
EXPECT_MISSIONS_IN_TABLE = 3986
EXPECT_CHAPTERS = 112

GROUP_ORDER = ["main", "event", "score", "tutorial", "simulation", "grayzone", "orphan"]
GROUP_TITLES = ["主线", "活动", "积分关卡", "教学", "模拟作战", "灰域探查", "无固定关卡"]
EXPECT_GROUP_CHAPTERS = {"main": 14, "event": 72, "score": 17, "tutorial": 6,
                         "simulation": 1, "grayzone": 1, "orphan": 1}
EXPECT_GROUP_STAGES = {"main": 140, "event": 835, "score": 33, "tutorial": 40,
                       "simulation": 9, "grayzone": 1288, "orphan": 0}

GRAY_AREAS = ["共生净土", "晶团挖掘点", "旅团商道", "放射区", "人形复制工厂",
              "废弃居民区", "秘密通道", "图腾圣所", "装甲突击", "交易地",
              "地坛遗迹", "最终贮藏地", "庇护所旧址", "坍缩狭缝"]

CHAPTER_KEYS = {"id", "category", "kind", "title", "subtitle", "stage_count",
                "team_count", "species_count", "difficulty_min", "difficulty_max",
                "tags"}
STAGE_LIST_KEYS = {"id", "title", "code", "difficulty", "recommend_level",
                   "team_count", "species_count", "tags", "order"}
TEAM_SUMMARY_KEYS = {"id", "power", "power_known", "units", "hp_total", "faction",
                     "tags", "species", "members", "gray_zone", "orphan", "stage"}
TEAM_DETAIL_KEYS = {"id", "power", "power_known", "units", "hp_total", "faction",
                    "tags", "gray_zone", "orphan", "params", "appearances",
                    "species", "members"}
STAT_KEYS = {"maxlife", "pow", "hit", "dodge", "armor", "armor_piercing", "range",
             "speed", "shield", "def", "crit", "crit_dmg", "tenacity"}
SPECIES_ITEM_KEYS = {"codex_no", "name", "faction", "type", "capturable", "tags",
                     "category", "has_normal", "has_grayzone", "has_orphan",
                     "team_count", "normal_team_count", "gray_zone_team_count",
                     "orphan_team_count", "icon"}
FORBIDDEN_KEY_PARTS = ("skill", "trigger", "buff", "action_", "guninfo",
                       "passive", "normal_attack", "special_attack", "cd_frames")


def _walk_keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from _walk_keys(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_keys(value, f"{path}[{index}]")


def _icon_available() -> bool:
    try:
        return any(DATA_ICON_DIR.glob("*.png"))
    except OSError:
        return False


class CatalogDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.meta = catalog.build(force=False)
        cls.catalog = catalog.load()
        cls.chapters_payload = cls.catalog.chapters()
        cls.groups = {group["id"]: group for group in cls.chapters_payload["groups"]}

    # -- 规模 ---------------------------------------------------------
    def test_counts(self):
        counts = self.catalog.counts
        self.assertEqual(counts["teams"], EXPECT_TEAMS)
        self.assertEqual(counts["species"], EXPECT_SPECIES)
        self.assertEqual(counts["stages"], EXPECT_STAGES)
        self.assertEqual(counts["missions"], EXPECT_MISSIONS_IN_TABLE)
        self.assertEqual(counts["chapters"], EXPECT_CHAPTERS)
        self.assertEqual(self.catalog.built_at, self.meta["built_at"])

    def test_meta_contract(self):
        for key in ("built_at", "counts", "sources", "elapsed_s"):
            self.assertIn(key, self.meta)
        self.assertLess(float(self.meta["elapsed_s"]), 90.0)
        tables = self.meta["sources"]["tables"]
        self.assertEqual(tables["enemy_team"], 16944)
        self.assertEqual(tables["enemy_in_team"], 136198)
        # 图标覆盖率报告（sources.icons）
        icons = self.meta["sources"]["icons"]
        for key in ("files", "codes_needed", "codes_covered",
                    "species_total", "species_covered"):
            self.assertIn(key, icons)
        self.assertEqual(icons["codes_needed"], 282)

    # -- 章节 7 组 ----------------------------------------------------
    def test_chapter_groups(self):
        groups = self.chapters_payload["groups"]
        self.assertEqual([group["id"] for group in groups], GROUP_ORDER)
        self.assertEqual([group["title"] for group in groups], GROUP_TITLES)
        for group in groups:
            self.assertEqual(len(group["chapters"]), EXPECT_GROUP_CHAPTERS[group["id"]],
                             f"组 {group['id']} 章节数变了")
            self.assertEqual(sum(chapter["stage_count"] for chapter in group["chapters"]),
                             EXPECT_GROUP_STAGES[group["id"]],
                             f"组 {group['id']} 关卡数变了")
        # 总章节/关卡对得上（灰域章节的 1288 个节点不在列表里单独展开）
        ids = [chapter["id"] for group in groups for chapter in group["chapters"]]
        self.assertEqual(len(ids), EXPECT_CHAPTERS)
        self.assertEqual(len(ids), len(set(ids)))
        listed_stages = sum(chapter["stage_count"] for group in groups
                            if group["id"] != "grayzone"
                            for chapter in group["chapters"])
        self.assertEqual(listed_stages + 1288, EXPECT_STAGES)

    def test_chapter_payload_fields(self):
        for group in self.chapters_payload["groups"]:
            for chapter in group["chapters"]:
                expected = CHAPTER_KEYS | ({"areas"} if chapter["category"] == "grayzone"
                                           else set())
                self.assertEqual(set(chapter), expected)
                self.assertEqual(chapter["category"], group["id"])
                self.assertIsInstance(chapter["tags"], list)

    def test_no_rerun_special_groups(self):
        ids = [group["id"] for group in self.chapters_payload["groups"]]
        self.assertNotIn("rerun", ids)
        self.assertNotIn("special", ids)
        # 往期复刻 / 特殊作战 并入 event，用 subtitle/tags 区分
        rerun = [chapter for chapter in self.groups["event"]["chapters"]
                 if chapter["kind"] == "rerun"]
        special = [chapter for chapter in self.groups["event"]["chapters"]
                   if chapter["kind"] == "special"]
        self.assertEqual(len(rerun), 10)
        self.assertEqual(len(special), 15)
        self.assertTrue(all("往期复刻" in chapter["subtitle"] for chapter in rerun))
        self.assertTrue(all("特殊作战" in chapter["subtitle"] for chapter in special))
        self.assertTrue(all("往期复刻" in chapter["tags"] for chapter in rerun))
        self.assertTrue(all("特殊作战" in chapter["tags"] for chapter in special))

    def test_main_and_simulation(self):
        detail = self.catalog.chapter("main-1")
        self.assertIsNotNone(detail)
        chapter = detail["chapter"]
        self.assertEqual(chapter["title"], "第1章")
        self.assertEqual(chapter["stage_count"], 10)
        self.assertEqual([stage["code"] for stage in detail["stages"]],
                         ["1-1", "1-2", "1-3", "1-4", "1-5", "1-6",
                          "1-1E", "1-2E", "1-3E", "1-4E"])
        simulation = self.catalog.chapter("simulation")
        self.assertEqual(simulation["chapter"]["stage_count"], 9)
        stage_ids = {stage["id"] for stage in simulation["stages"]}
        for mission_id in (1101, 1102, 1103, 1104, 1105, 1106, 1201, 1202, 1203):
            self.assertIn(mission_id, stage_ids)
        self.assertEqual(self.catalog.stage(1104)["stage"]["chapter_id"], "simulation")

    def test_score_chapters(self):
        score = self.groups["score"]
        self.assertEqual(len(score["chapters"]), 17)
        for chapter in score["chapters"]:
            self.assertEqual(chapter["category"], "score")
            self.assertEqual(chapter["tags"], ["积分关卡"])
            self.assertIn("积分关卡", chapter["subtitle"])
        # 自画像：标题=自画像，parent 慢休克（-40403）
        portrait = next((chapter for chapter in score["chapters"]
                         if chapter["title"] == "自画像"), None)
        self.assertIsNotNone(portrait, [c["title"] for c in score["chapters"]])
        self.assertEqual(portrait["stage_count"], 2)
        self.assertIn("慢休克", portrait["subtitle"])
        self.assertIn("积分关卡", portrait["subtitle"])
        # 其它已确认命中的积分关卡
        titles = [chapter["title"] for chapter in score["chapters"]]
        for title in ("终焉花海+", "谜境守卫+", "贝蒂数", "逃亡圣咏",
                      "从潘洛斯阶梯跃下", "铁雨礼赞"):
            self.assertIn(title, titles)
        # 搜索：自画像 / 积分关卡 / 慢休克 都能命中
        for query in ("自画像", "积分关卡", "慢休克"):
            result = self.catalog.search(query, limit=10)
            self.assertTrue(result["stages"], f"搜索 {query!r} 没有结果")
        result = self.catalog.search("自画像")
        self.assertTrue(any(stage["chapter_title"] == "自画像" for stage in result["stages"]))

    # -- 灰域 14 区域 -------------------------------------------------
    def test_grayzone_areas(self):
        areas = self.catalog.grayzone_areas()
        self.assertEqual(len(areas), 14)
        names = [area["id"] for area in areas]
        self.assertEqual(set(names), set(GRAY_AREAS))
        by_id = {area["id"]: area for area in areas}
        self.assertEqual(by_id["共生净土"]["stage_count"], 240)
        self.assertEqual(by_id["共生净土"]["team_count"], 1104)
        self.assertEqual(by_id["晶团挖掘点"]["team_count"], 872)
        self.assertEqual(by_id["旅团商道"]["stage_count"], 210)
        self.assertEqual(by_id["放射区"]["team_count"], 315)
        # 新增的两个区域暂时没有可收藏队伍，但必须存在
        self.assertEqual(by_id["庇护所旧址"]["stage_count"], 0)
        self.assertEqual(by_id["坍缩狭缝"]["stage_count"], 0)
        self.assertEqual(sum(area["stage_count"] for area in areas), 1288)
        for area in areas:
            self.assertEqual(set(area), {"id", "title", "stage_count",
                                         "team_count", "species_count"})

    def test_grayzone_chapter(self):
        detail = self.catalog.chapter("grayzone")
        chapter = detail["chapter"]
        self.assertEqual(chapter["stage_count"], 1288)
        self.assertEqual(chapter["team_count"], 3352)
        self.assertEqual(chapter["subtitle"], "14 个区域 · 1288 个节点")
        self.assertEqual(chapter["tags"], ["打灰"])
        self.assertEqual(detail["stages"], [])
        self.assertEqual(len(detail["areas"]), 14)

    def test_grayzone_teams_pagination_and_filters(self):
        page = self.catalog.grayzone_teams("共生净土", 0, 10)
        self.assertEqual(page["total"], 1104)
        self.assertEqual(len(page["items"]), 10)
        second = self.catalog.grayzone_teams("共生净土", 10, 10)
        self.assertFalse({item["id"] for item in page["items"]}
                         & {item["id"] for item in second["items"]})
        everything = self.catalog.grayzone_teams("", 0, 1)
        self.assertEqual(everything["total"], 3352)
        self.assertEqual(self.catalog.grayzone_teams("不存在的区域", 0, 10)["total"], 0)
        # 两种签名都兼容（app.py 用 area=，contract 写 area_id=）
        self.assertEqual(self.catalog.grayzone_teams(area="共生净土", offset=0, limit=2)["total"],
                         1104)
        self.assertEqual(self.catalog.grayzone_teams(area_id="共生净土", offset=0,
                                                     limit=2)["total"], 1104)
        # 效能筛选/排序（灰域普通节点基本 effect_ext=0 → power_known=False）
        known = self.catalog.grayzone_teams("", 0, 5, power_known=True)
        unknown = self.catalog.grayzone_teams("", 0, 5, power_known=False)
        self.assertEqual(known["total"] + unknown["total"], 3352)
        self.assertTrue(all(item["power_known"] for item in known["items"]))
        self.assertTrue(all(not item["power_known"] for item in unknown["items"]))
        desc = self.catalog.grayzone_teams("", 0, 10, sort="power_desc")
        powers = [item["power"] for item in desc["items"]]
        self.assertEqual(powers, sorted(powers, reverse=True))
        asc = self.catalog.grayzone_teams("", 0, 10, sort="power_asc")
        self.assertEqual([item["power"] for item in asc["items"]],
                         sorted(item["power"] for item in asc["items"]))
        hp_desc = self.catalog.grayzone_teams("", 0, 10, sort="hp_desc")
        hp = [item["hp_total"] for item in hp_desc["items"]]
        self.assertEqual(hp, sorted(hp, reverse=True))
        units_desc = self.catalog.grayzone_teams("", 0, 10, sort="units_desc")
        self.assertEqual([item["units"] for item in units_desc["items"]],
                         sorted((item["units"] for item in units_desc["items"]),
                                reverse=True))
        ranged = self.catalog.grayzone_teams("", 0, 5, power_min=100000,
                                             power_max=200000)
        self.assertTrue(ranged["total"] > 0)
        self.assertTrue(all(100000 <= item["power"] <= 200000
                            for item in ranged["items"]))

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
        detail = self.catalog.stage(404101)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["stage"]["chapter_id"], "event-unknown")
        self.assertEqual(detail["stage"]["team_count"], 4)
        self.assertEqual([team["id"] for team in detail["teams"]],
                         [9410101, 9410103, 9410106, 9410107])
        self.assertIsNotNone(self.catalog.team(9410106))
        chapter = self.catalog.chapter("event-unknown")["chapter"]
        self.assertEqual(chapter["category"], "event")
        self.assertEqual(chapter["title"], "特殊作战·未知")
        self.assertIn("特殊作战", chapter["tags"])

    # -- 队伍 / 效能 ---------------------------------------------------
    def test_team_detail_scaled_and_power(self):
        team = self.catalog.team(660011)
        self.assertIsNotNone(team)
        self.assertEqual(set(team), TEAM_DETAIL_KEYS)
        # 实测锚点：660011 总血 359,580（等级缩放口径）
        self.assertAlmostEqual(team["hp_total"], 359580, delta=3)
        self.assertEqual(team["power"], -100085)   # 负值原样保留
        self.assertTrue(team["power_known"])
        self.assertEqual(team["params"]["power_known"], True)
        self.assertEqual(team["units"], 10)
        for member in team["members"]:
            self.assertEqual(set(member["stats"]), STAT_KEYS)
            self.assertEqual(set(member["base_stats"]), STAT_KEYS)
            if "icon" not in member:
                self.fail("team detail member 缺 icon 字段")
        member = team["members"][0]
        self.assertGreater(member["stats"]["maxlife"], member["base_stats"]["maxlife"])
        self.assertEqual(member["base_stats"]["def"], 99999)
        self.assertEqual(member["stats"]["def"], 99999)

    def test_team_summary_power_known_and_icons(self):
        summaries = self.catalog.team_summaries([6549244, 660011, 123456789])
        self.assertEqual([item["id"] for item in summaries], [6549244, 660011])
        for summary in summaries:
            self.assertEqual(set(summary), TEAM_SUMMARY_KEYS)
            self.assertIsInstance(summary["power_known"], bool)
            self.assertEqual(summary["power_known"], summary["power"] != 0)
            for species in summary["species"]:
                self.assertEqual(set(species), {"codex_no", "name", "icon"})
            for member in summary["members"]:
                self.assertEqual(set(member), {"code", "name", "number", "count", "icon"})
            if summary["stage"] is not None:
                self.assertEqual(set(summary["stage"]),
                                 {"chapter_id", "title", "stage_title", "code"})
        # 6549244 无出处（orphan）但效能已标注
        self.assertTrue(summaries[0]["power_known"])
        self.assertIsNone(summaries[0]["stage"])

    def test_orphan_chapter_full_teams(self):
        chapter = self.catalog.chapter("orphan")
        self.assertEqual(chapter["chapter"]["category"], "orphan")
        self.assertEqual(len(chapter["teams"]), chapter["chapter"]["team_count"])
        self.assertGreater(len(chapter["teams"]), 4000)
        self.assertTrue(all("power_known" in team for team in chapter["teams"]))

    # -- 怪种 ---------------------------------------------------------
    def test_species_flags(self):
        page = self.catalog.species_list(limit=10)
        self.assertEqual(page["total"], EXPECT_SPECIES)
        for item in page["items"]:
            self.assertEqual(set(item), SPECIES_ITEM_KEYS)
            self.assertIsInstance(item["has_normal"], bool)
            self.assertIsInstance(item["has_grayzone"], bool)
            self.assertIsInstance(item["has_orphan"], bool)
        counts = {category: self.catalog.species_list(category=category)["total"]
                  for category in ("normal", "grayzone", "orphan")}
        # 非互斥：过滤数之和 > 264
        self.assertGreater(sum(counts.values()), EXPECT_SPECIES)
        self.assertLessEqual(abs(counts["normal"] - 244), 2)
        self.assertLessEqual(abs(counts["grayzone"] - 66), 2)
        self.assertLessEqual(abs(counts["orphan"] - 211), 2)
        self.assertEqual(self.catalog.species_list(category="all")["total"],
                         EXPECT_SPECIES)
        # 灰域过滤是「所有在灰域有队伍的物种」：既包含灰域 BOSS 变体，
        # 也包含在灰域出现过的普通怪（不再是 exclusive 的 4 个）
        gray_items = self.catalog.species_list(category="grayzone", limit=200)["items"]
        self.assertGreater(len(gray_items), 4)
        by_name = {item["name"]: item for item in gray_items}
        self.assertIn("法官（灰域Boss）", by_name)
        # 数据事实：法官 codex 35 只出现在**不可收藏**的灰域队伍里，所以按
        # catalog 的可收藏口径 has_grayzone=False；灰域 BOSS 变体 199 才是可收藏的。
        self.assertFalse(self.catalog.species(35)["species"]["has_grayzone"])
        self.assertTrue(self.catalog.species(199)["species"]["has_grayzone"])
        # 非互斥：至少一个物种同时 has_normal 与 has_orphan / has_grayzone
        self.assertTrue(any(item["has_normal"] and item["has_orphan"]
                            for item in self.catalog._species_items))
        self.assertTrue(any(item["has_normal"] and item["has_grayzone"]
                            for item in self.catalog._species_items))

    def test_species_detail_full_and_paged(self):
        detail = self.catalog.species(5)
        self.assertIsNotNone(detail)
        species = detail["species"]
        self.assertEqual(species["codex_no"], 5)
        self.assertEqual(species["name"], "稻草人")
        self.assertEqual(species["tags"], ["契约捕获"])
        # 无参调用 → 全量 teams（app.py 兼容）
        self.assertEqual(len(detail["teams"]), species["team_count"])
        self.assertEqual(detail["teams_total"], species["team_count"])
        # 显式传参 → 内部筛选/排序/分页
        paged = self.catalog.species(5, offset=0, limit=5, power_known=True,
                                     sort="power_desc")
        self.assertLessEqual(len(paged["teams"]), 5)
        self.assertGreater(paged["teams_total"], 0)
        self.assertTrue(all(team["power_known"] for team in paged["teams"]))
        powers = [team["power"] for team in paged["teams"]]
        self.assertEqual(powers, sorted(powers, reverse=True))
        page2 = self.catalog.species(5, offset=5, limit=5)
        self.assertEqual(page2["offset"], 5)
        self.assertEqual(page2["limit"], 5)
        filtered = self.catalog.species(5, q="BOSS")
        self.assertLessEqual(filtered["total"], species["team_count"])
        self.assertIsNone(self.catalog.species(99999999))

    # -- 搜索 / JSON / 缓存 --------------------------------------------
    def test_search(self):
        result = self.catalog.search("稻草人")
        self.assertEqual(set(result), {"teams", "stages", "species"})
        self.assertTrue(result["teams"])
        self.assertTrue(result["species"])
        stage = self.catalog.search("演习训练")["stages"][0]
        self.assertEqual(stage["id"], 5)
        self.assertTrue({"id", "title", "code", "chapter_title"} <= set(stage))
        self.assertTrue(self.catalog.search("660011")["teams"])
        self.assertTrue(self.catalog.search("自画像")["stages"])
        self.assertTrue(self.catalog.search("积分关卡")["stages"])
        self.assertEqual(self.catalog.search(""),
                         {"teams": [], "stages": [], "species": []})

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
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        self.assertGreater(len(text), 1_000_000)

    def test_datapaths_single_source(self):
        self.assertEqual(catalog.CATALOG_FILE, DATA_CATALOG_FILE)
        self.assertEqual(catalog.ICON_DIR, DATA_ICON_DIR)
        self.assertEqual(catalog.DATA_DIR, DATA_CATALOG_FILE.parent)

    def test_load_is_fast(self):
        started = time.time()
        fresh = catalog.reload()
        elapsed = time.time() - started
        self.assertLess(elapsed, 5.0, f"catalog load 太慢：{elapsed:.2f}s")
        self.assertEqual(fresh.built_at, self.catalog.built_at)

    def test_build_cache_hit(self):
        started = time.time()
        meta = catalog.build(force=False)
        elapsed = time.time() - started
        self.assertEqual(meta["counts"]["teams"], EXPECT_TEAMS)
        self.assertLess(elapsed, 10.0, f"build(force=False) 未命中缓存：{elapsed:.2f}s")


@unittest.skipUnless(_icon_available(), "图标未导出（先跑 tools/build_icons.py）")
class CatalogIconTest(unittest.TestCase):
    """小怪头像字段/覆盖率（图标目录为空时跳过）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = catalog.load()

    def test_icons_coverage(self):
        icons = self.catalog.sources["icons"]
        self.assertGreaterEqual(icons["codes_covered"], 200,
                                f"code 图标覆盖太低：{icons}")
        self.assertGreaterEqual(icons["species_covered"], 220,
                                f"species 图标覆盖太低：{icons}")
        with_icon = [item for item in self.catalog._species_items if item.get("icon")]
        self.assertGreaterEqual(len(with_icon), 220)
        for item in with_icon:
            self.assertTrue((DATA_ICON_DIR / item["icon"]).is_file(),
                            f"species 图标文件不存在：{item['icon']}")

    def test_team_icon_fields(self):
        summary = self.catalog.team_summaries([660011])[0]
        self.assertTrue(any(species["icon"] for species in summary["species"]))
        self.assertTrue(any(member["icon"] for member in summary["members"]))
        detail = self.catalog.team(660011)
        for member in detail["members"]:
            if member["icon"]:
                self.assertTrue((DATA_ICON_DIR / member["icon"]).is_file())
        for species in detail["species"]:
            if species["icon"]:
                self.assertTrue((DATA_ICON_DIR / species["icon"]).is_file())

    def test_icon_filenames_are_safe(self):
        for item in self.catalog._species_items:
            icon = item.get("icon")
            if not icon:
                continue
            self.assertNotIn("/", icon)
            self.assertNotIn("\\", icon)
            self.assertTrue(icon.endswith(".png"))

    def test_build_icons_helpers_consistent(self):
        try:
            from targetforge.tools import build_icons
        except ImportError:  # pragma: no cover - 老版本没有 tools/__init__
            self.skipTest("targetforge.tools.build_icons 不可导入")
        self.assertEqual(build_icons.icon_filename("Aegis_GA"),
                         catalog._icon_filename("Aegis_GA"))
        self.assertEqual(build_icons.icon_filename("M4 SOPMOD IIMod"),
                         "m4_sopmod_iimod.png")
        self.assertEqual(build_icons.bundle_code_key("Aegis_GA"), "aegisga")
        codes = build_icons.codes_from_catalog()
        self.assertEqual(len(codes), 282)


@unittest.skipUnless(_icon_available(), "图标未导出（先跑 tools/build_icons.py）")
class AppIntegrationTest(unittest.TestCase):
    """确认 Lead 的 app.py 调用签名与 catalog v1.2 实现一致（不起 HTTP 服务）。"""

    @classmethod
    def setUpClass(cls) -> None:
        from targetforge import app

        cls.app = app
        cls.catalog = catalog.load()
        app._CATALOG_STATE.update({"state": "ready",
                                   "built_at": cls.catalog.built_at,
                                   "counts": cls.catalog.counts})

    def test_app_catalog_routes(self):
        app = self.app
        cat = app.get_catalog()
        self.assertIs(cat, self.catalog)
        groups = cat.chapters()["groups"]
        self.assertEqual([group["id"] for group in groups], GROUP_ORDER)
        self.assertEqual(app.api_meta()["counts"]["teams"], EXPECT_TEAMS)
        self.assertEqual(app.api_chapter("grayzone")["chapter"]["id"], "grayzone")
        self.assertEqual(app.api_stage(5)["stage"]["id"], 5)
        self.assertEqual(app.api_team(660011)["id"], 660011)
        species = app.api_species_detail(5, {"offset": ["0"], "limit": ["10"]})
        self.assertEqual(len(species["teams"]), 10)   # app.py 服务端分页
        self.assertEqual(species["teams_total"], self.catalog.species(5)["total"])
        orphan = app.api_chapter("orphan", {"offset": ["20"], "limit": ["5"]})
        self.assertEqual(len(orphan["teams"]), 5)
        self.assertGreater(orphan["teams_total"], 4000)
        grayzone = cat.grayzone_teams(area="共生净土", offset=0, limit=2, q="")
        self.assertEqual(grayzone["total"], 1104)
        body = json.dumps(app.api_chapter("main-1"), ensure_ascii=False,
                          default=app._jsonable)
        self.assertIn("第1章", body)
        # 图标文件通过 app 的 ICON_DIR 能取到
        icon = self.catalog.species(5)["species"]["icon"]
        self.assertTrue((app.ICON_DIR / icon).is_file())


if __name__ == "__main__":
    unittest.main()
