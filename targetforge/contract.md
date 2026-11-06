# 靶机工坊 TargetForge —— 内部契约（Lead 维护，实现方只读）

本地 Web 应用：浏览 STC 关卡 / 可收藏怪种 / 怪组，编排靶机序列，用 GFLH 协议注入「收藏标靶」。
运行方式：`python -m targetforge`（系统 Python 3.14；需要 gflzirc、unit_model 可导入）。

本文件是三个模块 + 前端的接口契约。**写操作按任务里给的 write_scopes，不要越界改文件。**

目录：

```text
targetforge/
  contract.md        本契约（Lead）
  app.py             HTTP 服务 / 路由 / 状态 / job（Lead）
  __main__.py        入口（Lead）
  catalog.py         STC → catalog 缓存 + 查询（catalog 任务）
  gflh.py            capture / 序列规划 / 注入 / 游戏控制（gflh 任务）
  state.py           前端可改状态持久化（Lead，供 app 用）
  static/            index.html + css/ + js/（frontend 任务）
  tests/             unittest（各自任务写自己的 test_*.py）
  tools/             截图/自检脚本（Lead）
```

数据根：`dataMiner/derived/targetforge/`（整个目录不入 git，可重建）。
**路径不再写死**：默认是 `<GF Forge>/dataMiner/derived/targetforge`，可用环境变量
`TARGETFORGE_DATA_DIR` 覆盖（`datapaths.py` 是唯一来源；app/catalog/gflh 都从这里取）。
其中 `icons/` 是小怪头像缓存（`tools/build_icons.py` 从本机游戏资源导出，可重建）。

```text
catalog.json          catalog 缓存（catalog.py build 产出，load 读取）
state.json            前端状态：draft / tutorial / settings
creds_*.json          capture 抓到的 uid/sign + 当前靶机（敏感，勿入 git / 勿出现在 API）
run.log               运行日志（可选）
```

---

## 1. 产品语义（实现必须遵守）

- 靶机 = 游戏「靶机专训 → 收藏标靶」里的一条：`enemy_team_id`（队伍）+ `order_id`（显示序号 1..35）。
- 只有 `enemy_team.targettrain_cancollect == "1"` 的队伍可注入。
- 注入接口：`Targettrain/addCollect` / `Targettrain/delCollect`（走 gflzirc `GFLClient.send_request`）。
- **UI 不得展示怪组/怪种的具体技能信息**（不出现技能名、技能描述、技能组 id、触发器等）。
  可以展示：数值、编制、等级、坐标、力场、效能、关卡出处、队伍 id 等参数。
- 灰域（campaign=-404，标题以「旅团商道 / 放射区 / …」开头）**不列举每个节点的关卡**：
  灰域只作为 1 个章节，内部按 **5 个真实区域**（沙尘带/风暴带/硅状带/结晶带/特殊区域）分组，
  区域下面是 **14 个地点**（共生净土/晶团挖掘点/…），地点下列队伍。
- 无固定关卡的队伍归入「无固定关卡」章节（按队伍列出），保证 264 个可收藏怪种都能在怪种图鉴里找到队伍。
- 序列上限 35；草稿保存 `team_id` 列表（顺序即目标顺序）。
- 三种执行模式：
  - `append`：接在现有靶机后面（跳过已在列表的队伍；编号接着最大号往后排）
  - `replace`：草稿第 i 个替换当前第 i 号靶机（i=1..N，N=草稿长度）；当前多出来的保留；
    草稿多于当前则在末尾追加；草稿里某队伍若已存在于当前列表其它编号，先删旧项再放到目标编号
  - `rebuild`：清空当前全部靶机，再按草稿 1..N 全量填充（`order_id` = 1..N）
  - 另有 `clear`：只清空当前全部（不出现在执行向导的 3 个主选项里，但 API 支持）
- 执行完提示「大退重登游戏同步」；清空后必须强退，否则进靶机界面可能卡死。

---

## 2. catalog.py 契约（catalog 任务实现）

