"""catalog.py 数据层自检（v1.2，真数据，本机 STC；不 mock）。

跑法（仓库根目录，系统 python）::

    python -m unittest targetforge.tests.test_catalog -v

覆盖任务验收点（task-12）：
* 章节 7 组（main/event/score/tutorial/simulation/grayzone/orphan）；活动/往期复刻/
  特殊作战合并进 event；积分关卡按 **mission.event_score**（mission 级）拆章：
  混合活动（思域迷航）拆成 event+score 两章，全积分 campaign 只有 score 章；
* **stage.settlement**：event_score {mode,params} / score_prize {raw,tiers} /
  rank {id,name,title,type,score_rewards}（rank type=10 优先 type=6）；
* **支援队伍（v1.4）**：spot.ally_team_id → stage.support_teams/support_team_count、
  team.roles（enemy/support）、支援出处、orphan 4381→3802；
* **机场/后续刷新候选（v1.5）**：按 team id 族推断 stage.reserve_teams（role=reserve,
  inferred=true, reserve_reason），如 11435 AA-02 / 11946 威廉 / 11603 Hebe·Styx；
  reserve 不影响 team_count/support_team_count/orphan 真实状态；
* **全怪组总表 team_list（v1.6）**：q/chapter/species(AND)/role/enemy·support·reserve/
  power/units 筛选、8 种排序（稳定、未知效能最后）、分页；13,700 队单查询 <100ms；
* 灰域 14 个区域（含 庇护所旧址 / 坍缩狭缝）；
* 物种非互斥 flag：normal/grayzone/orphan 过滤数 = 244/66/211（±2）；
* 效能 power / power_known + power_min/power_max/power_known/sort 筛选排序；
* 队伍/物种列表分页；species() 无参仍返回全量 teams（app.py 兼容）；
* 小怪图标：icon 字段（species / team_summary.species / detail members）+ 覆盖率；
* 分析工具 tools/analyze_score_stages.py 关键数字；
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
EXPECT_SUPPORT_TEAMS = 864
EXPECT_ORPHAN_TEAMS = 3802
EXPECT_RESERVE_STAGES = 1637
EXPECT_SPECIES = 264
EXPECT_STAGES = 2345
EXPECT_MISSIONS_IN_TABLE = 3986
EXPECT_CHAPTERS = 121

GROUP_ORDER = ["main", "event", "score", "tutorial", "simulation", "grayzone", "orphan"]
GROUP_TITLES = ["主线", "活动", "积分关卡", "教学", "模拟作战", "灰域探查", "无固定关卡"]
EXPECT_GROUP_CHAPTERS = {"main": 14, "event": 73, "score": 25, "tutorial": 6,
                         "simulation": 1, "grayzone": 1, "orphan": 1}
EXPECT_GROUP_STAGES = {"main": 140, "event": 815, "score": 53, "tutorial": 40,
                       "simulation": 9, "grayzone": 1288, "orphan": 0}
#: mission.event_score 非空且有可收藏队伍的积分关卡
EXPECT_SCORE_STAGES = 53
EXPECT_SCORE_CHAPTERS = 25
#: v1.4 期望的 score 章节标题（15 个全积分 campaign + 8 个混合活动的「· 积分关卡」章 + 静默沙盘）
EXPECT_SCORE_TITLES = {
    "终焉花海+", "谜境守卫+", "混沌落幕+", "噩梦迷城+", "驱雾行动+", "秘密涡点+",
    "飓风营救+", "马蜂窝+", "虚数迷宫+", "坠入兔洞+", "贝蒂数", "逃亡圣咏",
    "自画像", "从潘洛斯阶梯跃下", "铁雨礼赞", "静默沙盘",
    "思域迷航 · 积分关卡", "迷笼猜想 · 积分关卡", "里坎禁猎区 · 积分关卡",
    "静风点 · 积分关卡", "熵减焓增 · 积分关卡", "镜像论 · 积分关卡",
    "双联乱数 · 积分关卡", "偏振光 · 积分关卡", "裂变链接 · 积分关卡",
}

GRAY_AREAS = ["共生净土", "晶团挖掘点", "旅团商道", "放射区", "人形复制工厂",
              "废弃居民区", "秘密通道", "图腾圣所", "装甲突击", "交易地",
              "地坛遗迹", "最终贮藏地", "庇护所旧址", "坍缩狭缝"]

CHAPTER_KEYS = {"id", "category", "kind", "title", "subtitle", "stage_count",
                "team_count", "species_count", "difficulty_min", "difficulty_max",
                "tags"}
STAGE_LIST_KEYS = {"id", "title", "code", "difficulty", "recommend_level",
                   "team_count", "support_team_count", "reserve_team_count",
                   "species_count", "tags", "order", "settlement"}
TEAM_SUMMARY_KEYS = {"id", "power", "power_known", "units", "hp_total", "faction",
                     "tags", "roles", "collectable", "species", "members",
                     "gray_zone", "orphan", "stage"}
TEAM_DETAIL_KEYS = {"id", "power", "power_known", "units", "hp_total", "faction",
                    "tags", "roles", "collectable", "gray_zone", "orphan", "params",
                    "appearances", "species", "members"}
TEAM_LIST_ITEM_KEYS = {"id", "power", "power_known", "units", "hp_total", "faction",
                       "roles", "collectable", "orphan", "species", "appearances",
                       "appearance_count", "chapter_titles"}
TEAM_LIST_APPEARANCE_KEYS = {"chapter_id", "chapter_title", "stage_title", "role",
                             "inferred"}
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
        self.assertEqual(counts["support_teams"], EXPECT_SUPPORT_TEAMS)
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
        self.assertEqual(tables["rank"], 118)
        settlement_meta = self.meta["sources"]["settlement"]
        self.assertEqual(settlement_meta["score_stages"], EXPECT_SCORE_STAGES)
        self.assertEqual(settlement_meta["rank_matched_stages"], 25)
        support_meta = self.meta["sources"]["support"]
        self.assertEqual(support_meta["with_slots"], EXPECT_SUPPORT_TEAMS)
        self.assertEqual(support_meta["collectable"], 818)
        self.assertEqual(support_meta["missions_with_support"], 329)
        self.assertEqual(support_meta["stage_support_links"], 824)
        reserve_meta = self.meta["sources"]["reserve"]
        self.assertEqual(reserve_meta["stages_with_reserve"], EXPECT_RESERVE_STAGES)
        self.assertGreater(reserve_meta["links"], 0)
        self.assertIn("机场", reserve_meta["reason"])
        # 图标覆盖率报告（sources.icons）；支援队伍类型也会进 types（v1.4 后 282→301 个 code）
        icons = self.meta["sources"]["icons"]
        for key in ("files", "codes_needed", "codes_covered",
                    "species_total", "species_covered"):
            self.assertIn(key, icons)
        self.assertGreaterEqual(icons["codes_needed"], 282)
        self.assertEqual(icons["codes_needed"], 301)

    # -- 机场/后续刷新候选（reserve，推断） -----------------------------
    def test_reserve_teams(self):
        """v1.5：按 team id 族推断的机场/后续刷新候选（明确标记 inferred）。"""
        detail = self.catalog.stage(11435)
        self.assertEqual(detail["stage"]["team_count"], 30)          # 敌方计数不变
        self.assertEqual(detail["stage"]["support_team_count"], 17)  # 支援计数不变
        self.assertEqual(detail["reserve_team_count"], 16)           # 6363xxx 未引用队
        reserve = {team["id"]: team for team in detail["reserve_teams"]}
        self.assertIn(6363057, reserve)   # AA-02
        self.assertIn(6363060, reserve)   # AA-02
        for team_id in (6363057, 6363060):
            item = reserve[team_id]
            self.assertEqual(item["role"], "reserve")
            self.assertTrue(item["inferred"])
            self.assertTrue(item["collectable"])
            self.assertEqual(item["reserve_reason"], catalog.RESERVE_REASON)
            self.assertIn("机场", item["reserve_reason"])
        self.assertEqual(reserve[6363057]["power"], 189798)
        self.assertEqual(reserve[6363060]["power"], 187497)
        # 静默沙盘（11946）后续含威廉 770060
        weilian = {team["id"] for team in self.catalog.stage(11946)["reserve_teams"]}
        self.assertIn(770060, weilian)
        # 潘洛斯（11603）后续机场含 Hebe/Styx
        panluo = {team["id"] for team in self.catalog.stage(11603)["reserve_teams"]}
        self.assertIn(660002, panluo)
        self.assertIn(660003, panluo)
        # 主线的普通关没有同族未引用队伍 → reserve 为空（合理）
        for stage in self.catalog.chapter("main-1")["stages"]:
            self.assertEqual(stage["reserve_team_count"], 0, stage["title"])
        # 章节 stage 行只带数量
        row = next(stage for stage in self.catalog.chapter("score--60")["stages"]
                   if stage["id"] == 11435)
        self.assertEqual(row["reserve_team_count"], 16)
        # appearances 里出现「可能刷新（推断）」条目，但不改变 orphan/roles 真实状态
        team = self.catalog.team(6363057)
        self.assertIsNotNone(team)
        self.assertTrue(team["orphan"])          # 推断链接不算真实出处
        self.assertEqual(team["roles"], [])
        appearance = next(entry for entry in team["appearances"]
                          if entry["mission_id"] == 11435)
        self.assertEqual(appearance["role"], "reserve")
        self.assertTrue(appearance["inferred"])
        self.assertEqual(appearance["chapter_id"], "score--60")
        # 有 reserve 的 stage 数量与 meta 一致
        self.assertEqual(len(self.catalog._stage_reserve_teams),
                         EXPECT_RESERVE_STAGES)

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
        # 10 个 id>=90000 的往期活动复刻 + 2 个多关「+」复刻活动（魔方行动/盲拆法则）
        self.assertEqual(len(rerun), 12)
        self.assertEqual(len(special), 15)
        self.assertTrue(all("往期复刻" in chapter["subtitle"] for chapter in rerun))
        self.assertTrue(all("特殊作战" in chapter["subtitle"] for chapter in special))
        self.assertTrue(all("往期复刻" in chapter["tags"] for chapter in rerun))
        self.assertTrue(all("特殊作战" in chapter["tags"] for chapter in special))

    def test_mofang_activity_is_not_score(self):
        """用户实测：EP 5.5 魔方行动（4 关）是常驻/复刻活动，不是积分关卡。"""
        score_titles = [chapter["title"] for chapter in self.groups["score"]["chapters"]]
        self.assertNotIn("魔方行动", score_titles)
        self.assertNotIn("盲拆法则", score_titles)
        # 回 event 组，两章都带「往期复刻」标记，4 关一场
        event = {chapter["id"]: chapter for chapter in self.groups["event"]["chapters"]}
        mofang = event.get("event--6")
        mangchai = event.get("event--7")
        self.assertIsNotNone(mofang)
        self.assertIsNotNone(mangchai)
        self.assertEqual((mofang["title"], mangchai["title"]), ("魔方行动", "盲拆法则"))
        for chapter in (mofang, mangchai):
            self.assertEqual(chapter["category"], "event")
            self.assertEqual(chapter["kind"], "rerun")
            self.assertEqual(chapter["stage_count"], 4)
            self.assertIn("往期复刻", chapter["subtitle"])
            self.assertIn("魔方行动+", chapter["subtitle"])
            self.assertIn("往期复刻", chapter["tags"])
        # 搜索仍能命中这两章
        self.assertTrue(self.catalog.search("魔方行动", limit=5)["stages"])
        self.assertTrue(self.catalog.search("盲拆法则", limit=5)["stages"])

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
        """score 是 mission.event_score 判定（mission 级）：25 章 / 53 关。"""
        score = self.groups["score"]
        self.assertEqual(len(score["chapters"]), EXPECT_SCORE_CHAPTERS)
        self.assertEqual(sum(chapter["stage_count"] for chapter in score["chapters"]),
                         EXPECT_SCORE_STAGES)
        for chapter in score["chapters"]:
            self.assertEqual(chapter["category"], "score")
            self.assertEqual(chapter["kind"], "score")
            self.assertEqual(chapter["tags"], ["积分关卡"])
            self.assertIn("积分关卡", chapter["subtitle"])
        # 标题集合：全积分 campaign + 混合活动的「· 积分关卡」章
        self.assertEqual({chapter["title"] for chapter in score["chapters"]},
                         EXPECT_SCORE_TITLES)
        # 自画像：标题=自画像，parent 慢休克（-40403，全部任务都是积分关卡）
        portrait = next((chapter for chapter in score["chapters"]
                         if chapter["title"] == "自画像"), None)
        self.assertIsNotNone(portrait)
        self.assertEqual(portrait["stage_count"], 2)
        self.assertIn("慢休克", portrait["subtitle"])
        # 贝蒂数：9 关全部 event_score，含 三维流形 G-1..S-2
        beiti = self.catalog.chapter("score--40401")
        self.assertIsNotNone(beiti)
        self.assertEqual(beiti["chapter"]["stage_count"], 9)
        beiti_titles = [stage["title"] for stage in beiti["stages"]]
        self.assertIn("三维流形G-1", beiti_titles)
        self.assertIn("三维流形S-2", beiti_titles)
        # 搜索：自画像 / 积分关卡 / 三维流形 / 禁止喂食EX 都能命中 score 关卡
        for query in ("自画像", "积分关卡", "三维流形", "禁止喂食EX"):
            result = self.catalog.search(query, limit=10)
            self.assertTrue(result["stages"], f"搜索 {query!r} 没有结果")
        portrait_hits = self.catalog.search("自画像")["stages"]
        self.assertTrue(any(stage["chapter_title"] == "自画像" for stage in portrait_hits))
        weidu = self.catalog.search("三维流形")["stages"]
        self.assertTrue(any(stage["chapter_title"] == "贝蒂数" for stage in weidu))

    def test_event_score_mission_split(self):
        """混合活动拆章：思域迷航(-61) 2 关进 score，其余 20 关留在 event。"""
        score = {chapter["id"]: chapter for chapter in self.groups["score"]["chapters"]}
        event = {chapter["id"]: chapter for chapter in self.groups["event"]["chapters"]}
        # 思域迷航：score 只含 禁止喂食 / 禁止喂食EX
        score_chapter = self.catalog.chapter("score--61")
        self.assertIsNotNone(score_chapter)
        self.assertEqual(score_chapter["chapter"]["stage_count"], 2)
        self.assertEqual(sorted(stage["title"] for stage in score_chapter["stages"]),
                         ["禁止喂食", "禁止喂食EX"])
        self.assertEqual({stage["id"] for stage in score_chapter["stages"]},
                         {11445, 11458})
        self.assertIn("思域迷航", score_chapter["chapter"]["title"])
        # 同 campaign 的 event 章保留其余 20 关且不含积分关卡任务
        event_chapter = self.catalog.chapter("event--61")
        self.assertIsNotNone(event_chapter)
        self.assertEqual(event_chapter["chapter"]["stage_count"], 20)
        event_ids = {stage["id"] for stage in event_chapter["stages"]}
        self.assertFalse(event_ids & {11445, 11458})
        # 全积分 campaign 不再生成 event 章（贝蒂数 / 终焉花海+ / 静默沙盘）
        for campaign in (-40401, -55, -77):
            self.assertNotIn(f"event-{campaign}", event)
            self.assertIn(f"score-{campaign}", score)
        # 全局：score 关卡与 event 关卡集合不重叠
        score_stage_ids = {stage["id"] for chapter in score.values()
                           for stage in self.catalog.chapter(chapter["id"])["stages"]}
        event_stage_ids = {stage["id"] for chapter in event.values()
                           for stage in self.catalog.chapter(chapter["id"])["stages"]}
        self.assertEqual(len(score_stage_ids), EXPECT_SCORE_STAGES)
        self.assertFalse(score_stage_ids & event_stage_ids)
        # 普通 EX 无 event_score 的不算积分关卡；10365 终焉花海EX 有 event_score
        self.assertIn(11451, event_stage_ids)       # 同频干扰EX（无 event_score）
        self.assertNotIn(11451, score_stage_ids)
        self.assertIn(10365, score_stage_ids)       # 终焉花海EX（有 event_score）

    def test_stage_settlement_chain(self):
        """stage.settlement：event_score / score_prize / rank 结构化（v1.3）。"""

        def settlement(mission_id):
            detail = self.catalog.stage(mission_id)
            self.assertIsNotNone(detail, f"stage {mission_id} 不存在")
            value = detail["stage"]["settlement"]
            self.assertEqual(set(value), {"type", "event_score", "score_prize", "rank"})
            return value

        # 思域迷航：11445 禁止喂食 / 11458 禁止喂食EX = 积分结算，mode=1 + score_prize
        for mission_id in (11445, 11458):
            item = settlement(mission_id)
            self.assertEqual(item["type"], "score")
            self.assertEqual(item["event_score"]["mode"], "1")
            self.assertIsInstance(item["event_score"]["params"], int)
            self.assertGreater(item["event_score"]["params"], 0)
        prize = settlement(11458)["score_prize"]
        self.assertIsNotNone(prize)
        self.assertGreaterEqual(prize["tiers"], 1)
        self.assertTrue(prize["raw"])
        # 普通 EX（同频干扰EX）没有 event_score → normal 结算
        normal = settlement(11451)
        self.assertEqual(normal["type"], "normal")
        self.assertIsNone(normal["event_score"])
        self.assertIsNone(normal["score_prize"])
        self.assertIsNone(normal["rank"])
        # 贝蒂数 11002/11005 的积分榜 = rank 311「贝蒂数常驻」（type=10 优先 type=6）
        for mission_id in (11002, 11005):
            item = settlement(mission_id)
            self.assertEqual(item["type"], "score")
            self.assertEqual(item["rank"]["id"], 311)
            self.assertEqual(item["rank"]["name"], "贝蒂数常驻")
            self.assertIn("贝蒂数", item["rank"]["title"])
            self.assertEqual(item["rank"]["type"], 10)
            self.assertEqual(set(item["rank"]),
                             {"id", "name", "title", "type", "score_rewards"})
        # 终焉花海+ 11320 = rank 306；铁雨礼赞 11988 同时有 type=6/10 → 取 type=10 的 316
        self.assertEqual(settlement(11320)["rank"]["id"], 306)
        self.assertEqual(settlement(11988)["rank"]["id"], 316)
        self.assertEqual(settlement(11988)["rank"]["type"], 10)
        # 未知 mission（404101）→ normal
        self.assertEqual(settlement(404101)["type"], "normal")
        # chapter 详情的 stages 每项都带 settlement；score 章全 score / event 章全 normal
        for chapter in self.groups["score"]["chapters"]:
            for stage in self.catalog.chapter(chapter["id"])["stages"]:
                self.assertEqual(stage["settlement"]["type"], "score",
                                 f"{chapter['id']} stage {stage['id']}")
        for chapter in self.groups["event"]["chapters"]:
            for stage in self.catalog.chapter(chapter["id"])["stages"]:
                self.assertEqual(stage["settlement"]["type"], "normal",
                                 f"{chapter['id']} stage {stage['id']}")
        main_stage = self.catalog.chapter("main-1")["stages"][0]
        self.assertEqual(main_stage["settlement"]["type"], "normal")

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
        # 章节详情行 / stage 详情现在都带支援 + reserve（推断）字段
        self.assertEqual(set(detail),
                         {"stage", "teams", "support_teams", "support_team_count",
                          "reserve_teams", "reserve_team_count"})
        stage = detail["stage"]
        self.assertEqual(stage["id"], 5)
        self.assertEqual(stage["title"], "演习训练")
        self.assertEqual(stage["chapter_id"], "main-1")
        self.assertEqual(stage["chapter_title"], "第1章")
        self.assertEqual(stage["reserve_team_count"], 0)
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
        self.assertEqual(team["roles"], ["enemy"])
        self.assertTrue(team["collectable"])
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
            self.assertIsInstance(summary["roles"], list)
            self.assertIsInstance(summary["collectable"], bool)
            for species in summary["species"]:
                self.assertEqual(set(species), {"codex_no", "name", "icon"})
            for member in summary["members"]:
                self.assertEqual(set(member), {"code", "name", "number", "count", "icon"})
            if summary["stage"] is not None:
                self.assertEqual(set(summary["stage"]),
                                 {"chapter_id", "title", "stage_title", "code"})
        # 6549244 无出处（orphan）但效能已标注；660011 是敌方队伍
        self.assertTrue(summaries[0]["power_known"])
        self.assertIsNone(summaries[0]["stage"])
        self.assertEqual(summaries[0]["roles"], [])
        self.assertEqual(summaries[1]["roles"], ["enemy"])

    def test_orphan_chapter_full_teams(self):
        chapter = self.catalog.chapter("orphan")
        self.assertEqual(chapter["chapter"]["category"], "orphan")
        self.assertEqual(len(chapter["teams"]), chapter["chapter"]["team_count"])
        # 支援链接把 579 支「只在支援侧出现」的可收藏队伍从 orphan 拉了出来
        self.assertEqual(len(chapter["teams"]), EXPECT_ORPHAN_TEAMS)
        self.assertGreater(len(chapter["teams"]), 3000)
        self.assertTrue(all("power_known" in team for team in chapter["teams"]))

    def test_support_teams(self):
        """v1.4：spot.ally_team_id → stage.support_teams（谜境守卫+ 67.3w 支援队）。"""
        detail = self.catalog.stage(11435)
        self.assertIsNotNone(detail)
        self.assertEqual(set(detail),
                         {"stage", "teams", "support_teams", "support_team_count",
                          "reserve_teams", "reserve_team_count"})
        # 敌方队伍列表/team_count 不变，支援队伍单独列
        self.assertEqual(detail["stage"]["team_count"], 30)
        self.assertNotIn(6363006, {team["id"] for team in detail["teams"]})
        self.assertEqual(detail["support_team_count"], 17)
        self.assertEqual(len(detail["support_teams"]), 17)
        support = {team["id"]: team for team in detail["support_teams"]}
        self.assertIn(6363006, support)
        self.assertIn(6363008, support)
        target = support[6363006]
        self.assertEqual(target["power"], 673555)          # 67.3w 效能
        self.assertTrue(target["power_known"])
        self.assertTrue(target["collectable"])
        self.assertEqual(target["role"], "support")
        self.assertEqual(target["roles"], ["support"])
        self.assertGreaterEqual(target["support_count"], 1)
        self.assertEqual(target["units"], 24)
        self.assertEqual(support[6363008]["power"], 677959)
        for item in detail["support_teams"]:
            self.assertIn("collectable", item)
            self.assertIn("role", item)
            self.assertIn("support_count", item)
        # 章节详情的 stage 行也带 support_team_count
        row = next(stage for stage in self.catalog.chapter("score--60")["stages"]
                   if stage["id"] == 11435)
        self.assertEqual(row["support_team_count"], 17)
        # team 详情可反查支援出处（role=support），且不再 orphan
        team = self.catalog.team(6363006)
        self.assertIsNotNone(team)
        self.assertEqual(team["roles"], ["support"])
        self.assertFalse(team["orphan"])
        appearance = next(entry for entry in team["appearances"]
                          if entry["mission_id"] == 11435)
        self.assertEqual(appearance["role"], "support")
        # 有敌方+支援双链接的可收藏队伍 roles = ["enemy","support"]
        both = next((record for record in self.catalog._teams.values()
                     if record.get("roles") == ["enemy", "support"]), None)
        self.assertIsNotNone(both)
        # 不可收藏的支援队伍也展示（collectable=False），但不进 team() 查询
        found = None
        for mission_id, links in self.catalog._stage_support_teams.items():
            for team_id, _count in links:
                if team_id in self.catalog._support_records:
                    found = (mission_id, team_id)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        mission_id, team_id = found
        items = self.catalog.stage(mission_id)["support_teams"]
        non_collectable = [item for item in items if not item["collectable"]]
        self.assertTrue(non_collectable)
        self.assertIsNone(self.catalog.team(team_id))

    # -- 全怪组总表 team_list（v1.6） ----------------------------------
    def test_team_list_basic(self):
        result = self.catalog.team_list()
        self.assertEqual(result["total"], EXPECT_TEAMS)
        self.assertEqual(result["offset"], 0)
        self.assertEqual(result["limit"], 50)
        self.assertEqual(len(result["items"]), 50)
        item = result["items"][0]
        self.assertEqual(set(item), TEAM_LIST_ITEM_KEYS)
        for species in item["species"]:
            self.assertEqual(set(species), {"codex_no", "name", "icon"})
        for appearance in item["appearances"]:
            self.assertTrue(TEAM_LIST_APPEARANCE_KEYS <= set(appearance))
        self.assertIsInstance(item["chapter_titles"], list)
        # 默认 id_asc；分页无缝衔接
        ids = [entry["id"] for entry in result["items"]]
        self.assertEqual(ids, sorted(ids))
        page1 = self.catalog.team_list(offset=0, limit=3)
        page2 = self.catalog.team_list(offset=3, limit=3)
        self.assertEqual([entry["id"] for entry in page1["items"]] +
                         [entry["id"] for entry in page2["items"]], ids[:6])
        self.assertEqual(page1["total"], EXPECT_TEAMS)
        # limit 上限 200
        self.assertEqual(len(self.catalog.team_list(limit=999)["items"]), 200)
        self.assertEqual(self.catalog.team_list(offset=999999)["items"], [])
        self.assertEqual(self.catalog.team_list(sort="id_desc")["items"][0]["id"],
                         self.catalog._team_ids[-1])

    def test_team_list_chapter_and_roles(self):
        # 章节：任意 role（敌方/支援/机场推断）出现即命中
        chapter = self.catalog.team_list(chapter="score--60", limit=200)
        ids = {entry["id"] for entry in chapter["items"]}
        self.assertIn(6363006, ids)   # 支援
        self.assertIn(6363057, ids)   # 机场推断（reserve）
        enemy_team_ids = self.catalog._stage_teams.get(11435) or []
        self.assertTrue(enemy_team_ids)
        self.assertIn(enemy_team_ids[0], ids)  # 敌方
        for team_id in ids:
            self.assertIn("score--60", self.catalog._team_chapters[team_id])
        for entry in chapter["items"]:
            self.assertIn("谜境守卫+", entry["chapter_titles"])
        # 混合筛选
        support_mixed = self.catalog.team_list(chapter="score--60", role="support")
        self.assertIn(6363006, {entry["id"] for entry in support_mixed["items"]})
        reserve_mixed = self.catalog.team_list(chapter="score--60", role="reserve")
        self.assertIn(6363057, {entry["id"] for entry in reserve_mixed["items"]})
        # role 过滤
        support = self.catalog.team_list(role="support")
        self.assertEqual(support["total"],
                         sum(1 for record in self.catalog._teams.values()
                             if "support" in (record.get("roles") or [])))
        self.assertEqual(support["total"], 818)
        self.assertIn(6363006, {entry["id"] for entry in
                                self.catalog.team_list(role="support", q="6363006")["items"]})
        reserve = self.catalog.team_list(role="reserve")
        self.assertEqual(reserve["total"],
                         self.catalog.sources["reserve"]["teams"])
        self.assertIn(6363057, {entry["id"] for entry in
                                self.catalog.team_list(role="reserve", q="6363057")["items"]})
        for entry in reserve["items"]:
            self.assertTrue(any(appearance["inferred"]
                                for appearance in entry["appearances"]))
        enemy = self.catalog.team_list(role="enemy")
        self.assertEqual(enemy["total"],
                         sum(1 for record in self.catalog._teams.values()
                             if "enemy" in (record.get("roles") or [])))
        self.assertEqual(self.catalog.team_list(role="any")["total"], EXPECT_TEAMS)

    def test_team_list_filters(self):
        # species AND：同时包含 5 稻草人 + 12 龙骑兵
        species = self.catalog.team_list(species=[5, 12])
        self.assertGreater(species["total"], 0)
        self.assertIn(-2, {entry["id"] for entry in species["items"]})
        for entry in species["items"]:
            codex = {item["codex_no"] for item in entry["species"]}
            self.assertTrue({5, 12} <= codex)
        self.assertEqual(self.catalog.team_list(species="5,12")["total"],
                         species["total"])
        self.assertEqual(self.catalog.team_list(species="5;12")["total"],
                         species["total"])
        # 单位数边界
        units = self.catalog.team_list(units_min=10, units_max=10, limit=200)
        self.assertTrue(all(entry["units"] == 10 for entry in units["items"]))
        self.assertEqual(self.catalog.team_list(units_min=10, units_max=10,
                                                q="660011")["items"][0]["id"], 660011)
        # 效能边界（含负值原样）
        power = self.catalog.team_list(power_min=673555, power_max=673555)
        self.assertEqual(power["total"], 1)
        self.assertEqual(power["items"][0]["id"], 6363006)
        known = self.catalog.team_list(power_known=True)
        unknown = self.catalog.team_list(power_known=False)
        self.assertEqual(known["total"] + unknown["total"], EXPECT_TEAMS)
        self.assertTrue(all(entry["power_known"] for entry in known["items"]))
        self.assertTrue(all(not entry["power_known"] for entry in unknown["items"]))
        # q：id 子串 / 怪种名 / 阵营
        hits = self.catalog.team_list(q="6363", limit=200)
        self.assertIn(6363057, {entry["id"] for entry in hits["items"]})
        self.assertIn(6363006, {entry["id"] for entry in hits["items"]})
        self.assertTrue(self.catalog.team_list(q="稻草人")["total"] > 0)
        self.assertTrue(self.catalog.team_list(q="军方")["total"] > 0)
        # collectable：默认只可收藏（13700）；false 时返回不可收藏支援队伍
        self.assertEqual(self.catalog.team_list()["total"], EXPECT_TEAMS)
        non_collectable = self.catalog.team_list(collectable=False)
        self.assertEqual(non_collectable["total"], 46)
        self.assertTrue(all(not entry["collectable"]
                            for entry in non_collectable["items"]))

    def test_team_list_sorting(self):
        # id_desc 单调
        desc = [entry["id"] for entry in self.catalog.team_list(sort="id_desc",
                                                                limit=200)["items"]]
        self.assertEqual(desc, sorted(desc, reverse=True))
        # power_desc / power_asc（只看有标注的，避免未知值干扰；未知值另测排最后）
        powers_desc = [entry["power"] for entry in
                       self.catalog.team_list(sort="power_desc", power_known=True,
                                              limit=200)["items"]]
        self.assertEqual(powers_desc, sorted(powers_desc, reverse=True))
        powers_asc = [entry["power"] for entry in
                      self.catalog.team_list(sort="power_asc", power_known=True,
                                             limit=200)["items"]]
        self.assertEqual(powers_asc, sorted(powers_asc))
        # units_desc / units_asc；同值按 id 升序（稳定）
        units_desc = self.catalog.team_list(sort="units_desc", limit=200)["items"]
        self.assertEqual([entry["units"] for entry in units_desc],
                         sorted((entry["units"] for entry in units_desc),
                                reverse=True))
        grouped: dict[int, list[int]] = {}
        for entry in units_desc:
            grouped.setdefault(entry["units"], []).append(entry["id"])
        for ids in grouped.values():
            self.assertEqual(ids, sorted(ids))
        units_asc = [entry["units"] for entry in
                     self.catalog.team_list(sort="units_asc", limit=200)["items"]]
        self.assertEqual(units_asc, sorted(units_asc))
        # hp_desc / species_desc 单调
        hp = [entry["hp_total"] for entry in
              self.catalog.team_list(sort="hp_desc", limit=200)["items"]]
        self.assertEqual(hp, sorted(hp, reverse=True))
        species_counts = [len(entry["species"]) for entry in
                          self.catalog.team_list(sort="species_desc",
                                                 limit=200)["items"]]
        self.assertEqual(species_counts, sorted(species_counts, reverse=True))
        # 效能排序：未知（power_known=false）排最后
        total = self.catalog.team_list()["total"]
        tail = self.catalog.team_list(sort="power_desc", offset=total - 5,
                                      limit=5)["items"]
        self.assertTrue(all(not entry["power_known"] for entry in tail))

    def test_team_list_performance(self):
        self.catalog.team_list()  # 预热（索引已在 load 时建好）
        unfiltered = []
        for _ in range(3):
            started = time.perf_counter()
            self.catalog.team_list()
            unfiltered.append(time.perf_counter() - started)
        self.assertLess(min(unfiltered), 0.1, f"team_list() 太慢：{min(unfiltered):.3f}s")
        queries = []
        for _ in range(3):
            started = time.perf_counter()
            self.catalog.team_list(q="6363", chapter="score--60", limit=50)
            queries.append(time.perf_counter() - started)
        self.assertLess(min(queries), 0.1, f"带条件 team_list 太慢：{min(queries):.3f}s")

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
        # v1.4 支援链接会让部分物种获得/失去场景 flag（正常 244→250、灰域 66→68、orphan 211→204）
        self.assertLessEqual(abs(counts["normal"] - 250), 2)
        self.assertLessEqual(abs(counts["grayzone"] - 68), 2)
        self.assertLessEqual(abs(counts["orphan"] - 204), 2)
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
        expected_codes = len({str(info.get("code") or "")
                              for info in self.catalog._types.values()
                              if str(info.get("code") or "")})
        self.assertEqual(len(codes), expected_codes)
        self.assertGreaterEqual(len(codes), 282)


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
        self.assertEqual(orphan["teams_total"], EXPECT_ORPHAN_TEAMS)
        # /api/stages/{id} 的支援队伍字段（app.py 直接透传 catalog）
        stage = app.api_stage(11435)
        self.assertEqual(stage["support_team_count"], 17)
        self.assertIn(6363006, {item["id"] for item in stage["support_teams"]})
        grayzone = cat.grayzone_teams(area="共生净土", offset=0, limit=2, q="")
        self.assertEqual(grayzone["total"], 1104)
        body = json.dumps(app.api_chapter("main-1"), ensure_ascii=False,
                          default=app._jsonable)
        self.assertIn("第1章", body)
        # 图标文件通过 app 的 ICON_DIR 能取到
        icon = self.catalog.species(5)["species"]["icon"]
        self.assertTrue((app.ICON_DIR / icon).is_file())


class ScoreAnalysisToolTest(unittest.TestCase):
    """tools/analyze_score_stages.py：结算链分析器自检（真 STC）。"""

    def test_build_report(self):
        from targetforge.tools import analyze_score_stages

        report = analyze_score_stages.build_report()
        self.assertTrue(report["ok"], report.get("mismatches"))
        checks = report["checks"]
        self.assertEqual(checks["event_score_total"], 102)
        self.assertEqual(checks["event_score_non_gray"], 58)
        self.assertEqual(checks["event_score_gray"], 44)
        self.assertEqual(checks["score_missions_with_teams"], 53)
        self.assertEqual(checks["score_campaigns"], 25)
        self.assertEqual(checks["score_prize_total"], 76)
        self.assertEqual(checks["score_prize_without_event_score"], 0)
        self.assertEqual(checks["rank_matched_score_missions"], 25)
        self.assertEqual(checks["rank_type10_rows"], 16)
        self.assertEqual(checks["rank_type6_rows"], 2)
        # 思域迷航(-61) 的积分关卡 = 11445 / 11458
        campaign = next(row for row in report["campaigns"]
                        if row["campaign"] == -61)
        self.assertEqual({mission["id"] for mission in campaign["missions"]},
                         {11445, 11458})
        self.assertEqual(campaign["missions"][0]["event_score"]["mode"], "1")

    def test_json_output(self):
        import contextlib
        import io

        from targetforge.tools import analyze_score_stages

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = analyze_score_stages.main(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"]["score_missions_with_teams"], 53)
        self.assertEqual(payload["rank"]["type10_rows"], 16)


if __name__ == "__main__":
    unittest.main()
