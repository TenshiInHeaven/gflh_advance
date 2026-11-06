# 加固清单与验证

## 已实现（v1.9.1）

| 加固 | 实现位置 | 说明 |
|---|---|---|
| Host 白名单 | `targetforge/security.py::request_allowed` | 只接受 `127.0.0.1` / `localhost` / `::1`，且端口匹配；阻断 DNS rebinding |
| Origin 校验 | 同上 | 带 `Origin` 的请求必须是本机应用页面；`null`/外部域拒绝 |
| CSRF 自定义头 | 同上 | 所有 POST 必须带 `X-TargetForge-Client: 1`；跨站请求无法带自定义头（会触发 CORS 预检，服务端不提供 CORS） |
| POST Content-Type | 同上 | 必须 `application/json`；不再接受 `text/plain` 简单请求 |
| 只绑 loopback | `targetforge/app.py::main` | `--host` 仅允许 `127.0.0.1`/`localhost`/`::1`，否则退出 |
| 安全响应头 | `app.py::Handler._send` | CSP、X-Frame-Options DENY、Referrer-Policy no-referrer、nosniff |
| UNC/网络路径拒绝 | `security.py::validate_local_game_path` | 拒绝 `\\server\share` / `//server/share` |
| 凭证不返回/日志打码 | `gflh.py::list_creds/capture_status/_cap_log` | API/状态不返回 sign；日志自动把 sign 替换为 `***` |
| 路径穿越防护 | `app.py::_icon/_static` | `relative_to` 白名单目录校验 |
| 系统代理自动还原 | `gflh.py` capture 流程 | 默认 `auto_restore_proxy` |
| 请求体上限 | `app.py::_dispatch` | 2MB 上限，超大请求 413 |

## 未完成 / 建议

| 项目 | 风险 | 建议 |
|---|---|---|
| 凭证加密 | `creds_latest.json` 明文 | 用 Windows DPAPI（`CryptProtectData`）加密；或至少 `icacls` 限制当前用户 |
| 依赖 hash | 安装时无校验 | `requirements.txt` 固定版本并用 `pip-compile --generate-hashes` / `--require-hashes` |
| 文件选择频率限制 | 可反复弹窗 | 对 `/api/game/pick` 增加进程内限流/冷却 |
| 数据目录 ACL | 同机其它用户可读 | 首次创建数据目录时设置仅当前用户 ACL |
| 前端文本渲染 | 数据被篡改时可能 XSS | 已加 CSP；持续审计 `innerHTML`，优先 `textContent` |
| 端口占用检测 | 本机恶意进程抢注端口 | 启动前检查端口占用；仅本机用户可修复 |

## 复测

```powershell
# 1) 单元测试（含安全头/CSRF/Host 测试）
python -m unittest targetforge.tests.test_app_api -v

# 2) 手工验证
curl.exe -i http://127.0.0.1:8765/api/health            # 200 + CSP / X-Frame-Options
curl.exe -i -X POST http://127.0.0.1:8765/api/sequence  # 403（缺自定义头）
curl.exe -i -H "Host: evil.example" http://127.0.0.1:8765/api/health  # 403
curl.exe -i -X POST -H "Content-Type: text/plain" -H "X-TargetForge-Client: 1" `
  -d "{}" http://127.0.0.1:8765/api/sequence           # 403（Content-Type 非 JSON）

# 3) 页面自检
python targetforge/tools/ui_selfcheck.py --url http://127.0.0.1:8765
```

## 安全设计原则

- **默认不可远程访问**：只绑 loopback；拒绝用户误绑 LAN。
- **写操作必须证明来自本机应用页面**：Host + Origin + 自定义头 + JSON Content-Type 四重条件。
- **最小暴露**：凭证/日志不返回 sign；游戏路径不回显给非本机页面。
- **失败关闭**：校验失败统一 403，不执行任何副作用。
- **不信任本地输入**：游戏目录、图标名、静态路径都做白名单/路径穿越校验。
