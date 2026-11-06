# GFLH Advance · 靶机工坊 (TargetForge)

把《少女前线》里**任意「可收藏」的敌方队伍**，可视化地编排进游戏内「靶机专训 → 收藏标靶」（最多 35 条）。
本项目是靶机工坊的应用本体：本地 Web 服务 + 数据层 + GFLH 登录抓取 / 注入模块 + 完整前端。

> **本仓库只包含应用代码与文档，不含任何游戏数据、账号凭证、日志或缓存。**
> 运行需要配合 [GF Forge](#前置依赖) 主仓库（提供本机 STC 数据解析与 GFLH 协议脚本）以及本机安装的游戏客户端。

![总览：深蓝星空 + 大蓝闪蝶](docs/screenshots/overview.jpg)

| 关卡图鉴：7 组 121 章（含积分关卡） | 怪种图鉴：每只怪都有真实头像 |
|---|---|
| ![关卡图鉴](docs/screenshots/chapters.jpg) | ![怪种图鉴](docs/screenshots/species.jpg) |

| 效能筛选：有标注 / 自定义区间 / 5 种排序 | 队伍详情：数值 / 参数 / 出处（不含技能） |
|---|---|
| ![效能筛选](docs/screenshots/power-filter.jpg) | ![队伍详情](docs/screenshots/team-detail.jpg) |

| 执行预览：删除 / 新增 / 保留 / 最终列表 | 使用教程：概念 / 流程 / FAQ / 安全 |
|---|---|
| ![执行预览](docs/screenshots/execute-preview.jpg) | ![使用教程](docs/screenshots/tutorial.jpg) |

![灰域探查：14 个区域](docs/screenshots/grayzone-areas.jpg)

| 积分结算：关卡行徽标 + tooltip | 关卡队伍页：结算形式（event_score / 积分奖励 / 积分榜） |
|---|---|
| ![积分结算](docs/screenshots/score-settlement.jpg) | ![结算形式](docs/screenshots/score-teams.jpg) |

| 谜境守卫+：敌方 30 · 支援 17 + 机场候选（推断） | 按怪组编号搜索并加入序列 |
|---|---|
| ![关卡队伍](docs/screenshots/stage-teams.jpg) | ![编号搜索](docs/screenshots/search-team.jpg) |

| 本怪组出现位置（支援队 6363006 → 谜境守卫+） | 侧栏高亮滑块（切换平滑移动） |
|---|---|
| ![本怪组出现位置](docs/screenshots/team-appearances.jpg) | ![侧栏高亮](docs/screenshots/sidebar-highlight.jpg) |

## 功能

- **关卡图鉴**：**7 组 121 章 2345 关**——主线 / 活动（含往期复刻、特殊作战）/ **积分关卡** / 教学 / 模拟作战 / 灰域探查 / 无固定关卡。
  积分关卡按 `mission.event_score` **结算配置**精确标记，混合活动会单独拆章（如「思域迷航 · 积分关卡：禁止喂食 / 禁止喂食EX」）；
  章节卡 → 关卡列表 → 该关可收藏队伍，支持「整关全部加入序列」。
- **结算形式**：每个关卡显示结算类型——**积分结算**（`event_score` 模式/参数数量、`score_prize` 积分奖励、`rank` 常驻积分榜）
  或**普通结算**；由 STC 结算字段决定，不靠名字/加号猜。可用 `targetforge/tools/analyze_score_stages.py` 复跑分析。
- **支援队伍（每关不同）**：把 `spot.ally_team_id` 的支援梯队按归属关系并入对应关卡队伍列表
  （顶部显示「敌方 X · 支援 Y」，支援卡带「支援队伍」徽标，同样可加入序列）；队伍详情新增
  **「本怪组出现位置」**，同一怪组在多个关卡以敌方/支援身份出现时全部列出
  （如谜境守卫+ 的支援队 6363006，效能 673,555、24 单位）。
- **机场/后续刷新候选（推断）**：关卡队伍列表下方默认折叠展示「可能刷新 N 支」候选，卡带「机场可能刷新（推断）」
  徽标，可展开/加入序列。STC 没有显式机场刷新池映射，候选按**同关卡队伍 id 族**推断
  （如谜境守卫+ 的 AA-02 队 6363057/6363060、静默沙盘的威廉队 770060、潘洛斯的 Hebe/Styx 660002/660003）。
- **按怪组编号搜索/加入**：顶栏全局搜索输入 `6363006` / `#6363006` 直接出队伍结果卡并可加入序列；
  序列页/序列面板也有「按编号加入」输入框。
- **怪种图鉴**：264 个图鉴怪种，每只怪都有从**本机游戏资源提取的真实头像**（透明底 160px）；
  按阵营 / 固定关卡 / 灰域 / 无固定关卡筛选（筛「灰域」得到所有在灰域出现过的怪种，含灰域 BOSS）；
  怪种详情列出所有怪组并分页。
- **灰域（打灰）**：不逐节点列举关卡，折叠为 **14 个区域**，区域内直接分页浏览队伍（单个区域最多 1104 支）。
- **效能筛选/排序**：灰域队伍、关卡队伍、怪种详情、无固定关卡、当前靶机都支持按怪组效能筛选与排序
  （全部 / 有标注 / 自定义区间；效能↓↑ / 总血↓ / 单位数↓）。客户端只有积分关卡/部分特殊队伍带效能，
  其余显示「未标注」（不伪造数值）。
- **队伍详情**：效能、单位数、总血、关卡出处、参数；单位聚合表（等级 / 编制 / 数量 / 防御修正 / 坐标 /
  HP / 火力 / 命中 / 回避 / 护甲 / 穿甲 / 射程 / 移速 / 护盾 / 力场）。**不展示任何技能信息。**
- **序列编排**：加入 / 移除 / 拖拽排序 / 从当前靶机导入；上限 35，实时显示总单位 / 总血量。
- **执行注入**：先预览（删除 / 新增 / 保留 / 最终 1..N 列表 + 警告），支持
  `追加（append）` / `按序号替换（replace）` / `清空重排（rebuild）` 三种模式 + 清空全部 + 演练模式（dry-run，不联网）；
  执行过程有 job 日志，完成后引导大退重登，并提供「重启游戏」按钮（二次确认）。
- **登录抓取**：内置向导启动本地抓包代理（端口可配置，默认 18080）→ 设置系统代理并重启游戏 →
  抓取 uid / sign / 当前靶机 → 关闭代理；也可加载历史凭证列表。
- **教程**：首次进入自动 6 步新手引导；教程页含概念、完整流程、抓取分步、三种执行模式、11 条 FAQ、安全须知。

数据规模（以当前国服客户端为例）：7 组 121 章（活动 73 + 积分关卡 25）/ 2345 关 / 13,700 支可收藏队伍 / 264 个可收藏怪种 /
灰域 14 区域 3352 队 / 无固定关卡 4381 队（含支援队伍后 3802 队）/ 支援梯队 864 支（818 可收藏，329 个关卡有支援链接）/
机场/后续刷新候选（推断）1637 个关卡有候选、覆盖 5461 支同系列未入场队伍。

## 前置依赖

| 依赖 | 说明 |
|---|---|
| Windows 10/11 | 抓包 / 游戏控制 / winreg 代理设置目前是 Windows 实现 |
| Python 3.14 | 运行 `python -m targetforge`；需 `gflzirc>=0.4.4`（`python -m pip install gflzirc==0.4.4`） |
| GF Forge 主仓库 | 提供 `unit_model/`（STC 二进制表解析、等级缩放口径）、`scripts/gflh_target_train.py`（编号规划 / payload / 本地状态）、`dataMiner/derived/client_text.json` 与 `enemy_full_model.csv` 等派生数据 |
| 本机游戏客户端 | 《少女前线》PC 版（Steam appid **3347970**）；路径写入 GF Forge 的 `local_paths.json` 或环境变量 `GF1_GAME_ROOT` |
| 端口 | 应用 **8765**；抓包代理默认 **18080**，可在「登录抓取 → 抓包端口」配置（8080 常被其它程序占用，不建议用） |
| 可选 | UnityPy + Pillow（导出小怪头像 `tools/build_icons.py`）、Playwright + Edge（页面自检） |

## 安装

```powershell
# 1) 克隆本仓库
git clone https://github.com/TenshiInHeaven/gflh_advance.git

# 2) 把 targetforge/ 整体复制到 GF Forge 仓库根目录，形成 <GF_FORGE_ROOT>\targetforge\...
xcopy /E /I gflh_advance\targetforge <GF_FORGE_ROOT>\targetforge

# 3) 安装依赖（已装可跳过）
python -m pip install gflzirc==0.4.4

# 4) 自检（可选）
cd <GF_FORGE_ROOT>
python -m unittest discover -s targetforge/tests -t .
```

> 也可以直接把本仓库克隆成 `<GF_FORGE_ROOT>\targetforge`：
> `git clone https://github.com/TenshiInHeaven/gflh_advance.git "<GF_FORGE_ROOT>\targetforge_tmp"`，
> 再把 `targetforge_tmp\targetforge` 移到 `<GF_FORGE_ROOT>\targetforge`。

## 运行

```powershell
cd <GF_FORGE_ROOT>
python -m targetforge                 # http://127.0.0.1:8765
python -m targetforge --open          # 顺便打开浏览器
python -m targetforge --port 8771     # 换端口
python -m targetforge --rebuild-catalog   # 强制重建数据缓存
```

首次启动会解析本机 STC 生成数据缓存（约 4 秒，约 7 MB），之后直接读缓存（<1 秒）。
游戏更新后点顶栏「刷新数据」或加 `--rebuild-catalog`。

**导出小怪头像（可选）**：界面对每个怪种/单位都有头像；头像由本机游戏资源提取，未随仓库分发：

```powershell
# 需要 UnityPy（GF Forge 的 .sim 环境自带）
.\.sim\Scripts\python.exe targetforge\tools\build_icons.py
# 导出后再重建一次 catalog，让 icon 字段进缓存
python -c "from targetforge import catalog; catalog.build(force=True)"
```

没有导出/缺失的头像会自动退化为按阵营着色的虫/机甲/首领/人形剪影。

## 使用流程（简版）

1. **登录抓取**：页面左侧「登录抓取」→ 开始抓取 →「设置代理并重启游戏」→ 在游戏里登录进主界面 →
   等状态出现 uid / sign / 当前靶机 →「完成并关闭代理」。（sign 每次登录都变，过期需重抓）
2. **挑队伍**：关卡图鉴（选关卡 → 选队伍）或怪种图鉴（选怪种 → 选怪组）→「加入序列」。
3. **编排**：右侧序列面板 / 序列编排页拖拽排序（上限 35）。
4. **执行**：执行向导 → 选择模式 → 先「演练模式」看 payload 预览 → 正式执行 → 完成后**大退重登游戏**，
   游戏内「靶机专训 → 收藏标靶」查看。

### 三种执行模式

| 模式 | 语义 |
|---|---|
| 追加 `append` | 保留现有靶机，草稿按顺序接在已有最大 `order_id` 后面；已在列表里的队伍自动跳过 |
| 按序号替换 `replace` | 草稿第 i 个换成「收藏標靶 i」；草稿比现有长则追加到末尾，现有比草稿长则保留；若草稿队伍已存在于其它编号会先删旧项避免重复 |
| 清空重排 `rebuild` | 先删光现有靶机，再按草稿 1..N 全量 `addCollect`（编号最干净，推荐一次配好整套） |

另有独立的「清空全部」（危险操作，二次确认）。执行完必须大退重登同步；清空靶机后要强退，否则进靶机界面可能卡死。

## 数据与安全

- 所有关卡 / 怪种 / 怪组数据都来自**本机客户端 STC 静态表**，应用离线运行；本仓库不含这些数据。
- 数据目录默认是 **GF Forge 仓库下的 `dataMiner/derived/targetforge/`**（由 `datapaths.py` 按模块位置计算，
  不是写死的绝对路径）；可用环境变量 `TARGETFORGE_DATA_DIR` 指定到别处，缓存 / 凭证 / 状态 / 头像都会跟着走。
- 应用只监听 `127.0.0.1`，不上传任何数据。
- 抓到的 `uid/sign` 只保存在数据目录下的 `creds_latest.json`（不入 git），**请勿提交或外传**。
- 抓包端口可配置（登录抓取页，默认 `18080`）；请确保使用完毕后系统代理已关闭。
- 游戏进程 PID 由 Windows `tasklist` 按进程名 `GrilsFrontLine.exe` **搜索**得到，顶栏 PID 仅本机展示，不是写死的。
- 本工具仅用于本地研究与学习；请遵守游戏服务条款，避免在主账号 / 线上环境滥用。产生的风险由使用者承担。

## 验证

```powershell
python -m unittest discover -s targetforge/tests -t .      # 130 个单测（app / catalog / gflh）
python targetforge/tools/api_smoke.py --url http://127.0.0.1:8765   # 真实数据 API 冒烟（29 项）
python targetforge/tools/ui_selfcheck.py --url http://127.0.0.1:8765 # Playwright 页面自检 + 22 张截图
python targetforge/tools/analyze_score_stages.py          # 积分关卡结算依据分析（event_score / score_prize / rank）
```

前端自检结果：177 项 DOM 断言通过，console error / page error 均为 0。

## 目录

```text
gflh_advance/
  README.md                    本文件
  LICENSE                      MIT
  docs/screenshots/            README 用截图
  targetforge/                 复制到 GF Forge 仓库根目录后的模块
    app.py                     HTTP 服务 / 路由 / 序列状态 / 后台 job / 头像接口
    catalog.py                 STC → 章节 / 关卡 / 怪种 / 怪组数据层（缓存 + 查询 + 效能/图标）
    gflh.py                    登录抓取（GFLProxy）/ 序列规划 / 注入（addCollect·delCollect）/ 游戏控制
    datapaths.py               数据目录唯一来源（支持 TARGETFORGE_DATA_DIR）
    static/                    前端（原生 HTML/CSS/JS，无构建步骤，离线）
    tests/                     unittest（app / catalog / gflh）
    tools/                     build_icons.py（游戏资源导出小怪头像）/ analyze_score_stages.py（结算分析）/
                               api_smoke.py / ui_selfcheck.py / screenshot.py
    contract.md                模块 / API 契约
    README.md                  应用层说明
```

## 常见问题

- **8080 端口被占**：抓包默认用 18080，可在登录抓取页改成其它空闲端口；8080 常被其它程序占用，不建议使用。
- **error:300**：队伍不可收藏 / 队伍重复 / 删除时 `order_id` 不对。应用已尽量规避；仍报错先重新登录抓取当前靶机再试。
- **出现多个「收藏标靶1」**：编号撞了，用「清空重排」重建编号。
- **清空后进靶机界面卡死**：强退游戏重进。
- **注入后游戏里没变化**：大退重登游戏同步。
- **游戏进不去 / 网络异常**：检查系统代理是否已关闭（Windows 设置 → 网络和 Internet → 代理）。
- **sign 过期**：重新走一遍登录抓取。
- **积分关卡是怎么判定的？**：不是按名字带 `+`，而是读 STC 的 `mission.event_score`（积分结算配置）、
  `mission.score_prize`（积分奖励）和 `rank`（常驻积分榜）；混合活动会拆出「XX · 积分关卡」章节；
  普通 EX 关卡没有该结算配置，仍属活动/普通结算。
- **为什么很多队伍效能是「未标注」**：客户端只在积分关卡/部分特殊队伍里写入 `effect_ext`（目标作战效能），
  常规关卡队伍该字段为 0；没有可靠公式可以从面板数值反推，所以应用不伪造效能，只对「有标注」的队伍做筛选排序。

## 更新记录

### v1.5.0（2026-11-07）

- **机场/后续刷新候选（推断）**：STC 没有显式机场刷新池，按同关卡队伍 id 族推断「可能刷新」候选并并入关卡队伍列表
  （默认折叠、卡带「机场可能刷新（推断）」徽标、可展开/加入序列）；例：谜境守卫+ AA-02 队 6363057/6363060、
  静默沙盘威廉队 770060、潘洛斯 Hebe/Styx 660002/660003。全量 1637 个关卡有候选（5461 支未入场队伍）。
- **按怪组编号搜索/加入**：顶栏搜索 `6363006` / `#6363006` 直接出队伍结果卡并可加入序列；序列页/面板增加「按编号加入」输入框。
- **侧栏高亮滑块**：当前菜单项背景改为独立高亮块，切换时平滑移动（reduced-motion 下关闭），并修复了 active 状态
  因 data-nav 带 `/` 前缀而从未生效的问题。
- 版本号 v1.5.0（catalog schema=5，10.2MB）。

### v1.4.0（2026-11-07）

- **支援队伍归属关系**：读取 `spot.ally_team_id`，把每关的支援梯队并入该关卡队伍列表（敌方 X · 支援 Y），
  支援卡带「支援队伍」徽标、同样可加入序列；解决「谜境守卫+ 的 67.3w 效能支援队 6363006 看不到」的问题。
- **本怪组出现位置**：队伍详情列出全部 appearances，标注该怪组在每关是以「敌方」还是「支援」身份出现；
  可收藏怪组被复用/多关卡出现时一目了然。
- 支援队伍数据：864 支有槽位（818 可收藏）、329 个关卡有支援链接（824 条）；orphan 4381 → 3802；
  物种非互斥 flag：normal 250 / grayzone 68 / orphan 204。
- 版本号 v1.4.0（catalog schema=4）。

### v1.3.0（2026-11-06）

- **积分关卡改为读取结算形式**：每个关卡解析 `mission.event_score`（积分结算配置：mode + 21~30 项参数）、
  `mission.score_prize`（积分奖励档位）与 `rank` 表（`type=10` 常驻积分榜 / `type=6` 活动积分榜），
  界面新增「积分结算 / 普通结算」徽标与关卡队伍页「结算形式」行，不再靠名字/加号猜。
- 新增 `tools/analyze_score_stages.py`：输出 event_score 分布、score_prize 覆盖、积分榜映射、普通 EX 反例，
  支持 `--json`；用于复核分类（当前：53 个积分关卡 / 25 个 campaign；普通 EX 无 event_score 反例 191 个）。
- 教程 FAQ 新增「积分关卡是怎么判定的？」；19 张页面自检截图。
- 版本号 v1.3.0（数据 schema=3，settlement 字段向后兼容）。

### v1.2.2（2026-11-06）

- **积分关卡改为 mission 级权威判定**：mission.event_score 非空即积分关卡（不再用 campaign 名称规则）；
  混合活动会拆出独立积分关卡章（如「思域迷航 · 积分关卡」= 禁止喂食 / 禁止喂食EX；活动组保留其余 20 关）。
- 修正后：**积分关卡 25 章 / 53 关**，活动 73 章，总章节 112 → **121**，总关卡仍 2345。
- 贝蒂数 9 关（一维/二维环面/三维流形 G-1..S-2）确认全部为积分关卡；魔方行动/盲拆法则仍属活动。

### v1.2.1（2026-11-06）

- 修正**积分关卡**判定：`魔方行动+ / 盲拆法则` 是 4 关的复刻活动而不是积分关卡，已回归「活动」组（带往期复刻标记）；
  积分关卡现在是 **15 章**（终焉花海+ / 谜境守卫+ / 混沌落幕+ / 噩梦迷城+ / 驱雾行动+ / 秘密涡点+ / 飓风营救+ /
  马蜂窝+ / 虚数迷宫+ / 坠入兔洞+ / 贝蒂数 / 逃亡圣咏 / 自画像 / 从潘洛斯阶梯跃下 / 铁雨礼赞），活动 74 章。

### v1.2.0（2026-11-06）

- **小怪真实头像**：从本机游戏资源提取 `pic_<Code>_SS` 纹理（256/282 个 code，怪种覆盖 264/264），缺失回退阵营剪影
- **大蓝闪蝶（Blue Morpho）** 重新绘制：亮蓝渐变翅膀 / 黑翅缘翅脉 / 对称展翅，替换上一版扁平蝴蝶
- **积分关卡** 独立分组，活动组合并往期复刻与特殊作战
- **灰域** 修正为 14 个区域（新增 庇护所旧址 / 坍缩狭缝）；物种「灰域」筛选改为「出现过」，灰域 BOSS 不再只剩 4 个
- **效能筛选/排序**：灰域 / 关卡 / 怪种详情 / 无固定关卡 / 当前靶机，有标注/自定义区间 + 5 种排序
- 数据目录动态化：`TARGETFORGE_DATA_DIR` 可覆盖，教程/抓取页显示实际路径，不再硬编码 creds 路径
- 章节总数 110 → 112（7 组），自画像等积分关卡可搜；版本号 v1.2.0

### v1.1.0（2026-11-06）

- 全新主题：**深蓝星空 + 蓝色蝴蝶**（替换原琥珀黄黑配色，更贴近少前调性）
- 修复：总览页无限自刷新/闪烁、切换页面被劫持回总览
- 抓包端口改为**可配置**（默认 18080，登录抓取页可改，不再写死）
- 顶栏游戏 PID 增加说明：由 `tasklist` 按进程名搜索得到
- 增加 MIT License

## 相关项目

- [GFLH](https://github.com/MaaGF1/GFLH) / [ZIRC](https://github.com/MaaGF1/ZIRC) —— 社区 GFL 协议库（`gflzirc`），本项目的注入与抓包基于它。
- **GF Forge** —— 本项目的配套主仓库，提供本机 STC 数据层与 `gflh_target_train.py` 编号规划脚本（未包含在本仓库中）。

---

## 许可证

[MIT License](LICENSE)

本项目与《少女前线》开发 / 运营方无关，不包含任何游戏素材。
