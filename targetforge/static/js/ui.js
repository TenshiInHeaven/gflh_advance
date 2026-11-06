/* ui.js —— 图标 / 弹窗 / 抽屉 / toast / 骨架 / 空态 / 通用卡片渲染 */
import { esc, fmtNum, fmtPower, fmtTime, factionClass, factionColor } from "./util.js";
import { api } from "./api.js";

/* ================================================================== */
/* 图标                                                               */
/* ================================================================== */
const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><path d="M9 4v14M15 6v14"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.2"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
  key: '<circle cx="8" cy="12" r="4"/><path d="M12 12h8M18 12v4M15 12v3"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21V5.5Z"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>',
  play: '<path d="M7 4.5v15l13-7.5-13-7.5Z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4.2-4.2"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 6.3"/><path d="M20 4v7h-7"/>',
  chevronRight: '<path d="m9 5 7 7-7 7"/>',
  chevronLeft: '<path d="m15 5-7 7 7 7"/>',
  chevronDown: '<path d="m5 9 7 7 7-7"/>',
  chevronUp: '<path d="m5 15 7-7 7 7"/>',
  close: '<path d="M5 5l14 14M19 5 5 19"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
  arrowUp: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  arrowDown: '<path d="M12 5v14M5 12l7 7 7-7"/>',
  arrowRight: '<path d="M5 12h14M13 5l7 7-7 7"/>',
  grip: '<circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/>',
  check: '<path d="m4 12.5 5 5L20 6.5"/>',
  alert: '<path d="M12 3 1.8 21h20.4L12 3Z"/><path d="M12 9v5M12 17.5v.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.2v.4"/>',
  shield: '<path d="M12 3 5 6v6c0 4.2 3 7.6 7 9 4-1.4 7-4.8 7-9V6l-7-3Z"/>',
  gamepad: '<rect x="2.5" y="7" width="19" height="10.5" rx="4"/><path d="M7.5 11v3M6 12.5h3M15.5 11.5v.5M18 13.5v.5"/>',
  wifi: '<path d="M2.5 8.5a15 15 0 0 1 19 0M6 12a10 10 0 0 1 12 0M9.5 15.4a5 5 0 0 1 5 0"/><circle cx="12" cy="19" r="1.2"/>',
  database: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.4l3.4 2"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.6 6-5.6s6 2.3 6 5.6"/><path d="M16 5.3a3 3 0 0 1 0 5.4M18 20c0-2.4-.9-4.3-2.4-5.3"/>',
  crosshair: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4"/>',
  terminal: '<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="m7 9 3 3-3 3M12.5 15H17"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z"/>',
  box: '<path d="m12 2.8 8.5 4.7v9L12 21.2 3.5 16.5v-9L12 2.8Z"/><path d="m3.5 7.6 8.5 4.7 8.5-4.7M12 12.3V21"/>',
  zap: '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/>',
  lock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  external: '<path d="M14 4h6v6M20 4 10 14"/><path d="M18.5 14v5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V7A1.5 1.5 0 0 1 5 5.5h5"/>',
  rotate: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4v6h6"/>',
  spark: '<path d="M12 2.5 14.5 9l6.5 2.5-6.5 2.5L12 21.5 9.5 14 3 11.5 9.5 9 12 2.5Z"/>',
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 19 7"/>',
  skull: '<path d="M12 2.8c-4.6 0-7.5 3-7.5 7 0 2.6 1.3 4.3 2.7 5.3v3.1c0 .9.7 1.6 1.6 1.6h6.4c.9 0 1.6-.7 1.6-1.6v-3.1c1.4-1 2.7-2.7 2.7-5.3 0-4-2.9-7-7.5-7Z"/><circle cx="9" cy="10.5" r="1.3"/><circle cx="15" cy="10.5" r="1.3"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1.2"/><circle cx="4" cy="12" r="1.2"/><circle cx="4" cy="18" r="1.2"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5v-3a2 2 0 0 0-2-2h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  power: '<path d="M12 3v9"/><path d="M6.2 6.5a8 8 0 1 0 11.6 0"/>',
  steps: '<path d="M4 20h5v-5h5v-5h5V5"/><path d="M4 20V15"/>',
  flag: '<path d="M5 21V4M5 4c4-2 7 2 11 0v9c-4 2-7-2-11 0"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4.5 20h15"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4.5 20h15"/>',
};

