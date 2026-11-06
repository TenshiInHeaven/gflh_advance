"""ui_selfcheck.py —— 靶机工坊前端 Playwright 自检 / 截图脚本。

用法（仓库根目录执行）：

    python targetforge/tools/ui_selfcheck.py                # 自动起服务(8771) + 真实 API 截图
    python targetforge/tools/ui_selfcheck.py --mock         # 自动起服务 + ?mock=1 假数据截图
    python targetforge/tools/ui_selfcheck.py --url http://127.0.0.1:8765   # 复用已有服务
    python targetforge/tools/ui_selfcheck.py --no-server    # 只跑浏览器，连默认 8771

行为：
  * 用系统 Edge（channel="msedge", headless）打开页面，视口 1600x1000；
  * **每个截图前都用全新 URL 全量加载页面**（带 run 计数参数，避免 hash 切换假象），
    并断言首屏 `#view` 真的渲染出了内容（防「首屏空白」回归）；
  * 收集 console error / pageerror，逐页等待关键 DOM 并截图到 tmp/frontend_shots/；
  * 真实 API 模式下会在结束后恢复原有序列草稿（避免污染 state.json）；
  * 有 console error / pageerror / 断言失败时退出码非 0。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 仓库根（GF Forge）
OUT_DIR = ROOT / "tmp" / "frontend_shots"
DEFAULT_PORT = 8771
VIEWPORT = {"width": 1600, "height": 1000}

SHOTS: list[str] = []

# 每个路由都用「全新整页加载」验证首屏渲染
ROUTE_SMOKE = [
    "/overview",
    "/chapters",
    "/chapters/main-1",
    "/stages/5",
    "/chapters/grayzone",
    "/grayzone/共生净土",
    "/species",
    "/species/5",
    "/teams/6549244",
    "/sequence",
    "/capture",
    "/tutorial",
    "/chapters/orphan",
]


# ---------------------------------------------------------------------------
# HTTP 工具（不启动浏览器时也能用）
# ---------------------------------------------------------------------------
def http_json(url: str, timeout: float = 5.0):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post(url: str, payload: dict, timeout: float = 10.0):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_server(port: int, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return http_json(f"http://127.0.0.1:{port}/api/health")
        except (urllib.error.URLError, ConnectionError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise SystemExit(f"服务在 {timeout}s 内没有就绪：{last_error}")


def wait_catalog(port: int, timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    printed = False
    while time.time() < deadline:
        try:
            health = http_json(f"http://127.0.0.1:{port}/api/health")
        except Exception:  # noqa: BLE001
            time.sleep(1)
            continue
        catalog = health.get("catalog") or {}
        state = catalog.get("state")
        if state == "ready":
            print(f"[selfcheck] catalog ready · counts={catalog.get('counts')} · built_at={catalog.get('built_at')}")
            return health
        if state == "error":
            raise SystemExit(f"catalog 构建失败：{catalog.get('error')}\n{catalog.get('detail', '')[:1500]}")
        if not printed:
            print(f"[selfcheck] 等待 catalog 构建（state={state}，首次约 20~60s）…")
            printed = True
        time.sleep(1.5)
    raise SystemExit(f"catalog 在 {timeout}s 内未就绪")


def start_server(port: int) -> subprocess.Popen:
    log_path = OUT_DIR / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")
    print(f"[selfcheck] 启动 python -m targetforge --port {port}（日志 {log_path}）")
    proc = subprocess.Popen(
        [sys.executable, "-m", "targetforge", "--port", str(port)],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_server(port)
    except SystemExit:
        proc.terminate()
        raise
    return proc


# ---------------------------------------------------------------------------
# 截图 / 断言工具
# ---------------------------------------------------------------------------
class Checker:
    def __init__(self, page, out_dir: Path, console_errors: list, page_errors: list):
        self.page = page
        self.out_dir = out_dir
        self.console_errors = console_errors
        self.page_errors = page_errors
        self.failures: list[str] = []
        self.passed: list[str] = []

    def wait(self, selector: str, timeout: int = 25000):
        try:
            self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            self.passed.append(f"DOM {selector}")
            return True
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"等待 DOM 失败：{selector}（{type(exc).__name__}: {exc}）")
            return False

    def assert_count(self, selector: str, minimum: int = 1):
        count = self.page.locator(selector).count()
        if count >= minimum:
            self.passed.append(f"{selector} 数量 {count} >= {minimum}")
            return True
        self.failures.append(f"{selector} 数量 {count} < {minimum}")
        return False

    def shot(self, name: str, selector: str | None = None, settle: int = 420, scroll_top: bool = True):
        if selector:
            self.wait(selector)
        if scroll_top:
            try:
                self.page.evaluate("() => { const m = document.querySelector('.main'); if (m) m.scrollTop = 0; }")
            except Exception:  # noqa: BLE001
                pass
        self.page.wait_for_timeout(settle)
        path = self.out_dir / name
        self.page.screenshot(path=str(path))
        SHOTS.append(str(path))
        print(f"[selfcheck] 截图 {name}  <- {self.page.url}")

    def assert_view_rendered(self, route: str):
        try:
            count = self.page.locator("#view > *").count()
        except Exception:  # noqa: BLE001
            count = 0
        if count > 0:
            self.passed.append(f"首屏渲染 {route}")
            return True
        self.failures.append(f"首屏空白：{route}（#view 没有子节点）")
        return False


def url_for(base_url: str, mock: bool, route: str, counter: int) -> str:
    params = []
    if mock:
        params.append("mock=1")
    params.append(f"_r={counter}")
    return f"{base_url.rstrip('/')}/?{'&'.join(params)}#/{(route or '').lstrip('/')}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_checks(base_url: str, mock: bool) -> int:
    from playwright.sync_api import sync_playwright

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[dict] = []
    page_errors: list[dict] = []
    url = base_url.rstrip("/") + "/" + ("?mock=1" if mock else "")
    print(f"[selfcheck] 打开 {url}")

    # 记录真实 API 原始序列，结束后恢复（mock 模式不影响服务端状态）
    original_sequence: list[int] | None = None
    if not mock:
        try:
            original_sequence = [int(team["id"]) for team in (http_json(base_url.rstrip("/") + "/api/sequence").get("draft") or [])]
            print(f"[selfcheck] 原始序列 {len(original_sequence)} 支队伍（结束后恢复）")
        except Exception as exc:  # noqa: BLE001
            print(f"[selfcheck] 读取原始序列失败（忽略）：{exc}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="zh-CN")
        page = context.new_page()

        page.on(
            "console",
            lambda message: console_errors.append({"type": message.type, "text": message.text})
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append({"error": str(error)}))

        checker = Checker(page, out_dir, console_errors, page_errors)
        state = {"counter": 0, "overlay_shot": False}

        def dismiss_overlay(allow_shot: bool = False):
            try:
                page.wait_for_selector(".tut-overlay", state="visible", timeout=1800)
            except Exception:  # noqa: BLE001
                return
            if allow_shot and not state["overlay_shot"]:
                page.wait_for_timeout(250)
                path = out_dir / "00_tutorial_overlay.png"
                page.screenshot(path=str(path))
                SHOTS.append(str(path))
                print("[selfcheck] 截图 00_tutorial_overlay.png")
                state["overlay_shot"] = True
            skip = page.locator(".tut-overlay [data-skip]")
            if skip.count() > 0:
                skip.click()
                page.wait_for_timeout(260)
            if mock:
                # mock 教程状态存 sessionStorage；标记已看，后续整页加载不再弹引导
                page.evaluate(
                    "() => window.sessionStorage.setItem('tf-mock-tutorial', JSON.stringify({completed: [], dismissed: true}))"
                )

        def ensure_overlay_shot():
            """真实 API 模式下教程可能已标记 dismissed，用顶栏按钮强制打开截一张 overlay。"""
            if state["overlay_shot"]:
                return
            trigger = page.locator("#topbar-tutorial")
            if trigger.count() == 0:
                return
            trigger.click()
            try:
                page.wait_for_selector(".tut-overlay", state="visible", timeout=4000)
            except Exception:  # noqa: BLE001
                return
            page.wait_for_timeout(300)
            path = out_dir / "00_tutorial_overlay.png"
            page.screenshot(path=str(path))
            SHOTS.append(str(path))
            print("[selfcheck] 截图 00_tutorial_overlay.png（顶栏手动打开新手引导）")
            state["overlay_shot"] = True
            skip = page.locator(".tut-overlay [data-skip]")
            if skip.count() > 0:
                skip.click()
                page.wait_for_timeout(260)

        def load(route: str, wait_selector: str | None = None, settle: int = 620, allow_overlay_shot: bool = False):
            state["counter"] += 1
            target = url_for(base_url, mock, route, state["counter"])
            page.goto(target, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#view", state="attached", timeout=25000)
            page.wait_for_function(
                "() => { const v = document.querySelector('#view'); return v && v.children.length > 0; }",
                timeout=30000,
            )
            dismiss_overlay(allow_shot=allow_overlay_shot)
            if wait_selector:
                checker.wait(wait_selector)
            page.wait_for_timeout(settle)
            checker.assert_view_rendered(route)

        def maybe_confirm():
            page.wait_for_timeout(450)
            confirm = page.locator(".modal [data-role='confirm']")
            if confirm.count() > 0:
                confirm.click()
                page.wait_for_timeout(600)

        try:
            # ---------------- 00 首次引导 overlay + 01 总览 ----------------
            load("/overview", ".hero", allow_overlay_shot=True)
            ensure_overlay_shot()
            checker.wait(".quick-card")
            checker.assert_count(".stat-tile", 6)
            checker.shot("01_overview.png", ".hero", settle=500)

            # ---------------- 02 关卡图鉴 ----------------
            load("/chapters", ".chapter-card")
            checker.assert_count(".chapter-card", 8)
            checker.shot("02_chapters.png", ".chapter-grid")

            # ---------------- 03 章节详情（main-1） ----------------
            load("/chapters/main-1", ".stage-row")
            checker.assert_count(".stage-row", 5)
            checker.shot("03_chapter_detail.png", ".stage-list")

            # ---------------- 04 关卡队伍（挑队伍最多的关卡） ----------------
            heaviest = page.evaluate(
                """() => {
                    const rows = [...document.querySelectorAll('.stage-row')];
                    let best = null, bestN = -1;
                    for (const row of rows) {
                        const b = row.querySelector('.stage-counts b');
                        const n = b ? parseInt(b.textContent.replace(/[^0-9]/g, ''), 10) || 0 : 0;
                        if (n > bestN) { bestN = n; best = row; }
                    }
                    if (best) { best.click(); return bestN; }
                    return -1;
                }"""
            )
            print(f"[selfcheck] 打开队伍最多的关卡（{heaviest} 支队伍）")
            checker.wait(".team-card")
            checker.shot("04_stage_teams.png", ".team-grid")

            # 加入序列，供序列页 / 执行预览使用
            add_all = page.locator('[data-act="add-all"]')
            if add_all.count() > 0:
                add_all.first.click()
                maybe_confirm()
                try:
                    page.wait_for_function(
                        "() => { const el = document.querySelector('[data-nav-count=\"sequence\"]');"
                        " return el && Number(el.textContent) > 0; }",
                        timeout=12000,
                    )
                    checker.passed.append("从关卡加入序列")
                except Exception as exc:  # noqa: BLE001
                    checker.failures.append(f"加入序列失败：{exc}")

            # ---------------- 05 怪种图鉴 ----------------
            load("/species", ".species-card")
            checker.assert_count(".species-card", 10)
            checker.shot("05_species.png", ".species-grid")

            # ---------------- 06 怪种详情（服务端分页） ----------------
            load("/species/5", ".team-card")
            checker.shot("06_species_detail.png", ".team-grid")

            # ---------------- 07 队伍详情抽屉（不得出现技能信息） ----------------
            first_card = page.locator(".team-card").first
            first_card.click(position={"x": 40, "y": 24})
            checker.wait(".drawer")
            checker.wait(".drawer .data-table tbody tr")
            checker.wait(".drawer .appear-list", timeout=12000)
            checker.shot("07_team_detail.png", ".drawer .data-table")
            drawer_text = page.locator(".drawer").inner_text()
            forbidden = ["技能", "skill", "Skill", "SKILL", "触发器", "trigger", "Trigger"]
            hits = [word for word in forbidden if word in drawer_text]
            if hits:
                checker.failures.append(f"队伍详情出现技能相关信息：{hits}")
            else:
                checker.passed.append("队伍详情无技能信息")
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

            # ---------------- 13 灰域区域 + 12 灰域队伍分页 ----------------
            load("/chapters/grayzone", ".area-card")
            checker.assert_count(".area-card", 12)
            checker.shot("13_grayzone_areas.png", ".area-grid")

            load("/grayzone/共生净土", ".team-card")
            checker.wait(".pager")
            title_text = page.locator(".page-title").first.inner_text()
            if "%E" in title_text:
                checker.failures.append(f"灰域区域标题未解码：{title_text}")
            elif "共生净土" in title_text:
                checker.passed.append("灰域区域标题已解码")
            checker.shot("12_grayzone.png", ".team-grid")
            add_page = page.locator('[data-act="add-page"]')
            if add_page.count() > 0:
                add_page.first.click()
                maybe_confirm()
                page.wait_for_timeout(700)

            # ---------------- 08 序列编排 ----------------
            load("/sequence", ".seq-big-item")
            checker.assert_count(".seq-big-item", 3)
            checker.shot("08_sequence.png", ".seq-page-cols")

            # ---------------- 09 执行预览（rebuild 模式，展示删除/新增/最终） ----------------
            mode_btn = page.locator('[data-mode="rebuild"]')
            if mode_btn.count() > 0:
                mode_btn.first.click()
                page.wait_for_timeout(250)
            execute_btn = page.locator('[data-act="execute"]').first
            execute_btn.wait_for(state="visible", timeout=10000)
            execute_btn.click()
            checker.wait(".modal .modal-body")
            page.wait_for_timeout(350)
            preview_btn = page.locator('.modal [data-act="preview"]')
            if preview_btn.count() > 0:
                preview_btn.first.click()
            checker.wait(".modal .plan-stat")
            page.wait_for_timeout(450)
            checker.shot("09_execute_preview.png", ".modal .plan-cols")
            page.keyboard.press("Escape")
            page.wait_for_timeout(350)

            # ---------------- 10 登录抓取 ----------------
            load("/capture", ".capture-panel")
            checker.wait(".wizard-step")
            if mock:
                start_btn = page.locator('.capture-panel [data-act="start"]').first
                if start_btn.count() and not start_btn.is_disabled():
                    start_btn.click()
                    page.wait_for_timeout(3400)
            checker.shot("10_capture.png", ".capture-cols")

            # ---------------- 11 使用教程 ----------------
            load("/tutorial", ".faq-item")
            checker.assert_count(".faq-item", 7)
            checker.shot("11_tutorial.png", ".tut-content")

            # ---------------- 14 无固定关卡章节（badge 数据） ----------------
            load("/chapters/orphan", ".team-card")
            checker.shot("14_orphan_chapter.png", ".team-grid")

            # ---------------- 路由首屏回归：逐个整页加载（覆盖全部 13 个路由） ----------------
            print("[selfcheck] 逐路由整页加载回归（每次都是全新 URL 全量加载）…")
            for route in ROUTE_SMOKE:
                state["counter"] += 1
                page.goto(url_for(base_url, mock, route, state["counter"]), wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector("#view", state="attached", timeout=25000)
                try:
                    page.wait_for_function(
                        "() => { const v = document.querySelector('#view'); return v && v.children.length > 0; }",
                        timeout=20000,
                    )
                    checker.passed.append(f"整页加载渲染 {route}")
                except Exception as exc:  # noqa: BLE001
                    checker.failures.append(f"整页加载后 #view 仍为空：{route}（{exc}）")
                error_state = page.locator(".error-state").count()
                if error_state:
                    checker.failures.append(f"路由出现错误态：{route}")

        finally:
            error_payload = {
                "console_errors": console_errors,
                "page_errors": page_errors,
                "assert_failures": checker.failures,
                "passed": checker.passed,
                "screenshots": SHOTS,
                "url": url,
            }
            (out_dir / "selfcheck_result.json").write_text(
                json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            context.close()
            browser.close()

    # 后端 12 个灰域区域都能返回队伍（真实 API 模式）
    if not mock:
        try:
            areas = http_json(base_url.rstrip("/") + "/api/grayzone/areas").get("areas") or []
            assert len(areas) == 12, f"灰域区域数量 {len(areas)} != 12"
            bad = []
            for area in areas:
                data = http_json(
                    base_url.rstrip("/")
                    + "/api/grayzone/teams?area="
                    + urllib.parse.quote(area["id"])
                    + "&limit=1"
                )
                if not (data.get("items") or []):
                    bad.append(area["id"])
            if bad:
                checker.failures.append(f"灰域区域取队伍为空：{bad}")
            else:
                checker.passed.append(f"灰域 12 个区域均能取到队伍（{areas[0]['id']} 等）")
        except Exception as exc:  # noqa: BLE001
            checker.failures.append(f"灰域区域后端校验失败：{exc}")

    # 恢复原始序列（真实 API 模式）
    if original_sequence is not None:
        try:
            if original_sequence:
                http_post(base_url.rstrip("/") + "/api/sequence", {"action": "set", "team_ids": original_sequence})
            else:
                http_post(base_url.rstrip("/") + "/api/sequence", {"action": "clear"})
            print(f"[selfcheck] 已恢复原始序列（{len(original_sequence)} 支）")
        except Exception as exc:  # noqa: BLE001
            print(f"[selfcheck] 恢复原始序列失败：{exc}")

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("自检结果 Selfcheck Summary")
    print("=" * 78)
    print(f"截图目录：{out_dir}")
    for path in SHOTS:
        exists = Path(path).is_file()
        print(f"  {'OK ' if exists else 'MISS'} {path}")
    print(f"\nDOM 断言通过：{len(checker.passed)} 项")
    if checker.failures:
        print(f"\n断言失败：{len(checker.failures)} 项")
        for item in checker.failures:
            print(f"  ! {item}")
    print(f"\nconsole error：{len(console_errors)} 条")
    for item in console_errors[:20]:
        print(f"  ! [{item['type']}] {item['text'][:500]}")
    print(f"page error：{len(page_errors)} 条")
    for item in page_errors[:20]:
        print(f"  ! {item['error'][:800]}")

    ok = not console_errors and not page_errors and not checker.failures and len(SHOTS) >= 12
    print("\n" + ("PASS - 前端自检通过（console 无 error）" if ok else "FAIL - 存在错误，请查看上面的日志"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TargetForge 前端 Playwright 自检")
    parser.add_argument("--url", default="", help="复用已有服务地址，例如 http://127.0.0.1:8765")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="自起服务端口（默认 8771）")
    parser.add_argument("--mock", action="store_true", help="使用 ?mock=1 假数据（catalog 未就绪时视觉自测）")
    parser.add_argument("--skip-catalog-wait", action="store_true", help="跳过 catalog ready 等待")
    parser.add_argument("--no-server", action="store_true", help="不启动服务，直接连 --port / 8771")
    args = parser.parse_args(argv)

    proc = None
    try:
        if args.url:
            base_url = args.url.rstrip("/")
            health = http_json(base_url + "/api/health")
            print(f"[selfcheck] 复用服务 {base_url}（catalog={health.get('catalog', {}).get('state')}）")
            if not args.mock and not args.skip_catalog_wait:
                port = base_url.rsplit(":", 1)[-1]
                if port.isdigit():
                    wait_catalog(int(port))
        elif args.no_server:
            base_url = f"http://127.0.0.1:{args.port}"
            wait_server(args.port)
            print(f"[selfcheck] 连接已有服务 {base_url}")
            if not args.mock and not args.skip_catalog_wait:
                wait_catalog(args.port)
        else:
            proc = start_server(args.port)
            base_url = f"http://127.0.0.1:{args.port}"
            if not args.mock and not args.skip_catalog_wait:
                wait_catalog(args.port)
        return run_checks(base_url, args.mock)
    finally:
        if proc is not None:
            print("[selfcheck] 关闭自启服务")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
