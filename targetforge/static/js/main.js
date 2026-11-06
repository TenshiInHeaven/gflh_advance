/* main.js —— 应用启动 / 路由 / 顶栏 / 全局交互 */
import { api, IS_MOCK } from "./api.js";
import {
  store,
  refreshHealth,
  refreshSequence,
  tryRefreshCurrent,
  loadTutorial,
  loadChapters,
  startHealthPolling,
  addTeam,
} from "./store.js";
import {
  icon,
  toast,
  toastOk,
  toastErr,
  showBuildOverlay,
  hideBuildOverlay,
  handleViewError,
  emptyState,
} from "./ui.js";
import { esc, fmtNum, fmtDate, timeAgo, navigate, parseRoute, debounce, bindSearch, powerDisplay, isSupportTeam, isReserveTeam } from "./util.js";
import { initSequencePanel } from "./components/sequence-panel.js";
import { openTeamDrawer } from "./components/team-drawer.js";
import { maybeShowTutorialOverlay } from "./components/tutorial-overlay.js";
import { addTeamById } from "./components/add-by-id.js";
import { fetchGameStatus, showGameSetupGate } from "./components/game-setup.js";

/* 视图 */
import * as overview from "./views/overview.js";
import * as chapters from "./views/chapters.js";
import * as chapterDetail from "./views/chapter-detail.js";
import * as stage from "./views/stage.js";
import * as grayzone from "./views/grayzone.js";
import * as grayzoneRegion from "./views/grayzone-region.js";
import * as species from "./views/species.js";
import * as speciesDetail from "./views/species-detail.js";
import * as roster from "./views/roster.js";
import * as teamPage from "./views/team-page.js";
import * as sequencePage from "./views/sequence-page.js";
import * as capture from "./views/capture.js";
import * as tutorialPage from "./views/tutorial-page.js";

const ROUTES = [
  { pattern: /^\/$/, view: overview, nav: "overview", viewId: "overview", title: "总览" },
  { pattern: /^\/overview$/, view: overview, nav: "overview", viewId: "overview", title: "总览" },
  { pattern: /^\/chapters$/, view: chapters, nav: "chapters", viewId: "chapters", title: "关卡图鉴" },
  { pattern: /^\/chapters\/([^/]+)$/, view: chapterDetail, nav: "chapters", viewId: "chapter-detail", param: "id", title: "章节详情" },
  { pattern: /^\/stages\/([^/]+)$/, view: stage, nav: "chapters", viewId: "stage", param: "id", title: "关卡队伍" },
  { pattern: /^\/grayzone\/region\/([^/]+)$/, view: grayzoneRegion, nav: "chapters", viewId: "grayzone-region", param: "region", title: "灰域节点" },
  { pattern: /^\/grayzone\/([^/]+)$/, view: grayzone, nav: "chapters", viewId: "grayzone", param: "area", title: "灰域地点" },
  { pattern: /^\/species$/, view: species, nav: "species", viewId: "species", title: "怪种图鉴" },
  { pattern: /^\/species\/([^/]+)$/, view: speciesDetail, nav: "species", viewId: "species-detail", param: "codex", title: "怪种详情" },
  { pattern: /^\/roster$/, view: roster, nav: "roster", viewId: "roster", title: "全怪组" },
  { pattern: /^\/teams\/([^/]+)$/, view: teamPage, nav: "chapters", viewId: "team", param: "id", title: "队伍详情" },
  { pattern: /^\/sequence$/, view: sequencePage, nav: "sequence", viewId: "sequence", title: "序列编排" },
  { pattern: /^\/capture$/, view: capture, nav: "capture", viewId: "capture", title: "登录抓取" },
  { pattern: /^\/tutorial$/, view: tutorialPage, nav: "tutorial", viewId: "tutorial", title: "使用教程" },
];

const viewEl = () => document.getElementById("view");
let currentRoute = null;
let routeToken = 0;
let firstBoot = true;
let appStarted = false;