```python
# 路径常量
CATALOG_FILE = ROOT/"dataMiner/derived/targetforge/catalog.json"

def build(force: bool = False) -> dict:
    """解析 STC + client_text + enemy_full_model.csv，写 catalog.json，返回 meta。
    force 时不看缓存 mtime。meta: {built_at, counts:{chapters,stages,teams,species,missions},
    sources:{...}, elapsed_s}"""

def load() -> Catalog:
    """加载 catalog.json（不存在则 build()）。单例 + 线程安全。"""

class Catalog:
    built_at: str
    counts: dict
    def chapters(self) -> list[dict]
    def chapter(self, chapter_id: str) -> dict | None
    def stage(self, mission_id: int) -> dict | None
    def grayzone_areas(self) -> dict   # {"regions":[...5 个...], "areas":[...14 个地点...]}
    def grayzone_teams(self, area_id, offset, limit, q="", region="",
                       power_min=None, power_max=None, power_known=None, sort="default") -> dict
    def team(self, team_id: int) -> dict | None
    def team_summaries(self, team_ids: list[int]) -> list[dict]
    def team_list(*, q="", chapter="", species=None, role="any", collectable=True,
                  power_known=None, power_min=None, power_max=None,
                  units_min=None, units_max=None, sort="id_asc",
                  offset=0, limit=50) -> dict   # 全怪组总表（v1.6，见 §2.5）
    def species_list(self, *, q="", faction="", category="", offset=0, limit=60) -> dict
    def species(self, codex_no, offset=None, limit=None, q="", power_min=None, power_max=None,
                power_known=None, sort="default") -> dict | None   # 无参数调用返回全量 teams
    def species(self, codex_no: int) -> dict | None
    def search(self, q: str, limit: int = 30) -> dict
```

### 2.1 数据源（只用这些，别自己发明）

| 数据 | 来源 | 用途 |
|---|---|---|
| 队伍 | `unit_model.core.stc.table("enemy_team")` (5035) | id / effect_ext / targettrain_cancollect / fight_type / use_building |
| 队伍编制 | `stc.table("enemy_in_team")` (5003) | 每格 type_id/level/number/def_percent/坐标/batch |
| 敌人类型 | `stc.table("enemy_character_type")` (5025) | name 文本 key / code / 基础数值 |
| 图鉴 | `stc.table("enemy_illustration")` (5090) | codex 编号=id、名称文本 key、forces/if_capture/type |
| 关卡 | `stc.table("mission")` (5016) | campaign/sub/type/difficulty/map_res_name/boss_team_id/order/if_emergency |
| 点位 | `stc.table("spot")` (5002) | mission_id ↔ enemy_team_id（敌方）/ ally_team_id（支援队伍） |
| 活动 | `stc.table("mission_event")` (5074)、`stc.table("normal_activity")` (5233) | campaign → 活动名/章节名 |
| 灰域区域 | `stc.table("daily_mission_group")`、`stc.table("daily_mission_difficulty_group")` | mission → difficulty_group（1..6）→ 真实区域（沙尘带/风暴带/硅状带/结晶带；5/6/未映射→特殊区域） |
| 文本 | `dataMiner/derived/client_text.json` | `mission-{10000000+id}`、`enemy_character_type` 行内 name key、`enemy_illustration` 行内 name key、`mission_event` 行内 event_name key、`normal_activity` 行内 name/chapter_name key |
| 类型索引 | `dataMiner/derived/enemy_full_model.csv` | type_id → codex_no / faction_name / boss / capturable（**只做映射与标签，不展示技能列**） |
| 等级缩放 | `unit_model.core.enemy.enemy_attributes(type_id, level, scale_by_level=True)` | 展示用实际数值（660011 实测口径） |

注意：`spot.enemy_team_id` 有的 mission_id 不在 mission 表（例 404101）→ 归「特殊作战」或忽略都可，
但不要崩。`mission.boss_team_id` 是 `"2152;0"` 这种分号/逗号串，需拆分。
`spot.ally_team_id` 是**支援队伍**（同一 mission 的友方支援编队）：有槽位即收，可收藏/不可收藏都收，
与敌方队伍分开展示（stage.support_teams）；支援链接也要计入队伍出处与 roles，不能当 orphan。

