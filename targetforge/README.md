# 靶机工坊 TargetForge

> 独立发布仓库：<https://github.com/TenshiInHeaven/gflh_advance>（`gflh_advance/targetforge/` 与本目录保持同步）

基于仓库里的 GFLH「抓取靶机」能力做的本地可视化应用：在网页里挑关卡 / 挑怪种 / 看怪组数值 /
编排靶机顺序，然后通过官方协议接口把队伍写进游戏「靶机专训 → 收藏标靶」（最多 35 个）。

> 所有数据来自**本机游戏客户端的 STC 静态表**，完全离线可用；不展示任何技能信息（按需求）。
> 应用只监听 `127.0.0.1`，不上传任何数据。

## 快速开始

```powershell
# 需要系统 Python 3.14（已装 gflzirc 0.4.4）+ 本机少前客户端
python -m targetforge                 # http://127.0.0.1:8765
python -m targetforge --open          # 启动后自动打开浏览器
python -m targetforge --port 8771     # 换端口
python -m targetforge --rebuild-catalog   # 强制重建数据缓存
```

首次启动会解析本机 STC 生成 `dataMiner/derived/targetforge/catalog.json`（约 4 秒，6.7MB），
之后直接读缓存（<1 秒）。游戏更新后点页面上的「刷新数据」或加 `--rebuild-catalog`。

## 功能

| 页面 | 内容 |
|---|---|
| 总览 | 游戏进程 / 系统代理 / 当前靶机数 / 数据时间 + 四步使用流程 |
| 关卡图鉴 | 8 组 110 章 2345 关：主线 / 活动 / 往期复刻 / 教学 / 特殊作战 / 模拟作战 / 灰域探查 / 无固定关卡。章节卡片 → 关卡列表 → 该关可收藏队伍（可整关加入序列） |
| 怪种图鉴 | 264 个图鉴怪种，按阵营/固定关卡/灰域/无固定关卡筛选；怪种详情列出所有怪组 |
| 队伍详情 | 队伍参数（效能/单位数/总血/关卡出处）+ 单位聚合表（等级/编制/数量/防御修正/坐标/HP/火力/命中/回避/护甲/穿甲/射程/移速/护盾/力场）——**不含技能信息** |
| 序列编排 | 加入/移除/拖拽排序/从当前靶机导入，上限 35，实时显示总单位/总血量 |
| 执行注入 | 预览（删除/新增/保留/最终 1..N 列表 + 警告）→ 三种模式：追加（append）/ 按序号替换（replace）/ 清空重排（rebuild），另有清空全部；支持演练模式（dry-run，不联网） |
| 登录抓取 | 内置向导：启动本地抓包代理（端口可配置，默认 18080）→ 设置系统代理并重启游戏 → 等抓到 uid/sign/当前靶机 → 完成并恢复代理；也可加载历史凭证 |
| 使用教程 | 概念 / 完整流程 / 登录抓取分步 / 三种执行模式 / FAQ / 安全须知；首次进入自动弹新手引导 |

数据规模（当前客户端）：8 组 110 章 · 2345 关（灰域 1288 节点折叠为 12 区域）· 13700 支可收藏队伍 ·
264 个可收藏怪种 · 灰域 3352 队 / 无固定关卡 4381 队。

## 执行模式语义

- **追加**：保留现有靶机，草稿按顺序接在最大 `order_id` 后面；已在列表里的队伍自动跳过。
- **按序号替换**：草稿第 i 个换成「收藏標靶 i」；草稿比现有长就追加，现有比草稿长则保留；
  若草稿队伍已存在于其它编号，先删旧项避免重复；每个 `delCollect` 都带正确的 `order_id`。
- **清空重排**：先删光现有靶机，再按草稿 1..N 全量 addCollect（编号最干净，推荐一次配好整套）。

注入完成后必须**大退重登游戏**同步；清空靶机后要强退，否则进靶机界面可能卡死（教程 FAQ 里也有）。

## 目录

```text
targetforge/
  app.py            HTTP 服务 / 路由 / 序列状态 / 后台 job
  catalog.py        STC → 章节/关卡/怪种/怪组 数据层（缓存 + 查询）
  gflh.py           登录抓取（GFLProxy）/ 序列规划 / 注入（addCollect·delCollect）/ 游戏控制
  static/           前端（原生 HTML/CSS/JS，无构建步骤，离线可用）
    index.html        单页壳：顶栏状态条 + 左侧导航 + 主区域 + 右侧可收起序列面板
    css/app.css       设计系统（暗色军事科技风：网格背景/斜切卡片/表格/弹窗/抽屉/toast/骨架/教程 overlay）
    js/main.js        启动、hash 路由、顶栏状态、全局搜索、全局点击委托
    js/api.js         同源 fetch 封装（错误归一化；?mock=1 时走 mock 层）
    js/store.js       全局状态（health/sequence/current/tutorial）+ 事件总线 + 序列操作
    js/util.js        文本转义/千分位/效能 0→—/力场 99999→无/时间/hash 路由解析
    js/ui.js          图标库 + toast/modal/抽屉/骨架/空态/分页 + 队伍卡/关卡行/怪种卡渲染
    js/mock.js        ?mock=1 离线假数据层（视觉自测用，真实 API 模式不加载）
    js/tutorial-data.js  新手引导 6 步 + 9 条 FAQ + 流程文案
    js/components/    sequence-panel / drag-sort / team-drawer / execute-modal / tutorial-overlay
    js/views/         overview / chapters / chapter-detail / stage / grayzone / species /
                      species-detail / team-page / sequence-page / capture / tutorial-page
  tests/            unittest（app / catalog / gflh）
  tools/            api_smoke.py（API 冒烟）、ui_selfcheck.py（Playwright 页面自检）、screenshot.py
  contract.md       模块 / API 契约
  LICENSE           MIT 许可证
```

## 页面路由（hash 无刷新）

`#/overview` · `#/chapters` · `#/chapters/{章节id}` · `#/stages/{mission_id}` · `#/grayzone/{区域}` ·
`#/species` · `#/species/{codex}` · `#/teams/{team_id}` · `#/sequence` · `#/capture` · `#/tutorial`

## 验证

```powershell
python -m unittest discover -s targetforge/tests -t .    # 100+ 单测
python targetforge/tools/api_smoke.py                    # 真实 catalog 的 API 冒烟（28 项）
python targetforge/tools/ui_selfcheck.py --url http://127.0.0.1:8765   # Playwright 页面自检 + 截图
```

## 安全 / 注意

- `dataMiner/derived/targetforge/`（数据缓存、凭证、前端状态）整个目录**不入 git**。
- `creds_latest.json` 含 uid/sign，**每次登录都会变**，不要提交/外传；sign 过期后重新走「登录抓取」。
- 抓包端口可配置（登录抓取页「抓包端口」，默认 `18080`）；`8080` 常被本机其它程序占用，建议不要用。
- 游戏进程通过 Windows `tasklist` 按进程名 `GrilsFrontLine.exe` **搜索**得到；顶栏 PID 仅本机展示（用来确认进程存在），不是写死的。
- 「设置代理并重启游戏」「重启游戏」按钮会强杀游戏进程，均有二次确认；不点就不会碰游戏。

## 许可证

MIT License，见 [LICENSE](LICENSE)。
