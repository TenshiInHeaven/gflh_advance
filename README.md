# GFLH Advance · 靶机工坊 (TargetForge)

把《少女前线》里**任意「可收藏」的敌方队伍**，可视化地编排进游戏内「靶机专训 → 收藏标靶」（最多 35 条）。
本项目是靶机工坊的应用本体：本地 Web 服务 + 数据层 + GFLH 登录抓取 / 注入模块 + 完整前端。

> **本仓库是自包含发行版**：包含应用本体、精简数据解析层（`unit_model/` 子集）、
> `scripts/gflh_target_train.py` 以及预构建的 `catalog.json` / 小怪头像；**不再需要另行克隆 GF Forge 主仓库**。
> 账号凭证、日志与运行状态不随仓库分发；游戏客户端仅用于「刷新数据 / 抓包注入」，纯浏览可直接使用内置数据。
> 仓库体积约 **43MB**（其中预构建数据约 39MB）。

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

| 灰域探查：4 区域 + 装甲突击（爬塔）+ 特殊区域 | 结晶带 · 278 个节点（地点小字 / 队伍 / 怪种图标） |
|---|---|
| ![灰域区域](docs/screenshots/grayzone-areas.jpg) | ![灰域节点](docs/screenshots/grayzone-nodes.jpg) |

| 积分结算：关卡行徽标 + tooltip | 关卡队伍页：结算形式（event_score / 积分奖励 / 积分榜） |
|---|---|
| ![积分结算](docs/screenshots/score-settlement.jpg) | ![结算形式](docs/screenshots/score-teams.jpg) |

| 谜境守卫+：敌方 30 · 支援 17 + 机场候选（推断） | 按怪组编号搜索并加入序列 |
|---|---|
| ![关卡队伍](docs/screenshots/stage-teams.jpg) | ![编号搜索](docs/screenshots/search-team.jpg) |

| 本怪组出现位置（支援队 6363006 → 谜境守卫+） | 侧栏高亮滑块（切换平滑移动） |
|---|---|
| ![本怪组出现位置](docs/screenshots/team-appearances.jpg) | ![侧栏高亮](docs/screenshots/sidebar-highlight.jpg) |

| 全怪组总表：表格排序 / 分页 | 多条件筛选：章节 + 怪种 AND + 角色 |
|---|---|
| ![全怪组](docs/screenshots/roster.jpg) | ![全怪组筛选](docs/screenshots/roster-filter.jpg) |

## 功能

- **关卡图鉴**：7 组 121 章 2345 关（主线 / 活动 / 积分关卡 / 教学 / 模拟 / 灰域 / 无固定关卡）；关卡 → 队伍，整关可一键加入序列。
- **图鉴与总表**：264 个图鉴怪种（真实头像）；13,700 支怪组总表，可排序，按章节 / 怪种（AND）/ 角色 / 效能 / 单位数筛选。
- **灰域**：4 个区域 + 装甲突击（爬塔）+ 特殊区域；区域 → 节点 → 队伍。
- **关卡情报**：结算形式（积分/普通）、效能与参数、出场位置；支援队与机场候选（推断）并入关卡队伍列表。
- **序列与注入**：35 个上限的拖拽编排；append / replace / rebuild 三种注入模式，预览 + 演练 + job 日志。
- **登录抓取与教程**：本地代理抓 uid / sign（端口可配置）；6 步新手引导 + 11 条 FAQ。

数据规模：121 章 / 2345 关 / 13,700 队 / 264 怪种 / 灰域 1,288 节点 / 支援 864 队 / 机场候选覆盖 2,178 关。

> 每项细节（结算判定、机场推断规则、怪组与筛选等）见 [详细功能说明](docs/FEATURES.md)。

## 安全

本地服务只监听 `127.0.0.1`，并对 Host / Origin / **随机访问 token** / POST 自定义请求头 / JSON Content-Type 做校验
（防 CSRF、DNS rebinding、本机其它进程冒充与误绑局域网），拒绝 UNC 网络路径，统一附带 CSP 等安全响应头；
`/api/game/pick` 有限流，500 错误不返回 traceback。威胁模型、已实现加固与剩余风险见 **[SECURITY/](SECURITY/README.md)**。

