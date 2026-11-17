/* views/bridge.js —— 本地靶机桥接（实验） */
import { api } from "../api.js";
import { store, refreshSequence } from "../store.js";
import { icon, pageHeadHtml, toastErr, toastOk, setBusy } from "../ui.js";
import { esc } from "../util.js";

const state = {
  status: null,
  mode: "inject",
  client: "pc",
  package: "com.sunborn.girlsfrontline.pt",
  timer: null,
  busy: false,
  targetInfo: new Map(),
  mixed: false,
  unknown: [],
  rendered: false,
  formInit: false,
};

function sequenceDraft() {
  return Array.isArray(store.sequence?.draft) ? store.sequence.draft : [];
}

function targetIds() {
  return sequenceDraft()
    .map((team) => Number(team.id))
    .filter((id) => Number.isInteger(id) && id > 0);
}

function statusPill(status) {
  const value = status?.state || "idle";
  const label = value === "running" ? "桥接运行中" : value === "stale" ? "有残留进程" : "未运行";
  const cls = value === "running" ? "green" : value === "stale" ? "warn" : "";
  return `<span class="badge ${cls}">${label}</span>`;
}

async function classifyTargets() {
  const ids = targetIds();
  const info = new Map();
  await Promise.all(ids.map(async (id) => {
    const known = sequenceDraft().find((team) => Number(team.id) === id);
    if (known && typeof known.collectable === "boolean") {
      info.set(id, { collectable: known.collectable, team: known });
      return;
    }
    try {
      const team = await api.team(id);
      info.set(id, { collectable: team.collectable !== false, team });
    } catch {
      info.set(id, { collectable: null, team: null });
    }
  }));
  state.targetInfo = info;
  const kinds = new Set([...info.values()].map((item) => item.collectable).filter((v) => v !== null));
  state.mixed = kinds.size > 1;
  state.unknown = [...info.entries()].filter(([, item]) => item.collectable === null).map(([id]) => id);
  return info;
}

function targetKindsHtml() {
  const ids = targetIds();
  if (!ids.length) {
    return `<div class="bridge-empty-sequence">${icon("layers", 14)} 序列为空。桥接直接共用右侧序列，请先到「序列编排」加入目标。</div>`;
  }
  const chips = ids.map((id) => {
    const item = state.targetInfo.get(id);
    const cls = item?.collectable === true ? "blue" : item?.collectable === false ? "red" : "unknown";
    const label = cls === "blue" ? "蓝框 · 可临时加入" : cls === "red" ? "红框 · 必须桥接" : "未知/无数据";
    return `<span class="bridge-target-chip ${cls}"><b>#${esc(id)}</b><span>${label}</span></span>`;
  }).join("");
  const hasBlue = [...state.targetInfo.values()].some((item) => item.collectable === true);
  const hasRed = [...state.targetInfo.values()].some((item) => item.collectable === false);
  let rule = "";
  if (hasRed && hasBlue) {
    rule = `<div class="bridge-rule red">红框 + 蓝框混接：只要包含红框，整组都只能作为临时桥接；停止桥接并重启后清空。</div>`;
  } else if (hasRed && !state.unknown.length) {
    rule = `<div class="bridge-rule red">红框目标：正常 addCollect 不会接受，只能通过桥接临时加入。</div>`;
  } else if (hasBlue && !state.unknown.length) {
    rule = `<div class="bridge-rule blue">蓝框目标走桥接 = 临时加入（向下兼容）；停止桥接并重启后清空。</div>`;
  }
  if (state.unknown.length) {
    rule += `<div class="bridge-rule warn">未知/无 STC 数据的编号：${state.unknown.map((id) => `#${id}`).join("、")}</div>`;
  }
  return `<div class="bridge-target-chips">${chips}</div>${rule}`;
}

function sequenceHeaderHtml() {
  return `<span>当前序列 <b>${sequenceDraft().length}</b> / 35</span>
    <button class="btn btn-xs btn-ghost" type="button" data-nav="/sequence">${icon("layers", 11)} 去序列编排</button>`;
}