**机场/后续刷新候选**：STC 没有显式的 mission→刷新池字段/表（`spot_buff_config.grow_enemy_pool`
只是布尔、`mission_entrance_package` 是旧关卡串），AA-02/威廉/潘洛斯 Boss 等队伍没有任何 spot/mission
引用，属于运行时刷新池。catalog 只能按 **team id 族**推断 `reserve_teams`（明确标 `inferred:true`）；
推断链接不算真实出处（不改变 orphan/roles、不计入 team_count/support_team_count）。

### 2.2 归类规则

1. `campaign == -404` → 灰域（chapter id `"grayzone"`，category `"grayzone"`）。
2. `-10006 <= campaign <= -10000` → 教学（category `"tutorial"`），按 campaign 一章，标题取首个
   `mission` 名冒号前部分（如「人形教学」）。
3. `campaign in 0..13` 且 mission id < 90000 且 `map_res_name` 不以 `Moni` 开头 →
   主线（category `"main"`），chapter id `f"main-{campaign}"`，标题 campaign==0 ? `"序章"` : `f"第{campaign}章"`。
4. mission id >= 90000 且 campaign >= 0 → 往期活动复刻（category `"rerun"`），
   chapter id `f"rerun-{campaign}"`，标题 `f"往期活动·第{campaign}章"`。
5. `map_res_name` 以 `Moni` 开头（模拟作战/靶场）且有关卡队伍 → category `"simulation"`，
   chapter id `"simulation"`，标题 `"模拟作战·靶场"`（通常 6 关）。
6. 负 campaign（其它）→ 活动（category `"event"`）：
   `normal_activity` 有 → 标题=chapter_name，副标题=活动 name；
   否则 `mission_event` → 标题=活动名；否则 category `"special"`，标题 `f"特殊作战 {campaign}"`，
   副标题取本章第一个关卡标题。
7. 其余（含 campaign 14 等无关卡队伍的 campaign 不产生章节）。
8. 敌方（`spot.enemy_team_id` ∪ `mission.boss_team_id`）与**支援**（`spot.ally_team_id`，需有槽位）
   都没有链接的可收藏队伍 → category `"orphan"`，chapter id `"orphan"`，标题 `"无固定关卡"`
   （灰域/随机/往期事件队伍都在这；chapter 详情里直接带分页 teams）。支援队伍不再落入 orphan。
9. `spot` 里缺失 mission 表的 orphan mission_id（例 404101）归入 event 的「特殊作战·未知」章节。
10. 队伍↔关卡：敌方链接（enemy/boss）与支援链接（ally）都进 `appearances`（带 role）；stage 的
    `teams`/`team_count` 只表示敌方，支援队伍单独放 `support_teams`/`support_team_count`，互不混淆。
11. `reserve_teams`（推断）：每个 stage 取已引用队伍（enemy∪ally∪boss，排除 id<=1000）中出现最多的
    `str(id)[:4]` id 族前缀（需 ≥3 个引用），候选 = 同前缀、有槽位、可收藏、未被该 mission 引用的队伍
    （id 升序，≤80）。stage 详情带 `reserve_teams`（team_summary + `role:"reserve"`、`inferred:true`、
    `reserve_reason`）与 `reserve_team_count`；章节 stage 行只带 `reserve_team_count`。

排序：组顺序 main → event → **score** → tutorial → simulation → grayzone → orphan；
组内章节按 `min(mission.order/id)` 升序。**groups 共 7 个，章节约 121 个**
（main 14 / event 73 / score 25 / tutorial 6 / simulation 1 / grayzone 1 / orphan 1）。

- `score`（积分关卡）：**mission 级**判定，`mission.event_score` 非空即积分关卡（结算配置，权威字段；
  不是名字带 `+`）。同一 campaign 里只有部分任务是积分关卡时会拆成 score 章 + event 章（例：思域迷航 -61，
  禁止喂食/禁止喂食EX 进 score，其余 20 关留 event）；全积分 campaign（贝蒂数 / 终焉花海+ / 自画像 /
  -77 静默沙盘 …）只生成 score 章。章节标题用活动名，subtitle = 所属大活动 + 「积分关卡」。
- 原 `rerun`/`special` 全部并入 `event`，不再单独分组；event 章节 id 用 `event-{campaign}`（不跨 campaign 合并），
  subtitle/tags 标「往期复刻 · 第N章」「往期活动」等，保证搜索能命中活动名与副标题。