## 前置依赖

| 依赖 | 说明 |
|---|---|
| Windows 10/11 | 抓包 / 游戏控制 / winreg 代理设置目前是 Windows 实现 |
| Python 3.10+（推荐 3.14） | 运行 `python -m targetforge`；需 `gflzirc==0.4.4`（`pip install -r requirements.txt`） |
| 内置数据层 | `unit_model/`（STC 解析最小集）+ `project_paths.py` + `scripts/gflh_target_train.py` + 预构建 `dataMiner/derived/{catalog.json,icons}`；无需 GF Forge 主仓库 |
| 本机游戏客户端（可选） | 《少女前线》PC 版（Steam appid **3347970**）。**注入/刷新数据时必须**；纯浏览可不用。首次启动会要求选择客户端目录（自动检测 / 浏览文件夹），之后可在「登录抓取」页修改 |
| 端口 | 应用 **8765**；抓包代理默认 **18080**，可在「登录抓取 → 抓包端口」配置（8080 常被其它程序占用，不建议用） |
| 可选 | UnityPy + Pillow（重新导出小怪头像）、Playwright + Edge（页面自检） |

## 安装

```powershell
# 1) 克隆本仓库（约 43MB，含预构建数据）
git clone https://github.com/TenshiInHeaven/gflh_advance.git
cd gflh_advance

# 2) 先创建并激活虚拟环境（推荐，避免污染系统 Python）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3) 安装锁定依赖（requirements.lock 带 sha256 校验）
python -m pip install --upgrade pip
python -m pip install --require-hashes -r requirements.lock

# 4) 启动（Windows 可双击/运行 start.ps1，会自动用 .venv）
python -m targetforge --open
```

> 不熟悉命令行的，可以把本 README 交给 AI 助手（如「大肥鱼」）阅读后按步骤构建。
> `start.ps1` 会自动创建 `.venv`、安装锁定依赖并启动，不想手输命令可以用它。

首次启动会弹出**「先选择游戏客户端」**前置步骤：自动检测本机 Steam/运行中游戏，或点「浏览文件夹」手动选择
`GIRLS' FRONTLINE` 安装目录（含 `GrilsFrontLine.exe` 与 `GrilsFrontLine_Data` 的那一层）。
路径无效时会明确提示（目录不存在 / 未找到 exe / 不是有效少前客户端目录）；保存后可在「登录抓取 → 游戏客户端」修改。
如果只是浏览数据、不注入，内置的 catalog/icons 可直接使用（选择客户端仅用于注入/刷新数据）。

## 运行

启动后终端会打印带一次性 token 的访问链接：

```text
本地地址（含本次访问 token）: http://127.0.0.1:8765/?token=xxxxx
访问 token 文件: <数据目录>/.api_token
```

直接打开 http://127.0.0.1:8765 会显示「需要访问令牌」，把终端里的 token 粘贴进去即可（之后浏览器会记住）。
token 也写在数据目录的 `.api_token`（ACL 仅当前 Windows 用户可读）；服务重启会换新 token，旧链接失效。

```powershell
cd gflh_advance
python -m targetforge                 # http://127.0.0.1:8765
python -m targetforge --open          # 顺便打开带 token 的浏览器链接
python -m targetforge --port 8771     # 换端口
python -m targetforge --rebuild-catalog   # 用本机客户端强制重建数据（约 4 秒）
```

游戏更新后点顶栏「刷新数据」或加 `--rebuild-catalog`；内置 catalog 只是发布时的客户端版本，版本不一致时请重建。

**重新导出小怪头像（可选）**：内置头像来自发布时客户端，游戏新版单位可能缺失：

