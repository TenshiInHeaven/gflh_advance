# 安全说明

TargetForge 是**本机单用户工具**：本地 Web 服务同时具备设置系统代理、重启游戏、使用已保存凭证
增删收藏标靶的能力。安全边界是「同一 Windows 用户会话内的本机进程/浏览器」，不是多用户服务器。

## 目录

- [threat-model.md](threat-model.md) —— 威胁模型、攻击路径与影响
- [hardening.md](hardening.md) —— 已实现的加固、未完成项与复测方法
- [disclosure.md](disclosure.md) —— 漏洞报告与使用边界

## 当前结论（v1.9.1）

- 本地 HTTP 接口只监听 loopback（`127.0.0.1` / `localhost` / `::1`），拒绝 `--host` 绑定其它地址。
- 所有请求校验 `Host`；带 `Origin` 的请求必须是本机应用 origin；POST 必须带
  `X-TargetForge-Client: 1` 且 `Content-Type: application/json` —— 防 CSRF / DNS rebinding。
- 响应附带 CSP、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` 等安全头。
- 游戏目录接口拒绝 UNC/网络路径，避免 SMB 认证泄露。
- 凭证（uid/sign）只在本地数据目录明文保存；接口与日志不返回 sign。
- 已知残留风险：凭证未加密（DPAPI）、依赖未做 hash 锁定、若本机已被完全控制则无法防护。

## 报告安全问题

请不要在公开 issue 里贴 uid/sign/本机路径。可以只描述复现步骤与影响范围；
维护者确认后再决定是否公开细节。详见 [disclosure.md](disclosure.md)。
