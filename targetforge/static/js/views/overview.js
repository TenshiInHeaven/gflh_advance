/* views/overview.js —— 总览：当前任务状态 / 快捷入口 / 使用流程 4 步图 */
import { store, refreshHealth, refreshSequence, tryRefreshCurrent, loadChapters, sequenceStats, hasBaseData } from "../store.js";
import { icon, pageHeadHtml, sectionHeadHtml, toastErr, handleViewError, statusPill, butterflySvg } from "../ui.js";
import { esc, fmtNum, fmtTime, fmtDate, timeAgo, navigate, fmtDuration } from "../util.js";
import { openExecuteModal } from "../components/execute-modal.js";
import { FLOW_STEPS } from "../tutorial-data.js";

function readLastExecution() {
  try {
    const raw = sessionStorage.getItem("tf:last-exec");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function countsOf(health) {
  return (health && health.catalog && health.catalog.counts) || {};
}

function catalogStateOf(health) {
  return (health && health.catalog && health.catalog.state) || "cold";
}

function gameOf(health) {
  const game = (health && health.game) || {};
  return game;
}

function radarSvg() {
  const rings = [108, 86, 64, 42].map(
    (r) =>
      `<circle cx="125" cy="125" r="${r}" fill="none" stroke="rgba(94,225,255,${(0.28 - r * 0.0018).toFixed(3)})" stroke-width="1"/>`,
  );
  const ticks = [];
  for (let i = 0; i < 24; i += 1) {
    const angle = (i * Math.PI) / 12;
    const inner = i % 6 === 0 ? 100 : 110;
    ticks.push(
      `<line x1="${125 + Math.cos(angle) * 116}" y1="${125 + Math.sin(angle) * 116}" x2="${125 + Math.cos(angle) * inner}" y2="${125 + Math.sin(angle) * inner}" stroke="rgba(255,255,255,.14)" stroke-width="1"/>`,
    );
  }
  const cross = `
    <line x1="7" y1="125" x2="243" y2="125" stroke="rgba(255,255,255,.07)" stroke-width="1"/>
    <line x1="125" y1="7" x2="125" y2="243" stroke="rgba(255,255,255,.07)" stroke-width="1"/>`;
  return `
    <svg viewBox="0 0 250 250" aria-hidden="true">
      <defs>
        <linearGradient id="radarSweepGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="rgba(94,225,255,0)"/>
          <stop offset="72%" stop-color="rgba(94,225,255,.16)"/>
          <stop offset="100%" stop-color="rgba(94,225,255,.5)"/>
        </linearGradient>
        <radialGradient id="radarCenter" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="rgba(94,225,255,.28)"/>
          <stop offset="100%" stop-color="rgba(94,225,255,0)"/>
        </radialGradient>
      </defs>
      ${rings}
      ${ticks}
      ${cross}
      <circle cx="125" cy="125" r="116" fill="none" stroke="rgba(94,225,255,.25)" stroke-width="1" stroke-dasharray="2 7"/>
      <g class="radar-sweep">
        <path d="M125 125 L241 125 A116 116 0 0 0 205 43 Z" fill="url(#radarSweepGrad)"/>
        <line x1="125" y1="125" x2="241" y2="125" stroke="rgba(94,225,255,.55)" stroke-width="1.2"/>
      </g>
      <circle cx="125" cy="125" r="16" fill="url(#radarCenter)"/>
      <circle cx="125" cy="125" r="3" fill="#5ee1ff"/>
      <circle class="radar-blip" cx="172" cy="92" r="2.2" fill="#4f8cff"/>
      <circle class="radar-blip" cx="88" cy="158" r="2.2" fill="#5ee1ff"/>
      <circle class="radar-blip" cx="158" cy="168" r="2.2" fill="#62d8a5"/>
      <circle class="radar-blip" cx="196" cy="143" r="2.2" fill="#4f8cff"/>
      <text x="125" y="270" text-anchor="middle" fill="rgba(255,255,255,.28)" font-size="8" font-family="Consolas,monospace" letter-spacing="3">TARGET SCAN · STC</text>
    </svg>
  `;
}

export async function render(root, options = {}) {
  const { skipRefresh = false } = options;
  // 视图标记：路由切走后旧回调据此放弃回写（防 overview 覆盖其它页面）
  root.dataset.view = "overview";
  root.classList.add("view-overview");
  // 自检用：每次真正渲染计数，供 Playwright 断言「30s 内不重复渲染」
  root.dataset.overviewRender = String((Number(root.dataset.overviewRender) || 0) + 1);
  const health = store.health;
  const seq = store.sequence;
  const current = store.current;
  const chapters = store.chapters;
  const counts = countsOf(health);
  const stats = sequenceStats(seq);
  const catalogState = catalogStateOf(health);
  const game = gameOf(health);
  const grayAreas =
    (chapters?.groups?.find((group) => group.id === "grayzone")?.chapters?.[0]?.areas || []).length || 12;
  const chapterTotal = counts.chapters || 0;
  const lastExec = readLastExecution();
  const currentTargets = current?.targets || [];
  const buildTime = health?.catalog?.built_at;

  const statusRows = [
    {
      label: "数据解析",
      value:
        catalogState === "ready"
          ? "已就绪"
          : catalogState === "building"
            ? "解析中…"
            : catalogState === "error"
              ? "解析失败"
              : "加载中…",
      cls: catalogState === "ready" ? "ok" : catalogState === "error" ? "err" : "warn",
      extra: buildTime ? `构建于 ${fmtTime(buildTime, true)}（${timeAgo(buildTime)}）` : "",
    },
    {
      label: "游戏进程",
      value: game.game_running ? `运行中 · PID ${game.pid ?? "—"}` : "未运行",
      cls: game.game_running ? "ok" : "warn",
      extra: game.game_window_title || "",
    },
    {
      label: "系统代理",
      value: game.system_proxy || "未开启",
      cls: game.system_proxy ? "warn" : "ok",
      extra: game.system_proxy ? "抓包代理生效中，抓完记得关闭" : "正常",
    },
    {
      label: "登录凭证",
      value: current?.uid ? `uid ${current.uid}` : "未抓取",
      cls: current?.uid ? "ok" : "warn",
      extra: current?.uid
        ? `${current.creds_file || `来源 ${current.source || "state"}`}${current.captured_at ? ` · ${timeAgo(current.captured_at)}` : ""}`
        : "先完成登录抓取",
    },
    {
      label: "当前靶机",
      value: currentTargets.length ? `${currentTargets.length} / 35` : "—",
      cls: currentTargets.length ? "ok" : "",
      extra: current?.source ? `来源 ${current.source}` : "",
    },
    {
      label: "序列草稿",
      value: `${stats.count} / ${stats.max}`,
      cls: stats.count ? "ok" : "",
      extra: stats.count ? `总效能 ${fmtNum(stats.power)}` : "还没有加入队伍",
    },
    {
      label: "最近执行",
      value: lastExec ? `${lastExec.mode} · ${lastExec.dryRun ? "演练" : "正式"}` : "本次会话暂无",
      cls: lastExec ? (lastExec.ok ? "ok" : "err") : "",
      extra: lastExec ? `${fmtTime(lastExec.at)} · 删 ${lastExec.deleted} / 增 ${lastExec.added}` : "执行后会显示在这里",
    },
  ];

  const statTiles = [
    {
      label: "章节",
      icon: "map",
      value: catalogState === "ready" ? fmtNum(chapterTotal) : "…",
      sub: `${chapters?.groups?.length || 8} 个分组`,
      accent: "amber",
    },
    { label: "关卡", icon: "flag", value: catalogState === "ready" ? fmtNum(counts.stages) : "…", sub: "含活动 / 复刻 / 教学" },
    { label: "收藏队伍", icon: "users", value: catalogState === "ready" ? fmtNum(counts.teams) : "…", sub: "仅可收藏队伍" },
    { label: "图鉴怪种", icon: "crosshair", value: catalogState === "ready" ? fmtNum(counts.species) : "…", sub: "含灰域 / 无固定关卡" },
    { label: "灰域地点", icon: "map", value: fmtNum(grayAreas), sub: "区域内的地点，不是区域", accent: "cyan" },
    { label: "当前靶机", icon: "target", value: currentTargets.length ? `${currentTargets.length}` : "0", sub: `上限 35 · ${current?.uid ? `uid ${current.uid}` : "未抓取"}` },
  ];

  root.innerHTML = `
    <div data-overview-root class="overview-page">
    ${pageHeadHtml({
      crumbs: [{ label: "总览" }],
      title: "靶机工坊 · 总览",
      badge: "OVERVIEW",
      sub: "浏览全部可收藏关卡与怪种，编排序列后通过 GFLH 协议注入「收藏标靶」。所有数据来自本机游戏文件，完全离线。",
      actions: `
        <button class="btn btn-ghost" type="button" data-act="refresh">${icon("refresh", 14)} 刷新状态</button>
        <button class="btn btn-cyan" type="button" data-nav="/capture">${icon("key", 14)} 登录抓取</button>
        <button class="btn btn-primary" type="button" data-act="execute">${icon("play", 14)} 执行注入</button>
      `,
    })}

    <section class="hero">
      <div class="hero-left">
        <div class="eyebrow">TARGET FORGE // 可收藏靶机编排</div>
        <h1>选敌人，<span class="hl">编排靶机</span><br><span class="thin">把想要的怪组写进收藏标靶</span></h1>
        <p class="hero-desc">
          覆盖 <b>${fmtNum(counts.stages || 2345)}</b> 个关卡 · <b>${fmtNum(counts.teams || 13700)}</b> 支可收藏队伍 · <b>${fmtNum(counts.species || 264)}</b> 个图鉴怪种。
          拖拽排序、三种注入模式、演练预览与登录抓取向导，全程本地执行。
        </p>
        <div class="hero-actions">
          <button class="btn btn-primary btn-lg cut" type="button" data-nav="/chapters">${icon("map", 15)} 开始选关卡</button>
          <button class="btn btn-lg" type="button" data-nav="/species">${icon("crosshair", 15)} 按怪种找队伍</button>
          <button class="btn btn-lg btn-ghost" type="button" data-act="show-tutorial">${icon("book", 15)} 新手引导</button>
        </div>
        <div class="hero-stats">
          <div class="hero-stat"><b class="amber">${fmtNum(counts.chapters || 0)}</b><span>章节</span></div>
          <div class="hero-stat"><b>${fmtNum(counts.stages || 0)}</b><span>关卡</span></div>
          <div class="hero-stat"><b>${fmtNum(counts.teams || 0)}</b><span>可收藏队伍</span></div>
          <div class="hero-stat"><b class="cyan">${fmtNum(counts.species || 0)}</b><span>图鉴怪种</span></div>
          <div class="hero-stat"><b>${grayAreas}</b><span>灰域地点</span></div>
        </div>
      </div>
      <div class="hero-right">
        <div class="radar">
          ${radarSvg()}
          <div class="hero-butterfly">${butterflySvg({ size: 176 })}</div>
        </div>
        <div class="hero-bf-a">${butterflySvg({ size: 46, opacity: 0.55, className: "float" })}</div>
        <div class="hero-bf-b">${butterflySvg({ size: 30, opacity: 0.42, className: "float-alt" })}</div>
        <div class="hero-bf-c">${butterflySvg({ size: 22, opacity: 0.34, className: "float-slow" })}</div>
      </div>
    </section>

    <div class="stat-grid">
      ${statTiles
        .map(
          (tile) => `
        <div class="stat-tile">
          <div class="st-label">${icon(tile.icon, 12)} ${esc(tile.label)}</div>
          <div class="st-value ${tile.accent || ""}">${esc(tile.value)}</div>
          <div class="st-sub">${esc(tile.sub)}</div>
        </div>`,
        )
        .join("")}
    </div>

    <div class="overview-cols">
      <div class="status-card">
        <h3>${icon("radar", 14)} 当前任务状态 <span class="badge ${catalogState === "ready" ? "green" : "amber"}" style="margin-left:4px">${catalogState === "ready" ? "数据就绪" : "数据构建中"}</span></h3>
        ${statusRows
          .map(
            (row) => `
          <div class="status-row">
            <span class="sr-label">${esc(row.label)}</span>
            <span class="sr-value ${row.cls}">${esc(row.value)}</span>
            <span class="sr-extra">${esc(row.extra)}</span>
          </div>`,
          )
          .join("")}
        <div class="divider"></div>
        <div class="tag-row">
          <button class="btn btn-sm btn-ghost" type="button" data-act="refresh">${icon("refresh", 12)} 刷新</button>
          <button class="btn btn-sm btn-ghost" type="button" data-nav="/capture">${icon("key", 12)} 登录抓取</button>
          <button class="btn btn-sm btn-ghost" type="button" data-nav="/sequence">${icon("layers", 12)} 打开序列</button>
          <button class="btn btn-sm btn-ghost" type="button" data-act="show-tutorial">${icon("book", 12)} 使用教程</button>
        </div>
      </div>

      <div class="status-card">
        <h3>${icon("target", 14)} 当前靶机 <span class="badge mono" style="margin-left:auto">${currentTargets.length} / 35</span></h3>
        ${
          currentTargets.length
            ? `<div class="targets-grid">
                ${currentTargets
                  .slice(0, 12)
                  .map(
                    (item) => `
                  <div class="target-item">
                    <span class="target-order">${esc(item.order)}</span>
                    <span class="target-team">team ${esc(item.team)}</span>
                  </div>`,
                  )
                  .join("")}
                ${
                  currentTargets.length > 12
                    ? `<div class="target-item" style="justify-content:center;color:var(--text-mute);font-family:var(--font-ui)">还有 ${currentTargets.length - 12} 条…</div>`
                    : ""
                }
              </div>
              <div class="param-note" style="margin-top:10px">uid ${esc(current?.uid || "—")} · 来源 ${esc(current?.source || "—")}${current?.captured_at ? ` · 抓取于 ${esc(timeAgo(current.captured_at))}` : ""}</div>`
            : `<div class="empty" style="padding:32px 16px">
                <div class="em-ico">${icon("key", 22)}</div>
                <h4>还没有抓到当前靶机</h4>
                <p>先完成一次「登录抓取」，执行向导才能计算要删除 / 保留哪些靶机。</p>
                <button class="btn btn-primary btn-sm" type="button" data-nav="/capture">${icon("key", 12)} 去登录抓取</button>
              </div>`
        }
        ${
          current?.duplicate_orders && Object.keys(current.duplicate_orders).length
            ? `<div class="warn-box"><b>${icon("alert", 11)} 发现重复编号</b>建议用「清空重排」修复：${Object.keys(current.duplicate_orders)
                .slice(0, 5)
                .join(", ")}</div>`
            : ""
        }
      </div>
    </div>

    <section class="section">
      ${sectionHeadHtml("使用流程", { hint: "四步完成一次靶机编排", iconName: "steps" })}
      <div class="flow">
        ${FLOW_STEPS.map(
          (step) => `
          <div class="flow-step">
            <div class="flow-num">${esc(step.num)}</div>
            <div class="flow-ico">${icon(["key", "map", "layers", "play"][Number(step.num) - 1], 17)}</div>
            <h4>${esc(step.title)}</h4>
            <p>${esc(step.desc)}</p>
            <button class="flow-go" type="button" data-nav="${esc(step.nav)}">${esc(step.navLabel)} ${icon("arrowRight", 12)}</button>
          </div>`,
        ).join("")}
      </div>
    </section>

    <section class="section">
      ${sectionHeadHtml("快捷入口", { hint: "常用功能一步直达", iconName: "grid" })}
      <div class="quick-grid">
        <button class="quick-card" type="button" data-nav="/chapters">
          <span class="qc-ico">${icon("map", 19)}</span>
          <span class="qc-body"><span class="qc-title">关卡图鉴</span><span class="qc-desc">7 个分组 · 按章节浏览关卡队伍</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
        <button class="quick-card cyan" type="button" data-nav="/species">
          <span class="qc-ico">${icon("crosshair", 19)}</span>
          <span class="qc-body"><span class="qc-title">怪种图鉴</span><span class="qc-desc">264 个怪种 · 按阵营 / 分类筛选</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
        <button class="quick-card violet" type="button" data-nav="/sequence">
          <span class="qc-ico">${icon("layers", 19)}</span>
          <span class="qc-body"><span class="qc-title">序列编排</span><span class="qc-desc">拖拽排序 · n/35 进度 · 三种执行模式</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
        <button class="quick-card green" type="button" data-nav="/capture">
          <span class="qc-ico">${icon("key", 19)}</span>
          <span class="qc-body"><span class="qc-title">登录抓取</span><span class="qc-desc">抓 uid / sign · 读取当前靶机</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
        <button class="quick-card" type="button" data-act="execute">
          <span class="qc-ico">${icon("play", 19)}</span>
          <span class="qc-body"><span class="qc-title">执行注入</span><span class="qc-desc">预览计划 → 执行 → 大退重登</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
        <button class="quick-card cyan" type="button" data-nav="/tutorial">
          <span class="qc-ico">${icon("book", 19)}</span>
          <span class="qc-body"><span class="qc-title">使用教程</span><span class="qc-desc">概念 / 流程 / 常见问题 / 安全须知</span></span>
          <span class="qc-bf">${butterflySvg({ size: 26 })}</span>
          <span class="qc-arrow">${icon("chevronRight", 16)}</span>
        </button>
      </div>
    </section>
    </div>
  `;

  bindOverviewEvents(root);

  // 关键：这里只允许「最多一次」异步刷新 + 一次重渲染，绝不递归自渲染。
  // 1) boot 阶段已加载过基础数据（hasBaseData）时直接跳过，避免首屏重复请求；
  // 2) 重渲染前校验 #view 当前仍是 overview（路由切走后旧回调不得覆盖别的页面）。
  if (skipRefresh) return;
  if (hasBaseData()) return;

  const token = {};
  root._tfToken = token;
  Promise.allSettled([
    refreshHealth(),
    refreshSequence(),
    tryRefreshCurrent(),
    loadChapters().catch((err) => {
      if (err.status === 503) throw err;
    }),
  ]).then((results) => {
    if (!root.isConnected || root._tfToken !== token) return;
    if (root.dataset.view !== "overview") return; // 已切到别的路由，放弃回写
    const fatal = results.find((item) => item.status === "rejected" && item.reason?.status === 503);
    if (fatal) {
      handleViewError(root, fatal.reason, () => render(root, { skipRefresh: true }));
      return;
    }
    render(root, { skipRefresh: true });
  });
}

function bindOverviewEvents(root) {
  root.querySelector('[data-act="refresh"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await Promise.allSettled([refreshHealth(), refreshSequence(), tryRefreshCurrent()]);
      await render(root, { skipRefresh: true });
    } finally {
      button.disabled = false;
    }
  });
  root.querySelector('[data-act="execute"]')?.addEventListener("click", () => openExecuteModal());
  root.querySelector('[data-act="show-tutorial"]')?.addEventListener("click", async () => {
    const { showTutorialOverlay } = await import("../components/tutorial-overlay.js");
    showTutorialOverlay();
  });
}