export function icon(name, size = 16, cls = "") {
  const body = ICONS[name] || ICONS.info;
  return `<svg class="ico ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

/* ================================================================== */
/* Toast                                                              */
/* ================================================================== */
let toastRoot = null;

function ensureToastRoot() {
  if (!toastRoot) {
    toastRoot = document.createElement("div");
    toastRoot.id = "toasts";
    document.body.appendChild(toastRoot);
  }
  return toastRoot;
}

export function toast(options, type = "info") {
  const opts = typeof options === "string" ? { title: options } : options || {};
  const kind = opts.type || type;
  const root = ensureToastRoot();
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  const iconName = { ok: "check", err: "alert", warn: "alert", info: "info" }[kind] || "info";
  node.innerHTML = `
    <span class="t-ico">${icon(iconName, 17)}</span>
    <div class="t-body">
      <div class="t-title">${esc(opts.title || "")}</div>
      ${opts.text ? `<div class="t-text">${esc(opts.text)}</div>` : ""}
    </div>
    <button class="t-close" type="button" aria-label="关闭">${icon("close", 13)}</button>
  `;
  const remove = () => {
    node.classList.add("leaving");
    setTimeout(() => node.remove(), 220);
  };
  node.querySelector(".t-close").addEventListener("click", remove);
  root.appendChild(node);
  while (root.children.length > 5) root.firstElementChild.remove();
  if (opts.duration !== 0) setTimeout(remove, opts.duration || 4200);
  return { remove };
}

export function toastOk(title, text) {
  return toast({ title, text, type: "ok" });
}
export function toastErr(title, text) {
  return toast({ title, text, type: "err", duration: 6000 });
}

/* ================================================================== */
/* Modal                                                              */
/* ================================================================== */
const modalStack = [];

export function openModal(options = {}) {
  const {
    title = "",
    subtitle = "",
    iconName = "",
    width = "",
    body = "",
    footer = "",
    onClose = null,
    onMount = null,
    closeOnBackdrop = true,
  } = options;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const widthClass = width === "wide" || width === "narrow" ? width : "";
  backdrop.innerHTML = `
    <div class="modal ${widthClass}" role="dialog" aria-modal="true">
      <div class="modal-head">
        ${iconName ? `<span class="mh-ico">${icon(iconName, 17)}</span>` : ""}
        <div>
          <h3>${esc(title)}</h3>
          ${subtitle ? `<div class="mh-sub">${esc(subtitle)}</div>` : ""}
        </div>
        <button class="modal-close" type="button" aria-label="关闭">${icon("close", 16)}</button>
      </div>
      <div class="modal-body"></div>
      ${footer ? `<div class="modal-foot"></div>` : ""}
    </div>
  `;
  const bodyEl = backdrop.querySelector(".modal-body");
  if (typeof body === "string") bodyEl.innerHTML = body;
  else if (body instanceof Node) bodyEl.appendChild(body);
  const footEl = backdrop.querySelector(".modal-foot");
  if (footEl) {
    if (typeof footer === "string") footEl.innerHTML = footer;
    else if (footer instanceof Node) footEl.appendChild(footer);
  }
  const modal = backdrop.querySelector(".modal");

  const handle = {
    backdrop,
    modal,
    body: bodyEl,
    foot: footEl,
    close(result) {
      const index = modalStack.indexOf(handle);
      if (index >= 0) modalStack.splice(index, 1);
      backdrop.remove();
      if (onClose) onClose(result);
    },
  };

  const closeBtn = backdrop.querySelector(".modal-close");
  closeBtn.addEventListener("click", () => handle.close());
  if (closeOnBackdrop) {
    backdrop.addEventListener("mousedown", (event) => {
      if (event.target === backdrop) handle.close();
    });
  }
  document.body.appendChild(backdrop);
  modalStack.push(handle);
  if (onMount) onMount(handle);
  return handle;
}

export function closeTopModal() {
  const top = modalStack[modalStack.length - 1];
  if (top) {
    top.close();
    return true;
  }
  return false;
}

/* ================================================================== */
/* 抽屉                                                               */
/* ================================================================== */
const drawerStack = [];

export function openDrawer(options = {}) {
  const { head = "", body = "", footer = "", onClose = null, onMount = null, width = "" } = options;
  const backdrop = document.createElement("div");
  backdrop.className = "drawer-backdrop";
  const panel = document.createElement("aside");
  panel.className = "drawer";
  if (width) panel.style.width = typeof width === "number" ? `${width}px` : width;
  panel.innerHTML = `
    <div class="drawer-head"></div>
    <div class="drawer-body"></div>
    ${footer ? `<div class="drawer-foot"></div>` : ""}
  `;
  const headEl = panel.querySelector(".drawer-head");
  const bodyEl = panel.querySelector(".drawer-body");
  const footEl = panel.querySelector(".drawer-foot");
  if (typeof head === "string") headEl.innerHTML = head;
  else if (head instanceof Node) headEl.appendChild(head);
  if (typeof body === "string") bodyEl.innerHTML = body;
  else if (body instanceof Node) bodyEl.appendChild(body);
  if (footEl) {
    if (typeof footer === "string") footEl.innerHTML = footer;
    else if (footer instanceof Node) footEl.appendChild(footer);
  }
  const handle = {
    backdrop,
    panel,
    head: headEl,
    body: bodyEl,
    foot: footEl,
    close(result) {
      const index = drawerStack.indexOf(handle);
      if (index >= 0) drawerStack.splice(index, 1);
      backdrop.remove();
      panel.remove();
      if (onClose) onClose(result);
    },
  };
  backdrop.addEventListener("mousedown", () => handle.close());
  document.body.appendChild(backdrop);
  document.body.appendChild(panel);
  drawerStack.push(handle);
  if (onMount) onMount(handle);
  return handle;
}

export function closeTopDrawer() {
  const top = drawerStack[drawerStack.length - 1];
  if (top) {
    top.close();
    return true;
  }
  return false;
}

/* 全局 ESC 关闭 */
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (modalStack.length) {
    event.preventDefault();
    closeTopModal();
  } else if (drawerStack.length) {
    closeTopDrawer();
  }
});

/* ================================================================== */
/* 二次确认                                                           */
/* ================================================================== */
export function confirmDialog(options = {}) {
  const {
    title = "确认操作",
    message = "",
    detail = "",
    confirmText = "确认",
    cancelText = "取消",
    danger = false,
    iconName = "alert",
  } = options;
  return new Promise((resolve) => {
    let settled = false;
    const handle = openModal({
      title,
      iconName,
      width: "narrow",
      closeOnBackdrop: false,
      body: `
        <p style="font-size:13px;line-height:1.8;color:var(--text-dim);margin:0">${esc(message)}</p>
        ${detail ? `<div class="warn-box" style="margin-top:14px">${esc(detail)}</div>` : ""}
      `,
      footer: `
        <div class="spacer"></div>
        <button class="btn btn-ghost" data-role="cancel" type="button">${esc(cancelText)}</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-role="confirm" type="button">${esc(confirmText)}</button>
      `,
      onClose: () => {
        if (!settled) resolve(false);
      },
    });
    handle.foot.querySelector('[data-role="cancel"]').addEventListener("click", () => {
      settled = true;
      handle.close();
      resolve(false);
    });
    handle.foot.querySelector('[data-role="confirm"]').addEventListener("click", () => {
      settled = true;
      handle.close();
      resolve(true);
    });
    setTimeout(() => handle.foot.querySelector('[data-role="confirm"]').focus(), 60);
  });
}

/* ================================================================== */
/* catalog 构建遮罩                                                   */
/* ================================================================== */
let buildOverlay = null;
let buildTimer = 0;

export function showBuildOverlay(detail = "", onReady = null) {
  if (!buildOverlay) {
    buildOverlay = document.createElement("div");
    buildOverlay.className = "build-overlay";
    buildOverlay.innerHTML = `
      <div class="build-card">
        <div class="build-ring">${icon("database", 26)}</div>
        <h3>正在解析本机数据…</h3>
        <p>首次启动需要读取 STC / client_text / enemy_full_model，<br>通常 20~60 秒；页面会自动重试，无需刷新。</p>
        <div class="build-log"></div>
      </div>
    `;
    document.body.appendChild(buildOverlay);
  }
  const logEl = buildOverlay.querySelector(".build-log");
  if (detail) logEl.textContent = detail;
  if (buildTimer) clearInterval(buildTimer);
  buildTimer = setInterval(async () => {
    try {
      const health = await api.health();
      const catalogState = health?.catalog?.state;
      if (catalogState === "ready") {
        hideBuildOverlay();
        if (onReady) onReady();
        return;
      }
      if (catalogState === "error") {
        logEl.textContent = `解析失败：${health?.catalog?.error || "未知错误"}（点击页面任意处重试，或检查控制台日志）`;
      } else {
        logEl.textContent = `catalog 状态：${catalogState || "building"} · 已等待 ${Math.round((Date.now() - startedAt) / 1000)}s`;
      }
    } catch {
      /* 服务还没起时静默重试 */
    }
  }, 2000);
  const startedAt = Date.now();
}

export function hideBuildOverlay() {
  if (buildTimer) {
    clearInterval(buildTimer);
    buildTimer = 0;
  }
  if (buildOverlay) {
    buildOverlay.remove();
    buildOverlay = null;
  }
}

/* ================================================================== */
/* 骨架 / 空态 / 错误态                                               */
/* ================================================================== */
export function skeletonCards(count = 6, { height = 178, minWidth = 288 } = {}) {
  const items = Array.from({ length: count })
    .map(
      () => `
      <div class="sk-card" style="height:${height}px;min-width:${minWidth}px">
        <div class="skeleton sk-line w40"></div>
        <div class="skeleton sk-line tall w80" style="margin-top:18px"></div>
        <div class="skeleton sk-line w60"></div>
        <div class="skeleton sk-line w80" style="margin-top:22px"></div>
      </div>`,
    )
    .join("");
  return `<div class="sk-grid">${items}</div>`;
}

export function skeletonRows(count = 6) {
  const items = Array.from({ length: count })
    .map(
      () => `
      <div style="display:flex;gap:16px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line-faint)">
        <div class="skeleton" style="width:72px;height:24px"></div>
        <div style="flex:1"><div class="skeleton sk-line w40"></div><div class="skeleton sk-line w60" style="margin-bottom:0"></div></div>
        <div class="skeleton" style="width:110px;height:12px"></div>
        <div class="skeleton" style="width:90px;height:12px"></div>
      </div>`,
    )
    .join("");
  return `<div style="border:1px solid var(--line);border-radius:10px;overflow:hidden">${items}</div>`;
}

export function emptyState({ iconName = "box", title = "暂无数据", desc = "", actionText = "", actionId = "", extra = "" } = {}) {
  return `
    <div class="empty">
      <div class="em-ico">${icon(iconName, 25)}</div>
      <h4>${esc(title)}</h4>
      ${desc ? `<p>${esc(desc)}</p>` : ""}
      ${actionText ? `<button class="btn btn-primary" type="button" ${actionId ? `id="${esc(actionId)}"` : ""}>${esc(actionText)}</button>` : ""}
      ${extra}
    </div>
  `;
}

export function errorState({ error, retryId = "retry-btn" } = {}) {
  const status = error?.status ? `HTTP ${error.status}` : "ERROR";
  const title = error?.status === 404 ? "没有找到对应数据" : "数据加载失败";
  const hint = error?.hint || "";
  const detail = error?.detail ? String(error.detail).slice(0, 900) : "";
  return `
    <div class="error-state">
      <div class="er-code">${esc(status)}</div>
      <h4>${esc(title)}</h4>
      <p>${esc(error?.message || "未知错误")}${hint ? `<br>${esc(hint)}` : ""}</p>
      ${detail ? `<div class="er-detail">${esc(detail)}</div>` : ""}
      <div class="er-actions">
        <button class="btn btn-primary" type="button" id="${esc(retryId)}">${icon("refresh", 14)} 重试</button>
      </div>
    </div>
  `;
}

/** 通用错误处理：503（catalog 构建中）→ 全局遮罩轮询；否则渲染错误态 */
export function handleViewError(container, error, retry) {
  if (!container) return;
  if (error && (error.status === 503 || error.status === 0)) {
    container.innerHTML = `
      <div class="empty" style="padding:100px 24px">
        <div class="em-ico">${icon("database", 25)}</div>
        <h4>${error.status === 503 ? "正在解析本机数据…" : "本地服务未响应"}</h4>
        <p>${esc(error.message || "")}${error.hint ? `<br>${esc(error.hint)}` : ""}</p>
      </div>`;
    showBuildOverlay(error.detail || error.message, retry);
    return;
  }
  container.innerHTML = errorState({ error });
  const btn = container.querySelector("#retry-btn");
  if (btn) btn.addEventListener("click", retry);
}

/* ================================================================== */
/* 分页                                                               */
/* ================================================================== */
export function renderPager(options = {}) {
  const { page = 1, total = 0, pageSize = 60, onChange = null, extra = "" } = options;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, page), totalPages);
  const buttons = [];
  const push = (value, label, cls = "") => {
    buttons.push(
      `<button class="pg ${cls}" data-page="${value}" type="button" ${value === current ? 'disabled aria-current="page"' : ""}>${label}</button>`,
    );
  };
  push(current - 1, icon("chevronLeft", 12), "nav");
  const windowPages = new Set([1, totalPages]);
  for (let i = current - 2; i <= current + 2; i += 1) {
    if (i >= 1 && i <= totalPages) windowPages.add(i);
  }
  const sorted = [...windowPages].sort((a, b) => a - b);
  let prev = 0;
  sorted.forEach((value) => {
    if (prev && value - prev > 1) buttons.push('<span class="pg-gap">…</span>');
    push(value, String(value), value === current ? "active" : "");
    prev = value;
  });
  push(current + 1, icon("chevronRight", 12), "nav");
  const from = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const to = Math.min(total, current * pageSize);
  return `
    <div class="pager" data-pager>
      <span class="pg-info">共 <b>${fmtNum(total)}</b> 条 · ${fmtNum(from)}-${fmtNum(to)}</span>
      ${extra}
      ${buttons.join("")}
    </div>
  `;
}

export function bindPager(container, { page, total, pageSize, onChange }) {
  const pagerEl = container.querySelector("[data-pager]");
  if (!pagerEl) return;
  pagerEl.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-page]");
    if (!btn || btn.disabled) return;
    const next = Number(btn.dataset.page);
    if (!Number.isFinite(next) || next < 1 || next === page) return;
    onChange(next);
  });
}

/* ================================================================== */
/* 通用小片段                                                         */
/* ================================================================== */
export function factionChip(faction, { small = false } = {}) {
  const cls = factionClass(faction);
  return `<span class="faction-chip ${cls}"><i></i>${esc(faction || "其它")}</span>`;
}

export function tagsHtml(tags, { amberFirst = true, max = 6 } = {}) {
  if (!tags || !tags.length) return "";
  return tags
    .slice(0, max)
    .map((tag, index) => {
      const amber = amberFirst && (index === 0 || ["BOSS", "精英", "满力场", "紧急"].includes(tag));
      return `<span class="tag ${amber ? "amber" : ""}">${esc(tag)}</span>`;
    })
    .join("");
}

export function speciesChips(species, { max = 8 } = {}) {
  if (!species || !species.length) return "";
  const chips = species.slice(0, max).map(
    (item) =>
      `<span class="sp-chip" style="--fc:${factionColor(item.faction)}" title="${esc(item.name)}">${esc(item.name || item.codex_no)}</span>`,
  );
  if (species.length > max) chips.push(`<span class="sp-chip more">+${species.length - max}</span>`);
  return chips.join("");
}

export function powerHtml(power) {
  return fmtPower(power) === "—" ? `<b class="dim">—</b>` : `<b>${fmtNum(power)}</b>`;
}

/** 队伍列表排序：未标注效能（0）的排最后，其它按效能降序 */
export function sortTeamsByPower(items = []) {
  return items.slice().sort((a, b) => {
    const pa = Number(a?.power) > 0 ? Number(a.power) : -1;
    const pb = Number(b?.power) > 0 ? Number(b.power) : -1;
    return pb - pa;
  });
}

/** 队伍卡片（列表通用） */
export function teamCardHtml(team, options = {}) {
  const { selected = false, showStage = true, compact = false } = options;
  const fc = factionColor(team.faction);
  const flags = [];
  if (team.gray_zone) flags.push('<span class="badge cyan">灰域</span>');
  if (team.orphan) flags.push('<span class="badge violet">无固定关卡</span>');
  const powerUnknown = !(Number(team.power) > 0);
  const stageLine = team.stage
    ? `${esc(team.stage.title || "")} · ${esc(team.stage.stage_title || "")} <b>${esc(team.stage.code || "")}</b>`
    : team.gray_zone
      ? "灰域探查"
      : team.orphan
        ? "无固定关卡"
        : "";
  return `
    <article class="team-card ${selected ? "is-selected" : ""}" style="--fc:${fc}" data-team-detail="${team.id}">
      <div class="tc-top">
        <span class="tc-id">队伍 <b>#${esc(team.id)}</b></span>
        <span class="tc-power">${powerUnknown ? '<b class="dim">—</b><span>未标注效能</span>' : `${powerHtml(team.power)}<span>效能</span>`}</span>
      </div>
      <div class="tc-meta">
        <span class="m">${icon("users", 11)} ${team.units} 单位</span>
        <span class="m">${icon("shield", 11)} 总血 ${fmtNum(team.hp_total)}</span>
        ${factionChip(team.faction)}
        ${flags.join("")}
      </div>
      ${tagsHtml(team.tags, { max: 3 }) ? `<div class="tag-row mt8">${tagsHtml(team.tags, { max: 3 })}</div>` : ""}
      ${!compact ? `<div class="tc-species">${speciesChips(team.species, { max: 6 })}</div>` : ""}
      ${!compact && team.members?.length
        ? `<div class="tc-members">${team.members
            .slice(0, 5)
            .map((member) => `<span class="mem-chip">${esc(member.name || member.code)}×${member.count ?? 1}</span>`)
            .join("")}</div>`
        : ""}
      <div class="tc-foot">
        <span class="tc-stage">${showStage && stageLine ? `${icon("map", 11)} ${stageLine}` : ""}</span>
        <span class="tc-btns">
          <button class="btn btn-sm btn-ghost" type="button" data-team-detail="${team.id}">${icon("eye", 12)} 详情</button>
          <button class="btn btn-sm btn-primary" type="button" data-add-team="${team.id}">${icon("plus", 12)} 加入序列</button>
        </span>
      </div>
    </article>
  `;
}

/** 关卡行 */
export function stageRowHtml(stage, options = {}) {
  const { chapterMin = 0, chapterMax = 1 } = options;
  const span = Math.max(1, chapterMax - chapterMin);
  const width = Math.max(4, Math.min(100, ((stage.difficulty - chapterMin) / span) * 100));
  return `
    <button class="stage-row" type="button" data-stage-detail="${stage.id}">
      <span class="stage-code">${esc(stage.code || stage.id)}</span>
      <span class="stage-name">
        <b>${esc(stage.title || "未命名关卡")}</b>
        <span>mission #${esc(stage.id)}${stage.recommend_level ? ` · 推荐等级 ${stage.recommend_level}` : ""}</span>
      </span>
      <span class="diff-meter">
        <span class="diff-bar"><i style="--w:${width.toFixed(1)}%"></i></span>
        <span class="diff-val">难度 ${fmtNum(stage.difficulty)}</span>
      </span>
      <span class="stage-counts">
        <span><b>${stage.team_count ?? 0}</b> 支队伍</span>
        <span>${stage.species_count ?? 0} 个怪种</span>
      </span>
      <span class="stage-tags">${tagsHtml(stage.tags, { max: 3 })}</span>
      <span class="stage-row-arrow">${icon("chevronRight", 15)}</span>
    </button>
  `;
}

/** 怪种卡片 */
export function speciesCardHtml(item) {
  const fc = factionColor(item.faction);
  const tags = tagsHtml(item.tags, { max: 2 });
  return `
    <button class="species-card" type="button" data-species-detail="${item.codex_no}">
      <span class="sp-avatar" style="--fc:${fc}">${esc((item.name || "?").slice(0, 1))}</span>
      <span class="sp-main">
        <span class="sp-name-row">
          <span class="sp-name">${esc(item.name)}</span>
          <span class="sp-codex">#${String(item.codex_no).padStart(3, "0")}</span>
        </span>
        <span class="sp-meta">
          ${factionChip(item.faction)}
          <span class="sp-teams"><b>${fmtNum(item.team_count)}</b> 支队伍</span>
        </span>
        <span class="sp-tags">${tags}</span>
      </span>
      <span class="sp-arrow">${icon("chevronRight", 15)}</span>
    </button>
  `;
}

/** 迷你状态灯 + 文本 */
export function statusPill(state, text) {
  const cls = { ok: "ok", warn: "warn", err: "err", idle: "" }[state] || "";
  return `<span class="dot ${cls} ${state === "warn" || state === "ok" ? "pulse" : ""}"></span>${esc(text)}`;
}

/** 按钮 loading 态 */
export function setBusy(button, busy, busyText = "处理中…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>${esc(busyText)}`;
  } else {
    button.disabled = false;
    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
      delete button.dataset.originalHtml;
    }
  }
}