- 关卡结算形式结构化：每个 stage 带 `settlement`（event_score / score_prize / rank），见 §2.3。
- 灰域区域层级（v1.7）：真实区域来自 `daily_mission_group`（mission→difficulty_group）+
  `daily_mission_difficulty_group`，固定 **5 个区域**：
  沙尘带（组1）/ 风暴带（组2）/ 硅状带（组3）/ 结晶带（组4）/ **特殊区域**（组5+6+未映射，
  客户端无区域名，不编造）。组 5/6 的节点数 286/12、未映射 28，都归特殊区域。
- 灰域 **14 个地点**（原 mission 标题前缀去编号/空格）：共生净土/晶团挖掘点/旅团商道/放射区/
  人形复制工厂/废弃居民区/秘密通道/图腾圣所/装甲突击/交易地/地坛遗迹/最终贮藏地/庇护所旧址/坍缩狭缝；
  地点带 `region_ids`（该地点涉及的区域；如 共生净土 跨全部 5 个区域，装甲突击/最终贮藏地只在特殊区域）。
- `spot` 里缺失 mission 表的 mission_id（例 404101）归入 event 的「特殊作战·未知」章节。

### 2.3 返回结构（前端直接消费）

```jsonc
// GET /api/chapters
{"built_at": "...", "counts": {"chapters":121,"stages":2345,"teams":13700,"support_teams":864,"species":264},
 "groups": [
   {"id":"main","title":"主线","chapters":[...]},
   {"id":"event","title":"活动","chapters":[...]},
   {"id":"score","title":"积分关卡","chapters":[...]},
   {"id":"tutorial","title":"教学","chapters":[...]},
   {"id":"simulation","title":"模拟作战","chapters":[...]},
   {"id":"grayzone","title":"灰域探查","chapters":[...]},
   {"id":"orphan","title":"无固定关卡","chapters":[...]}
 ]}

// GET /api/chapters/{id}
{"chapter": {...同上}, "stages":[...]}
// grayzone chapter: stages 为空；subtitle "5 个区域 · 14 个地点 · 1288 个节点"；
//   regions=[{"id":"sand","title":"沙尘带","groups":[1],"stage_count":228,"team_count":579,
//             "species_count":39,"source":"daily_mission_difficulty_group-10000001","note":""},
//            ... 5 个（special: groups [5,6], source:null, note:「客户端无区域名…」）]
//   areas=[{"id":"共生净土","title":"共生净土","region_ids":["sand","storm","silicon","crystal","special"],
//           "stage_count":240,"team_count":1104,"species_count":23},...14 个地点]
// orphan chapter: stages 为空，直接返回分页 teams：
//   GET /api/chapters/orphan?offset=0&limit=60&q=
{"chapter":{...}, "stages":[], "teams":[team_summary...], "teams_total":3802, "offset":0, "limit":60}
// orphan 只保留敌方+支援都无链接的可收藏队伍（支援链接也会把队伍从 orphan 拉出来）

// team_summary（列表里到处用）
{"id":6549244,"power":113600,"power_known":true,"units":9,"hp_total":164238,
 "faction":"铁血","tags":["BOSS","满力场"],"roles":["enemy"],"collectable":true,
 "species":[{"codex_no":5,"name":"稻草人","icon":"scarecrow.png"},...最多8个],
 "members":[{"code":"Aegis_GA","name":"圣盾_GA","icon":"aegis_ga.png","number":5,"count":3},...最多6组],
 "gray_zone":false,"orphan":false,
 "stage": {"chapter_id":"main-1","title":"第1章","stage_title":"演习训练","code":"1-1"} | null}
// roles: ["enemy"] / ["support"] / ["enemy","support"]（v1.4 支援队伍链接）

// GET /api/stages/{id}
{"stage":{..., "team_count":30, "support_team_count":17, "reserve_team_count":16, "settlement": {
   "type":"score|normal",
   "event_score":{"mode":"1","params":24}|null,      // 积分结算配置（非空即积分关卡）
   "score_prize":{"raw":"1-0|110054:1","tiers":1}|null, // 积分奖励
   "rank":{"id":306,"name":"终焉花海PLUS常驻","title":"<终焉花海+>常驻积分榜",
           "type":10,"score_rewards":""}|null       // 常驻积分榜（rank 表）
 }}, "teams":[team_summary,...],                      // 敌方队伍（不含支援）
 "support_teams":[{...team_summary, "role":"support", "support_count":1,
                   "collectable":true},...],          // 支援队伍（spot.ally_team_id，v1.4）
 "support_team_count":17,
 "reserve_teams":[{...team_summary, "role":"reserve", "inferred":true,
                   "reserve_reason":"同系列未入场怪组（机场/后期刷新候选，STC 无显式映射）"},...],
 "reserve_team_count":16}                             // 机场/后续刷新候选（推断，v1.5）
// team_count 只算敌方；support/reserve 数量互不影响。
// 章节详情 /api/chapters/{id} 的每个 stage 行带 team_count / support_team_count / reserve_team_count。
// 积分关卡判定依据（不是名字带 +）：mission.event_score 结算配置；score_prize 为积分奖励；
// rank 表 type=10 行是「<活动名>常驻积分榜」，sub_type 直接列 mission id（type=6 为活动积分榜）。
// 分析工具：python targetforge/tools/analyze_score_stages.py [--json]

// GET /api/teams/{id}（详情）
{"id":6549244,"power":113600,"power_known":true,"units":9,"hp_total":164238,"faction":"铁血",
 "tags":["BOSS"],"roles":["enemy"],"collectable":true,"gray_zone":false,"orphan":false,
 ...
 // 出处：敌方与支援都在 appearances 里，role 标 "enemy"/"support"；reserve 推断条目
 // role="reserve"、inferred=true（「可能刷新」，不改变 orphan），同关多角色时 roles 有多个
 "appearances":[{"mission_id":11435,"chapter_id":"score--60","chapter_title":"谜境守卫+",
                 "stage_title":"谜境守卫+","code":"-60-1","difficulty":32000,
                 "gray_zone":false,"role":"support","roles":["support"]},...最多24],
 "species":[{"codex_no":5,"name":"稻草人","faction":"铁血","type":1,"icon":"scarecrow.png"}],
 "members":[{"type_id":11028,"code":"Aegis_GA","name":"圣盾_GA","codex_no":15,"icon":"aegis_ga.png",
   "level":140,"number":5,"count":3,"def_percent":0,"batch":0,"x":8.0,"y":0.0,
   "stats":{...}}]}

// GET /api/species?q=&faction=&category=&offset=&limit=
{"total":264,"items":[{"codex_no":5,"name":"稻草人","faction":"铁血","type":1,
  "icon":"scarecrow.png",
  "team_count":20,"normal_team_count":14,"gray_zone_team_count":6,"orphan_team_count":3,
  "has_normal":true,"has_grayzone":true,"has_orphan":true,"capturable":true,
  "tags":["契约捕获"]}]}
// category: normal|grayzone|orphan 为「出现在该场景」的非互斥过滤（grayzone 约 66 个，含法官）

// GET /api/species/{codex_no}?offset=&limit=&q=&power_min=&power_max=&power_known=&sort=
{"species":{...},"total":N,"offset":0,"limit":60,"teams":[...分页 team_summary...]}

// GET /api/grayzone/areas -> {"regions":[{"id":"sand","title":"沙尘带","groups":[1],"stage_count":228,
//    "team_count":579,"species_count":39,"source":"daily_mission_difficulty_group-10000001","note":""},...
//    5 个：沙尘带/风暴带/硅状带/结晶带/特殊区域（special source:null, note 说明无客户端名称+未映射）],
//  "areas":[{"id":"共生净土","title":"共生净土","region_ids":["sand",...,"special"],
//            "stage_count":240,"team_count":1104,"species_count":23},...14 个地点]}
// GET /api/grayzone/teams?area=&region=&offset=&limit=&q=&power_min=&power_max=&power_known=&sort=
//   region: 沙尘带/风暴带/硅状带/结晶带/特殊区域（也接受 sand/storm/silicon/crystal/special、组号 1..6）
//   -> {"total":789,"offset":0,"region":"crystal","items":[team_summary...]}
// sort: default|power_desc|power_asc|hp_desc|units_desc；power_known=1 只看有标注效能的队伍
// GET /api/icons/{icon} -> PNG（怪种/单位头像，来自本机游戏资源，缺失 404）
// GET /api/search?q= -> {"teams":[team_summary],"stages":[{id,title,code,chapter_title}],"species":[...]}
```

