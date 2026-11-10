/* components/game-setup.js —— 首次启动游戏客户端目录 gate + 设置修改卡片（本地数据，不上传） */
import { api } from "../api.js";
import { icon, toastErr, toastOk, setBusy } from "../ui.js";
import { esc } from "../util.js";

const SOURCE_LABELS = {
  settings: "设置",
  env: "环境变量",
  environment: "环境变量",
  local_paths: "本地配置 local_paths",
  local: "本地配置 local_paths",
  detected: "自动检测",
  running: "运行进程",
  process: "运行进程",
  steam: "Steam 库",
  registry: "注册表/Steam",
  default: "默认路径",
  mock: "Mock",
};

const MISSING_LABELS = [
  [/stc/i, "不是有效客户端目录（缺少 *_Data/StreamingAssets/Res/Pc/stc）"],
  [/GrilsFrontLine\.exe|grilsfrontline/i, "未找到 GrilsFrontLine.exe"],
  [/不存在|not found|no such|missing dir/i, "目录不存在"],
];

export function sourceLabel(source) {
  const key = String(source || "").trim().toLowerCase();
  return SOURCE_LABELS[key] || (source ? String(source) : "未配置");
}

/** 把后端 missing[]/error 翻成明确中文；无法识别时保留原文 */
export function missingText(missing) {
  if (!missing) return "";
  const list = Array.isArray(missing) ? missing : [missing];
  const texts = list
    .map((item) => {
      const raw = typeof item === "string" ? item : item?.error || item?.message || item?.detail || "";
      if (!raw) return "";
      const hit = MISSING_LABELS.find(([pattern]) => pattern.test(raw));
      return hit ? hit[1] : String(raw);
    })
    .filter(Boolean);
  return [...new Set(texts)].join("；");
}

/** 后端错误 → 明确提示文案（目录不存在/未找到 exe/缺少 stc/取消/检测失败） */
export function gameErrorMessage(err, fallback = "游戏客户端目录无效，请重新选择。") {
  const payload = err?.payload || {};
  const raw =
    payload.error ||
    payload.message ||
    payload.detail ||
    (typeof err === "string" ? err : "") ||
    err?.message ||
    "";
  const fromMissing = missingText(payload.missing);
  const fromRaw = missingText(raw);
  const text = [fromRaw || fromMissing || raw || fallback].filter(Boolean).join("；");
  return text;
}

export function normalizeGameStatus(raw) {
  const data = raw && typeof raw === "object" ? raw : {};
  const missing = Array.isArray(data.missing) ? data.missing : data.missing ? [data.missing] : [];
  return {
    configured: Boolean(data.configured),
    path: String(data.path || "").trim(),
    source: String(data.source || "").trim(),
    exists: data.exists !== false,
    valid: Boolean(data.valid),
    missing,
    game_running: Boolean(data.game_running),
    process_path: String(data.process_path || "").trim(),
    detected: data.detected || null,
    catalog_ready: data.catalog_ready !== false,
    needs_setup: Boolean(data.needs_setup) || Boolean(data.valid) === false,
  };
}

/** 读取游戏客户端状态；旧后端没有接口时返回 null（降级不阻塞 app） */
export async function fetchGameStatus() {
  try {
    return normalizeGameStatus(await api.gameStatus());
  } catch (err) {
    if (err?.status === 404) return null;
    throw err;
  }
}

export function statusBadge(status) {
  if (!status) return `<span class="badge mono">未配置</span>`;
  if (status.valid) {
    return status.game_running
      ? `<span class="badge cyan">${icon("check", 9)} 已找到 · 客户端运行中</span>`
      : `<span class="badge cyan">${icon("check", 9)} 已找到 · 客户端未运行</span>`;
  }
  if (status.configured || status.path) return `<span class="badge amber">${icon("alert", 9)} 目录无效</span>`;
  return `<span class="badge mono">未配置</span>`;
}