/* ================================================================== */
/* 启动                                                               */
/* ================================================================== */
async function boot() {
  renderNavCounts();
  initTopbar();
  bindGlobalEvents();
  initNavHighlight();

  // 首次启动前置：必须先选择游戏客户端目录（valid=false / needs_setup=true → 全屏 gate）
  const gateShown = await maybeRequireGameSetup();
  if (gateShown) return;
  await startApp();
}

/** 启动前置 gate：返回 true 表示已显示 gate、等待用户选择后由 onReady 继续 */
async function maybeRequireGameSetup() {
  try {
    const status = await fetchGameStatus();
    if (!status) return false; // 旧后端无 /api/game/status：降级直接进入
    if (status.valid && !status.needs_setup) return false;
    showGameSetupGate({
      status,
      onReady: () => {
        startApp();
      },
    });
    return true;
  } catch (err) {
    // 状态接口异常不阻塞正常使用（避免旧版本/接口短暂失败导致进不去）
    console.warn("读取游戏客户端状态失败，跳过 setup gate：", err);
    return false;
  }
}

async function startApp() {
  if (appStarted) return;
  appStarted = true;

  // 先注册全局事件，保证基础数据首次加载时顶栏/导航角标就能同步刷新
  store.on("health", (payload) => {
    updateTopbar(payload);
    updateNavCounts(payload);
    renderNavCounts();
  });
  store.on("sequence", () => renderNavCounts());
  store.on("current", () => renderNavCounts());

  // 初次健康检查
  let health = null;
  try {
    health = await refreshHealth();
  } catch (err) {
    health = null;
  }
  updateTopbar(health);
  updateNavCounts(health);

  const catalogReady = health?.catalog?.state === "ready";
  if (!catalogReady && health) {
    showBuildOverlay(health?.catalog?.detail || health?.catalog?.state || "", async () => {
      await Promise.allSettled([refreshHealth(), refreshSequence(), tryRefreshCurrent(), loadChapters()]);
      updateTopbar(store.health);
      renderRoute();
    });
  }

  // 并行拉取基础数据（catalog 未就绪时部分接口 503，静默失败）
  // 说明：序列面板在数据就绪后再初始化，避免 boot 与面板各发一次 /api/sequence
  await Promise.allSettled([
    refreshSequence(),
    tryRefreshCurrent(),
    loadTutorial(),
    loadChapters(),
  ]);
  updateTopbar(store.health);
  updateNavCounts(store.health);
  renderNavCounts();
  initSequencePanel(document.getElementById("sequence-panel"));
  firstBoot = false;
  renderRoute();

  if (catalogReady || IS_MOCK) {
    setTimeout(() => maybeShowTutorialOverlay(), 500);
  }

  // 顶栏状态轮询
  startHealthPolling(15000);
  store.registerCleanup(() => {});
  firstBoot = false;
}

/* ================================================================== */
/* 顶栏                                                               */
/* ================================================================== */
function initTopbar() {
  const searchInput = document.getElementById("global-search");
  if (searchInput) {
    bindSearch(searchInput, (value) => runSearch(value, 260));
    searchInput.addEventListener("focus", () => {
      if (searchInput.value.trim()) runSearch(searchInput.value.trim(), 0);
    });
    document.getElementById("topbar-refresh")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await Promise.allSettled([refreshHealth(), refreshSequence(), tryRefreshCurrent()]);
        updateTopbar(store.health);
        toastOk("状态已刷新");
      } finally {
        button.disabled = false;
      }
    });
    document.getElementById("topbar-tutorial")?.addEventListener("click", async () => {
      const { showTutorialOverlay } = await import("./components/tutorial-overlay.js");
      showTutorialOverlay();
    });
  }
  const mockFlag = document.getElementById("mock-flag");
  if (mockFlag && IS_MOCK) mockFlag.classList.remove("hidden");

  document.getElementById("nav-execute")?.addEventListener("click", async () => {
    const { openExecuteModal } = await import("./components/execute-modal.js");
    openExecuteModal();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !isTypingTarget(event.target)) {
      event.preventDefault();
      searchInput?.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".searchbox")) {
      const drop = document.getElementById("search-drop");
      if (drop) drop.innerHTML = "";
    }
  });
}