### 2.4 可收藏怪种口径

- 怪种 = `enemy_illustration.id`（= codex 编号）；264 个 = 所有出现在「可收藏且有效」队伍里的 codex。
- `enemy_full_model.csv` 的 `codex_no` 映射 type→codex；名称用 `enemy_illustration` 行的文本 key 解析。
- `has_normal` / `has_grayzone` / `has_orphan` = 该怪种在对应场景是否有可收藏队伍（**非互斥**）：
  灰域过滤应返回约 66 个怪种（含 法官 codex 35），而不是只返回「只在灰域出现」的 4 个。
- 头像：`dataMiner/derived/targetforge/icons/<code>.png` 由 `tools/build_icons.py` 从本机游戏
  `character<code>.ab` 的 `pic_<Code>_SS` 纹理导出；catalog 扫描该目录填 `icon`（缺失为 null，前端退化）。
- 队伍 13700 条（有编制的可收藏队伍），只做展示，不做注入合法性以外的过滤。
- **支援队伍口径（v1.4）**：`spot.ally_team_id` 指向的友方支援编队，有槽位即收（全局 864 支，
  其中 818 可收藏）；`counts.support_teams`=864。支援队伍出现在 stage.support_teams（带
  role/support_count/collectable），也可通过 team 详情反查出处（role=support），不计入敌方
  `teams`/`team_count`。不可收藏的支援队伍只在 stage.support_teams 里展示（`collectable=false`），
  不进 `team()` 查询与序列。
