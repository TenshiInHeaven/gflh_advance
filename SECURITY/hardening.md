# 加固清单与验证

## 已实现（v1.9.3）

| 加固 | 实现位置 | 说明 |
|---|---|---|
| Host 白名单 | `targetforge/security.py::request_allowed` | 只接受 `127.0.0.1` / `localhost` / `::1`，且端口匹配；阻断 DNS rebinding |
| Origin 校验 | 同上 | 带 `Origin` 的请求必须是本机应用页面；`null`/外部域拒绝 |
| **本机 API token** | `security.py::ensure_api_token/request_allowed` | 启动生成随机 token；`/api/*`（icons 除外）要求 `X-TargetForge-Token`；token 文件 ACL 仅当前用户 |
| CSRF 自定义头 | 同上 | 所有 POST 必须带 `X-TargetForge-Client: 1`；跨站请求无法带自定义头（会触发 CORS 预检，服务端不提供 CORS） |
| POST Content-Type | 同上 | 必须 `application/json`；不再接受 `text/plain` 简单请求 |
| 只绑 loopback | `targetforge/app.py::main` | `--host` 仅允许 `127.0.0.1`/`localhost`/`::1`，否则退出 |
| 安全响应头 | `app.py::Handler._send` | CSP、X-Frame-Options DENY、Referrer-Policy no-referrer、nosniff |
| UNC/网络路径拒绝 | `security.py::validate_local_game_path` | 拒绝 `\\server\share` / `//server/share` |
| **pick 限流** | `app.py::api_game_pick` | 5 秒冷却，连续调用 429 |
| **500 不回显堆栈** | `app.py::_dispatch` | 堆栈只写启动终端；页面只返回错误类型 |
| 凭证 DPAPI 加密 | `targetforge/creds_store.py` | 新写入凭证用 Windows DPAPI 加密（绑定当前用户）；旧明文启动时自动迁移 |
| 凭证/数据目录 ACL | `security.py::restrict_file_acl/restrict_dir_acl` | 凭证文件 ACL 仅当前用户；数据目录启动时收紧 |
| 依赖 hash 锁定 | `requirements.lock` + `start.ps1` | 6 个依赖固定版本 + 各平台 wheel/sdist sha256；`pip install --require-hashes` |
| 凭证不返回/日志打码 | `gflh.py::list_creds/capture_status/_cap_log` | API/状态不返回 sign；日志自动把 sign 替换为 `***` |
| 路径穿越防护 | `app.py::_icon/_static` | `relative_to` 白名单目录校验 |
| 系统代理自动还原 | `gflh.py` capture 流程 | 默认 `auto_restore_proxy` |
| 请求体上限 | `app.py::_dispatch` | 2MB 上限，超大请求 413 |

## 未完成 / 建议

| 项目 | 风险 | 建议 |
|---|---|---|
| 前端文本渲染 | 数据被篡改时可能 XSS | 已加 CSP；持续审计 `innerHTML`，优先 `textContent` |
| 端口占用检测 | 本机恶意进程抢注端口 | 启动前检查端口占用；仅本机用户可修复 |
| 同用户恶意程序 | 可读 token 文件/调用 DPAPI | 本机工具固有限制；建议系统级杀软/EDR |

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