function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName?.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

export function updateTopbar(health) {
  if (!health) {
    setStatus("game", "warn", "读取中…");
    setStatus("proxy", "ok", "—");
    setStatus("data", "warn", "读取中…");
    setStatus("targets", "ok", "—");
    return;
  }
  const game = health.game || {};
  const pidTip = "PID 由 tasklist 按进程名 GrilsFrontLine.exe 搜索得到，仅本机展示，不会上传。";
  if (game.game_running) {
    setStatusHtml(
      "game",
      "ok",
      `运行中 · <span class="pid-chip" title="${esc(pidTip)}">PID ${esc(game.pid ?? "—")}</span><span class="pid-info" tabindex="0" title="${esc(pidTip)}">?</span>`,
      pidTip,
    );
  } else {
    setStatusHtml("game", "warn", "未运行", "未找到 GrilsFrontLine.exe 进程（tasklist 按进程名搜索）");
  }
  setStatus("proxy", game.system_proxy ? "warn" : "ok", game.system_proxy || "未开启", game.system_proxy ? `系统代理：${game.system_proxy}` : "");

  const catalog = health.catalog || {};
  if (catalog.state === "ready" && catalog.built_at) {
    setStatus("data", "ok", `${fmtDate(catalog.built_at)}`, `数据构建 ${timeAgo(catalog.built_at)}`);
  } else if (catalog.state === "building") {
    setStatus("data", "warn", "解析中…");
  } else if (catalog.state === "error") {
    setStatus("data", "err", "解析失败");
  } else {
    setStatus("data", "warn", "加载中…");
  }
  const navDataTime = document.getElementById("nav-data-time");
  if (navDataTime) navDataTime.textContent = catalog.built_at ? fmtDate(catalog.built_at) : "—";
  const navVersion = document.getElementById("nav-version");
  if (navVersion && health.version) navVersion.textContent = `v${health.version}`;

  const targets = store.current?.targets || [];
  setStatus("targets", targets.length ? "cyan" : "warn", targets.length ? `${targets.length} / 35` : "未抓取");
}

function setStatus(key, cls, value, title) {
  const node = document.querySelector(`[data-status="${key}"]`);
  if (!node) return;
  node.className = `si-value ${cls || ""}`;
  node.textContent = value;
  if (title) node.title = title;
}

function setStatusHtml(key, cls, html, title) {
  const node = document.querySelector(`[data-status="${key}"]`);
  if (!node) return;
  node.className = `si-value ${cls || ""}`;
  node.innerHTML = html;
  if (title) node.title = title;
}

function updateNavCounts(health) {
  const counts = health?.catalog?.counts || {};
  setNavCount("chapters", counts.chapters);
  setNavCount("species", counts.species);
  setNavCount("roster", counts.teams);
}

function renderNavCounts() {
  const counts = store.health?.catalog?.counts || {};
  setNavCount("chapters", counts.chapters);
  setNavCount("species", counts.species);
  const seq = store.sequence;
  const seqEl = document.querySelector('[data-nav-count="sequence"]');
  if (seqEl && seq) seqEl.textContent = `${seq.count}`;
}

function setNavCount(key, value) {
  const el = document.querySelector(`[data-nav-count="${key}"]`);
  if (el && value !== undefined && value !== null) el.textContent = String(value);
}

