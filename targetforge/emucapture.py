"""安卓模拟器抓包：mitmproxy + 自签 CA，抓 uid/sign/收藏标靶。

与 PC 模式（gflzirc.GFLProxy + 系统代理）相互独立：
* 模拟器模式只监听用户指定地址（默认 0.0.0.0:8084），**不改系统代理**；
* 用户在模拟器 Wi-Fi 里填 PC 的局域网 IP:端口，并安装本模块生成的 CA；
* 抓到的 uid/sign/base_url 会写入 creds_latest.json，后续注入直接复用。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from targetforge.datapaths import CREDS_LATEST, DATA_DIR
from targetforge.regions import get_region
from targetforge import creds_store

LOCK = threading.Lock()
_PROC: subprocess.Popen | None = None
_THREAD: threading.Thread | None = None
_LOG_FILE = None
_STATE: dict[str, Any] = {
    "state": "idle",
    "mode": "emulator",
    "region": "tw",
    "port": 8084,
    "listen_host": "0.0.0.0",
    "proxy_active": False,
    "system_proxy_on": False,
    "uid": None,
    "sign_set": False,
    "base_url": None,
    "targets_count": 0,
    "creds_path": None,
    "error": None,
    "started_at": None,
    "logs": [],
}

CA_DIR = Path(DATA_DIR) / "mitm_ca"
CONF_DIR = Path(DATA_DIR) / "mitm_conf"
CAPTURE_JSON = Path(DATA_DIR) / "emulator_capture.json"
CAPTURE_LOG = Path(DATA_DIR) / "emulator_capture.log"


def _log(level: str, text: str) -> None:
    line = {"level": level, "text": text, "at": time.strftime("%H:%M:%S")}
    with LOCK:
        _STATE["logs"] = (_STATE["logs"] + [line])[-80:]


def ensure_ca() -> tuple[Path, Path]:
    """生成（或复用）本地 CA；返回 (cert, key)。"""
    CA_DIR.mkdir(parents=True, exist_ok=True)
    cert_path = CA_DIR / "ca.crt"
    key_path = CA_DIR / "ca.key"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime
    except ImportError as exc:
        raise RuntimeError(
            "模拟器抓包需要 cryptography 生成 CA；请安装：pip install mitmproxy cryptography"
        ) from exc
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "TargetForge Emulator CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TargetForge"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                          content_commitment=False, key_encipherment=False,
                          data_encipherment=False, key_agreement=False,
                          encipher_only=False, decipher_only=False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    return cert_path, key_path


def ca_cert_path() -> Path:
    return ensure_ca()[0]


def _prepare_conf(cert: Path, key: Path) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    (CONF_DIR / "mitmproxy-ca.pem").write_bytes(key.read_bytes() + cert.read_bytes())
    (CONF_DIR / "mitmproxy-ca-cert.pem").write_bytes(cert.read_bytes())


def _finalize_creds() -> None:
    with LOCK:
        data = dict(_STATE)
    sign = data.get("_sign")
    if not (data.get("uid") and sign):
        return
    if data.get("creds_path") and Path(data["creds_path"]).is_file():
        return
    rows = []
    payload: dict[str, Any] = {
        "uid": str(data["uid"]),
        "sign": str(sign),
        "base_url": data.get("base_url"),
        "enemies": [],
        "orders": [],
        "urls": data.get("urls") or [],
        "region": data.get("region"),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    try:
        raw = json.loads(CAPTURE_JSON.read_text(encoding="utf-8"))
        rows = raw.get("target_rows") or []
        payload["enemies"] = [str(item.get("enemy_team_id")) for item in rows
                              if item.get("enemy_team_id")]
        payload["orders"] = [int(item.get("order_id") or 0) for item in rows]
        payload["urls"] = raw.get("urls") or payload["urls"]
        payload["base_url"] = raw.get("base_url") or payload["base_url"]
    except (OSError, ValueError):
        pass
    try:
        path = creds_store.write_creds(CREDS_LATEST, payload)
    except OSError as exc:
        _log("error", f"写凭证失败：{type(exc).__name__}: {exc}")
        return
    with LOCK:
        _STATE["creds_path"] = str(path)
    _log("info", f"凭证已写入 {path}")


def _monitor(proc: subprocess.Popen, generation: int) -> None:
    while True:
        with LOCK:
            if _PROC is not proc:
                return
        try:
            if CAPTURE_JSON.is_file():
                raw = json.loads(CAPTURE_JSON.read_text(encoding="utf-8"))
                with LOCK:
                    _STATE["uid"] = raw.get("uid")
                    _STATE["_sign"] = raw.get("sign")
                    _STATE["sign_set"] = bool(raw.get("sign"))
                    _STATE["base_url"] = raw.get("base_url") or _STATE.get("base_url")
                    _STATE["urls"] = raw.get("urls") or _STATE.get("urls") or []
                    _STATE["targets_count"] = len(raw.get("target_rows") or [])
                if raw.get("sign"):
                    _finalize_creds()
        except (OSError, ValueError):
            pass
        if proc.poll() is not None:
            with LOCK:
                if _PROC is proc:
                    _STATE["proxy_active"] = False
                    _STATE["state"] = "stopped"
                    _STATE["error"] = None if proc.returncode == 0 else f"mitmproxy 退出码 {proc.returncode}"
            _finalize_creds()
            return
        time.sleep(1.0)


def status() -> dict:
    with LOCK:
        data = dict(_STATE)
    data.pop("_sign", None)
    data["logs"] = list(data.get("logs") or [])
    data["targets_captured"] = bool(data.get("targets_count"))
    data["login_captured"] = bool(data.get("uid") and data.get("sign_set"))
    if data.get("started_at") and data.get("state") in ("running", "starting"):
        try:
            from datetime import datetime
            started = datetime.fromisoformat(str(data["started_at"]))
            data["elapsed_s"] = round((datetime.now(started.tzinfo) - started).total_seconds(), 1)
        except (ValueError, TypeError):
            data["elapsed_s"] = 0.0
    else:
        data.setdefault("elapsed_s", 0.0)
    return data


def is_active() -> bool:
    with LOCK:
        return _STATE.get("state") in ("starting", "running") or _PROC is not None


def start(*, port: int = 8084, region: str = "tw",
          listen_host: str = "0.0.0.0") -> dict:
    global _PROC, _THREAD, _LOG_FILE
    with LOCK:
        if _PROC is not None and _PROC.poll() is None:
            return {"error": "模拟器抓包已在运行", "state": _STATE.get("state")}
        _STATE.update({
            "state": "starting", "mode": "emulator", "region": region,
            "port": port, "listen_host": listen_host, "proxy_active": False,
            "system_proxy_on": False, "uid": None, "sign_set": False,
            "base_url": get_region(region).get("base_url") or None,
            "targets_count": 0, "creds_path": None, "error": None,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "logs": [],
        })
    if not (1024 <= int(port) <= 65535):
        with LOCK:
            _STATE["state"] = "error"
            _STATE["error"] = "端口必须在 1024-65535"
        return status()
    try:
        import mitmproxy  # noqa: F401
    except ImportError:
        with LOCK:
            _STATE["state"] = "error"
            _STATE["error"] = "缺少 mitmproxy；请先执行 pip install mitmproxy cryptography"
        return status()
    try:
        cert, key = ensure_ca()
        _prepare_conf(cert, key)
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            _STATE["state"] = "error"
            _STATE["error"] = str(exc)
        return status()
    script = Path(__file__).resolve().parent / "tools" / "emulator_mitm.py"
    CAPTURE_JSON.unlink(missing_ok=True)
    _LOG_FILE = open(CAPTURE_LOG, "w", encoding="utf-8", errors="replace")
    cmd = [sys.executable, str(script), "--port", str(port), "--listen-host", listen_host,
           "--confdir", str(CONF_DIR), "--ca-dir", str(CA_DIR), "--out", str(CAPTURE_JSON)]
    try:
        proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[1]),
                                stdout=_LOG_FILE, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONUNBUFFERED": "1"})
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            _STATE["state"] = "error"
            _STATE["error"] = f"启动 mitmproxy 失败：{exc}"
        return status()
    with LOCK:
        _PROC = proc
        _STATE["state"] = "running"
        _STATE["proxy_active"] = True
        _STATE["port"] = port
        _STATE["pid"] = proc.pid
        _THREAD = threading.Thread(target=_monitor, args=(proc, id(proc)),
                                   name="targetforge-emucapture", daemon=True)
        _THREAD.start()
    _log("info", f"模拟器抓包已启动：{listen_host}:{port}，CA={cert}（模拟器需安装此 CA）")
    return status()


def stop() -> dict:
    global _PROC, _THREAD
    with LOCK:
        proc = _PROC
        if proc is None:
            _STATE["state"] = "idle"
            _STATE["proxy_active"] = False
            return status()
        _STATE["state"] = "stopping"
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError:
        pass
    with LOCK:
        _PROC = None
        _THREAD = None
        _STATE["state"] = "stopped"
        _STATE["proxy_active"] = False
    _finalize_creds()
    return status()