```powershell
python -m pip install UnityPy Pillow
python targetforge\tools\build_icons.py
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

- 所有关卡 / 怪种 / 怪组数据都由**本机客户端 STC 静态表**解析而来；仓库内置发布时的预构建 `catalog.json`/icons，
  首次选择客户端后也可随时「刷新数据」。应用完全离线运行，不上传任何数据。
- 数据目录默认是本仓库下的 `dataMiner/derived/targetforge/`（由 `datapaths.py` 按模块位置计算，不是写死的绝对路径）；
  可用环境变量 `TARGETFORGE_DATA_DIR` 指定到别处，缓存 / 凭证 / 状态 / 头像都会跟着走。
- 游戏客户端路径保存在仓库根 `local_paths.json`（本地文件，**不入 git**），首次启动由向导写入，后续可在页面修改；
  也可用环境变量 `GF1_GAME_ROOT` 覆盖。
- 应用只监听 `127.0.0.1`，不上传任何数据。
- 抓到的 `uid/sign` 只保存在数据目录下的 `creds_latest.json`（不入 git），**请勿提交或外传**。
- 抓包端口可配置（登录抓取页，默认 `18080`）；请确保使用完毕后系统代理已关闭。
- 游戏进程 PID 由 Windows `tasklist` 按进程名 `GrilsFrontLine.exe` **搜索**得到，顶栏 PID 仅本机展示，不是写死的。
- 本工具仅用于本地研究与学习；请遵守游戏服务条款，避免在主账号 / 线上环境滥用。产生的风险由使用者承担。

## 验证

```powershell
python -m unittest discover -s targetforge/tests -t .      # 150 个单测（app / catalog / gflh / game setup）
python targetforge/tools/api_smoke.py --url http://127.0.0.1:8765   # 真实数据 API 冒烟（33 项）
python targetforge/tools/ui_selfcheck.py --url http://127.0.0.1:8765 # Playwright 页面自检 + 26 张截图
python targetforge/tools/analyze_score_stages.py          # 积分关卡结算依据分析（event_score / score_prize / rank）
```

前端自检结果：215 项 DOM 断言通过，console error / page error 均为 0。

## 目录

```text
gflh_advance/
  README.md                    本文件
  LICENSE                      MIT
  start.ps1                    一键安装依赖并启动（Windows）
  requirements.txt             运行依赖（gflzirc）
  local_paths.example.json     本机游戏目录示例（复制为 local_paths.json，或首次启动向导写入）
  docs/screenshots/            README 用截图
  project_paths.py             仓库根 / 游戏目录解析（内置精简数据层）
  unit_model/                  精简 STC 解析层（core: stc/enemy/paths + stc-mapping）
  scripts/gflh_target_train.py 靶机编号规划 / payload / 本地状态
  dataMiner/derived/
    client_text.json           名称文本（构建 catalog 用）
    enemy_full_model.csv       怪种映射（构建 catalog 用）
    targetforge/catalog.json   预构建数据缓存（约 11MB）
    targetforge/icons/         预构建小怪头像（约 10MB）
  targetforge/                 应用本体
    app.py                     HTTP 服务 / 路由 / 序列状态 / 后台 job / 头像接口 / 游戏目录设置
    gamepath.py                游戏客户端检测 / 校验 / 文件夹选择 / local_paths
    catalog.py                 STC → 章节 / 关卡 / 怪种 / 怪组数据层（缓存 + 查询 + 效能/图标）
    gflh.py                    登录抓取（GFLProxy）/ 序列规划 / 注入（addCollect·delCollect）/ 游戏控制
    datapaths.py               数据目录唯一来源（支持 TARGETFORGE_DATA_DIR）
    static/                    前端（原生 HTML/CSS/JS，无构建步骤，离线）
    tests/                     unittest（app / catalog / gflh / game setup）
    tools/                     build_icons.py / analyze_score_stages.py / api_smoke.py / ui_selfcheck.py
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
- **首次启动要求选择游戏客户端**：只用来读取本机 STC / 注入，不上传；可自动检测或浏览选择 `GIRLS' FRONTLINE`
  根目录（含 `GrilsFrontLine.exe` 与 `GrilsFrontLine_Data`）。后续在「登录抓取 → 游戏客户端」可修改。
  选择无效会提示具体缺项；纯浏览可先用内置数据，注入前再选。