function statusFieldsHtml() {
  const status = state.status || {};
  return `
    <div><span>PID</span><b>${esc(status.pid || "—")}</b></div>
    <div><span>端口</span><b>${esc(status.port || 18080)}</b></div>
    <div><span>目标数</span><b>${targetIds().length}</b></div>
    <div><span>模式</span><b>${esc(status.mode || state.mode)}</b></div>`;
}

function bindEvents(root) {
  root.querySelector("[data-bridge-mode]")?.addEventListener("change", (event) => {
    state.mode = event.target.value;
  });
  root.querySelector("[data-bridge-client]")?.addEventListener("change", (event) => {
    state.client = event.target.value;
  });
  root.querySelector("[data-bridge-package]")?.addEventListener("input", (event) => {
    state.package = event.target.value;
  });
  root.querySelector("[data-bridge-start]")?.addEventListener("click", () => startBridge(root));
  root.querySelector("[data-bridge-stop]")?.addEventListener("click", () => stopBridge(root));
}

function renderBody(root) {
  const log = state.status?.log || "还没有桥接日志。";
  root.innerHTML = `
    <div class="bridge-warning">
      <span class="help-dot" title="实验功能：仅修改客户端 Index/index 响应，不写服务器">?</span>
      <b>实验功能 · 仅测试账号使用</b>
      红框和蓝框可以混接，但只要包含红框，整组都只能作为<strong>临时桥接</strong>。
      桥接靶机只能<strong>直接进入战斗</strong>：不能删除、锁定、管理或用于任何服务器写入操作。
      关闭桥接并重启游戏后，桥接靶机会清空。若进入战斗闪退，立即点击“停止桥接并恢复代理”。
    </div>
    <div class="bridge-grid">
      <section class="panel panel-pad">
        <div class="subhead">${icon("layers", 13)} 桥接目标 · 共用右侧序列</div>
        <div class="bridge-sequence-head" data-bridge-seq-head>${sequenceHeaderHtml()}</div>
        <div class="bridge-target-kinds" data-bridge-kinds>${targetKindsHtml()}</div>

        <label class="bridge-field">
          <span>模式</span>
          <select data-bridge-mode class="rf-select">
            <option value="roundtrip" ${state.mode === "roundtrip" ? "selected" : ""}>仅验证 roundtrip（不追加）</option>
            <option value="inject" ${state.mode === "inject" ? "selected" : ""}>注入模式（临时加入）</option>
          </select>
        </label>
        <div class="bridge-field-row">
          <label class="bridge-field">
            <span>客户端</span>
            <select data-bridge-client class="rf-select">
              <option value="pc" ${state.client !== "emulator" ? "selected" : ""}>PC 客户端</option>
              <option value="emulator" ${state.client === "emulator" ? "selected" : ""}>安卓模拟器（ADB）</option>
            </select>
          </label>
          <label class="bridge-field">
            <span>模拟器包名</span>
            <input data-bridge-package type="text" value="${esc(state.package)}" placeholder="com.sunborn.girlsfrontline.pt" />
          </label>
        </div>
        <p class="bridge-note">模拟器模式会通过 ADB 自动检测设备、adb reverse 和全局 http_proxy；HTTPS 仍然直通。</p>
        <div class="bridge-actions">
          <button class="btn btn-primary" data-bridge-start ${state.busy ? "disabled" : ""}>${icon("play", 13)} 启动桥接并重启游戏</button>
          <button class="btn btn-danger" data-bridge-stop ${state.busy ? "disabled" : ""}>${icon("close", 13)} 停止桥接并恢复代理</button>
        </div>
        <p class="bridge-note">普通注入入口仍在「序列编排」；含红框时普通执行注入会失败，请用本页桥接临时加入。启动前请先关闭普通抓包和模拟器抓包。HTTPS 会直通，不安装证书。</p>
      </section>
      <section class="panel panel-pad">
        <div class="subhead">${icon("radar", 13)} 状态 <span data-bridge-state>${statusPill(state.status)}</span></div>
        <div class="bridge-status" data-bridge-status>${statusFieldsHtml()}</div>
        <div class="subhead">${icon("terminal", 13)} 日志</div>
        <pre class="bridge-log" data-bridge-log>${esc(log)}</pre>
      </section>
    </div>`;
  bindEvents(root);
}

