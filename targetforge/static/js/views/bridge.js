/* views/bridge.js —— 本地靶机桥接（实验） */
import { api } from "../api.js";
import { store } from "../store.js";
import {
  icon,
  pageHeadHtml,
  toastErr,
  toastOk,
  setBusy,
} from "../ui.js";
import { esc } from "../util.js";

const state = {
  status: null,
  targets: "",
  mode: "inject",
  timer: null,
  busy: false,
};

function targetsText(status) {
  return (status?.targets || []).join(", ");
}

function statusPill(status) {
  const value = status?.state || "idle";
  const label = value === "running" ? "桥接运行中" : value === "stale" ? "有残留进程" : "未运行";
  const cls = value === "running" ? "green" : value === "stale" ? "warn" : "";
  return `<span class="badge ${cls}">${label}</span>`;
}

function renderBody(root) {
  const status = state.status || {};
  const log = status.log || "还没有桥接日志。";
  root.innerHTML = `
    <div class="bridge-warning">
      <span class="help-dot" title="实验功能：仅修改客户端 Index/index 响应，不写服务器">?</span>
      <b>实验功能 · 仅测试账号使用</b>
      桥接靶机只能<strong>直接进入战斗</strong>：不能删除、锁定、管理或用于任何服务器写入操作。
      关闭桥接并重启游戏后，桥接靶机会清空。若进入战斗闪退，立即点击“停止桥接并恢复代理”。
    </div>
    <div class="bridge-grid">
      <section class="panel panel-pad">
        <div class="subhead">${icon("crosshair", 13)} 桥接目标</div>
        <label class="bridge-field">
          <span>队伍编号（逗号分隔，最多 35 个）</span>
          <textarea data-bridge-targets rows="4" spellcheck="false" placeholder="7301601, 7300101">${esc(state.targets)}</textarea>
        </label>
        <label class="bridge-field">
          <span>模式</span>
          <select data-bridge-mode class="rf-select">
            <option value="roundtrip" ${state.mode === "roundtrip" ? "selected" : ""}>仅验证 roundtrip（不追加）</option>
            <option value="inject" ${state.mode === "inject" ? "selected" : ""}>注入模式（追加目标）</option>
          </select>
        </label>
        <div class="bridge-actions">
          <button class="btn btn-primary" data-bridge-start ${state.busy ? "disabled" : ""}>${icon("play", 13)} 启动桥接并重启游戏</button>
          <button class="btn btn-danger" data-bridge-stop ${state.busy ? "disabled" : ""}>${icon("close", 13)} 停止桥接并恢复代理</button>
        </div>
        <p class="bridge-note">启动前请先关闭普通抓包和模拟器抓包。HTTPS 会直通，不安装证书。</p>
      </section>
      <section class="panel panel-pad">
        <div class="subhead">${icon("radar", 13)} 状态 ${statusPill(status)}</div>
        <div class="bridge-status">
          <div><span>PID</span><b>${esc(status.pid || "—")}</b></div>
          <div><span>端口</span><b>${esc(status.port || 18080)}</b></div>
          <div><span>目标数</span><b>${(status.targets || []).length}</b></div>
          <div><span>模式</span><b>${esc(status.mode || state.mode)}</b></div>
        </div>
        <div class="subhead">${icon("terminal", 13)} 日志</div>
        <pre class="bridge-log" data-bridge-log>${esc(log)}</pre>
      </section>
    </div>
  `;

  root.querySelector("[data-bridge-targets]")?.addEventListener("input", (event) => {
    state.targets = event.target.value;
  });
  root.querySelector("[data-bridge-mode]")?.addEventListener("change", (event) => {
    state.mode = event.target.value;
  });
  root.querySelector("[data-bridge-start]")?.addEventListener("click", () => startBridge(root));
  root.querySelector("[data-bridge-stop]")?.addEventListener("click", () => stopBridge(root));
}

async function refresh(root) {
  try {
    state.status = await api.bridgeStatus();
    if (!state.targets && (state.status.targets || []).length) state.targets = targetsText(state.status);
    if (state.status.mode) state.mode = state.status.mode === "roundtrip" ? "roundtrip" : "inject";
    const log = root.querySelector("[data-bridge-log]");
    if (log) log.textContent = state.status.log || "还没有桥接日志。";
    const host = root.querySelector("[data-bridge-body]");
    if (host) renderBody(host);
  } catch (err) {
    const host = root.querySelector("[data-bridge-body]");
    if (host) host.innerHTML = `<div class="roster-error">${icon("alert", 15)} ${esc(err.message || "读取桥接状态失败")}</div>`;
  }
}

function parseTargets() {
  return state.targets.split(/[,;\\s]+/).map((item) => Number(item)).filter((item) => Number.isInteger(item) && item > 0);
}

async function startBridge(root) {
  if (state.busy) return;
  state.busy = true;
  const button = root.querySelector("[data-bridge-start]");
  setBusy(button, true, "启动中…");
  try {
    state.status = await api.bridgeStart({
      targets: parseTargets(),
      mode: state.mode,
      restart_game: true,
    });
    state.targets = targetsText(state.status);
    toastOk("桥接已启动", "游戏正在重启，请登录测试账号。");
    await refresh(root);
  } catch (err) {
    toastErr("启动桥接失败", err.hint || err.detail || err.message);
  } finally {
    state.busy = false;
    const body = root.querySelector("[data-bridge-body]");
    if (body) renderBody(body);
  }
}

async function stopBridge(root) {
  if (state.busy) return;
  state.busy = true;
  const button = root.querySelector("[data-bridge-stop]");
  setBusy(button, true, "停止中…");
  try {
    state.status = await api.bridgeStop({ restart_game: true });
    toastOk("桥接已停止", "系统代理已恢复，游戏已重启，桥接靶机已清空。");
    await refresh(root);
  } catch (err) {
    toastErr("停止桥接失败", err.hint || err.detail || err.message);
  } finally {
    state.busy = false;
    const body = root.querySelector("[data-bridge-body]");
    if (body) renderBody(body);
  }
}

export async function render(root) {
  root.innerHTML =
    pageHeadHtml({
      crumbs: [{ label: "本地靶机桥接" }],
      title: "本地靶机桥接",
      badge: "EXPERIMENTAL",
      sub: "在客户端 Index 响应上追加本地临时靶机。只追加、不替换、不写服务器；停止桥接并重启游戏后清空。",
    }) +
    '<div data-bridge-body><div class="roster-loading"><span class="spinner"></span> 读取桥接状态…</div></div>';

  await refresh(root);
  if (state.timer) window.clearInterval(state.timer);
  state.timer = window.setInterval(() => refresh(root), 3000);
  store.registerCleanup(() => {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = null;
  });
}