- **积分关卡是怎么判定的？**：不是按名字带 `+`，而是读 STC 的 `mission.event_score`（积分结算配置）、
  `mission.score_prize`（积分奖励）和 `rank`（常驻积分榜）；混合活动会拆出「XX · 积分关卡」章节；
  普通 EX 关卡没有该结算配置，仍属活动/普通结算。
- **为什么很多队伍效能是「未标注」**：客户端只在积分关卡/部分特殊队伍里写入 `effect_ext`（目标作战效能），
  常规关卡队伍该字段为 0；没有可靠公式可以从面板数值反推，所以应用不伪造效能，只对「有标注」的队伍做筛选排序。

## 更新记录

### v1.9.3（2026-11-07）

- **本机 API 随机 token**：启动生成随机 token，浏览器用 `?token=` 链接或页面提示框输入；所有 `/api/*`
  （icons 除外）要求 `X-TargetForge-Token`，防止本机其它进程/其它 Windows 用户冒充；token 文件 ACL 仅当前用户。
- **`/api/game/pick` 限流**：5 秒冷却，连续调用返回 429。
- **500 不再返回 traceback**：详细堆栈只写启动终端日志，页面只看到错误类型。
- 版本号 v1.9.3。

### v1.9.2（2026-11-07）

- **凭证 DPAPI 加密 + ACL**：`creds_latest.json` 默认用 Windows DPAPI 加密（绑定当前用户），文件 ACL 收紧为当前用户；
  启动时自动把历史明文凭证迁移为加密格式；API/日志仍不返回 sign。
- **依赖 hash 锁定**：新增 `requirements.lock`（gflzirc/requests/charset-normalizer/idna/urllib3/certifi，
  含各平台 wheel/sdist sha256）；安装使用 `pip install --require-hashes`。
- **虚拟环境引导**：README 安装步骤改为先 `python -m venv .venv` 并激活，再安装锁定依赖；
  `start.ps1` 自动创建/使用 `.venv`。不熟悉命令行的可把 README 交给 AI 助手（如「大肥鱼」）阅读后按步骤构建。
- 版本号 v1.9.2。

### v1.9.1（2026-11-07）

- **安全加固**：新增 `targetforge/security.py` 与 `SECURITY/` 文档目录。
  - Host 白名单（只允许 loopback/当前端口）与 Origin 校验，防 DNS rebinding；
  - POST 强制 `X-TargetForge-Client: 1` + `application/json`，防 CSRF；
  - `--host` 拒绝非 loopback 地址；
  - 响应增加 CSP / X-Frame-Options / Referrer-Policy；
  - 游戏目录接口拒绝 UNC/网络路径（防 SMB 认证泄露）。
- 新增单元测试覆盖安全头、缺自定义头/非法 Host 的 403。
- 详细威胁模型与剩余风险见 [SECURITY/](SECURITY/README.md)。

### v1.9.0（2026-11-07）

- **自包含发行**：仓库内置精简 GF Forge 数据层（`unit_model` 最小集 + `project_paths.py` + `scripts/gflh_target_train.py`）
  以及预构建 `catalog.json` / icons；**不再需要 GF Forge 主仓库**，克隆后可直接 `python -m targetforge`。
- **首次启动游戏客户端向导**：类似文件浏览的前置步骤，自动检测运行中游戏 / Steam 目录，或浏览文件夹选择；
  无效路径明确提示（目录不存在 / 未找到 `GrilsFrontLine.exe` / 不是有效客户端目录缺 stc）；
  之后可在「登录抓取 → 游戏客户端」修改并重建数据。
- 新增 `targetforge/gamepath.py` 与 `/api/game/status|detect|pick|confirm`；游戏路径写入本地 `local_paths.json`（不入 git）。
- 仓库体积约 43MB（预构建数据约 39MB）；纯浏览无需启动游戏，注入/刷新数据仍需本机客户端。
- 版本号 v1.9.0。

