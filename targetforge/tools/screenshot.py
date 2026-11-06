"""TargetForge 页面截图 / console 自检（Lead 用，Playwright + 系统 Edge headless）。

用法：
    python targetforge/tools/screenshot.py --url http://127.0.0.1:8765 --out tmp/lead_shots
    python targetforge/tools/screenshot.py --url http://127.0.0.1:8765 --hash "#/chapters,#/species"
    python targetforge/tools/screenshot.py --url http://127.0.0.1:8765 --steps-file tmp/steps.json

steps-file JSON 格式：[{"name":"01_chapters","hash":"#/chapters","click":["text=关卡图鉴"],"wait":800}, ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_STEPS = [
    {"name": "01_overview", "hash": "", "wait": 1200},
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--out", default="tmp/lead_shots")
    parser.add_argument("--steps-file", default=None)
    parser.add_argument("--hash", default=None, help="逗号分隔的 hash 路由，如 #/chapters,#/species")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--full-page", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps = DEFAULT_STEPS
    if args.steps_file:
        steps = json.loads(Path(args.steps_file).read_text(encoding="utf-8-sig"))
    elif args.hash:
        steps = [{"name": f"{i:02d}_{h.strip('#/').replace('/', '_')}", "hash": h.strip(), "wait": 1200}
                 for i, h in enumerate(args.hash.split(",")) if h.strip()]

    console_errors: list[str] = []
    page_errors: list[str] = []
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": args.width, "height": args.height},
                                      device_scale_factor=1)
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
                if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        for step in steps:
            url = args.url.rstrip("/") + "/" + (step.get("hash") or "")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(int(step.get("wait") or 800))
            for selector in step.get("click") or []:
                try:
                    page.click(selector, timeout=5000)
                    page.wait_for_timeout(int(step.get("click_wait") or 700))
                except Exception as exc:  # noqa: BLE001
                    results.append({"step": step.get("name"), "click_error": f"{selector}: {exc}"})
            text = ""
            try:
                text = page.inner_text("body")[:4000]
            except Exception:  # noqa: BLE001
                pass
            target = out_dir / f"{step.get('name') or 'shot'}.png"
            page.screenshot(path=str(target), full_page=bool(step.get("full_page", args.full_page)))
            results.append({"step": step.get("name"), "url": page.url, "shot": str(target),
                            "title": page.title(), "body_head": text[:300],
                            "body_len": len(text)})
            print(f"[shot] {target} ({page.title()}) head={text[:80]!r}")
        browser.close()

    print("\n== console errors/warnings ==")
    for entry in console_errors:
        print(entry[:400])
    print("\n== page errors ==")
    for entry in page_errors:
        print(entry[:400])
    print("\n== summary ==")
    print(json.dumps(results, ensure_ascii=False, indent=1)[:6000])
    (out_dir / "report.json").write_text(json.dumps(
        {"results": results, "console": console_errors, "page_errors": page_errors},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if page_errors or any("error" in e for e in console_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
