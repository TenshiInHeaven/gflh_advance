# 致谢与第三方许可

TargetForge 以 **MIT License** 发布。MIT 允许使用、修改与再分发，但要求保留原作者的版权与许可声明；
本项目也受益于以下上游项目、开源库与社区工作，在此致谢。

## 上游项目

- **GFLH** —— 由 **MaaGF1** 及贡献者开发的《少女前线》PC 端协议/自动化项目。本项目的登录抓取与
  收藏标靶注入流程基于 GFLH 使用的协议与思路：[MaaGF1/GFLH](https://github.com/MaaGF1/GFLH)。
- **ZIRC / gflzirc** —— ZIRC 的 IL2CPP 协议库，PyPI 包作者 **MaaGF1**，以 **MIT** 许可发布；
  本项目通过 `gflzirc==0.4.4` 与游戏接口/本地抓包交互：
  [PyPI](https://pypi.org/project/gflzirc/)。
- **GF Forge** —— 本项目的配套数据层来源（STC 表解析、等级缩放口径、靶机编号规划）；
  自 v1.9.0 起本仓库内置其精简子集，由本项目作者维护并以 MIT 随本仓库分发。

感谢以上项目的作者与所有贡献者：没有这些上游工作，本项目的注入、抓包和数据解析无法实现。

## 开源依赖

运行依赖（`requirements.lock` 固定版本并校验 sha256）：

| 组件 | 作者 / 维护者 | 许可证 |
|---|---|---|
| [gflzirc](https://pypi.org/project/gflzirc/) | MaaGF1 | MIT |
| [requests](https://requests.readthedocs.io/) | Kenneth Reitz 及贡献者 | Apache-2.0 |
| [urllib3](https://urllib3.readthedocs.io/) | Andrey Petrov 及贡献者 | MIT |
| [charset-normalizer](https://github.com/Ousret/charset_normalizer) | Ahmed TAHRI 及贡献者 | MIT |
| [idna](https://github.com/kjd/idna) | Kim Davies | BSD-3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | Kenneth Reitz 及贡献者 | MPL-2.0 |

头像导出 / 自检（可选）：

| 组件 | 作者 / 维护者 | 许可证 |
|---|---|---|
| [UnityPy](https://github.com/K0lb3/UnityPy) | K0lb3 及贡献者 | MIT |
| [Pillow](https://python-pillow.org/) | Alex Clark 及贡献者 | HPND |
| [Playwright](https://playwright.dev/) | Microsoft | Apache-2.0 |

## 社区数据贡献

- **秋水Ameth** —— 整理《少女前线积分关卡 固定怪组表 + 刷怪表》合集（16 个关卡）：
  [腾讯表格合集](https://docs.qq.com/sheet/DYWFRU1dmRnJmY0JV?nlc=1&tab=BB08J2)
  表中提供了各区域/回合的刷怪队伍编号与基础效能，本项目据此为这些积分关卡
  建立显式刷怪表（`targetforge/manual_spawns.json`），替代不可靠的 ID 前缀推断。
  数据版权归原整理者。

## 游戏数据与素材

- 《少女前线》游戏及其角色、单位、图标等素材版权归 **Sunborn Network Technology / MICA Team**
  等原权利方所有。
- 本仓库预构建的 `catalog.json` / `icons` 仅用于本机数据索引与展示，不主张任何游戏素材版权；
  本项目与游戏开发/运营方无关联。若权利方有异议，请联系删除相关派生数据。

## MIT 合规说明

- 本仓库根目录的 [LICENSE](LICENSE) 仅覆盖本项目作者原创的代码与文档。
- 第三方组件保留其原有许可证与版权；`gflzirc` 等以 MIT 发布的上游作品，其版权与许可声明
  同样适用于对应部分。分发本仓库或再分发时请保留本文件与上游许可证信息。
- 如果你再分发本项目的修改版，请保留本致谢文件及 `LICENSE`。
