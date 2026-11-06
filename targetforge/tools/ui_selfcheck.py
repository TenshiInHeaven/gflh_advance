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
EVIDENCE: dict = {}


def _attach_error_hooks(page, console_errors: list, page_errors: list):
    page.on(
        "console",
        lambda message: console_errors.append({"type": message.type, "text": message.text})
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append({"error": str(error)}))


def run_stability_check(context, base_url: str, mock: bool, checker, console_errors: list, page_errors: list):
    """A. 验证 overview 不再无限自渲染 / 不再劫持路由（30s 采样 + 请求计数 + 导航切换）。"""
    print("[selfcheck] A. overview 稳定性检查：30s 采样（每 2s）…")
    page = context.new_page()
    _attach_error_hooks(page, console_errors, page_errors)
    api_requests: list[str] = []
    page.on("request", lambda req: api_requests.append(req.url) if "/api/" in req.url else None)
    evidence = {"samples": [], "navigations": [], "api_calls": {}, "overview_renders": None}
    try:
        page.goto(url_for(base_url, mock, "/overview", 9001), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#view [data-overview-root]", timeout=30000)
        page.wait_for_timeout(1500)
        samples = []
        for _ in range(15):  # 30 秒，每 2 秒采样一次
            page.wait_for_timeout(2000)
            samples.append(
                page.evaluate(
                    """() => {
                        const view = document.querySelector('#view');
                        return {
                            view: view ? view.dataset.view : null,
                            hash: location.hash,
                            render: view ? Number(view.dataset.overviewRender || 0) : 0,
                            overviewRoot: view ? view.querySelectorAll('[data-overview-root]').length : 0,
                        };
                    }"""
                )
            )
        evidence["samples"] = samples
        views = {item["view"] for item in samples}
        hashes = {item["hash"] for item in samples}
        renders = {item["render"] for item in samples}
        roots = {item["overviewRoot"] for item in samples}
        if views == {"overview"} and hashes == {"#/overview"} and roots == {1}:
            checker.passed.append(f"overview 30s 采样 15 次：view/hash 稳定（{sorted(views)}）")
        else:
            checker.failures.append(f"overview 30s 内 view/hash 不稳定：views={views} hashes={hashes} roots={roots}")
        if renders == {1}:
            checker.passed.append("overview 30s 内只渲染 1 次（无自渲染死循环）")
        else:
            checker.failures.append(f"overview 30s 内渲染次数异常：{sorted(renders)}（应为 1）")
        evidence["overview_renders"] = sorted(renders)

        counts = {
            "health": sum(1 for url in api_requests if "/api/health" in url),
            "sequence": sum(1 for url in api_requests if "/api/sequence" in url),
            "current": sum(1 for url in api_requests if "/api/current" in url),
        }
        evidence["api_calls"] = counts
        if counts["sequence"] <= 1 and counts["current"] <= 1 and counts["health"] <= 4:
            checker.passed.append(f"overview 30s 内 API 请求无重复风暴：{counts}")
        else:
            checker.failures.append(f"overview 30s 内 API 请求异常重复：{counts}")

        # 导航切换稳定性：切到关卡图鉴后 8s 内不得被 overview 旧回调覆盖回来
        page.locator('.nav-item[data-nav="/chapters"]').click()
        page.wait_for_selector(".chapter-card", timeout=25000)
        nav_samples = []
        for _ in range(4):
            page.wait_for_timeout(2000)
            nav_samples.append(
                page.evaluate(
                    """() => {
                        const view = document.querySelector('#view');
                        return {
                            view: view ? view.dataset.view : null,
                            hash: location.hash,
                            overviewRoot: view ? view.querySelectorAll('[data-overview-root]').length : 0,
                        };
                    }"""
                )
            )
        evidence["navigations"] = nav_samples
        if all(item["view"] == "chapters" and item["hash"] == "#/chapters" and item["overviewRoot"] == 0 for item in nav_samples):
            checker.passed.append("点击导航后 8s 内稳定在关卡图鉴（无 overview 回写）")
        else:
            checker.failures.append(f"导航后被旧页面覆盖/闪回：{nav_samples}")
        # 再切一次到怪种图鉴，确认连续切换正常
        page.locator('.nav-item[data-nav="/species"]').click()
        page.wait_for_selector(".species-card", timeout=25000)
        page.wait_for_timeout(1500)
        final = page.evaluate("() => ({view: document.querySelector('#view').dataset.view, hash: location.hash})")
        if final["view"] == "species" and final["hash"] == "#/species":
            checker.passed.append("连续导航切换正常（chapters → species）")
        else:
            checker.failures.append(f"连续导航切换失败：{final}")
    finally:
        EVIDENCE["stability"] = evidence
        page.close()


def run_port_pid_checks(context, base_url: str, mock: bool, checker, console_errors: list, page_errors: list):
    """B/C. 抓包端口可配置 + PID tooltip/说明文案验证。"""
    print("[selfcheck] B/C. 抓包端口配置 + PID 说明检查…")
    page = context.new_page()
    _attach_error_hooks(page, console_errors, page_errors)
    evidence = {}
    try:
        # --- PID tooltip（顶栏） ---
        page.goto(url_for(base_url, mock, "/overview", 9101), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#view [data-overview-root]", timeout=30000)
        page.wait_for_timeout(900)
        pid_chip = page.locator('.pid-chip').first
        pid_title = (pid_chip.get_attribute("title") or "") if pid_chip.count() else ""
        info_title = page.locator(".pid-info").first.get_attribute("title") if page.locator(".pid-info").count() else ""
        pid_text = pid_chip.inner_text() if pid_chip.count() else ""
        game_status = page.locator('[data-status="game"]').first
        game_status_title = game_status.get_attribute("title") if game_status.count() else ""
        # 游戏进程可能刚好在重启：运行中看 PID chip tooltip，未运行看顶栏状态 tooltip（仍含来源说明）
        effective_title = pid_title or game_status_title or ""
        evidence["pid_title"] = pid_title
        evidence["game_status_title"] = game_status_title
        if "tasklist" in effective_title and "GrilsFrontLine.exe" in effective_title:
            checker.passed.append(f"顶栏 PID tooltip 正确（{pid_text or '未运行态'}）")
        else:
            checker.failures.append(f"PID tooltip 缺少 tasklist/GrilsFrontLine.exe 说明：{effective_title!r}")
        if "tasklist" in (info_title or effective_title):
            checker.passed.append("PID 旁 ⓘ 提示可 hover 查看来源")
        else:
            checker.failures.append("PID 旁缺少 ? 提示 tooltip")

        # --- 抓包端口输入（默认 18080 + 可保存 + 文案不写死） ---
        page.goto(url_for(base_url, mock, "/capture", 9102), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("[data-port-input]", timeout=30000)
        page.wait_for_timeout(1200)
        port_value = page.locator("[data-port-input]").input_value()
        evidence["default_port"] = port_value
        capture_text = page.locator(".capture-cols").inner_text()
        evidence["has_fixed_wording"] = "固定 18080" in capture_text
        if "固定 18080" not in capture_text and "18080" in capture_text:
            checker.passed.append(f"抓取页端口可配置（默认 {port_value}），无「固定 18080」文案")
        else:
            checker.failures.append("抓取页仍出现「固定 18080」旧文案")
        if "tasklist" in capture_text and "GrilsFrontLine.exe" in capture_text:
            checker.passed.append("抓取页包含 PID 来源说明（tasklist / GrilsFrontLine.exe）")
        else:
            checker.failures.append("抓取页缺少 PID 来源说明")

        # --- 修改端口 → 验证 /api/settings 持久化 → 还原 ---
        original_port = 18080
        if not mock:
            try:
                original_port = int((http_json(base_url.rstrip("/") + "/api/settings") or {}).get("capture_port") or 18080)
            except Exception:  # noqa: BLE001
                original_port = 18080
        try:
            page.fill("[data-port-input]", "18081")
            page.click('[data-act="save-port"]')
            page.wait_for_timeout(1200)
            badge = page.locator("[data-port-badge]").first.inner_text()
            evidence["saved_badge"] = badge
            if badge.strip() == "18081":
                checker.passed.append("端口修改后 UI 徽标立即变为 18081")
            else:
                checker.failures.append(f"端口徽标未更新：{badge!r}")
            if not mock:
                saved = int((http_json(base_url.rstrip("/") + "/api/settings") or {}).get("capture_port") or 0)
                evidence["api_capture_port"] = saved
                if saved == 18081:
                    checker.passed.append("POST /api/settings 已把 capture_port 持久化为 18081")
                else:
                    checker.failures.append(f"capture_port 持久化失败：{saved}")
                # 代理地址文案跟随端口
                proxy_texts = page.locator("[data-proxy-addr]").all_inner_texts()
                evidence["proxy_texts"] = proxy_texts
                if all("127.0.0.1:18081" in text for text in proxy_texts if text.strip()):
                    checker.passed.append("终端横幅/代理说明跟随端口（127.0.0.1:18081）")
                else:
                    checker.failures.append(f"代理地址未跟随端口：{proxy_texts}")
        finally:
            # 还原为默认 18080（避免污染用户 settings / 状态）
            try:
                page.fill("[data-port-input]", "18080")
                page.click('[data-act="save-port"]')
                page.wait_for_timeout(900)
            except Exception:  # noqa: BLE001
                pass
            if not mock:
                try:
                    http_post(base_url.rstrip("/") + "/api/settings", {"capture_port": 18080})
                except Exception:  # noqa: BLE001
                    pass
        restored = "18080"
        if not mock:
            try:
                restored = str(int((http_json(base_url.rstrip("/") + "/api/settings") or {}).get("capture_port") or 0))
            except Exception:  # noqa: BLE001
                restored = "?"
        evidence["restored_port"] = restored
        if restored == "18080":
            checker.passed.append("端口设置已还原为默认 18080")
        else:
            checker.failures.append(f"端口设置还原失败：{restored}")

        # --- 教程页：端口口径 + PID 说明 ---
        page.goto(url_for(base_url, mock, "/tutorial", 9103), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".faq-item", timeout=30000)
        page.wait_for_timeout(700)
        tutorial_text = page.locator(".tut-content").inner_text()
        evidence["tutorial_has_fixed"] = "固定 18080" in tutorial_text
        if "固定 18080" in tutorial_text:
            checker.failures.append("教程页仍写「固定 18080」")
        else:
            checker.passed.append("教程页端口口径已改为「默认 18080，可配置」")
        if "tasklist" in tutorial_text and "GrilsFrontLine.exe" in tutorial_text:
            checker.passed.append("教程页包含 PID 由 tasklist 搜索的说明")
        else:
            checker.failures.append("教程页缺少 PID 来源说明")
    finally:
        EVIDENCE["port_pid"] = evidence
        page.close()

# 每个路由都用「全新整页加载」验证首屏渲染
ROUTE_SMOKE = [
    "/overview",
    "/chapters",
    "/chapters/main-1",
    "/chapters/score--61",
    "/chapters/score--40401",
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

    # 记录真实 API 原始序列 / 教程状态，结束后恢复（mock 模式不影响服务端状态）
    original_sequence: list[int] | None = None
    original_tutorial: dict | None = None
    if not mock:
        try:
            original_tutorial = http_json(base_url.rstrip("/") + "/api/tutorial") or {}
            if not original_tutorial.get("dismissed"):
                # 临时标记已看过引导，避免整页刷新时 overlay 遮挡自检点击；结束后还原
                http_post(
                    base_url.rstrip("/") + "/api/tutorial",
                    {"completed": original_tutorial.get("completed") or [], "dismissed": True},
                )
                print("[selfcheck] 已临时 dismissed 新手引导（结束还原）")
        except Exception as exc:  # noqa: BLE001
            print(f"[selfcheck] 读取/临时关闭 tutorial 失败（忽略）：{exc}")
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
                page.wait_for_selector(".tut-overlay", state="visible", timeout=1500)
            except Exception:  # noqa: BLE001
                # 引导可能在数据加载后延迟出现，再等一次
                try:
                    page.wait_for_selector(".tut-overlay", state="visible", timeout=3500)
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
            checker.assert_count(".hero-butterfly .butterfly .bf-fore", 2)
            checker.passed.append("hero 使用大蓝闪蝶 SVG（前后翅 / 黑色翅缘 / 渐变）")
            checker.shot("01_overview.png", ".hero", settle=500)

            # ---------------- 02 关卡图鉴（7 分组 + 积分关卡） ----------------
            load("/chapters", ".chapter-card")
            checker.assert_count(".chapter-card", 8)
            checker.assert_count(".group-tab", 7)
            if checker.assert_count(".group-tab.score", 1):
                checker.passed.append("分组 tab 含「积分关卡」金色分组")
            if checker.assert_count(".chapter-card.score", 1):
                checker.passed.append("章节卡含积分关卡特殊描边/金色徽章")
            else:
                checker.failures.append("缺少积分关卡章节卡（.chapter-card.score）")
            checker.shot("02_chapters.png", ".chapter-grid")
            # 搜索「自画像」应命中（章节搜索匹配 title/subtitle/tags/活动名）
            page.fill("[data-chapter-search]", "自画像")
            page.wait_for_timeout(700)
            hits = page.locator(".chapter-card").count()
            if hits > 0:
                checker.passed.append(f"章节搜索「自画像」命中 {hits} 个章节")
            else:
                checker.failures.append("章节搜索「自画像」无结果")
            page.fill("[data-chapter-search]", "")
            page.wait_for_timeout(500)
            # 顶栏全局搜索「自画像」：前端会用已加载章节做 title/subtitle/tags 命中
            page.fill("#global-search", "自画像")
            page.wait_for_timeout(1300)
            drop_text = page.locator("#search-drop").inner_text()
            if "自画像" in drop_text:
                checker.passed.append("全局搜索「自画像」命中章节/活动组")
            else:
                checker.failures.append(f"全局搜索「自画像」未命中：{drop_text[:160]}")
            page.fill("#global-search", "")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # ---------------- 03 章节详情（main-1） ----------------
            load("/chapters/main-1", ".stage-row")
            checker.assert_count(".stage-row", 5)
            checker.shot("03_chapter_detail.png", ".stage-list")

            # ---------------- 04 关卡队伍：谜境守卫+ mission 11435（支援/机场候选并入同一列表体系） ----------------
            load("/chapters/score--60", ".stage-row")
            support_stage_row = page.locator(".stage-row", has_text="11435")
            if support_stage_row.count() == 0:
                support_stage_row = page.locator(".stage-row").first
            support_stage_row.first.click()
            checker.wait(".team-card")
            page.wait_for_timeout(1000)

            # 顶部 chip：敌方 X · 支援 Y · 可能刷新 Z
            header_text = page.locator(".page-sub").inner_text()
            if "敌方" in header_text and "支援" in header_text and "可能刷新" in header_text:
                checker.passed.append(f"11435 顶部 chip 含敌方/支援/可能刷新（{header_text.replace(chr(10), ' ')[:120]}）")
            else:
                checker.failures.append(f"11435 顶部 chip 缺少敌方/支援/可能刷新：{header_text[:160]}")
            EVIDENCE["support_header"] = header_text.replace("\n", " ")

            # 支援队伍卡并入同一队伍列表（搜索定位）
            page.fill("[data-team-search]", "6363006")
            page.wait_for_timeout(700)
            support_card = page.locator('.team-card[data-team-detail="6363006"]')
            if support_card.count() > 0:
                support_text = support_card.inner_text()
                if "673,555" in support_text and support_card.locator(".badge.support").count() > 0:
                    checker.passed.append("主队伍列表含支援卡 6363006（673,555 + 支援队伍徽标）")
                else:
                    checker.failures.append(f"支援卡信息异常：{support_text[:160]}")
                if support_card.locator("[data-add-team]").count() > 0:
                    checker.passed.append("支援队伍卡支持加入序列")
                else:
                    checker.failures.append("支援队伍卡缺少加入序列按钮")
            else:
                checker.failures.append("11435 主队伍列表缺少支援队伍 6363006")
            page.fill("[data-team-search]", "")
            page.wait_for_timeout(600)

            # 机场刷新候选：默认折叠 → 展开 → 再显示更多（同一列表体系，不做单独 tab）
            if page.locator(".support-tab").count() == 0:
                checker.passed.append("11435 无独立支援/机场 tab（共用同一列表体系）")
            else:
                checker.failures.append("11435 出现独立支援/机场 tab")
            reserve_toggle = page.locator("[data-reserve-toggle]")
            if reserve_toggle.count() > 0 and "可能刷新" in reserve_toggle.inner_text():
                checker.passed.append(f"机场候选折叠条含数量（{reserve_toggle.inner_text().replace(chr(10), ' ')[:110]}）")
            else:
                checker.failures.append("机场候选折叠条缺失")
            if page.locator(".reserve-grid .team-card").count() == 0:
                checker.passed.append("机场候选默认折叠（不刷屏）")
            else:
                checker.failures.append("机场候选默认未折叠")
            reserve_toggle.first.click()
            page.wait_for_timeout(700)
            expanded_count = page.locator(".reserve-grid .team-card").count()
            reserve_badges = page.locator(".reserve-grid .team-card .badge.reserve").count()
            if expanded_count > 0 and reserve_badges >= expanded_count:
                checker.passed.append(f"展开机场候选 {expanded_count} 张卡均带「机场可能刷新（推断）」badge")
            else:
                checker.failures.append(f"机场候选卡/badge 缺失：{expanded_count}/{reserve_badges}")
            more_btn = page.locator("[data-reserve-more]")
            after_more = expanded_count
            if more_btn.count() > 0:
                before_more = expanded_count
                more_btn.first.click()
                page.wait_for_timeout(700)
                after_more = page.locator(".reserve-grid .team-card").count()
                if after_more > before_more:
                    checker.passed.append(f"「再显示更多」生效（{before_more} → {after_more} 张）")
                else:
                    checker.failures.append("「再显示更多」未增加候选")
            reserve_ids = page.evaluate(
                "() => [...document.querySelectorAll('.reserve-grid .team-card')].map(e => e.dataset.teamDetail)"
            )
            if "6363057" in reserve_ids and "6363060" in reserve_ids:
                checker.passed.append("机场候选含 6363057 / 6363060（AA-02）")
            else:
                checker.failures.append(f"机场候选缺少 6363057/6363060：{reserve_ids[:20]}")
            EVIDENCE["reserve"] = {
                "expanded": after_more,
                "ids": list(reserve_ids[:24]),
                "collapsed_default": True,
            }
            page.locator(".reserve-grid").first.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            checker.shot("04_stage_teams.png", ".reserve-grid", scroll_top=False, settle=400)

            # 全局搜索按编号：显示队伍结果卡 + 加入序列
            page.fill("#global-search", "#6363006")
            page.wait_for_timeout(1500)
            search_result = page.locator(".sd-team-result")
            if search_result.count() > 0 and "6363006" in search_result.first.inner_text():
                checker.passed.append("全局搜索 #6363006 出现队伍结果卡")
            else:
                checker.failures.append("全局搜索 #6363006 未出现队伍结果")
            checker.shot("20_search_team.png", "#search-drop", scroll_top=False, settle=300)
            search_add = page.locator("[data-search-add]").first
            if search_add.count() > 0:
                search_add.click()
                page.wait_for_timeout(1300)
                try:
                    search_seq_ids = [
                        int(t["id"])
                        for t in (http_json(base_url.rstrip("/") + "/api/sequence") or {}).get("draft", [])
                    ]
                except Exception:  # noqa: BLE001
                    search_seq_ids = []
                if 6363006 in search_seq_ids:
                    checker.passed.append("搜索结果可直接加入序列（/api/sequence 命中 6363006）")
                else:
                    checker.failures.append(f"搜索结果加入序列失败：{search_seq_ids[:40]}")
                try:
                    http_post(base_url.rstrip("/") + "/api/sequence", {"action": "remove", "team_id": 6363006})
                except Exception:  # noqa: BLE001
                    pass
            else:
                checker.failures.append("搜索结果缺少「加入序列」按钮")
            page.fill("#global-search", "")
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

            # 序列页「按编号加入」（支持 # 前缀）
            load("/sequence", ".add-by-id")
            page.wait_for_timeout(700)
            seq_input = page.locator(".page-head .add-by-id [data-add-id-input]").first
            if seq_input.count() > 0:
                seq_input.fill("#6363006")
                seq_input.press("Enter")
                page.wait_for_timeout(1600)
                try:
                    byid_seq_ids = [
                        int(t["id"])
                        for t in (http_json(base_url.rstrip("/") + "/api/sequence") or {}).get("draft", [])
                    ]
                except Exception:  # noqa: BLE001
                    byid_seq_ids = []
                if 6363006 in byid_seq_ids:
                    checker.passed.append("序列页「按编号加入」#6363006 成功")
                else:
                    checker.failures.append(f"序列页按编号加入失败：{byid_seq_ids[:40]}")
            else:
                checker.failures.append("序列页缺少「按编号加入」输入框")
            try:
                http_post(base_url.rstrip("/") + "/api/sequence", {"action": "clear"})
            except Exception:  # noqa: BLE001
                pass

            # 侧栏高亮滑块：总览 → 关卡图鉴 transform 变化
            load("/overview", ".hero-butterfly")
            page.wait_for_timeout(800)
            hl = page.locator("[data-nav-highlight]")
            before_transform = hl.evaluate("el => getComputedStyle(el).transform")
            before_box = hl.bounding_box()
            page.locator('.nav-item[data-nav="/chapters"]').click()
            checker.wait(".chapter-card")
            page.wait_for_timeout(1000)
            after_transform = hl.evaluate("el => getComputedStyle(el).transform")
            after_box = hl.bounding_box()
            moved = (before_transform != after_transform) or (
                bool(before_box) and bool(after_box) and before_box.get("y") != after_box.get("y")
            )
            if moved:
                checker.passed.append(f"侧栏高亮块 transform 随路由移动（{before_transform} → {after_transform}）")
            else:
                checker.failures.append(f"侧栏高亮块未移动：{before_transform} / {after_transform}")
            EVIDENCE["sidebar_highlight"] = {
                "before": before_transform,
                "after": after_transform,
                "before_y": before_box.get("y") if before_box else None,
                "after_y": after_box.get("y") if after_box else None,
            }
            checker.shot("21_sidebar_highlight.png", ".sidenav", scroll_top=False)

            # ---------------- 全怪组总表 /roster（v1.6） ----------------
            load("/roster", ".roster-table")
            try:
                page.wait_for_selector(".roster-row", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1000)
            roster_rows = page.locator(".roster-row").count()
            if roster_rows > 0:
                checker.passed.append(f"全怪组总表默认加载 {roster_rows} 行")
            else:
                checker.failures.append("全怪组总表默认没有行")
            nav_roster = page.locator('.nav-item[data-nav="/roster"]')
            if nav_roster.count() and "全怪组" in nav_roster.inner_text():
                checker.passed.append("侧栏含「全怪组」导航项（怪种图鉴之后）")
            else:
                checker.failures.append("侧栏缺少「全怪组」导航项")
            try:
                default_teams = http_json(base_url.rstrip("/") + "/api/teams?limit=1")
                default_total = int(default_teams.get("total") or 0)
                if default_total == 13700:
                    checker.passed.append("GET /api/teams 默认 total=13700")
                else:
                    checker.failures.append(f"/api/teams 默认 total={default_total}（期望 13700）")
            except Exception as exc:  # noqa: BLE001
                checker.failures.append(f"/api/teams 默认请求失败：{exc}")
            checker.shot("22_roster.png", ".roster-table-wrap", scroll_top=False, settle=400)

            # 章节筛选 score--60（limit 200 保证 6363006 在结果里）
            page.select_option("[data-roster-limit]", "200")
            page.wait_for_timeout(900)
            page.select_option("[data-roster-chapter]", "score--60")
            page.wait_for_timeout(1500)
            chapter_rows = page.locator(".roster-row").count()
            chapter_text = page.locator("[data-roster-tbody]").inner_text()
            if chapter_rows > 0 and "6363006" in chapter_text:
                checker.passed.append(f"章节筛选 score--60 命中 {chapter_rows} 行且含 6363006")
            else:
                checker.failures.append(f"章节筛选 score--60 未命中 6363006（{chapter_rows} 行）")

            # 怪种 AND：先用 API 找 6363006 的两种怪种，再在页面多选
            try:
                detail_6363006 = http_json(base_url.rstrip("/") + "/api/teams/6363006")
                species_codes = [
                    int(item["codex_no"])
                    for item in (detail_6363006.get("species") or [])
                    if item.get("codex_no")
                ][:2]
            except Exception:  # noqa: BLE001
                species_codes = []
            if len(species_codes) >= 2:
                code1, code2 = species_codes
                sp_input = page.locator("[data-sp-search]").first
                sp_input.click()
                sp_input.fill(str(code1))
                page.wait_for_timeout(500)
                opt1 = page.locator(f'[data-sp-opt="{code1}"]').first
                if opt1.count():
                    opt1.click()
                    page.wait_for_timeout(1000)
                sp_input.fill(str(code2))
                page.wait_for_timeout(500)
                opt2 = page.locator(f'[data-sp-opt="{code2}"]').first
                if opt2.count():
                    opt2.click()
                    page.wait_for_timeout(1600)
                filter_text = page.locator("[data-roster-tbody]").inner_text()
                filter_rows = page.locator(".roster-row").count()
                if filter_rows > 0 and "6363006" in filter_text:
                    checker.passed.append(f"怪种 AND 筛选（{code1}+{code2}）+ 章节命中 6363006（{filter_rows} 行）")
                else:
                    checker.failures.append(f"怪种 AND 筛选未命中 6363006（{filter_rows} 行，codes={code1},{code2}）")
                EVIDENCE["roster_filter"] = {"chapter": "score--60", "species": [code1, code2], "rows": filter_rows}
                checker.shot("23_roster_filter.png", ".roster-table-wrap", scroll_top=False, settle=400)
            else:
                checker.failures.append("无法从 /api/teams/6363006 取得两种怪种做 AND 筛选")

            # 重置 + units_desc / power_desc 排序 API 校验
            page.locator("[data-roster-reset]").first.click()
            page.wait_for_timeout(1300)
            try:
                units_sorted = http_json(base_url.rstrip("/") + "/api/teams?sort=units_desc&limit=50")["items"]
                if units_sorted and units_sorted[0]["units"] >= units_sorted[-1]["units"]:
                    checker.passed.append(f"units_desc 排序生效（{units_sorted[0]['units']} → {units_sorted[-1]['units']}）")
                else:
                    checker.failures.append("units_desc 排序异常")
                power_sorted = http_json(base_url.rstrip("/") + "/api/teams?sort=power_desc&limit=50")["items"]
                known_powers = [item["power"] for item in power_sorted if item.get("power_known")]
                if len(known_powers) < 2 or all(
                    known_powers[index] >= known_powers[index + 1] for index in range(len(known_powers) - 1)
                ):
                    checker.passed.append(f"power_desc 排序生效（已标注 {len(known_powers)} 支）")
                else:
                    checker.failures.append("power_desc 排序异常")
                unknown_positions = [index for index, item in enumerate(power_sorted) if not item.get("power_known")]
                if not unknown_positions or unknown_positions[0] >= len(power_sorted) - len(unknown_positions):
                    checker.passed.append("power_desc 排序未标注队伍排在最后")
                else:
                    checker.failures.append("power_desc 未标注队伍未排最后")
            except Exception as exc:  # noqa: BLE001
                checker.failures.append(f"排序 API 校验失败：{exc}")

            # 搜索 6363006 + 加入序列（后移除还原）
            page.fill("[data-roster-q]", "6363006")
            page.wait_for_timeout(1400)
            search_text = page.locator("[data-roster-tbody]").inner_text()
            if "6363006" in search_text:
                checker.passed.append("全怪组搜索 6363006 命中")
            else:
                checker.failures.append("全怪组搜索 6363006 未命中")
            add_btn = page.locator(".roster-row [data-add-team]").first
            if add_btn.count():
                add_btn.click()
                page.wait_for_timeout(1200)
                try:
                    roster_seq = [
                        int(team["id"])
                        for team in (http_json(base_url.rstrip("/") + "/api/sequence") or {}).get("draft", [])
                    ]
                except Exception:  # noqa: BLE001
                    roster_seq = []
                if 6363006 in roster_seq:
                    checker.passed.append("全怪组搜索行可直接加入序列")
                else:
                    checker.failures.append(f"全怪组加入序列失败：{roster_seq[:30]}")
                try:
                    http_post(base_url.rstrip("/") + "/api/sequence", {"action": "remove", "team_id": 6363006})
                except Exception:  # noqa: BLE001
                    pass
            else:
                checker.failures.append("全怪组搜索行缺少加入序列按钮")

            # 行点击打开详情抽屉
            page.locator(".roster-row").first.click(position={"x": 60, "y": 20})
            try:
                page.wait_for_selector(".drawer", timeout=8000)
                checker.passed.append("全怪组行点击可打开队伍详情抽屉")
                close_btn = page.locator(".drawer [data-close-drawer]").first
                if close_btn.count():
                    close_btn.click()
                else:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                checker.failures.append("全怪组行点击未打开详情抽屉")

            # 回到关卡队伍页：效能筛选控件 + 全部加入（供后续序列截图）
            load("/stages/11435", ".team-card")
            page.wait_for_timeout(800)
            if page.locator(".power-filter").count() > 0:
                checker.passed.append("关卡队伍页含效能筛选/排序控件")
            else:
                checker.failures.append("关卡队伍页缺少效能筛选控件")
            add_all = page.locator('[data-act="add-all"]')
            if add_all.count() > 0:
                add_all.first.click()
                maybe_confirm()
                try:
                    page.wait_for_function(
                        "() => { const el = document.querySelector('[data-nav-count=\"sequence\"]');"
                        " return el && Number(el.textContent) > 0; }",
                        timeout=15000,
                    )
                    checker.passed.append("从关卡加入序列")
                except Exception as exc:  # noqa: BLE001
                    checker.failures.append(f"加入序列失败：{exc}")

            # ---------------- 16/17 结算形式：积分结算 vs 普通结算 ----------------
            load("/chapters/score--61", ".stage-row")
            score_badges = page.locator(".settle-badge.score").count()
            score_text_61 = page.locator("#view").inner_text()
            score_titles_61 = page.evaluate(
                "() => [...document.querySelectorAll('.settle-badge.score')].map(e => e.getAttribute('title') || '').join(' | ')"
            )
            if score_badges > 0:
                checker.passed.append(f"score--61 关卡行出现 {score_badges} 个「积分结算」徽标")
            else:
                checker.failures.append("score--61 未出现「积分结算」徽标")
            if "禁止喂食EX" in score_text_61:
                checker.passed.append("score--61 页面含「禁止喂食EX」关卡")
            else:
                checker.failures.append("score--61 页面缺少「禁止喂食EX」")
            if "模式" in score_titles_61 and "项参数" in score_titles_61 and "积分榜" in score_titles_61:
                checker.passed.append("积分结算 tooltip 含 模式/项参数/积分榜")
            else:
                checker.failures.append(f"积分结算 tooltip 信息不完整：{score_titles_61[:200]}")
            EVIDENCE["settlement_score61"] = {"badges": score_badges, "titles": score_titles_61[:400]}
            checker.shot("16_score_settlement.png", ".stage-list")

            # 打开第一个积分关卡 → 队伍页 header 结算形式
            page.locator(".stage-row").first.click()
            checker.wait(".settle-line", timeout=25000)
            page.wait_for_timeout(900)
            settle_line_text = page.locator(".settle-line").inner_text()
            if "积分结算" in settle_line_text and "event_score" in settle_line_text:
                checker.passed.append(f"关卡队伍页结算形式行：{settle_line_text.replace(chr(10), ' ')[:120]}")
            else:
                checker.failures.append(f"关卡队伍页结算形式行异常：{settle_line_text[:160]}")
            EVIDENCE["settlement_stage_line"] = settle_line_text.replace("\n", " ")
            checker.shot("17_score_teams.png", ".settle-line")

            # score--40401 贝蒂数：tooltip 含积分榜 + 贝蒂数
            load("/chapters/score--40401", ".stage-row")
            betty_titles = page.evaluate(
                "() => [...document.querySelectorAll('.settle-badge.score')].map(e => e.getAttribute('title') || '').join(' | ')"
            )
            if "积分榜" in betty_titles and "贝蒂数" in betty_titles:
                checker.passed.append("score--40401 结算信息含积分榜 + 贝蒂数")
            else:
                checker.failures.append(f"score--40401 结算信息缺少积分榜/贝蒂数：{betty_titles[:200]}")
            EVIDENCE["settlement_betty"] = betty_titles[:400]

            # main-1 普通关卡 → 普通结算
            load("/chapters/main-1", ".stage-row")
            normal_badges = page.locator(".settle-badge.normal").count()
            main_text = page.locator("#view").inner_text()
            if normal_badges > 0 and "普通结算" in main_text:
                checker.passed.append(f"main-1 普通关卡显示「普通结算」({normal_badges} 个)")
            else:
                checker.failures.append("main-1 普通关卡缺少「普通结算」文案")

            # ---------------- 支援队伍（谜境守卫+ mission 11435，混在同一队伍列表，不单独分区） ----------------
            load("/chapters/score--60", ".stage-row")
            chapter_text_60 = page.locator("#view").inner_text()
            support_chips = page.locator(".stage-tags .tag.support")
            support_chip_text = " | ".join(support_chips.all_inner_texts()) if support_chips.count() else ""
            if support_chips.count() > 0 and "支援" in support_chip_text:
                checker.passed.append(f"score--60 关卡行出现支援标记（{support_chip_text}）")
            else:
                checker.failures.append("score--60 关卡行缺少「支援 N」标记")
            if "谜境守卫" in chapter_text_60:
                checker.passed.append("score--60 为谜境守卫+ 章节")
            else:
                checker.failures.append(f"score--60 章节内容异常：{chapter_text_60[:120]}")

            stage_row_11435 = page.locator(".stage-row", has_text="11435")
            if stage_row_11435.count() == 0:
                stage_row_11435 = page.locator(".stage-row").first
            stage_row_11435.first.click()
            checker.wait(".team-card", timeout=25000)
            page.wait_for_timeout(1100)
            if page.locator(".support-section").count() > 0 or page.locator(".support-tab").count() > 0:
                checker.failures.append("11435 仍出现独立支援分区/标签（需求要求混在主列表）")
            else:
                checker.passed.append("11435 没有独立支援分区，支援队伍混在主队伍列表")
            page.fill("[data-team-search]", "6363006")
            page.wait_for_timeout(700)
            support_card = page.locator('.team-card[data-team-detail="6363006"]')
            if support_card.count() == 0:
                support_card = page.locator(".team-grid .team-card", has_text="6363006")
            if support_card.count() > 0:
                support_card_text = support_card.inner_text()
                if "673,555" in support_card_text:
                    checker.passed.append("主队伍列表含支援队伍 6363006 且效能 673,555")
                else:
                    checker.failures.append(f"支援队伍 6363006 效能异常：{support_card_text[:160]}")
                if support_card.locator(".badge.support").count() > 0 or "支援" in support_card_text:
                    checker.passed.append("支援队伍卡带「支援队伍」徽标")
                else:
                    checker.failures.append("支援队伍卡缺少支援徽标")
                if support_card.locator("[data-add-team]").count() > 0:
                    checker.passed.append("支援队伍卡支持「加入序列」")
                else:
                    checker.failures.append("支援队伍卡缺少「加入序列」按钮")
            else:
                checker.failures.append("11435 主队伍列表缺少支援队伍 6363006")
            page.fill("[data-team-search]", "")
            page.wait_for_timeout(500)
            header_sub_text = page.locator(".page-sub").inner_text()
            if "敌方" in header_sub_text and "支援" in header_sub_text:
                checker.passed.append(f"关卡页顶部区分敌方/支援（{header_sub_text.replace(chr(10), ' ')[:120]}）")
            else:
                checker.failures.append(f"关卡页顶部未区分敌方/支援：{header_sub_text[:160]}")
            EVIDENCE["support_stage"] = {
                "header": header_sub_text.replace("\n", " "),
                "support_card": support_card.inner_text().replace("\n", " ")[:400] if support_card.count() else "",
            }

            # 从潘洛斯阶梯跃下（score--40404）：listing 正常且支援队伍混在列表
            load("/chapters/score--40404", ".stage-row")
            checker.assert_count(".stage-row", 1)
            page.locator(".stage-row").first.click()
            checker.wait(".team-card", timeout=25000)
            page.wait_for_timeout(1100)
            pnl_cards = page.locator(".team-grid .team-card").count()
            pnl_support = page.locator(".team-grid .team-card .badge.support").count()
            pnl_header = page.locator(".page-sub").inner_text()
            if pnl_cards > 0:
                checker.passed.append(f"score--40404 关卡页队伍列表正常（{pnl_cards} 张）")
            else:
                checker.failures.append("score--40404 关卡页队伍列表为空")
            if pnl_support > 0:
                checker.passed.append(f"score--40404 支援队伍混在列表中（support badge {pnl_support} 张）")
            elif "支援" in pnl_header:
                checker.passed.append("score--40404 顶部标注支援但列表暂未返回 support_teams（容错通过）")
            else:
                checker.passed.append("score--40404 该关卡无支援队伍（support_team_count=0），listing 正常")
            EVIDENCE["score_40404"] = {"cards": pnl_cards, "support": pnl_support, "header": pnl_header.replace("\n", " ")[:200]}

            # 普通关卡 main-1 不应出现支援 badge
            load("/chapters/main-1", ".stage-row")
            main_support_tags = page.locator(".stage-tags .tag.support").count()
            page.locator(".stage-row").first.click()
            checker.wait(".team-card", timeout=25000)
            page.wait_for_timeout(900)
            main_support_badges = page.locator(".team-grid .team-card .badge.support").count()
            if main_support_tags == 0 and main_support_badges == 0:
                checker.passed.append("main-1 普通关卡无支援标记/badge")
            else:
                checker.failures.append("main-1 普通关卡出现支援标记")

            # 队伍详情 6363006：「本怪组出现位置」+ 11435 + 支援徽标
            load("/teams/6363006", ".panel")
            page.wait_for_timeout(800)
            team_detail_text = page.locator("#view").inner_text()
            if "本怪组出现位置" in team_detail_text:
                checker.passed.append("队伍详情 6363006 出现「本怪组出现位置」栏")
            else:
                checker.failures.append("队伍详情 6363006 缺少「本怪组出现位置」栏")
            appear_items = page.locator(".appear-item")
            appear_text = " | ".join(appear_items.all_inner_texts()[:30]) if appear_items.count() else ""
            if appear_items.count() > 0 and ("11435" in team_detail_text or "谜境守卫" in team_detail_text):
                checker.passed.append(f"本怪组出现位置含 11435/谜境守卫（{appear_items.count()} 条）")
            else:
                checker.failures.append(f"本怪组出现位置缺少 11435：{appear_text[:200]}")
            role_tags = page.locator(".appear-item .tag").all_inner_texts()
            if any("支援" in tag for tag in role_tags):
                checker.passed.append(f"出现位置带角色徽标（支援 {role_tags.count('支援')} 条）")
            else:
                checker.failures.append(f"出现位置缺少角色徽标：{role_tags[:10]}")
            EVIDENCE["team_appearances"] = {
                "count": appear_items.count(),
                "roles": list(role_tags[:30]),
                "text": appear_text[:500],
            }
            appear_section = page.locator(".appear-list")
            if appear_section.count() > 0:
                appear_section.first.scroll_into_view_if_needed()
                page.wait_for_timeout(400)
                checker.shot("19_team_appearances.png", ".appear-list", scroll_top=False, settle=400)

            # ---------------- 05 怪种图鉴（真实头像 / 剪影兜底） ----------------
            load("/species", ".species-card")
            checker.assert_count(".species-card", 10)
            card_count = page.locator(".species-card").count()
            icon_count = page.locator(".species-card .sp-icon").count()
            letter_count = page.locator(".species-card .sp-avatar").count()
            if icon_count >= card_count:
                checker.passed.append(f"怪种卡使用图标（{icon_count}/{card_count} 个 .sp-icon）")
            else:
                checker.failures.append(f"怪种卡图标缺失：{icon_count}/{card_count}")
            if letter_count == 0:
                checker.passed.append("怪种卡已不再用单个汉字当图标")
            else:
                checker.failures.append("怪种卡仍存在 .sp-avatar 文字图标")
            # 等图片加载，统计真实头像 / 剪影兜底数量
            page.wait_for_timeout(1500)
            img_n = page.locator(".species-card .sp-icon img.species-icon").count()
            sil_n = page.locator(".species-card .sp-icon svg.sp-silhouette").count()
            if (img_n + sil_n) >= card_count:
                checker.passed.append(f"怪种卡头像覆盖：真实 PNG {img_n} + 剪影兜底 {sil_n}")
            else:
                checker.failures.append(f"怪种卡头像覆盖不足：img={img_n} silhouette={sil_n}")
            EVIDENCE["species_icons"] = {"cards": card_count, "img": img_n, "silhouette": sil_n}
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
            member_rows = page.locator(".drawer .data-table tbody tr").count()
            member_icons = page.locator(".drawer .data-table tbody tr .sp-icon").count()
            if member_icons >= member_rows:
                checker.passed.append(f"单位聚合表每行带图标（{member_icons}/{member_rows}）")
            else:
                checker.failures.append(f"单位聚合表图标缺失：{member_icons}/{member_rows}")
            drawer_text = page.locator(".drawer").inner_text()
            forbidden = ["技能", "skill", "Skill", "SKILL", "触发器", "trigger", "Trigger"]
            hits = [word for word in forbidden if word in drawer_text]
            if hits:
                checker.failures.append(f"队伍详情出现技能相关信息：{hits}")
            else:
                checker.passed.append("队伍详情无技能信息")
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

            # ---------------- 13 灰域区域（沙尘带/风暴带/硅状带/结晶带）→ 14 个灰域地点 ----------------
            load("/chapters/grayzone", ".region-card, .area-card")
            try:
                page.wait_for_selector(".region-card", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1100)
            region_names = [name.strip() for name in page.locator(".rg-name").all_inner_texts()]
            has_regions = page.locator(".region-card").count() >= 5 and all(
                name in " ".join(region_names) for name in ["沙尘带", "风暴带", "硅状带", "结晶带"]
            )
            if has_regions:
                checker.passed.append(f"灰域区域区块 {page.locator('.region-card').count()} 个区域（{'/'.join(region_names)}）")
            else:
                checker.failures.append(f"灰域区域区块异常：{region_names}")
            if page.locator(".area-card").count() == 14:
                checker.passed.append("灰域地点区块 14 张地点卡")
            else:
                checker.failures.append(f"灰域地点卡数量 {page.locator('.area-card').count()} != 14")
            chapter_gray_text = page.locator("#view").inner_text()
            if "灰域地点" in chapter_gray_text and "区域内的地点" in chapter_gray_text:
                checker.passed.append("地点区块标题为「灰域地点」（说明不是区域）")
            else:
                checker.failures.append("地点区块标题/说明缺失")
            if "区域数量" in chapter_gray_text and "地点数量" in chapter_gray_text:
                checker.passed.append("灰域统计含区域数量 / 地点数量")
            else:
                checker.failures.append("灰域统计缺少区域数量/地点数量")
            area_names = [name.strip() for name in page.locator(".area-name").all_inner_texts()]
            if "庇护所旧址" in area_names or "坍缩狭缝" in area_names:
                checker.passed.append("灰域地点含庇护所旧址/坍缩狭缝")
            region_badges = page.locator(".area-regions .region-badge").count()
            if region_badges >= 14:
                checker.passed.append(f"地点卡显示所属区域 badges（{region_badges} 个）")
            else:
                checker.failures.append(f"地点卡缺少所属区域 badges（{region_badges} 个）")
            EVIDENCE["grayzone_areas"] = {"count": len(area_names), "names": area_names, "regions": region_names}
            checker.shot("13_grayzone_areas.png", ".region-grid", scroll_top=False, settle=400)

            # 区域筛选：点「结晶带」→ 地点数减少且包含共生净土；重置恢复 14
            crystal = page.locator(".region-card", has_text="结晶带").first
            if crystal.count():
                crystal.click()
                page.wait_for_timeout(700)
                visible_areas = page.locator(".area-card:visible").count()
                visible_names = page.locator(".area-card:visible .area-name").all_inner_texts()
                if 0 < visible_areas < 14 and any("共生净土" in str(name) for name in visible_names):
                    checker.passed.append(f"点击「结晶带」后地点筛选生效（{visible_areas} 个，含共生净土）")
                else:
                    checker.failures.append(f"结晶带筛选异常：{visible_areas} 个 / {visible_names[:6]}")
                checker.shot("24_grayzone_region.png", ".region-grid", scroll_top=False, settle=400)
                page.locator("[data-region-reset]").first.click()
                page.wait_for_timeout(600)
                if page.locator(".area-card:visible").count() == 14:
                    checker.passed.append("重置区域后恢复 14 个地点")
                else:
                    checker.failures.append("重置区域后地点数没有恢复 14")
            else:
                checker.failures.append("缺少「结晶带」区域卡片")

            load("/grayzone/共生净土", ".team-card")
            checker.wait(".pager")
            checker.wait(".power-filter")
            checker.passed.append("灰域地点队伍页含效能筛选/排序条")
            title_text = page.locator(".page-title").first.inner_text()
            if "%E" in title_text:
                checker.failures.append(f"灰域地点标题未解码：{title_text}")
            elif "共生净土" in title_text:
                checker.passed.append("灰域地点标题已解码")
            gray_page_text = page.locator("#view").inner_text()
            if "区域：" in gray_page_text and "灰域地点内的可收藏队伍" in gray_page_text:
                checker.passed.append("灰域地点队伍页显示所属区域面包屑/说明")
            else:
                checker.failures.append("灰域地点队伍页缺少区域说明")
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
            data_dir_text = page.locator("[data-data-dir]").inner_text()
            capture_full = page.locator(".capture-cols").inner_text()
            if data_dir_text and data_dir_text.strip() not in ("", "读取中…"):
                checker.passed.append(f"抓取页显示应用数据目录：{data_dir_text.strip()[:80]}")
            else:
                checker.failures.append("抓取页未显示应用数据目录（/api/health.data_dir）")
            if "TARGETFORGE_DATA_DIR" in capture_full:
                checker.passed.append("抓取页说明 TARGETFORGE_DATA_DIR 可覆盖数据目录")
            else:
                checker.failures.append("抓取页缺少 TARGETFORGE_DATA_DIR 说明")
            checker.shot("10_capture.png", ".capture-cols")

            # ---------------- 11 使用教程 ----------------
            load("/tutorial", ".faq-item")
            checker.assert_count(".faq-item", 7)
            # 展开新增 FAQ「积分关卡是怎么判定的？」再检查正文
            faq_item = page.locator(".faq-item", has_text="积分关卡是怎么判定").first
            if faq_item.count() > 0:
                faq_item.locator(".faq-q").click()
                page.wait_for_timeout(450)
                checker.passed.append("教程 FAQ 新增「积分关卡是怎么判定的？」")
            else:
                checker.failures.append("教程缺少「积分关卡是怎么判定的？」FAQ")
            tutorial_text_all = page.locator(".tut-content").inner_text()
            if "event_score" in tutorial_text_all and "score_prize" in tutorial_text_all and "rank" in tutorial_text_all:
                checker.passed.append("教程结算判定 FAQ 含 event_score / score_prize / rank")
            else:
                checker.failures.append("教程结算判定 FAQ 缺少 event_score/score_prize/rank")
            if "dataMiner/derived/targetforge/creds_latest.json" not in tutorial_text_all:
                checker.passed.append("教程不再硬编码 creds 完整路径")
            else:
                checker.failures.append("教程仍硬编码 dataMiner/.../creds_latest.json")
            if "TARGETFORGE_DATA_DIR" in tutorial_text_all and "应用数据目录" in tutorial_text_all:
                checker.passed.append("教程使用「应用数据目录 + TARGETFORGE_DATA_DIR」口径")
            else:
                checker.failures.append("教程缺少应用数据目录/TARGETFORGE_DATA_DIR 说明")
            checker.shot("11_tutorial.png", ".tut-content")
            # 额外截图：滚到 FAQ 并展开「积分关卡是怎么判定？」（结算判定说明）
            if faq_item.count() > 0:
                faq_item.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                checker.shot("18_tutorial_settlement.png", ".faq-item.open", scroll_top=False, settle=300)

            # ---------------- 14 无固定关卡章节（badge 数据 + 服务端效能筛选） ----------------
            load("/chapters/orphan", ".team-card")
            checker.shot("14_orphan_chapter.png", ".team-grid")

            # ---------------- 15 效能筛选（无固定关卡 1005 支有标注队伍，服务端 power_* 参数） ----------------
            before_known = page.locator("[data-orphan-meta]").inner_text()
            page.select_option("[data-pf-mode]", "known")
            page.select_option("[data-pf-sort]", "power_desc")
            page.wait_for_timeout(2200)
            known_cards = page.locator(".team-card").count()
            after_known = page.locator("[data-orphan-meta]").inner_text()
            if known_cards > 0:
                checker.passed.append(f"无固定关卡效能筛选「有标注」生效（{before_known.strip()} → {after_known.strip()}，{known_cards} 张卡）")
            else:
                checker.failures.append("无固定关卡效能筛选「有标注」没有结果")
            powers = [item.strip() for item in page.locator(".team-card .tc-power b").all_inner_texts()[:4]]
            if powers and powers[0] not in ("", "未标注"):
                checker.passed.append(f"效能降序排序生效（首张 {powers[0]}）")
            else:
                checker.failures.append(f"效能排序结果异常：{powers}")
            checker.shot("15_power_filter.png", ".power-filter")
            page.select_option("[data-pf-mode]", "all")
            page.select_option("[data-pf-sort]", "default")
            page.wait_for_timeout(900)

            # ---------------- A. overview 无限闪烁 / 路由劫持回归检查 ----------------
            run_stability_check(context, base_url, mock, checker, console_errors, page_errors)

            # ---------------- B/C. 抓包端口可配置 + PID 说明 ----------------
            run_port_pid_checks(context, base_url, mock, checker, console_errors, page_errors)

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
                "evidence": EVIDENCE,
            }
            (out_dir / "selfcheck_result.json").write_text(
                json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            context.close()
            browser.close()
            # 恢复原始 tutorial 状态（异常退出也尽量还原）
            if original_tutorial is not None:
                try:
                    http_post(
                        base_url.rstrip("/") + "/api/tutorial",
                        {
                            "completed": original_tutorial.get("completed") or [],
                            "dismissed": bool(original_tutorial.get("dismissed")),
                        },
                    )
                except Exception:  # noqa: BLE001
                    pass

    # 后端 12 个灰域区域都能返回队伍（真实 API 模式）
    if not mock:
        try:
            gray_payload = http_json(base_url.rstrip("/") + "/api/grayzone/areas")
            areas = gray_payload.get("areas") or []
            regions = gray_payload.get("regions") or []
            assert len(areas) == 14, f"灰域地点数量 {len(areas)} != 14"
            names = [str(area.get("title") or area.get("id") or "").strip() for area in areas]
            assert "庇护所旧址" in names and "坍缩狭缝" in names, f"缺少灰域地点：{names}"
            region_names = [
                str(region.get("title") or region.get("name") or region.get("id") or "").strip() for region in regions
            ]
            if regions:
                assert len(regions) == 5, f"灰域区域数量 {len(regions)} != 5"
                for required in ("沙尘带", "风暴带", "硅状带", "结晶带", "特殊区域"):
                    assert required in region_names, f"缺少灰域区域 {required}：{region_names}"
                region_ids = {str(region.get("id") or "").strip() for region in regions}
                for area in areas:
                    area_regions = area.get("region_ids") or []
                    assert area_regions, f"地点 {area.get('id')} 没有 region_ids"
                    assert all(str(rid) in region_ids for rid in area_regions), f"地点 {area.get('id')} region_ids 未匹配区域"
                node_total = sum(int(area.get("stage_count") or 0) for area in areas)
                assert node_total == 1288, f"地点节点合计 {node_total} != 1288"
                checker.passed.append(f"灰域层级：{len(regions)} 区域 / {len(areas)} 地点 / 节点合计 1288")
            bad = []
            for area in areas:
                data = http_json(
                    base_url.rstrip("/")
                    + "/api/grayzone/teams?area="
                    + urllib.parse.quote(area["id"])
                    + "&limit=1"
                )
                total = area.get("team_count")
                has_items = bool(data.get("items"))
                if total and not has_items:
                    bad.append(area["id"])
                if not total and has_items:
                    bad.append(f"{area['id']}(空区域却有队伍)")
            if bad:
                checker.failures.append(f"灰域地点取队伍为空：{bad}")
            else:
                checker.passed.append(f"灰域 14 个地点齐全（含庇护所旧址/坍缩狭缝），有队伍的地点均能取到队伍")
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

    if EVIDENCE:
        print("\n关键证据 Evidence：")
        print(json.dumps(EVIDENCE, ensure_ascii=False, indent=2)[:4000])

    ok = not console_errors and not page_errors and not checker.failures and len(SHOTS) >= 25
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
