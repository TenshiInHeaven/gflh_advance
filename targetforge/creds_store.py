"""凭证文件的安全读写：Windows DPAPI 加密 + 文件 ACL。

格式（加密）::

    {"dpapi": "v1", "data": "<base64(CryptProtectData(json))>"}

兼容旧的明文 JSON（读取时自动识别）；新写入默认加密（非 Windows 无 DPAPI 时退化为明文）。
加密绑定当前 Windows 用户，复制到别的机器/用户无法解密。
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from targetforge.security import restrict_file_acl

MARKER = "dpapi"
VERSION = "v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DataBlob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _take_blob(blob: _DataBlob) -> bytes:
    value = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return value


def _dpapi(data: bytes, protect: bool) -> bytes | None:
    """调用 CryptProtectData / CryptUnprotectData；失败返回 None（不抛）。"""
    if os.name != "nt" or not data:
        return None
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob = _blob(data)
    out_blob = _DataBlob()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN（后台调用不弹窗）
    try:
        if protect:
            ok = crypt32.CryptProtectData(
                ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob))
        else:
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob))
        if not ok:
            return None
        try:
            return _take_blob(out_blob)
        except (ValueError, OSError):
            return None
    except (AttributeError, OSError, ValueError):
        return None


def encrypt_payload(payload: dict) -> dict:
    """把凭证对象包成 DPAPI 加密 JSON；无法加密（非 Windows/失败）时返回原对象。"""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob = _dpapi(text, protect=True)
    if blob is None:
        return payload
    return {MARKER: VERSION, "data": base64.b64encode(blob).decode("ascii")}


def decrypt_payload(payload: Any) -> dict | None:
    """接受加密包装或明文 JSON 对象；解不开返回 None。"""
    if not isinstance(payload, dict):
        return None
    if payload.get(MARKER) != VERSION:
        return dict(payload)
    raw = str(payload.get("data") or "")
    try:
        blob = base64.b64decode(raw.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return None
    plain = _dpapi(blob, protect=False)
    if plain is None:
        return None
    try:
        data = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_creds(path: str | Path) -> dict | None:
    """读凭证（自动解密）；不存在/损坏/解密失败返回 None。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return decrypt_payload(payload)


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    restrict_file_acl(path)
    return path


def write_creds(path: str | Path, payload: dict) -> Path:
    """原子写凭证：优先 DPAPI 加密；失败退化为明文（仍设置 ACL）。"""
    target = Path(path)
    wrapped = encrypt_payload(payload)
    text = json.dumps(wrapped, ensure_ascii=False, indent=1)
    return _atomic_write(target, text)


def is_encrypted(path: str | Path) -> bool:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get(MARKER) == VERSION


def migrate_plain(path: str | Path) -> bool:
    """把已有的明文凭证原地改成 DPAPI 加密；无法加密/无文件返回 False。"""
    target = Path(path)
    if not target.is_file() or is_encrypted(target):
        return False
    payload = read_creds(target)
    if payload is None:
        return False
    try:
        write_creds(target, payload)
        return is_encrypted(target)
    except OSError:
        return False


def dpapi_available() -> bool:
    return os.name == "nt" and _dpapi(b"probe", protect=True) is not None
