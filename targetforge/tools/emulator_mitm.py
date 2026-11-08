"""台服 HTTPS 抓包：mitmproxy + 自定义 CA，解出 uid/sign。

前置：python scripts\\android_ca_setup.py 已经把 CA 绑挂进模拟器的系统证书目录。

用法：
  python scripts/tw_mitm.py --port 8084 --confdir dataMiner/derived/mitm_conf --ca-dir dataMiner/derived/mitm_ca
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.parse
from pathlib import Path

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

try:
    from gflzirc import gf_authcode
except ModuleNotFoundError:
    gf_authcode = None

STATIC_KEY = "yundoudou"


def prepare_confdir(confdir: Path, ca_dir: Path) -> None:
    confdir.mkdir(parents=True, exist_ok=True)
    cert = (ca_dir / "ca.crt").read_bytes()
    key = (ca_dir / "ca.key").read_bytes()
    (confdir / "mitmproxy-ca.pem").write_bytes(key + cert)
    (confdir / "mitmproxy-ca-cert.pem").write_bytes(cert)


def try_decode(text: str, key: str = STATIC_KEY) -> str | None:
    if gf_authcode is None or not text:
        return None
    try:
        return gf_authcode(text, "DECODE", key)
    except Exception:
        return None


def decode_any(text: str, sign: str | None) -> str | None:
    """先按静态 key 解（明文包），失败再按本次登录的 sign 解（会话包）。"""
    for key in (STATIC_KEY, sign):
        if not key:
            continue
        decoded = try_decode(text, key)
        if not decoded:
            continue
        stripped = decoded.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return decoded
        # 解出来是乱码/二进制 → 换下一个 key
    return None


class Recorder:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.data = {"uid": None, "sign": None, "base_url": None, "urls": [],
                     "targets": [], "target_rows": []}

    def save(self) -> None:
        self.out.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def request(self, flow) -> None:
        url = flow.request.pretty_url
        if url not in self.data["urls"]:
            self.data["urls"].append(url)
            print(f"[REQ] {flow.request.method} {url}", flush=True)
        if "index.php/" in url and not self.data["base_url"]:
            head, tail = url.split("index.php/", 1)
            zone = tail.split("/")[0]
            if zone.isdigit():
                self.data["base_url"] = f"{head}index.php/{zone}/"
                print(f"[BASE] {self.data['base_url']}", flush=True)
        body = flow.request.get_text(strict=False) or ""
        if "outdatacode" in body:
            parsed = urllib.parse.parse_qs(body)
            raw = (parsed.get("outdatacode") or [""])[0]
            decoded = decode_any(raw, self.data.get("sign"))
            if decoded:
                print(f"[C2S] {url}\n     {decoded[:400]}", flush=True)
                self._scan(json.loads(decoded) if decoded.strip().startswith("{") else {})

    def response(self, flow) -> None:
        text = flow.response.get_text(strict=False) or ""
        if "#" not in text:
            return
        import re

        match = re.search(r"#([A-Za-z0-9+/=]+)", text)
        if not match:
            return
        decoded = decode_any(match.group(1), self.data.get("sign"))
        if not decoded:
            return
        print(f"[S2C] {flow.request.pretty_url}\n     {decoded[:300]}", flush=True)
        try:
            payload = json.loads(decoded)
        except Exception:
            return
        self._scan(payload)
        info = payload.get("targettrain_collect_user_info") if isinstance(payload, dict) else None
        if isinstance(info, list):
            # 保留 order_id：这是「收藏標靶N」的真实编号，注入前必须知道
            rows = [{"order_id": int(i.get("order_id") or 0),
                     "enemy_team_id": int(i.get("enemy_team_id") or 0),
                     "fight_type": i.get("fight_type"),
                     "fight_coef": i.get("fight_coef"),
                     "fight_environment_group": i.get("fight_environment_group")}
                    for i in info if i.get("enemy_team_id")]
            self.data["target_rows"] = sorted(rows, key=lambda r: r["order_id"])
            self.data["targets"] = [str(r["enemy_team_id"]) for r in self.data["target_rows"]]
            print(f"[TARGETS] {len(rows)} 个: "
                  f"{[(r['order_id'], r['enemy_team_id']) for r in self.data['target_rows'][:8]]}",
                  flush=True)
            self.save()

    def _scan(self, payload) -> bool:
        if not isinstance(payload, dict):
            return False
        uid = payload.get("uid")
        sign = payload.get("sign")
        if uid and sign and str(sign) != self.data.get("sign"):
            self.data["uid"] = str(uid)
            self.data["sign"] = str(sign)
            print(f"[KEY] uid={uid} sign={sign}", flush=True)
            self.save()
            return True
        return False


async def run(args) -> None:
    ca_dir = Path(args.ca_dir)
    confdir = Path(args.confdir)
    prepare_confdir(confdir, ca_dir)
    recorder = Recorder(Path(args.out))
    # 代理中途重启时拿不到登录包 → 允许用 --sign 直接喂已知 sign 解会话包
    if args.sign:
        recorder.data["sign"] = str(args.sign)
        recorder.data["uid"] = str(args.uid) if args.uid else None
        print(f"[SEED] sign={args.sign} uid={args.uid or '-'}", flush=True)

    opts = options.Options(
        listen_host=args.listen_host,
        listen_port=args.port,
        confdir=str(confdir),
        ssl_insecure=True,
    )
    master = DumpMaster(opts)
    master.addons.add(recorder)
    print(f"[MITM] 0.0.0.0:{args.port}  CA={ca_dir/'ca.crt'}", flush=True)
    try:
        await master.run()
    finally:
        recorder.save()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--confdir", default="dataMiner/derived/mitm_conf")
    parser.add_argument("--ca-dir", default="dataMiner/derived/mitm_ca")
    parser.add_argument("--out", default="dataMiner/derived/tw_creds.json")
    parser.add_argument("--sign", default=None,
                        help="已知 sign（代理中途重启、抓不到登录包时用）")
    parser.add_argument("--uid", default=None)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