- **机场/后续刷新候选（v1.5）**：STC 无显式刷新池映射，按 team id 族推断的 `reserve_teams`
  明确标 `role="reserve"`、`inferred=true`、`reserve_reason`；全局 1637 个 stage 有候选。
  推断条目只用于展示「可能刷新」，**不改变 orphan/roles 真实链接状态**，也不计入
  `team_count`/`support_team_count`；team 详情 appearances 里同样以 `role="reserve"`、
  `inferred=true` 呈现（不当作真实出处）。
- 效能：`power` 来自 `enemy_team.effect_ext`；`power_known=false` 表示客户端未标注（常规关卡绝大多数如此），
  只有积分关卡/部分特殊队伍有值（含负值）。**不要伪造公式反推。**
- **不要输出 enemy_full_model 的技能列**，也不要在详情里放 skill/group 字段。

### 2.5 team_list（全怪组总表，v1.6）

`GET /api/teams`（app.py 路由）→ `catalog.team_list(...)`。纯内存筛选/排序/分页，
13,700 支队伍单次查询 **<100ms**（加载时已预计算每队的 species codex 集合 / 章节集合 /
搜索快照）。

参数（全部可选）：

| 参数 | 说明 |
|---|---|
| `q` | 队伍 id 子串 / 阵营 / 怪种名称 / 成员 code·name / tags（不区分大小写） |
| `chapter` | 章节 id 精确匹配（如 `score--60`、`event--61`、`grayzone`）；队伍在该章节有**任意 role**（敌方/支援/机场推断）出现即命中；`orphan` 表示无固定关卡章节 |
| `species` | codex_no 列表（list 或逗号串，如 `5,12`），**AND**：队伍包含全部指定怪种 |
| `role` | `enemy` / `support` / `reserve` / `any`（默认 any）；reserve = 有推断候选 appearance 的队伍 |
| `collectable` | bool，默认 `true`（只可收藏队伍）；`false` 时返回不可收藏的支援队伍（46 支） |
| `power_known` | bool（effect_ext != 0） |
| `power_min` / `power_max` | 含边界 |
| `units_min` / `units_max` | 单位数 = 成员 count 合计（与 team_summary.units 一致） |
| `sort` | `id_asc`（默认）/ `id_desc` / `power_desc` / `power_asc` / `units_desc` / `units_asc` / `hp_desc` / `species_desc`；稳定排序（同值按 id 升序），效能未知在效能排序时排最后 |
| `offset` / `limit` | 默认 0/50，`limit` 上限 200 |

返回：