export function gameClientCardHtml(status, { error = "" } = {}) {
  if (!status) {
    return `<section class="capture-panel game-client-card" data-game-client-card>
      <div class="gc-head">${icon("gamepad", 13)}<span class="gc-title">游戏客户端</span><span class="badge mono">接口未就绪</span></div>
      <div class="gc-hint">当前后端未提供 /api/game/status（v1.9 升级后可用）。模板目录 / 数据构建仍按默认配置运行。</div>
    </section>`;
  }
  const source = sourceLabel(status.source);
  const path = status.path || status.detected?.path || "";
  const missing = missingText(status.missing);
  return `<section class="capture-panel game-client-card" data-game-client-card>
    <div class="gc-head">
      ${icon("gamepad", 13)}
      <span class="gc-title">游戏客户端</span>
      ${statusBadge(status)}
      <span class="badge mono" title="路径来源">${esc(source)}</span>
      <span style="flex:1"></span>
      <span class="gc-running ${status.game_running ? "on" : ""}">${icon("users", 10)} 进程：${status.game_running ? "运行中" : "未运行"}</span>
    </div>
    <div class="gc-path"><code data-game-path-current>${esc(path || "未配置")}</code></div>
    <div class="gc-meta">
      <span>来源：<b>${esc(source)}</b></span>
      <span>目录：<b>${status.exists ? "存在" : "不存在"}</b></span>
      ${status.process_path ? `<span>进程路径：<code>${esc(status.process_path)}</code></span>` : ""}
    </div>
    ${missing ? `<div class="gc-error" data-game-card-error>${icon("alert", 12)} ${esc(missing)}</div>` : ""}
    <div class="gc-edit">
      <input type="text" class="gc-input" data-game-path-input value="${esc(path)}" placeholder="客户端目录，例如 D:\\Games\\GirlsFrontline" spellcheck="false" />
      <button class="btn btn-sm btn-ghost" type="button" data-game-detect>${icon("search", 12)} 自动检测</button>
      <button class="btn btn-sm btn-ghost" type="button" data-game-pick>${icon("box", 12)} 浏览…</button>
      <button class="btn btn-sm btn-cyan" type="button" data-game-apply>${icon("refresh", 12)} 应用并重建数据</button>
    </div>
    <div class="gc-hint">只用于读取本机游戏数据 / 注入收藏标靶，不会上传；修改路径后会重新构建数据索引。</div>
    <div class="gc-error hidden" data-game-error></div>
  </section>`;
}

function candidateHtml(candidate, index) {
  const path = String(candidate?.path || "").trim();
  const source = sourceLabel(candidate?.source);
  const valid = candidate?.valid !== false;
  return `<button class="sg-candidate ${valid ? "" : "invalid"}" type="button" data-candidate-path="${esc(path)}">
    <span class="sg-cand-path">${esc(path || "（空路径）")}</span>
    <span class="sg-cand-meta">${esc(source)}</span>
    <span class="badge ${valid ? "cyan" : "amber"} mono">${valid ? "有效" : "无效"}</span>
  </button>`;
}

/* ================================================================== */
/* 首次启动 setup gate（覆盖全屏、不可关闭）                           */
/* ================================================================== */
let gateEl = null;
let gateStatus = null;
let gateOnReady = null;

