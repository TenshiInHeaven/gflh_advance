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
    manual_spawns.json         社区显式刷怪表（铁雨礼赞；来源/作者/区域/回合/效能）
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

## 当前版本

**v1.9.4**（当前发布）：铁雨礼赞积分关卡改用**社区显式刷怪表**（15 支实际队伍 + 基础效能，来源：秋水Ameth），
不再展示被 80 上限截断/无关的推断候选；本机 API token、pick 限流、500 错误不回显 traceback 也在本版。
完整历史见 [版本历史](docs/CHANGELOG.md)，详细功能见 [详细功能说明](docs/FEATURES.md)，
安全模型见 [SECURITY/](SECURITY/README.md)；文档总索引见 [docs/](docs/README.md)。

## 致谢

- **GFLH**：感谢 **MaaGF1** 及所有贡献者。本项目的登录抓取与收藏标靶注入流程建立在
  [GFLH](https://github.com/MaaGF1/GFLH) 的协议与思路上。
- **ZIRC / gflzirc**：感谢 **MaaGF1** 与 ZIRC 贡献者；`gflzirc` 以 **MIT** 发布，
  是本项目与游戏接口、本地抓包交互的基础。
- **秋水Ameth**：感谢整理「铁雨礼赞 - 刷怪表（无烟花强化）」及基础效能数据；
  该表已作为 `铁雨礼赞` 积分关卡的社区显式刷怪表来源（见 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)）。
- **GF Forge**：感谢数据层与靶机编号规划的上游工作；自 v1.9.0 起其精简子集已内置在本仓库。
- 也感谢 Python、requests、urllib3、charset-normalizer、idna、certifi、UnityPy、Pillow、Playwright
  等开源项目的作者与维护者。

完整的上游项目、依赖许可证与 MIT 合规说明见 **[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)**。
MIT 允许自由使用/修改/再分发，但请保留原作者版权与许可声明。

---

## 许可证

[MIT License](LICENSE)

第三方组件（尤其以 MIT 发布的 `gflzirc` / GFLH 相关上游）保留原有版权与许可；完整列表与合规说明见
[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

本项目与《少女前线》开发 / 运营方无关，不包含任何游戏素材。
