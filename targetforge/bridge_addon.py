import base64
import gzip
import hashlib
import json
import re
import time
import os
from pathlib import Path

from gflzirc import gf_authcode

STATIC_KEY = "yundoudou"


def _resolve_data_dir() -> Path:
    override = os.environ.get("TARGETFORGE_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    # bridge_addon.py 位于 <repo>/targetforge/ 下，向上**一级**就是仓库根。
    # 不能再用 parents[2]：那会跳到仓库的上一层，导致 addon 读不到界面写入的
    # inject_targets.json，表现是 APPEND bridges=[] 的静默失效。
    return Path(__file__).resolve().parents[1] / "dataMiner" / "derived" / "targetforge"


DATA_DIR = _resolve_data_dir()
LOG = DATA_DIR / "inject_proxy.log"
MODE_FILE = DATA_DIR / "inject_mode.txt"
TARGETS_FILE = DATA_DIR / "inject_targets.json"
TARGET_URL_PART = "Index/index"
KEYFILE = DATA_DIR / "inject_key.txt"

_current_key = STATIC_KEY
_targets_warned = False


def _log(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    except OSError:
        pass


def _mode() -> str:
    try:
        value = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        return value if value in ("roundtrip", "inject") else "roundtrip"
    except OSError:
        return "roundtrip"


def _targets() -> list[int]:
    global _targets_warned
    try:
        raw = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        if not _targets_warned:
            _log(f"TARGETS_READ_FAILED path={TARGETS_FILE} err={type(exc).__name__}: {exc}")
            _targets_warned = True
        return []
    if isinstance(raw, dict):
        raw = raw.get("targets") or []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        try:
            tid = int(item)
        except (TypeError, ValueError):
            continue
        if tid > 0 and tid not in out:
            out.append(tid)
    if not out and not _targets_warned:
        _log(f"TARGETS_EMPTY path={TARGETS_FILE}")
        _targets_warned = True
    return out[:35]


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _raw_decrypt(encoded: str, key: str) -> bytes:
    key_hash = _md5(key)
    keya = _md5(key_hash[0:16])
    keyb = _md5(key_hash[16:32])
    cryptkey = keyb + _md5(keyb)
    cryptkey_bytes = cryptkey.encode("ascii")
    b64 = encoded.strip()
    b64 += "=" * ((4 - len(b64) % 4) % 4)
    encrypted = base64.b64decode(b64)
    box = list(range(256))
    rndkey = [cryptkey_bytes[i % len(cryptkey_bytes)] for i in range(256)]
    j = 0
    for i in range(256):
        j = (j + box[i] + rndkey[i]) % 256
        box[i], box[j] = box[j], box[i]
    a = j = 0
    result = bytearray()
    for idx in range(len(encrypted)):
        a = (a + 1) % 256
        j = (j + box[a]) % 256
        box[a], box[j] = box[j], box[a]
        result.append(encrypted[idx] ^ box[(box[a] + box[j]) % 256])
    return bytes(result)


def _encrypt_bytes(payload: bytes, key: str) -> str:
    key_hash = _md5(key)
    keya = _md5(key_hash[0:16])
    keyb = _md5(key_hash[16:32])
    cryptkey = keyb + _md5(keyb)
    cryptkey_bytes = cryptkey.encode("ascii")
    expiry = f"{int(time.time()) + 3600:010d}".encode("ascii")
    checksum = hashlib.md5(payload + keya.encode("ascii")).hexdigest()[:16].encode("ascii")
    data = expiry + checksum + payload
    box = list(range(256))
    rndkey = [cryptkey_bytes[i % len(cryptkey_bytes)] for i in range(256)]
    j = 0
    for i in range(256):
        j = (j + box[i] + rndkey[i]) % 256
        box[i], box[j] = box[j], box[i]
    a = j = 0
    result = bytearray()
    for idx in range(len(data)):
        a = (a + 1) % 256
        j = (j + box[a]) % 256
        box[a], box[j] = box[j], box[a]
        result.append(data[idx] ^ box[(box[a] + box[j]) % 256])
    return base64.b64encode(bytes(result)).decode("ascii")


def _decode(body: bytes):
    match = re.search(rb"#([A-Za-z0-9+/=]+)", body or b"")
    if not match:
        return None, None, None, False
    encoded = match.group(1).decode("ascii")
    for key in (_current_key, STATIC_KEY):
        decoded = gf_authcode(encoded, "DECODE", key)
        if not decoded:
            continue
        try:
            payload = json.loads(decoded)
        except Exception:
            continue
        raw = _raw_decrypt(encoded, key)
        compressed = len(raw) > 26 and raw[26:28] == b"\x1f\x8b"
        return payload, match, key, compressed
    return None, None, None, False


def _update_key(payload: dict) -> None:
    global _current_key
    uid = payload.get("uid")
    sign = payload.get("sign")
    if uid and sign:
        _current_key = str(sign)
        try:
            KEYFILE.write_text(f"uid={uid}\nsign={sign}\n", encoding="utf-8")
        except OSError:
            pass
        _log(f"KEY_UPDATE uid={uid} sign_len={len(str(sign))}")


def request(flow):
    return


def error(flow):
    return


def response(flow):
    try:
        url = flow.request.pretty_url or ""
        path = flow.request.path or ""
        if "index.php" not in url:
            return
        body = flow.response.content or b""
        payload, match, key_used, compressed = _decode(body)
        if not isinstance(payload, dict) or match is None:
            if TARGET_URL_PART in path:
                _log(f"Index decode failed bytes={len(body)} head={body[:32]!r}")
            return
        _update_key(payload)
        if TARGET_URL_PART not in path:
            return
        mode = _mode()
        entries = payload.get("targettrain_collect_user_info")
        if not isinstance(entries, list):
            entries = []
        if mode == "inject":
            targets = _targets()
            existing = {int(item.get("enemy_team_id") or 0) for item in entries if isinstance(item, dict)}
            next_order = max([int(item.get("order_id") or 0) for item in entries if isinstance(item, dict)] or [0]) + 1
            appended = []
            for tid in targets:
                if tid in existing or len(entries) >= 35:
                    continue
                entries.append({
                    "user_id": payload.get("uid") or 0,
                    "order_id": next_order,
                    "enemy_team_id": tid,
                    "fight_type": 0,
                    "fight_coef": "",
                    "fight_environment_group": "",
                    "is_lock": 0,
                })
                existing.add(tid)
                appended.append(tid)
                next_order += 1
            payload["targettrain_collect_user_info"] = entries
            _log(f"APPEND bridges={appended} total_entries={len(entries)} next_order={next_order}")
        decoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if compressed:
            payload_bytes = gzip.compress(decoded.encode("utf-8"), compresslevel=9, mtime=0)
            encrypted = _encrypt_bytes(payload_bytes, key_used)
        else:
            encrypted = gf_authcode(decoded, "ENCODE", key_used)
        new_body = body[:match.start(1)] + encrypted.encode("ascii") + body[match.end(1):]
        flow.response.content = new_body
        try:
            del flow.response.headers["content-encoding"]
        except KeyError:
            pass
        flow.response.headers["content-length"] = str(len(new_body))
        _log(f"REENCODED mode={mode} key={key_used} gzip={compressed} body={len(body)}->{len(new_body)}")
    except Exception as exc:
        _log(f"response hook error: {type(exc).__name__}: {exc}")