export function showGameSetupGate({ status, onReady }) {
  if (gateEl) return;
  gateStatus = status || null;
  gateOnReady = onReady || null;
  const missing = missingText(status?.missing);
  gateEl = document.createElement("div");
  gateEl.className = "setup-gate";
  gateEl.setAttribute("role", "dialog");
  gateEl.setAttribute("aria-modal", "true");
  gateEl.setAttribute("aria-labelledby", "setup-gate-title");
  gateEl.innerHTML = `
    <div class="sg-panel">
      <div class="sg-eyebrow">TARGET FORGE // FIRST RUN SETUP</div>
      <h1 id="setup-gate-title">先选择游戏客户端</h1>
      <p class="sg-desc">首次使用需要指定《少女前线》客户端目录，用于<b>读取本机游戏数据 / 注入收藏标靶</b>。所有处理都在本机完成，不会上传任何数据。</p>
      <div class="sg-current">
        <span>当前状态：</span>
        ${statusBadge(status)}
        ${status?.game_running ? `<span class="badge mono">进程运行中</span>` : `<span class="badge mono">进程未运行</span>`}
        ${status?.path ? `<span class="sg-current-path"><code>${esc(status.path)}</code></span>` : ""}
      </div>
      ${missing ? `<div class="sg-error" data-gate-status-error>${icon("alert", 13)} ${esc(missing)}</div>` : ""}
      <label class="sg-label" for="setup-gate-path">客户端目录</label>
      <div class="sg-input-row">
        <input id="setup-gate-path" type="text" class="sg-input" data-game-path value="${esc(status?.path || "")}" placeholder="例如 D:\\Games\\GirlsFrontline" spellcheck="false" autocomplete="off" />
        <button class="btn btn-ghost" type="button" data-gate-pick>${icon("box", 13)} 浏览文件夹…</button>
      </div>
      <div class="sg-actions">
        <button class="btn btn-ghost" type="button" data-gate-detect>${icon("search", 13)} 自动检测</button>
        <button class="btn btn-primary" type="button" data-gate-confirm>${icon("check", 13)} 确认并继续</button>
      </div>
      <div class="sg-candidates" data-gate-candidates></div>
      <div class="sg-error hidden" data-gate-error></div>
      <div class="sg-hint">客户端目录应包含 <code>GrilsFrontLine.exe</code> 与 <code>*_Data/StreamingAssets/Res/Pc/stc</code>；也可以手动粘贴完整路径。</div>
      <div class="sg-rebuild hidden" data-gate-rebuild><span class="spinner"></span> 正在读取游戏数据并构建索引，请稍候…</div>
    </div>`;
  document.body.appendChild(gateEl);
  document.body.classList.add("setup-gate-open");
  bindGateEvents();
  if (status?.detected?.path) {
    const input = gateEl.querySelector("[data-game-path]");
    if (input && !input.value) input.value = status.detected.path;
  }
  autoDetectCandidates();
}

function gateQuery(selector) {
  return gateEl ? gateEl.querySelector(selector) : null;
}

function setGateError(message) {
  const el = gateQuery("[data-gate-error]");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `${icon("alert", 13)} ${esc(message)}`;
  el.classList.remove("hidden");
}

function setRebuilding(active, text = "") {
  const el = gateQuery("[data-gate-rebuild]");
  if (!el) return;
  el.classList.toggle("hidden", !active);
  if (text) el.innerHTML = `<span class="spinner"></span> ${esc(text)}`;
}

async function autoDetectCandidates() {
  const listEl = gateQuery("[data-gate-candidates]");
  if (listEl) listEl.innerHTML = `<div class="sg-cand-loading"><span class="spinner"></span> 正在自动检测客户端…</div>`;
  try {
    const data = await api.gameDetect();
    const candidates = Array.isArray(data.candidates) ? data.candidates : [];
    const detected = data.detected && (data.detected.path || typeof data.detected === "string") ? data.detected : null;
    const detectedPath = typeof detected === "string" ? detected : detected?.path || candidates.find((c) => c.valid)?.path || "";
    if (detectedPath) {
      const input = gateQuery("[data-game-path]");
      if (input && !input.value.trim()) input.value = detectedPath;
    }
    if (listEl) {
      listEl.innerHTML = candidates.length
        ? `<div class="sg-cand-title">自动检测候选 · 点击填入</div>${candidates.map(candidateHtml).join("")}`
        : `<div class="sg-cand-empty">未自动检测到客户端，请点「浏览文件夹…」手动选择或手动输入路径。</div>`;
      listEl.querySelectorAll("[data-candidate-path]").forEach((button) => {
        button.addEventListener("click", () => {
          const input = gateQuery("[data-game-path]");
          if (input) input.value = button.dataset.candidatePath || "";
          setGateError("");
        });
      });
    }
  } catch (err) {
    if (listEl) listEl.innerHTML = `<div class="sg-cand-empty">自动检测失败：${esc(gameErrorMessage(err, "检测接口不可用"))}</div>`;
  }
}