```jsonc
{"total": 13700, "offset": 0, "limit": 50, "sort": "id_asc",
 "items": [{
   "id":6363006, "power":673555, "power_known":true, "units":24, "hp_total":1075993,
   "faction":"军方", "roles":["support"], "collectable":true, "orphan":false,
   "species":[{"codex_no":50,"name":"...","icon":"..."}],
   "appearances":[{"mission_id":11435,"chapter_id":"score--60","chapter_title":"谜境守卫+",
                   "stage_title":"谜境守卫+","role":"support","inferred":false},...最多60],
   "appearance_count":1,                    // 总出处数（含推断；appearances 截断到 60）
   "chapter_titles":["谜境守卫+"]}          // 去重后的章节标题
 ]}
```

---

## 3. gflh.py 契约（gflh 任务实现）

```python
MAX_TARGETS = 35
DEFAULT_CREDS = ROOT/"dataMiner/derived/targetforge/creds_latest.json"   # 随 TARGETFORGE_DATA_DIR 变化，见 datapaths.py
CAPTURE_PORT = 18080   # 默认端口；可配置（别用 8080，另一个 bot 占用）
STATIC_KEY = "yundoudou"
API_ADD = "Targettrain/addCollect"; API_DEL = "Targettrain/delCollect"

def player_status() -> dict
# {"game_running":true,"pid":12345,"game_window_title":"少女前线",
#  "system_proxy":"127.0.0.1:18080"|None,"gflzirc_ok":true}

def capture_status() -> dict
# {"state":"idle|starting|running|stopped|error","port":18080,
#  "proxy_active":bool,"system_proxy_on":bool,"auto_restore_proxy":bool,
#  "uid":"100000001"|None,"sign_set":true,"base_url":"...",
#  "targets_count":30,"login_captured":true,"targets_captured":true,
#  "started_at":iso|null,"elapsed_s":12.3,"creds_path":null,
#  "logs":[{"t":iso,"level":"info|warn|error","text":"..."}...最多200]}
def capture_start(*, port: int = CAPTURE_PORT, set_proxy: bool = True,
                  auto_restore_proxy: bool = True) -> dict  # 端口可配置，默认 18080
def capture_stop() -> dict    # 停代理 + 恢复系统代理 + 写 creds_latest.json
def capture_restart_game() -> dict
# 要求 capture 正在运行：设置系统代理 → taskkill GrilsFrontLine.exe → steam://rungameid/3347970
# 返回 {"ok":true,"steps":["设置系统代理 127.0.0.1:<当前抓包端口>","强杀游戏","重新启动游戏"],"hint":"..."}

def list_creds() -> list[dict]  # [{name,path,updated_at,uid,base_url,targets_count}]（不返回 sign）
def current_targets(source: str = "auto") -> dict
# source: auto|creds|state
# {"source":"creds","creds_file":"creds_latest.json","uid":"100000001",
#  "base_url":"http://...", "captured_at":"...","targets":[{"order":1,"team":770007},...],
#  "duplicate_orders":{"3":[a,b]}, "max_targets":35, "warnings":["..."]}

def plan(mode: str, draft_team_ids: list[int], *, current: dict, max_targets: int = 35) -> dict
# mode: append|replace|rebuild|clear
# {"mode":"replace","deletes":[{"order":1,"team":770007}],"adds":[{"order":1,"team":6549244}],
#  "kept":[{"order":6,"team":123}],"skipped":[{"team":x,"reason":"..."}],
#  "final":[{"order":1,"team":6549244}],"warnings":["..."],"valid":true,
#  "payloads":{"add":[{"enemy_team_id":..,"fight_type":0,"fight_coef":"","fight_environment_group":"","order_id":..}],
#              "del":[...]}}

def execute(mode: str, draft_team_ids: list[int], *, creds_file: str | None = None,
            dry_run: bool = False, log=None, cancel=None) -> dict
# 同步执行（app.py 放线程池跑）。log(level, text)；cancel() -> bool。
# 返回 {"ok":true,"mode":..,"deleted":n,"added":n,"failed":[{"step","team","error"}],
#       "final":[{"order","team"}],"creds_file":"...","restart_required":true}
# 内部使用 scripts/gflh_target_train.py 的 add_payload/del_payload/plan_add/update_state，
# 本地状态写 dataMiner/derived/target_injection_state.json（复用现有逻辑，别重复实现）。

def restart_game(*, wait_ready: bool = True) -> dict  # 大退重登（无代理）
def set_system_proxy(enable: bool, addr: str = f"127.0.0.1:{CAPTURE_PORT}") -> dict
```

