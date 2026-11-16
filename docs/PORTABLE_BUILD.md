# 自包含便携版（Portable Release）

## 目标

让没有安装 Python 的 Windows 用户下载后解压即可使用：

```text
TargetForge-1.16.0-portable-x64.zip
  TargetForge-portable/
    Start TargetForge.bat
    README-PORTABLE.txt
    python/                  # python.org embeddable Python 3.14.7
      python.exe
      python314.zip
      Lib/site-packages/     # gflzirc、requests、mitmproxy、cryptography 等
    app/
      targetforge/           # WebUI 与全部运行时代码
      dataMiner/derived/targetforge/
        catalog.json
        reserve_audit.json
        icons/
      README.md
      LICENSE
      docs/
```

## 构建

在装有正常 Python + pip 的机器上执行：

```powershell
python scripts/build_portable_release.py
```

可选参数：

```powershell
python scripts/build_portable_release.py --keep-build
python scripts/build_portable_release.py --skip-deps
```

脚本会：

1. 从 python.org 下载对应版本的 Windows embeddable zip；
2. 解压到 `build/TargetForge-portable/python`；
3. 把 `gflzirc`、`requests`、`mitmproxy`、`cryptography` 安装到 `Lib/site-packages`；
4. 复制应用、catalog、图标和文档；
5. 生成 `Start TargetForge.bat`；
6. 对便携 Python 做 import 冒烟测试；
7. 打包为 `dist/TargetForge-<version>-portable-x64.zip`。

## 安全边界

构建脚本只复制运行数据：

- `catalog.json`
- `reserve_audit.json`
- `icons/`

**不会复制**：

- `.api_token`
- `creds_latest.json`
- 抓包事件日志
- 桥接日志 / PID / 目标配置
- 本机 CA
- 用户设置
- 原始 STC / 客户端大文件

## 限制

- 仅 Windows x64；
- 便携包内是预构建 catalog，不能在没有原始 STC 的情况下重建数据；
- 桥接/模拟器仍需要用户自行启动游戏/模拟器；
- 首次运行时 Windows 防火墙可能询问本机回环端口，允许即可；
- 便携包不等于免审核的官方客户端，使用时仍需遵守游戏规则与风险提示。