### v1.8.1（2026-11-07）

- **修复「坠入兔洞+」机场候选为 0**：原 reserve 规则要求同 4 位前缀 ≥3 引用，10105 的 4 支 BOSS 队
  2147~2150 前缀各异导致漏判。改为 **3~6 位最短公共前缀**（10105 → prefix「214」，候选 2141~2146）
  + 引用 id **±20 邻近窗口 fallback**。
- **全部积分关卡审计**：25 个 score 章节 / 53 关，改进前 41 关有 reserve、12 关为 0 →
  改进后 **53/53 关都有 reserve**（prefix 43 / neighbor 10）；逐关报告
  `dataMiner/derived/targetforge/reserve_audit.json`（本地生成，不入仓库）。
- 全量 reserve 覆盖 1637 → 2178 个关卡、候选队伍 5461 → 7742；原有 AA-02/威廉/Hebe 例子保持命中。
- 版本号 v1.8.1（catalog schema=8）。

### v1.8.0（2026-11-07）

- **灰域信息架构重构**：删除「地点卡 + 区域筛选」组织，改为玩家口径 **区域 → 节点 → 节点内队伍**：
  - 首页：4 张区域卡（沙尘带 228 / 风暴带 228 / 硅状带 228 / 结晶带 278 节点）+ **装甲突击**（爬塔，10 节点）
    + 特殊区域（316 节点，组5/6 客户端无区域名）；统计 区域 4 / 装甲突击 1 / 节点 1288 / 队伍 3352 / 怪种 66。
  - 区域节点列表：`GET /api/grayzone/nodes?region=`，返回节点标题/地点/难度/队伍数/怪种数/前 4 个怪种；
    支持搜索/排序/分页；点节点进入该节点队伍列表（含支援/机场推断）。
  - 地点名降为节点副标题，不再作为顶层结构。
- 版本号 v1.8.0（catalog schema=7）。

### v1.7.0（2026-11-07）

- **灰域区域层级修正**：之前把 14 个 mission 标题前缀（共生净土、晶团挖掘点…）误当区域。现按客户端
  `daily_mission_group` → `daily_mission_difficulty_group` 还原真实层级：**5 个区域**（沙尘带 / 风暴带 / 硅状带 / 结晶带 /
  特殊区域）→ **14 个地点**；每个地点显示所属区域 badges，区域卡可点击筛选地点（结晶带 → 11 个地点）。
- 区域统计（有可收藏队伍节点）：沙尘带 228 / 风暴带 228 / 硅状带 228 / 结晶带 278 / 特殊区域 326，
  合计 1288 节点；`/api/grayzone/teams` 新增 `region` 参数（结晶带 789 支）。
- 组5/6 客户端无区域文本，不编造名称，统一归「特殊区域」并注明来源。
- 版本号 v1.7.0（catalog schema=6）。

### v1.6.0（2026-11-07）

- **全怪组总表**：新增独立页面（侧栏「全怪组」，13,700 支可收藏队伍），表格展示编号/效能/单位数/总血/阵营/
  角色/怪种/出现章节，支持表头排序（编号、效能、单位数、总血、怪种数）与分页。
- **多条件筛选**：搜索（编号/阵营/怪种名）+ **出现在指定章节** + **同时包含多个怪种（AND）** + 角色
  （敌方/支援/机场推断）+ 单位数区间 + 效能区间/只看有标注；筛选即时生效、可重置。
- 新增 `GET /api/teams`（`catalog.team_list()`）：服务端筛选/排序/分页，13,700 队查询 <10ms。
- 版本号 v1.6.0。

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
- **GF Forge** —— 本项目的配套主仓库（数据层来源）；自 v1.9.0 起本仓库已内置所需精简数据层，无需单独安装。

---

## 许可证

[MIT License](LICENSE)

本项目与《少女前线》开发 / 运营方无关，不包含任何游戏素材。