function updateStatusDom(root) {
  const stateEl = root.querySelector("[data-bridge-state]");
  if (stateEl) stateEl.innerHTML = statusPill(state.status);
  const fields = root.querySelector("[data-bridge-status]");
  if (fields) fields.innerHTML = statusFieldsHtml();
  const log = root.querySelector("[data-bridge-log]");
  if (log) log.textContent = state.status?.log || "还没有桥接日志。";
}

async function refresh(root) {
  try {
    state.status = await api.bridgeStatus();
    if (!state.formInit) {
      if (state.status.mode) state.mode = state.status.mode === "roundtrip" ? "roundtrip" : "inject";
      if (state.status.client) state.client = state.status.client === "emulator" ? "emulator" : "pc";
      if (state.status.package) state.package = state.status.package;
      state.formInit = true;
    }
    if (!state.rendered) {
      const host = root.querySelector("[data-bridge-body]") || root;
      renderBody(host);
      state.rendered = true;
      await classifyTargets();
      const kinds = root.querySelector("[data-bridge-kinds]");
      if (kinds) kinds.innerHTML = targetKindsHtml();
    } else {
      updateStatusDom(root);
    }
  } catch (err) {
    const host = root.querySelector("[data-bridge-body]");
    if (host) host.innerHTML = `<div class="roster-error">${icon("alert", 15)} ${esc(err.message || "读取桥接状态失败")}</div>`;
  }
}

async function startBridge(root) {
  if (state.busy) return;
  const ids = targetIds();
  if (!ids.length) {
    toastErr("序列为空", "桥接直接共用右侧序列，请先到「序列编排」加入目标。");
    return;
  }
  if (state.mode === "inject" && !ids.length) {
    toastErr("缺少桥接目标", "注入模式至少需要一个序列目标。");
    return;
  }
  await classifyTargets();
  state.busy = true;
  const button = root.querySelector("[data-bridge-start]");
  setBusy(button, true, "启动中…");
  try {
    state.status = await api.bridgeStart({
      targets: ids,
      mode: state.mode,
      client: state.client,
      package: state.package,
      restart_game: true,
    });
    toastOk("桥接已启动", "游戏正在重启，请登录测试账号。");
    updateStatusDom(root);
  } catch (err) {
    toastErr("启动桥接失败", err.hint || err.detail || err.message);
  } finally {
    state.busy = false;
    setBusy(button, false);
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
    updateStatusDom(root);
  } catch (err) {
    toastErr("停止桥接失败", err.hint || err.detail || err.message);
  } finally {
    state.busy = false;
    setBusy(button, false);
  }
}

export async function render(root) {
  state.rendered = false;
  state.formInit = false;
  state.status = null;
  root.innerHTML =
    pageHeadHtml({
      crumbs: [{ label: "本地靶机桥接" }],
      title: "本地靶机桥接",
      badge: "EXPERIMENTAL",
      sub: "直接共用右侧序列。含红框时整组作为临时注入；只追加、不替换、不写服务器；停止桥接并重启游戏后清空。",
    }) +
    '<div data-bridge-body><div class="roster-loading"><span class="spinner"></span> 读取桥接状态…</div></div>';

  try {
    await refreshSequence();
  } catch {
    /* 序列读取失败时留空，桥接页会提示 */
  }
  await refresh(root);

  const seqRoot = root.querySelector("[data-bridge-body]");
  const syncSequence = async () => {
    if (!seqRoot) return;
    const head = seqRoot.querySelector("[data-bridge-seq-head]");
    if (head) head.innerHTML = sequenceHeaderHtml();
    await classifyTargets();
    const kinds = seqRoot.querySelector("[data-bridge-kinds]");
    if (kinds) kinds.innerHTML = targetKindsHtml();
  };
  const unsub = store.on("sequence", syncSequence);
  store.registerCleanup(() => {
    if (typeof unsub === "function") unsub();
    if (state.timer) window.clearInterval(state.timer);
    state.timer = null;
  });
  if (state.timer) window.clearInterval(state.timer);
  state.timer = window.setInterval(() => refresh(root).catch(() => {}), 3000);
}
