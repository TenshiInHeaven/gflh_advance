# 安全说明

TargetForge 是**本机单用户工具**：本地 Web 服务同时具备设置系统代理、重启游戏、使用已保存凭证
增删收藏标靶的能力。安全边界是「同一 Windows 用户会话内的本机进程/浏览器」，不是多用户服务器。

## 目录

- [threat-model.md](threat-model.md) —— 威胁模型、攻击路径与影响
- [hardening.md](hardening.md) —— 已实现的加固、未完成项与复测方法
- [disclosure.md](disclosure.md) —— 漏洞报告与使用边界

## 当前结论（v1.9.3）

- 本地 HTTP 接口只监听 loopback（`127.0.0.1` / `localhost` / `::1`），拒绝 `--host` 绑定其它地址。
- 所有请求校验 `Host`；带 `Origin` 的请求必须是本机应用 origin；POST 必须带
  `X-TargetForge-Client: 1` 且 `Content-Type: application/json` —— 防 CSRF / DNS rebinding。
- **本机 API 随机 token**：启动生成，浏览器通过 `?token=` 链接或页面提示框输入；所有 `/api/*`（icons 除外）
  要求 `X-TargetForge-Token`，防本机其它进程/其它 Windows 用户冒充；token 文件 ACL 仅当前用户。
- 响应附带 CSP、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` 等安全头。
- 游戏目录接口拒绝 UNC/网络路径，避免 SMB 认证泄露；`/api/game/pick` 有 5 秒冷却；500 不返回 traceback。
- 凭证 `creds_latest.json` 使用 **Windows DPAPI 加密**（绑定当前用户）+ 文件 ACL 收紧为当前用户；
  旧明文凭证启动时自动迁移。接口与日志不返回 sign。
- 依赖使用 `requirements.lock` 做 **sha256 hash 锁定**（`pip install --require-hashes`）。
- 已知残留风险：同用户恶意程序/本机已被完全控制时无法防护（可读 token 文件/调用 DPAPI）；游戏 ToS 风险。

## 报告安全问题

请不要在公开 issue 里贴 uid/sign/本机路径。可以只描述复现步骤与影响范围；
维护者确认后再决定是否公开细节。详见 [disclosure.md](disclosure.md)。