规则：
- **不自动联网/不碰游戏进程**，除非对应 endpoint 被调用。
- 测试必须 mock `GFLClient`/`GFLProxy`/`subprocess`，禁止真的启代理/杀游戏。
- 错误提示要带可操作建议（error:300 → 「队伍不可收藏或重复」；sign 过期 → 「重新登录抓取」）。
- capture 抓到 `Index/index` 的 `targettrain_collect_user_info` 后落 `creds_latest.json`：
  `{"uid","sign","base_url","enemies":[...],"orders":[...],"urls":[...],"captured_at":iso}`。
- 依赖 `gflzirc`（系统 Python 已装 0.4.4）：`from gflzirc import GFLClient, GFLProxy, set_windows_proxy`。

---

## 4. app.py 路由（Lead 实现，前端按这个写）

静态：`/` → `static/index.html`，`/static/...` 原样。

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/health` | 应用/数据/game/gflzirc 状态 |
| GET | `/api/chapters` | 章节分组 |
| GET | `/api/chapters/{id}` | 章节详情 + 关卡（灰域返回 areas） |
| GET | `/api/stages/{mission_id}` | 关卡 + 队伍列表 |
| GET | `/api/teams` | 全怪组总表（q/chapter/species/role/power/units/sort/offset/limit，见 §2.5） |
| GET | `/api/teams/{team_id}` | 队伍详情 |
| GET | `/api/grayzone/areas` | 灰域层级：5 个区域 + 14 个地点（含 region_ids） |
| GET | `/api/grayzone/teams?area=&region=&offset=&limit=&q=` | 灰域队伍分页（地点/区域筛选） |
| GET | `/api/species?q=&faction=&category=&offset=&limit=` | 怪种列表 |
| GET | `/api/species/{codex_no}` | 怪种 + 所有队伍 |
| GET | `/api/search?q=` | 全局搜索 |
| GET | `/api/current?source=auto` | 当前靶机（真实列表） |
| GET | `/api/creds` | 可用凭证列表 |
| GET | `/api/player` | 游戏进程/系统代理状态 |
| GET | `/api/sequence` | `{"draft":[team_summary...],"count":n,"max":35,"updated_at":...}` |
| POST | `/api/sequence` | `{"action":"add|add_many|remove|move|set|clear|import_current","team_id"|"team_ids"|"from"|"to"}` |
| POST | `/api/execute/preview` | `{"mode":"append|replace|rebuild|clear","source":"auto|creds|state"}` → plan |
| POST | `/api/execute` | 同上 + `{"dry_run":bool,"creds_file":...}` → `{"job_id":...}` |
| GET | `/api/jobs/{job_id}` | `{"id","kind","state":"running|done|error","logs":[...],"result":...,"error":...}` |
| POST | `/api/jobs/{job_id}/cancel` | 取消 execute |
| GET | `/api/capture/status` | |
| POST | `/api/capture/start` | `{"port":18080,"set_proxy":true,"auto_restore_proxy":true}` |
| POST | `/api/capture/stop` | |
| POST | `/api/capture/restart_game` | 设置代理并重启游戏（抓 sign 用） |
| POST | `/api/creds/load` | `{"name":"creds_xxx.json"}` 复制为 creds_latest.json 并返回 current_targets |
| POST | `/api/game/restart` | 注入后大退重登 |
| POST | `/api/catalog/refresh` | 后台重建 catalog → job |
| GET/POST | `/api/tutorial` | `{"completed":[step_id...],"dismissed":false}` |
| GET/POST | `/api/settings` | capture_port / auto_restore_proxy / preferred_creds |
| GET | `/api/meta` | 版本、数据时间、数量 |

错误统一：HTTP 4xx/5xx + `{"error":"人类可读","detail":"...","hint":"..."}`。
所有接口本地绑定 127.0.0.1；`/api/*` 返回 JSON UTF-8，`Cache-Control: no-store`。