/* ================================================================== */
/* 全局搜索                                                           */
/* ================================================================== */
const runSearch = debounce(async (value, wait = 0) => {
  const drop = document.getElementById("search-drop");
  if (!drop) return;
  if (!value || value.length < 1) {
    drop.innerHTML = "";
    return;
  }
  // 纯数字 / #编号：直接按队伍编号查详情，显示队伍结果卡 + 加入序列
  const numericMatch = value.trim().match(/^#?(\d{2,})$/);
  if (numericMatch) {
    const teamId = Number(numericMatch[1]);
    try {
      const detail = await api.team(teamId);
      const disp = powerDisplay(detail.power, detail.power_known);
      const roleBadges = [];
      if (isSupportTeam(detail)) roleBadges.push('<span class="badge support">支援队伍</span>');
      const isReserve =
        isReserveTeam(detail) ||
        Boolean(detail.reserve_reason) ||
        (Array.isArray(detail.appearances) &&
          detail.appearances.some((item) => String(item?.role || "").toLowerCase() === "reserve"));
      if (isReserve) roleBadges.push('<span class="badge reserve">机场可能刷新（推断）</span>');
      const inSequence = (store.sequence?.draft || []).some((team) => Number(team.id) === Number(detail.id));
      drop.innerHTML = `
        <div class="sd-group-title">队伍（按编号）</div>
        <div class="sd-item sd-team-result" data-search-nav="/teams/${esc(detail.id)}">
          <span class="badge mono sd-team-id">#${esc(detail.id)}</span>
          <span class="sd-main">
            <span class="sd-title">效能 ${disp.known ? disp.text : "未标注"} · ${esc(String(detail.units ?? ""))} 单位 · ${esc(detail.faction || "")}</span>
            <span class="sd-sub">总血量 ${fmtNum(detail.hp_total)}${roleBadges.length ? ` · ${roleBadges.join(" ")}` : ""}</span>
          </span>
          <span class="sd-actions"><button class="btn btn-xs btn-cyan" type="button" data-search-add="${esc(detail.id)}" ${inSequence ? "disabled" : ""}>${inSequence ? "已在序列" : `${icon("plus", 11)} 加入序列`}</button></span>
        </div>`;
      return;
    } catch (err) {
      drop.innerHTML = `<div class="sd-empty">没有找到编号为 #${teamId} 的可收藏队伍<br><span class="text-mute">可在序列页「按编号加入」再试。</span></div>`;
      return;
    }
  }
  try {
    const data = await api.search(value, 20);
    const teams = data.teams || [];
    const stages = data.stages || [];
    const speciesList = data.species || [];
    const q = value.trim().toLowerCase();
    const chapterHits = [];
    (store.chapters?.groups || []).forEach((group) => {
      (group.chapters || []).forEach((chapter) => {
        if (chapterHits.length >= 6) return;
        const hay = `${chapter.title || ""} ${chapter.subtitle || ""} ${(chapter.tags || []).join(" ")} ${group.title || ""}`.toLowerCase();
        if (hay.includes(q)) chapterHits.push({ chapter, group });
      });
    });
    if (!teams.length && !stages.length && !speciesList.length && !chapterHits.length) {
      drop.innerHTML = `<div class="sd-empty">没有找到「${esc(value)}」相关结果</div>`;
      return;
    }
    const groups = [];
    if (chapterHits.length) {
      groups.push(`<div class="sd-group-title">章节 / 活动</div>${chapterHits
        .map(
          ({ chapter, group }) => `
        <div class="sd-item" data-search-nav="/chapters/${esc(chapter.id)}">
          <span class="badge gold mono" style="height:18px">${esc(group.title)}</span>
          <span class="sd-main"><span class="sd-title">${esc(chapter.title || chapter.id)}</span><span class="sd-sub">${esc(chapter.subtitle || "")}</span></span>
        </div>`,
        )
        .join("")}`);
    }
    if (stages.length) {
      groups.push(`<div class="sd-group-title">关卡</div>${stages
        .slice(0, 5)
        .map(
          (item) => `
        <div class="sd-item" data-search-nav="/stages/${esc(item.id)}">
          <span class="badge amber mono">${esc(item.code || item.id)}</span>
          <span class="sd-main"><span class="sd-title">${esc(item.title || "")}</span><span class="sd-sub">${esc(item.chapter_title || "")}</span></span>
        </div>`,
        )
        .join("")}`);
    }
    if (speciesList.length) {
      groups.push(`<div class="sd-group-title">怪种</div>${speciesList
        .slice(0, 5)
        .map(
          (item) => `
        <div class="sd-item" data-search-nav="/species/${esc(item.codex_no)}">
          <span class="badge cyan mono">#${String(item.codex_no).padStart(3, "0")}</span>
          <span class="sd-main"><span class="sd-title">${esc(item.name)}</span><span class="sd-sub">${esc(item.faction || "")} · ${esc(String(item.team_count ?? ""))} 支队伍</span></span>
        </div>`,
        )
        .join("")}`);
    }
    if (teams.length) {
      groups.push(`<div class="sd-group-title">队伍</div>${teams
        .slice(0, 5)
        .map(
          (item) => `
        <div class="sd-item" data-search-nav="/teams/${esc(item.id)}">
          <span class="badge mono">#${esc(item.id)}</span>
          <span class="sd-main"><span class="sd-title">效能 ${powerDisplay(item.power, item.power_known).known ? powerDisplay(item.power, item.power_known).text : "未标注"}</span><span class="sd-sub">${esc(item.faction || "")} · ${esc(String(item.units ?? ""))} 单位</span></span>
        </div>`,
        )
        .join("")}`);
    }
    drop.innerHTML = groups.join("");
  } catch (err) {
    drop.innerHTML = `<div class="sd-empty">搜索失败：${esc(err.message)}</div>`;
  }
}, 180);

/* ================================================================== */
/* 路由                                                               */
/* ================================================================== */
function matchRoute(path) {
  for (const route of ROUTES) {
    const match = route.pattern.exec(path);
    if (match) return { route, match };
  }
  return null;
}

function setNavActive(navId) {
  const target = navId ? `/${navId}` : "";
  document.querySelectorAll(".nav-item").forEach((item) => {
    const nav = item.dataset.nav || "";
    item.classList.toggle("active", Boolean(target) && (nav === target || nav === navId));
  });
  moveNavHighlight(true);
}

/* 侧栏高亮滑块：独立高亮块通过 transform 平滑移动到当前菜单项 */
function initNavHighlight() {
  moveNavHighlight(false);
  window.addEventListener("resize", debounce(() => moveNavHighlight(false), 120));
}

function moveNavHighlight(animate = false) {
  const nav = document.querySelector(".nav");
  const hl = document.querySelector("[data-nav-highlight]");
  if (!nav || !hl) return;
  const active = nav.querySelector(".nav-item.active");
  if (!active || !active.offsetHeight) {
    hl.classList.remove("is-visible");
    return;
  }
  const first = !hl.dataset.positioned;
  const top = active.offsetTop;
  const height = active.offsetHeight;
  const noAnim = first || !animate;
  if (noAnim) hl.style.transition = "none";
  hl.style.transform = `translateY(${top}px)`;
  hl.style.height = `${height}px`;
  hl.classList.add("is-visible", "is-ready");
  hl.dataset.positioned = "1";
  if (noAnim) {
    // 初始化 / resize 直接定位，无动画；下一帧恢复 CSS transition
    void hl.offsetHeight;
    requestAnimationFrame(() => {
      hl.style.transition = "";
    });
  }
}

export async function renderRoute() {
  const { path, query } = parseRoute();
  const matched = matchRoute(path);
  const token = ++routeToken;

  if (!matched) {
    setNavActive("");
    const el = viewEl();
    el.dataset.view = "not-found";
    el.className = "view";
    el.innerHTML = emptyState({
      iconName: "compass",
      title: "页面不存在",
      desc: `没有找到路径 ${path}，请从左侧导航重新进入。`,
      actionText: "回到总览",
      actionId: "goto-overview",
    });
    el.querySelector("#goto-overview")?.addEventListener("click", () => navigate("/overview"));
    return;
  }

  const { route, match } = matched;
  currentRoute = route;
  setNavActive(route.nav);
  const params = {};
  if (route.param) {
    let raw = match[1];
    try {
      raw = decodeURIComponent(raw);
    } catch {
      /* keep raw */
    }
    params[route.param] = raw;
  }
  const el = viewEl();
  if (!el) return;
  store.runCleanups();
  // 先切 data-view / 重置类名，再清空内容：旧路由的异步回调据此判断「已经切走」，
  // 防止 overview 之类的延迟回调把新页面覆盖回去（曾经的无限闪烁根因）。
  el.dataset.view = route.viewId || route.nav || "page";
  el.className = "view";
  el.innerHTML = "";
  document.title = `${route.title} · 靶机工坊 TargetForge`;
  const mainEl = document.querySelector(".main");
  if (mainEl) mainEl.scrollTop = 0;
  try {
    await route.view.render(el, { params, query });
  } catch (err) {
    if (token !== routeToken) return;
    handleViewError(el, err, () => renderRoute());
  }
}

/* ================================================================== */
/* 全局事件                                                           */
/* ================================================================== */
function bindGlobalEvents() {
  window.addEventListener("hashchange", () => {
    if (firstBoot) return;
    renderRoute();
  });
  document.addEventListener("click", async (event) => {
    const navEl = event.target.closest("[data-nav]");
    if (navEl) {
      event.preventDefault();
      navigate(navEl.dataset.nav);
      return;
    }
    const searchAdd = event.target.closest("[data-search-add]");
    if (searchAdd) {
      event.preventDefault();
      event.stopPropagation();
      const teamId = Number(searchAdd.dataset.searchAdd);
      searchAdd.disabled = true;
      const ok = await addTeamById(teamId);
      if (ok) {
        searchAdd.textContent = "已在序列";
      } else if (searchAdd.isConnected) {
        searchAdd.disabled = false;
      }
      return;
    }
    const searchNav = event.target.closest("[data-search-nav]");
    if (searchNav) {
      const drop = document.getElementById("search-drop");
      if (drop) drop.innerHTML = "";
      const input = document.getElementById("global-search");
      if (input) input.value = "";
      navigate(searchNav.dataset.searchNav);
      return;
    }
    const addEl = event.target.closest("[data-add-team]");
    if (addEl) {
      event.preventDefault();
      event.stopPropagation();
      const teamId = Number(addEl.dataset.addTeam);
      addEl.disabled = true;
      try {
        const sequence = await addTeam(teamId);
        toastOk("已加入序列", `队伍 #${teamId} · 当前序列 ${sequence.count}/${sequence.max}`);
      } catch (err) {
        toastErr("加入失败", err.message);
      } finally {
        addEl.disabled = false;
      }
      return;
    }
    const teamEl = event.target.closest("[data-team-detail]");
    if (teamEl && !event.target.closest(".seq-actions") && !event.target.closest("[data-seq-act]")) {
      event.preventDefault();
      try {
        sessionStorage.setItem("tf:last-list", window.location.hash.replace(/^#/, "") || "/chapters");
      } catch {
        /* ignore */
      }
      openTeamDrawer(Number(teamEl.dataset.teamDetail));
      return;
    }
  });

  // 记录列表页来源，用于详情页「返回」
  window.addEventListener("hashchange", () => {
    const path = (window.location.hash || "#/").replace(/^#/, "");
    if (/^\/(chapters|species|stages|grayzone)(\/|$)/.test(path)) {
      try {
        sessionStorage.setItem("tf:last-list", path);
      } catch {
        /* ignore */
      }
    }
  });
}

/* ================================================================== */
/* 启动                                                               */
/* ================================================================== */
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
