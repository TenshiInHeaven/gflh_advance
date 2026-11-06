/* views/capture.js —— 登录抓取：开始抓取 / 设置代理并重启游戏 / 实时日志 / 凭证 / 当前靶机 */
import { api } from "../api.js";
import { store, refreshHealth, refreshCurrent, tryRefreshCurrent } from "../store.js";
import {
  icon,
  pageHeadHtml,
  sectionHeadHtml,
  skeletonRows,
  toast,
  toastOk,
  toastErr,
  confirmDialog,
  setBusy,
  emptyState,
  logLineHtml,
} from "../ui.js";
import { esc, fmtNum, fmtPower, fmtTime, fmtDuration, timeAgo, navigate } from "../util.js";

const STATE_LABEL = {
  idle: "空闲",
  starting: "启动中",
  running: "抓取中",
  stopped: "已停止",
  error: "错误",
};

const teamCache = new Map();
let rootEl = null;
let pollTimer = 0;
let captureStatus = null;
let currentData = null;
let credsData = null;
let targetFillToken = 0;

function cleanup() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = 0;
  }
}

export async function render(root) {
  rootEl = root;
  cleanup();
  captureStatus = null;
  currentData = null;
  credsData = null;
  targetFillToken += 1;

  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [{ label: "登录抓取" }],
      title: "登录抓取",
      badge: "CAPTURE",
      sub: "通过本地抓包代理获取当前登录的 uid / sign 与游戏内收藏标靶列表。抓包端口固定 18080，不要使用 8080。抓到后可以开始编排并执行注入。",
      actions: `
        <button class="btn btn-ghost" type="button" data-act="refresh">${icon("refresh", 14)} 刷新状态</button>
        <button class="btn btn-cyan" type="button" data-act="start">${icon("key", 14)} 开始抓取</button>
        <button class="btn btn-danger" type="button" data-act="stop">${icon("power", 14)} 完成并关闭代理</button>
      `,
    })}
    <div class="capture-cols">
      <div>
        <div class="capture-panel" data-capture-panel>
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
            <span class="cap-state" data-cap-state><span class="dot"></span><span data-cap-state-text>读取中…</span></span>
            <span class="mono-inline text-mute" style="font-size:10.5px">PORT <b data-cap-port>18080</b> · 代理固定 18080</span>
            <span style="flex:1"></span>
            <span class="badge mono" data-cap-elapsed>—</span>
          </div>
          <div class="capture-status-grid">
            <div class="cap-stat"><div class="cs-label">${icon("users", 10)} UID</div><div class="cs-value" data-cap-uid>—</div></div>
            <div class="cap-stat"><div class="cs-label">${icon("lock", 10)} SIGN</div><div class="cs-value" data-cap-sign>—</div></div>
            <div class="cap-stat"><div class="cs-label">${icon("target", 10)} 已抓靶机</div><div class="cs-value" data-cap-targets>—</div></div>
            <div class="cap-stat"><div class="cs-label">${icon("wifi", 10)} 系统代理</div><div class="cs-value" data-cap-proxy>—</div></div>
          </div>
          <div class="wizard-steps" data-wizard>
            <div class="wizard-step" data-step="1">
              <span class="ws-num">1</span>
              <div class="ws-body">
                <div class="ws-title">开始抓取 <span class="badge mono">POST /api/capture/start</span></div>
                <div class="ws-desc">启动本地抓包代理并监听 18080 端口。</div>
                <div class="ws-action"><button class="btn btn-primary btn-sm" type="button" data-act="start">${icon("play", 12)} 开始抓取</button></div>
              </div>
            </div>
            <div class="wizard-step" data-step="2">
              <span class="ws-num">2</span>
              <div class="ws-body">
                <div class="ws-title">设置代理并重启游戏</div>
                <div class="ws-desc">让系统代理指向 127.0.0.1:18080，然后强杀并重启游戏。</div>
                <div class="ws-action"><button class="btn btn-cyan btn-sm" type="button" data-act="restart-game">${icon("refresh", 12)} 设置代理并重启游戏</button></div>
                <div class="ws-note">${icon("info", 11)} 会强杀游戏进程，请先回到安全界面；本操作需要二次确认。</div>
              </div>
            </div>
            <div class="wizard-step" data-step="3">
              <span class="ws-num">3</span>
              <div class="ws-body">
                <div class="ws-title">在游戏里登录到主界面</div>
                <div class="ws-desc">正常登录游戏，停留在主界面即可；抓包代理会自动截取 index/index。</div>
              </div>
            </div>
            <div class="wizard-step" data-step="4">
              <span class="ws-num">4</span>
              <div class="ws-body">
                <div class="ws-title">等待抓取 uid / sign / 当前靶机</div>
                <div class="ws-desc">右侧日志会实时显示抓取进度；成功后会看到 uid、sign 与靶机数量。</div>
              </div>
            </div>
            <div class="wizard-step" data-step="5">
              <span class="ws-num">5</span>
              <div class="ws-body">
                <div class="ws-title">完成并关闭代理</div>
                <div class="ws-desc">写盘 creds_latest.json 并恢复系统代理，避免游戏断网。</div>
                <div class="ws-action"><button class="btn btn-danger btn-sm" type="button" data-act="stop">${icon("power", 12)} 完成并关闭代理</button></div>
              </div>
            </div>
            <div class="wizard-step" data-step="6">
              <span class="ws-num">6</span>
              <div class="ws-body">
                <div class="ws-title">去编排与执行</div>
                <div class="ws-desc">凭证就绪后，去关卡图鉴挑队伍，然后执行注入。</div>
                <div class="ws-action"><button class="btn btn-ghost btn-sm" type="button" data-nav="/chapters">${icon("map", 12)} 去关卡图鉴</button></div>
              </div>
            </div>
          </div>
          <div class="cap-actions">
            <button class="btn" type="button" data-act="refresh">${icon("refresh", 13)} 刷新状态</button>
          </div>
          <div class="cap-hint" data-cap-hint>${icon("info", 12)} 提示：抓取期间游戏可能提示网络异常，属正常现象；抓完「完成并关闭代理」即可恢复。</div>
        </div>

        <div class="capture-panel mt16">
          ${sectionHeadHtml("可用凭证", { hint: "点击加载会复制为 creds_latest.json", iconName: "database" })}
          <div class="creds-list" data-creds-list>${skeletonRows(3)}</div>
          <div class="mt12" style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" type="button" data-act="load-creds" disabled>${icon("upload", 12)} 加载选中凭证</button>
            <span class="text-mute" style="font-size:10.5px;align-self:center" data-cred-hint>先选择一条凭证</span>
          </div>
        </div>
      </div>

      <div>
        <div class="terminal">
          <div class="terminal-head">
            <span class="dots"><i></i><i></i><i></i></span>
            <span>CAPTURE STREAM · 127.0.0.1:18080</span>
            <span class="th-right"><span class="dot" data-term-dot></span><span data-term-state>等待开始</span></span>
          </div>
          <div class="terminal-body" data-cap-logs>
            <div class="log-idle">
              <div class="li-prompt">$</div>
              <div class="li-body">
                <div class="li-title">等待开始抓取<span class="cursor-blink" style="margin-left:6px"></span></div>
                <div class="li-line"># 本地抓包代理 · 127.0.0.1:18080（固定端口，勿用 8080）</div>
                <div class="li-line"># 步骤：开始抓取 → 设置代理并重启游戏 → 在游戏里登录到主界面</div>
                <div class="li-line"># 抓到 uid / sign / 当前靶机后，点「完成并关闭代理」写盘</div>
              </div>
            </div>
          </div>
          <div class="terminal-foot">
            <span class="cursor-blink"></span>
            <span>日志每 1.5s 刷新 · 最多保留 200 条</span>
            <span style="flex:1"></span>
            <span data-term-time>—</span>
          </div>
        </div>

        <div class="capture-panel mt16">
          ${sectionHeadHtml("当前靶机", { hint: "来自最新凭证 / 本地状态", iconName: "target", actions: `<span class="badge mono" data-current-count>—</span>` })}
          <div data-current-targets>${skeletonRows(3)}</div>
        </div>
      </div>
    </div>
  `;

  bindShellEvents(root);
  await Promise.allSettled([refreshStatus(), loadCreds(), loadCurrent()]);

  pollTimer = setInterval(() => {
    if (!rootEl || !rootEl.isConnected) {
      cleanup();
      return;
    }
    refreshStatus({ silent: true });
  }, 1500);
  store.registerCleanup(cleanup);
}

function bindShellEvents(root) {
  root.querySelectorAll('[data-act="refresh"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      setBusy(target, true, "刷新中…");
      try {
        await Promise.allSettled([refreshStatus(), loadCreds(), loadCurrent(), refreshHealth()]);
      } finally {
        setBusy(target, false);
      }
    }),
  );
  root.querySelectorAll('[data-act="start"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      setBusy(target, true, "启动中…");
      try {
        const status = await api.captureStart({ port: 18080, set_proxy: true, auto_restore_proxy: true });
        applyStatus(status);
        toastOk("抓包代理已启动", "下一步：设置代理并重启游戏，然后登录到主界面。");
      } catch (err) {
        toastErr("启动失败", err.message + (err.hint ? `（${err.hint}）` : ""));
      } finally {
        setBusy(target, false);
      }
    }),
  );
  root.querySelectorAll('[data-act="restart-game"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const ok = await confirmDialog({
        title: "设置代理并重启游戏",
        message: "将把系统代理指向 127.0.0.1:18080，强杀游戏进程并重新启动。",
        detail: "请先确认游戏已回到安全界面（不要停留在战斗 / 编队中）。抓取结束后记得「完成并关闭代理」恢复系统代理。",
        confirmText: "强杀并重启",
        danger: true,
      });
      if (!ok) return;
      setBusy(target, true, "处理中…");
      try {
        const result = await api.captureRestartGame();
        toastOk(
          "已设置代理并重启游戏",
          (result.steps || []).join(" → ") || result.hint || "请在游戏里重新登录到主界面",
        );
        await refreshStatus();
      } catch (err) {
        toastErr("操作失败", err.message + (err.hint ? `（${err.hint}）` : ""));
      } finally {
        setBusy(target, false);
      }
    }),
  );
  root.querySelectorAll('[data-act="stop"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const ok = await confirmDialog({
        title: "完成并关闭代理",
        message: "将停止抓包代理、恢复系统代理，并把凭证写入 creds_latest.json。",
        confirmText: "完成并关闭",
      });
      if (!ok) return;
      setBusy(target, true, "关闭中…");
      try {
        const status = await api.captureStop();
        applyStatus(status);
        toastOk("抓取完成", "代理已关闭，凭证已写入。下一步可以编排序列并执行注入。");
        await Promise.allSettled([loadCurrent(), loadCreds()]);
      } catch (err) {
        toastErr("关闭失败", err.message);
      } finally {
        setBusy(target, false);
      }
    }),
  );
  root.querySelector('[data-act="load-creds"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const selected = root.querySelector(".cred-item.active");
    if (!selected) {
      toastErr("请先选择凭证", "在列表中点选一条凭证后再加载。");
      return;
    }
    const name = selected.dataset.credName;
    setBusy(button, true, "加载中…");
    try {
      const result = await api.loadCreds(name);
      toastOk(`已加载 ${name}`, "creds_latest.json 已更新，当前靶机列表同步刷新。");
      if (result.current) currentData = result.current;
      renderCreds();
      await loadCurrent();
    } catch (err) {
      toastErr("加载失败", err.message);
    } finally {
      setBusy(button, false);
    }
  });
}

/* ------------------------------------------------------------------ */
/* capture 状态                                                       */
/* ------------------------------------------------------------------ */
async function refreshStatus({ silent = false } = {}) {
  try {
    const status = await api.captureStatus();
    applyStatus(status);
  } catch (err) {
    if (!silent) toastErr("状态读取失败", err.message);
  }
}

function applyStatus(status) {
  if (!rootEl || !rootEl.isConnected || !status) return;
  captureStatus = status;
  const state = status.state || "idle";
  const chip = rootEl.querySelector("[data-cap-state]");
  if (chip) {
    chip.className = `cap-state ${state === "running" || state === "starting" ? state : state === "error" ? "error" : ""}`;
    chip.innerHTML = `<span class="dot ${state === "running" ? "ok pulse" : state === "starting" ? "warn pulse" : state === "error" ? "err" : ""}"></span><span data-cap-state-text>${STATE_LABEL[state] || state}</span>`;
  }
  const setText = (selector, text, cls) => {
    const node = rootEl.querySelector(selector);
    if (!node) return;
    node.textContent = text;
    if (cls !== undefined) node.className = `cs-value ${cls}`;
  };
  setText("[data-cap-uid]", status.uid || "未抓到", status.uid ? "ok" : "idle");
  setText("[data-cap-sign]", status.sign_set ? "已就绪" : "未就绪", status.sign_set ? "ok" : "idle");
  setText("[data-cap-targets]", status.targets_count ? `${status.targets_count} 个` : "0 个", status.targets_count ? "ok" : "idle");
  setText("[data-cap-proxy]", status.proxy_active ? "127.0.0.1:18080" : "未开启", status.proxy_active ? "warn" : "idle");
  const elapsedEl = rootEl.querySelector("[data-cap-elapsed]");
  if (elapsedEl) elapsedEl.textContent = `ELAPSED ${fmtDuration(status.elapsed_s)}`;
  const portEl = rootEl.querySelector("[data-cap-port]");
  if (portEl) portEl.textContent = String(status.port || 18080);

  // 向导步骤状态
  const captured = Boolean(status.uid && status.sign_set);
  const stepsDone = {
    1: state === "running" || captured || state === "stopped",
    2: Boolean(status.uid) || state === "stopped",
    3: Boolean(status.login_captured),
    4: Boolean(status.targets_captured),
    5: state === "stopped" || (!status.proxy_active && captured),
    6: state === "stopped" || (!status.proxy_active && captured),
  };
  const activeStep = !state || state === "idle" ? 1 : !status.proxy_active ? 5 : !captured ? 2 : !status.targets_captured ? 4 : 5;
  rootEl.querySelectorAll("[data-step]").forEach((el) => {
    const step = Number(el.dataset.step);
    el.classList.toggle("done", Boolean(stepsDone[step]) && step < activeStep);
    el.classList.toggle("active", step === activeStep);
  });

  // 按钮可用性
  const startBtns = rootEl.querySelectorAll('[data-act="start"]');
  startBtns.forEach((button) => {
    button.disabled = state === "running" || state === "starting";
  });
  const restartBtns = rootEl.querySelectorAll('[data-act="restart-game"]');
  restartBtns.forEach((button) => {
    button.disabled = !(state === "running" || state === "starting");
  });
  const stopBtns = rootEl.querySelectorAll('[data-act="stop"]');
  stopBtns.forEach((button) => {
    button.disabled = !(state === "running" || state === "starting");
  });
  const hintEl = rootEl.querySelector("[data-cap-hint]");
  if (hintEl) {
    if (state === "running" && !status.uid) {
      hintEl.innerHTML = `${icon("info", 12)} 抓包代理运行中。请点「设置代理并重启游戏」，然后在游戏里正常登录到主界面。`;
    } else if (state === "running" && status.uid && !status.targets_captured) {
      hintEl.innerHTML = `${icon("info", 12)} 已抓到 uid=${esc(status.uid)}，正在读取收藏标靶列表…`;
    } else if (status.targets_captured && state !== "stopped") {
      hintEl.innerHTML = `${icon("check", 12)} 抓取完成：uid=${esc(status.uid)} · 靶机 ${status.targets_count} 条。点「完成并关闭代理」已写入凭证。`;
    } else if (state === "stopped") {
      hintEl.innerHTML = `${icon("check", 12)} 抓取已完成、代理已关闭。可以去关卡图鉴挑队伍，或到序列页执行注入。`;
    } else {
      hintEl.innerHTML = `${icon("info", 12)} 提示：抓取期间游戏可能提示网络异常，属正常现象；抓完「完成并关闭代理」即可恢复。`;
    }
  }

  // terminal
  const termDot = rootEl.querySelector("[data-term-dot]");
  if (termDot) {
    termDot.className = `dot ${state === "running" ? "ok pulse" : state === "error" ? "err" : state === "starting" ? "warn pulse" : ""}`;
  }
  const termState = rootEl.querySelector("[data-term-state]");
  if (termState) termState.textContent = STATE_LABEL[state] || state;
  const termTime = rootEl.querySelector("[data-term-time]");
  if (termTime) termTime.textContent = status.started_at ? `START ${fmtTime(status.started_at)}` : "IDLE";
  const logsEl = rootEl.querySelector("[data-cap-logs]");
  if (logsEl) {
    const logs = status.logs || [];
    if (logs.length) {
      const wasBottom = logsEl.scrollHeight - logsEl.scrollTop - logsEl.clientHeight < 40;
      logsEl.innerHTML = logs.map((log) => logLineHtml(log)).join("");
      if (wasBottom) logsEl.scrollTop = logsEl.scrollHeight;
    }
  }
}

/* ------------------------------------------------------------------ */
/* 凭证 / 当前靶机                                                     */
/* ------------------------------------------------------------------ */
async function loadCreds() {
  try {
    const data = await api.creds();
    credsData = data.creds || [];
    renderCreds();
  } catch (err) {
    const listEl = rootEl?.querySelector("[data-creds-list]");
    if (listEl) {
      listEl.innerHTML = `<div class="plan-empty" style="padding:16px">凭证列表读取失败：${esc(err.message)}</div>`;
    }
  }
}

function renderCreds() {
  const listEl = rootEl?.querySelector("[data-creds-list]");
  if (!listEl) return;
  const creds = credsData || [];
  if (!creds.length) {
    listEl.innerHTML = `<div class="plan-empty" style="padding:16px">暂无凭证文件，先完成一次登录抓取。</div>`;
    const loadBtn = rootEl.querySelector('[data-act="load-creds"]');
    if (loadBtn) loadBtn.disabled = true;
    return;
  }
  listEl.innerHTML = creds
    .map(
      (cred) => `
      <button class="cred-item" type="button" data-cred-name="${esc(cred.name)}">
        <span class="cred-radio"></span>
        <span class="cred-main">
          <span class="cred-name">${esc(cred.name)}</span>
          <span class="cred-sub">
            <span>uid ${esc(cred.uid || "—")}</span>
            <span>${cred.targets_count ?? 0} 个靶机</span>
            <span>${esc(cred.updated_at ? timeAgo(cred.updated_at) : "—")}</span>
          </span>
        </span>
        <span class="badge ${cred.name === "creds_latest.json" ? "green" : ""}">${cred.name === "creds_latest.json" ? "最新" : "历史"}</span>
      </button>`,
    )
    .join("");
  listEl.addEventListener("click", (event) => {
    const item = event.target.closest("[data-cred-name]");
    if (!item) return;
    listEl.querySelectorAll(".cred-item").forEach((node) => node.classList.remove("active"));
    item.classList.add("active");
    const loadBtn = rootEl.querySelector('[data-act="load-creds"]');
    if (loadBtn) loadBtn.disabled = false;
    const hint = rootEl.querySelector("[data-cred-hint]");
    if (hint) hint.textContent = `已选择 ${item.dataset.credName}`;
  });
}

async function loadCurrent() {
  const areaEl = rootEl?.querySelector("[data-current-targets]");
  if (!areaEl) return;
  try {
    const data = await refreshCurrent("auto");
    currentData = data;
    renderCurrent();
  } catch (err) {
    // 未抓取时接口可能 503/400，展示引导
    currentData = null;
    areaEl.innerHTML = emptyState({
      iconName: "target",
      title: "还没有当前靶机",
      desc: "完成登录抓取后，这里会显示游戏内现有收藏标靶的编号与队伍。",
      actionText: "开始抓取",
      actionId: "cap-empty-start",
    });
    areaEl.querySelector("#cap-empty-start")?.addEventListener("click", () => {
      rootEl?.querySelector('[data-act="start"]')?.click();
    });
    const countEl = rootEl?.querySelector("[data-current-count]");
    if (countEl) countEl.textContent = "—";
  }
}

function renderCurrent() {
  const areaEl = rootEl?.querySelector("[data-current-targets]");
  if (!areaEl) return;
  const targets = currentData?.targets || [];
  const countEl = rootEl?.querySelector("[data-current-count]");
  if (countEl) countEl.textContent = `${targets.length} / 35`;
  if (!targets.length) {
    areaEl.innerHTML = emptyState({
      iconName: "target",
      title: "当前靶机列表为空",
      desc: "抓取成功但游戏内没有收藏标靶，可以直接编排序列后使用「追加」模式。",
    });
    return;
  }
  const duplicates = currentData?.duplicate_orders || {};
  areaEl.innerHTML = `
    ${
      Object.keys(duplicates).length
        ? `<div class="warn-box" style="margin-bottom:10px"><b>${icon("alert", 11)} 发现重复编号</b>${Object.entries(duplicates)
            .slice(0, 6)
            .map(([order, teams]) => `编号 ${esc(order)}：team ${esc((teams || []).join(", "))}`)
            .join("；")}。建议用「清空重排」修复。</div>`
        : ""
    }
    <div class="targets-grid">
      ${targets
        .map(
          (item) => `
        <div class="target-item ${duplicates[item.order] ? "dup" : ""}" data-current-team="${item.team}">
          <span class="target-order">${esc(item.order)}</span>
          <span class="target-team">team ${esc(item.team)}</span>
          <span class="target-extra" data-team-extra="${item.team}">…</span>
        </div>`,
        )
        .join("")}
    </div>
    <div class="param-note" style="margin-top:10px">
      uid ${esc(currentData?.uid || "—")} · 来源 ${esc(currentData?.source || "—")}
      ${currentData?.captured_at ? ` · 抓取于 ${esc(fmtTime(currentData.captured_at, true))}` : ""}
      · 上限 ${currentData?.max_targets || 35}
    </div>
  `;
  fillTargetExtras(targets.map((item) => item.team));
}

async function fillTargetExtras(teamIds) {
  const token = ++targetFillToken;
  const queue = [...new Set(teamIds)];
  const worker = async () => {
    while (queue.length) {
      const teamId = queue.shift();
      if (token !== targetFillToken) return;
      let team = teamCache.get(teamId);
      if (!team) {
        try {
          team = await api.team(teamId);
          teamCache.set(teamId, team);
        } catch {
          team = null;
        }
      }
      if (token !== targetFillToken || !rootEl?.isConnected) return;
      const el = rootEl.querySelector(`[data-team-extra="${teamId}"]`);
      if (el) {
        if (team) {
          const species = (team.species || []).slice(0, 1).map((item) => item.name).join("");
          const powerText = fmtPower(team.power);
          el.textContent = `${powerText}${species ? ` · ${species}` : ""}`;
          el.title = `${Number(team.power) > 0 ? `效能 ${fmtNum(team.power)}` : "未标注效能"} · ${team.units} 单位${species ? ` · ${species}` : ""}`;
        } else {
          el.textContent = "不可收藏";
          el.style.color = "var(--red)";
        }
      }
      el?.closest("[data-current-team]")?.addEventListener("click", () => {
        window.location.hash = `#/teams/${teamId}`;
      });
    }
  };
  await Promise.all(Array.from({ length: 5 }, worker));
}