/** 通用页面头 */
export function pageHeadHtml({ crumbs = [], title = "", badge = "", sub = "", actions = "" } = {}) {
  const crumbHtml = crumbs
    .map((crumb, index) => {
      const isLast = index === crumbs.length - 1;
      const label = esc(crumb.label);
      if (isLast) return `<span class="cur">${label}</span>`;
      if (crumb.nav) return `<button type="button" data-nav="${esc(crumb.nav)}">${label}</button><span class="sep">/</span>`;
      return `<span>${label}</span><span class="sep">/</span>`;
    })
    .join("");
  return `
    <div class="page-head">
      <div class="page-head-main">
        ${crumbs.length ? `<div class="crumbs">${crumbHtml}</div>` : ""}
        <h1 class="page-title"><span class="pt-mark"></span>${esc(title)}${badge ? `<span class="pt-badge">${esc(badge)}</span>` : ""}</h1>
        ${sub ? `<div class="page-sub">${sub}</div>` : ""}
      </div>
      ${actions ? `<div class="page-actions">${actions}</div>` : ""}
    </div>
  `;
}

/** 分区标题 */
export function sectionHeadHtml(title, { hint = "", actions = "", iconName = "" } = {}) {
  return `
    <div class="section-head">
      <h2>${iconName ? icon(iconName, 14) : ""}${esc(title)}</h2>
      ${hint ? `<span class="hint">${esc(hint)}</span>` : ""}
      <span class="section-rule"></span>
      ${actions ? `<div class="head-actions">${actions}</div>` : ""}
    </div>
  `;
}

export function logLineHtml(log) {
  const level = (log.level || "info").toLowerCase();
  return `<div class="log-line ${level}">
    <span class="log-time">${fmtTime(log.t)}</span>
    <span class="log-level ${level}">${level.toUpperCase().slice(0, 5)}</span>
    <span class="log-text">${esc(log.text || "")}</span>
  </div>`;
}

/** 简单 debounce 绑定（供视图使用） */
export function escapeHtml(value) {
  return esc(value);
}