function bindGateEvents() {
  if (!gateEl) return;
  gateQuery("[data-gate-detect]")?.addEventListener("click", (event) => {
    if (event.currentTarget.classList.contains("is-busy")) return;
    autoDetectCandidates();
    toastOk("已重新自动检测");
  });
  gateQuery("[data-gate-pick]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "打开选择框…");
    try {
      const data = await api.gamePick();
      const path = String(data.path || "").trim();
      if (!path) throw new Error("未返回文件夹路径");
      const input = gateQuery("[data-game-path]");
      if (input) input.value = path;
      setGateError("");
      toastOk("已选择文件夹，请确认并继续");
    } catch (err) {
      const msg = /取消|cancel/i.test(gameErrorMessage(err, "")) ? "已取消选择文件夹" : gameErrorMessage(err, "无法打开文件夹选择框");
      setGateError(msg);
      toastErr("浏览文件夹失败", msg);
    } finally {
      setBusy(button, false);
    }
  });
  gateQuery("[data-gate-confirm]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const input = gateQuery("[data-game-path]");
    const path = String(input?.value || "").trim();
    if (!path) {
      setGateError("请输入游戏客户端目录，或点击「浏览文件夹…」选择。");
      toastErr("请选择客户端目录", "还没有填写路径。");
      input?.focus();
      return;
    }
    setGateError("");
    setBusy(button, true, "校验中…");
    try {
      const data = await api.gameConfirm(path);
      const status = normalizeGameStatus(data.status || data);
      if (status.valid === false && status.missing?.length) {
        throw Object.assign(new Error(missingText(status.missing)), { payload: { missing: status.missing } });
      }
      setRebuilding(true, "正在读取游戏数据并构建索引，请稍候…");
      // catalog 未就绪时触发重建；失败不阻塞（后续健康轮询会继续）
      if (!status.catalog_ready) {
        try {
          await api.catalogRefresh();
        } catch {
          /* 由健康轮询兜底 */
        }
        await waitForCatalogReady(120000, (state) => {
          if (state === "building") setRebuilding(true, `正在构建数据索引（${state}）…`);
        });
      }
      setRebuilding(false);
      hideGameSetupGate();
      toastOk("游戏客户端已设置", "正在进入靶机工坊…");
      gateOnReady?.();
    } catch (err) {
      const msg = gameErrorMessage(err);
      setGateError(msg);
      toastErr("客户端目录无效", msg);
    } finally {
      setBusy(button, false);
    }
  });
  // gate 不可关闭：拦截 Escape
  gateEl.addEventListener("keydown", (event) => {
    if (event.key === "Escape") event.preventDefault();
  });
}

export function hideGameSetupGate() {
  if (!gateEl) return;
  gateEl.remove();
  gateEl = null;
  document.body.classList.remove("setup-gate-open");
}

/** 轮询 /api/health 直到 catalog ready（或超时） */
export async function waitForCatalogReady(timeoutMs = 120000, onTick = null) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const health = await api.health();
      const state = health?.catalog?.state || "";
      onTick?.(state);
      if (state === "ready") return true;
      if (state === "error") return false;
    } catch {
      /* 轮询期间后端可能重启，继续等 */
    }
    await new Promise((resolve) => setTimeout(resolve, 1800));
  }
  return false;
}

/* 供设置卡片复用的轻量操作 */
export async function detectGameClient() {
  return api.gameDetect();
}
export async function pickGameClient() {
  return api.gamePick();
}
export async function confirmGameClient(path) {
  const data = await api.gameConfirm(path);
  return normalizeGameStatus(data.status || data);
}
export async function refreshCatalogForGame() {
  try {
    await api.catalogRefresh();
  } catch {
    /* 健康轮询兜底 */
  }
  return waitForCatalogReady(120000);
}
