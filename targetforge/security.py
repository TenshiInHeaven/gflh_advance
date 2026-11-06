"""TargetForge 本地 HTTP 安全策略。

威胁模型（详见仓库 ``SECURITY/threat-model.md``）：

* 应用只应被本机浏览器访问，但浏览器里的**任意网页**都可能向 ``127.0.0.1`` 发请求
  （CSRF），或用 DNS rebinding 绕过同源策略读取响应；
* 本地 API 有能力设置系统代理、重启游戏、使用已保存凭证增删收藏标靶，因此必须有
  明确的 Host / Origin / 自定义请求头校验；
* 应用不监听非 loopback 地址。

本模块只做无状态的请求校验与响应头常量，便于单元测试。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

CLIENT_HEADER = "X-TargetForge-Client"
CLIENT_HEADER_VALUE = "1"

#: 只允许本机回环地址（Host/Origin）
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

#: 允许的 Origin scheme（本地无 HTTPS）
ORIGIN_SCHEMES = {"http", "https"}


def security_headers() -> dict[str, str]:
    """所有响应统一附带的安全头（只返回新增头，Content-Type 等由调用方负责）。"""
    return {
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        ),
    }


def _split_host(value: str) -> tuple[str, int | None]:
    """把 Host/authority 拆成 ``(hostname, port)``；无法识别时 hostname 为空。"""
    text = (value or "").strip()
    if not text:
        return "", None
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            return "", None
        host = text[1:end]
        rest = text[end + 1:]
        if rest.startswith(":") and rest[1:].isdigit():
            return host.lower(), int(rest[1:])
        return host.lower(), None
    if text.count(":") == 1:
        host, _, port = text.partition(":")
        if port.isdigit():
            return host.lower(), int(port)
        return "", None
    return text.lower(), None


def _port_matches(value: int | None, expected: int | None) -> bool:
    return value is None or expected is None or value == expected


def host_allowed(host_header: str, expected_port: int | None) -> bool:
    """Host 白名单：只接受 loopback + 当前端口（或无端口）。"""
    host, port = _split_host(host_header)
    if host not in LOOPBACK_HOSTS:
        return False
    return _port_matches(port, expected_port)


def origin_allowed(origin: str, expected_port: int | None) -> bool:
    """若浏览器带 Origin，必须是本机应用 origin；没有 Origin 的本地客户端可继续由自定义头校验。"""
    text = (origin or "").strip()
    if not text or text == "null":
        return not text
    match = re.match(r"^([a-z][a-z0-9+.-]*)://([^/]+)$", text, re.I)
    if not match:
        return False
    scheme, authority = match.group(1).lower(), match.group(2)
    if scheme not in ORIGIN_SCHEMES:
        return False
    host, port = _split_host(authority)
    if host not in LOOPBACK_HOSTS:
        return False
    return _port_matches(port, expected_port)


def request_allowed(
    method: str,
    headers: Mapping[str, str],
    expected_port: int | None,
) -> str | None:
    """校验一个 HTTP 请求；允许返回 ``None``，否则返回中文拒绝原因（403）。"""
    host = str(headers.get("Host") or "")
    if not host_allowed(host, expected_port):
        return "Host 不被允许（仅限本机 127.0.0.1/localhost/::1）"
    origin = str(headers.get("Origin") or "")
    if origin and not origin_allowed(origin, expected_port):
        return "Origin 不被允许（仅限本机应用页面）"
    site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site == "cross-site":
        return "跨站请求被拒绝"
    if method.upper() == "POST":
        if str(headers.get(CLIENT_HEADER) or "").strip() != CLIENT_HEADER_VALUE:
            return f"缺少安全请求头 {CLIENT_HEADER}"
        content_type = str(headers.get("Content-Type") or "").lower()
        if not content_type.startswith("application/json"):
            return "POST 请求必须使用 application/json"
    return None


def is_unc_path(raw: str | Path) -> bool:
    """拒绝 Windows UNC / 网络路径（防 SMB 认证泄露）；普通盘符/相对路径不算。"""
    text = str(raw or "").strip()
    return text.startswith("\\\\") or text.startswith("//")


def validate_local_game_path(raw: str | Path) -> tuple[Path | None, str | None]:
    """把用户输入的游戏目录转为本地绝对路径；拒绝 UNC / 网络路径。"""
    text = str(raw or "").strip().strip('"')
    if not text:
        return None, "缺少游戏目录路径"
    if is_unc_path(text):
        return None, "不支持网络路径（UNC），请选择本机磁盘上的游戏目录"
    try:
        path = Path(text).expanduser()
    except (OSError, ValueError) as exc:
        return None, f"路径无效：{exc}"
    if not path.is_absolute():
        return None, "请提供游戏目录的绝对路径"
    return path, None
