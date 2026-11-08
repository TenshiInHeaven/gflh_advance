/* views/capture.js —— 登录抓取：开始抓取 / 设置代理并重启游戏 / 实时日志 / 凭证 / 当前靶机
 * 抓包端口可配置（默认 18080，范围 1024-65535，持久化到 /api/settings）。
 */
import { api, setCapturePort, getCapturePort, markCapturePortLoaded } from "../api.js";
import { store, refreshHealth, refreshCurrent, tryRefreshCurrent, loadChapters, refreshSequence } from "../store.js";
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
  butterflySvg,
} from "../ui.js";
import { esc, fmtNum, fmtPower, fmtTime, fmtDuration, timeAgo, navigate, powerDisplay } from "../util.js";
import {
  bindPowerFilter,
  powerFilterBarHtml,
  powerFilterMeta,
  defaultPowerFilter,
} from "../components/power-filter.js";
import {
  gameClientCardHtml,
  fetchGameStatus,
  detectGameClient,
  pickGameClient,
  confirmGameClient,
  refreshCatalogForGame,
  gameErrorMessage,
} from "../components/game-setup.js";

const STATE_LABEL = {
  idle: "空闲",
  starting: "启动中",
  running: "抓取中",
  stopped: "已停止",
  error: "错误",
};

const PORT_MIN = 1024;
const PORT_MAX = 65535;
const DEFAULT_PORT = 18080;

const teamCache = new Map();
let rootEl = null;
let pollTimer = 0;
let captureStatus = null;
let currentData = null;
let credsData = null;
let historyData = [];
let historyDir = "";
let targetFillToken = 0;
let currentPort = getCapturePort();
let portSaveBusy = false;
let currentFilter = defaultPowerFilter();
let targetDataLoading = false;

function cleanup() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = 0;
  }
}

function validPort(value) {
  const port = Number(value);
  return Number.isInteger(port) && port >= PORT_MIN && port <= PORT_MAX ? port : null;
}

function proxyAddr(port = currentPort) {
  return `127.0.0.1:${port}`;
}

export async function render(root) {
  rootEl = root;
  cleanup();
  captureStatus = null;
  currentData = null;
  credsData = null;
  historyData = [];
  historyDir = "";
  targetFillToken += 1;
  currentPort = getCapturePort();

  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [{ label: "登录抓取" }],
      title: "登录抓取",
      badge: "CAPTURE",
      sub: `通过本地抓包代理获取当前登录的 uid / sign 与游戏内收藏标靶列表。抓包端口默认 <b class="mono-inline" data-port>${currentPort}</b>（可配置，范围 ${PORT_MIN}-${PORT_MAX}）；8080 常被其它程序占用，建议避开。`,
      actions: `
        <button class="btn btn-ghost" type="button" data-act="refresh">${icon("refresh", 14)} 刷新状态</button>
        <button class="btn btn-cyan" type="button" data-act="start">${icon("key", 14)} 开始抓取</button>
        <button class="btn btn-danger" type="button" data-act="stop">${icon("power", 14)} 完成并关闭代理</button>
      `,
    })}
    <div data-game-client></div>
    <div class="capture-mode-card" style="margin:0 0 14px;padding:12px 14px;border:1px solid var(--line);border-radius:var(--r);background:rgba(10,18,39,.55)">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span class="pc-title">${icon("wifi", 13)} 抓包模式 / 区服</span>
        <select class="rf-select" data-capture-mode>
          <option value="pc">PC / 国服（系统代理）</option>
          <option value="emulator">安卓模拟器（LAN + CA）</option>
        </select>
        <select class="rf-select" data-capture-region>
          <option value="cn">国服 PC</option>
          <option value="cn_revival">国服复活版（安卓）</option>
          <option value="tw">台服 TW</option>
          <option value="jp">日服 JP</option>
          <option value="custom">自定义区服</option>
        </select>
        <span class="pc-hint" data-capture-mode-hint>国服 PC 模式：沿用系统代理 + 本地 127.0.0.1 端口。</span>
      </div>
      <div data-emulator-box style="display:none;margin-top:10px;padding-top:10px;border-top:1px dashed var(--line)">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="pc-hint">模拟器代理：<b class="mono-inline">PC 局域网 IP :</b></span>
          <input type="number" class="port-input" data-emu-port min="${PORT_MIN}" max="${PORT_MAX}" step="1" value="8084" aria-label="模拟器抓包端口" />
          <span class="pc-hint">监听地址</span>
          <select class="rf-select" data-listen-host>
            <option value="0.0.0.0">0.0.0.0（局域网）</option>
            <option value="127.0.0.1">127.0.0.1（仅本机）</option>
          </select>
          <button class="btn btn-sm btn-cyan" type="button" data-act="download-ca">${icon("lock", 12)} 下载 CA 证书</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
          <span class="pc-hint">ADB</span>
          <input type="text" class="port-input" style="width:260px" data-adb-path placeholder="自动检测 / 填 adb.exe 路径" />
          <input type="text" class="port-input" style="width:140px" data-adb-serial placeholder="串口，如 127.0.0.1:7555" />
          <button class="btn btn-sm btn-ghost" type="button" data-act="detect-adb">${icon("search", 12)} 自动检测</button>
          <span class="pc-hint" data-adb-detect-hint></span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
          <span class="pc-hint">游戏包名</span>
          <input type="text" class="port-input" style="width:230px" data-emu-package placeholder="台服 tw.txwy.and.snqx" />
          <button class="btn btn-sm btn-primary" type="button" data-act="emu-setup">${icon("settings", 12)} 一键装 CA / 设代理 / 重启游戏</button>
        </div>
        <div class="pc-hint" style="margin-top:6px;line-height:1.7">
          1. 推荐先点「自动检测」填入 ADB 和串口；<br>
          2. 一键操作会 <b>adb reverse</b>，把模拟器 127.0.0.1:端口 转发到本机，不需要把代理暴露到局域网；<br>
          3. 打开游戏登录，抓包会从 HTTPS 流量里识别 uid/sign/base_url。<br>
          <span class="text-mute">注意：MuMu/雷电/夜神/BlueStacks 的 ADB 路径不同；只要 ADB 能连、能 root 装系统 CA，抓包流程通用。</span>
        </div>
      </div>
    </div>
    <div class="capture-cols">
      <div>
        <div class="capture-panel" data-capture-panel>
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
            <span class="cap-state" data-cap-state><span class="dot"></span><span data-cap-state-text>读取中…</span></span>
            <span class="mono-inline text-mute" style="font-size:10.5px">PORT <b data-cap-port>${currentPort}</b> · 本地代理</span>
            <span style="flex:1"></span>
            <span class="badge mono" data-cap-elapsed>—</span>
          </div>

          <div class="port-config">
            <div class="pc-head">
              ${icon("wifi", 13)}
              <span class="pc-title">抓包端口</span>
              <span class="badge mono" data-port-badge>${currentPort}</span>
              <span class="pc-tip">默认 ${DEFAULT_PORT}，可配置（${PORT_MIN}-${PORT_MAX}）；8080 常被其它程序占用，建议保持默认 / 按需修改</span>
            </div>
            <div class="pc-row">
              <input type="number" class="port-input" data-port-input min="${PORT_MIN}" max="${PORT_MAX}" step="1" value="${currentPort}" aria-label="抓包端口" />
              <button class="btn btn-sm btn-cyan" type="button" data-act="save-port">${icon("check", 12)} 保存端口</button>
              <span class="pc-hint" data-port-hint>修改后点保存，下一次「开始抓取」生效</span>
            </div>
            <div class="pc-hint data-dir-line" style="margin-top:7px">
              ${icon("database", 11)} 应用数据目录：<code data-data-dir>读取中…</code>
              · 可用环境变量 <b class="mono-inline">TARGETFORGE_DATA_DIR</b> 覆盖；creds_latest.json 就放在该目录下
            </div>
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
                <div class="ws-desc">启动本地抓包代理并监听 <b class="mono-inline" data-port>${currentPort}</b> 端口。</div>
                <div class="ws-action"><button class="btn btn-primary btn-sm" type="button" data-act="start">${icon("play", 12)} 开始抓取</button></div>
              </div>
            </div>
            <div class="wizard-step" data-step="2">
              <span class="ws-num">2</span>
              <div class="ws-body">
                <div class="ws-title">设置代理并重启游戏</div>
                <div class="ws-desc">让系统代理指向 <b class="mono-inline" data-proxy-addr>${proxyAddr()}</b>，然后强杀并重启游戏。</div>
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
          <div class="param-note" style="margin-top:10px">${icon("info", 12)} 顶栏显示的游戏进程 PID 由 <b class="mono-inline">tasklist</b> 按进程名 <b class="mono-inline">GrilsFrontLine.exe</b> 搜索得到，仅在本机展示，不会上传。</div>
        </div>

        <div class="capture-panel mt16">
          ${sectionHeadHtml("登录凭证", { hint: "每个区服只保留一份最新凭证", iconName: "key", actions: `<button class="btn btn-xs btn-ghost" type="button" data-act="toggle-creds">收起</button>` })}
          <div data-creds-body>
            <div class="creds-list" data-creds-list>${skeletonRows(3)}</div>
            <div class="mt12" style="display:flex;gap:8px">
              <button class="btn btn-ghost btn-sm" type="button" data-act="load-creds" disabled>${icon("upload", 12)} 加载选中凭证</button>
              <span class="text-mute" style="font-size:10.5px;align-self:center" data-cred-hint>先选择一条凭证</span>
            </div>
          </div>
        </div>

        <div class="capture-panel mt16" data-target-history-panel>
          ${sectionHeadHtml("历史靶机配置", { hint: "手动备份当前批次；只存靶机，不存 sign", iconName: "database" })}
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <button class="btn btn-cyan btn-sm" type="button" data-act="save-target-history">${icon("database", 12)} 保存当前靶机批次</button>
            <span class="text-mute" style="font-size:10.5px" data-history-hint>存档按时间命名，可一键全部加入当前序列</span>
          </div>
          <div class="target-history-list mt12" data-target-history-list>${skeletonRows(2)}</div>
          <div class="pc-hint" style="margin-top:6px">存于 <code data-history-dir>dataMiner/derived/targetforge/target_history/</code>；不自动覆盖，需手动保存。</div>
        </div>
      </div>

      <div>
        <div class="terminal">
          <div class="terminal-head">
            <span class="dots"><i></i><i></i><i></i></span>
            <span>CAPTURE STREAM · <b class="mono-inline" data-proxy-addr>${proxyAddr()}</b></span>
            <span class="th-right"><span class="dot" data-term-dot></span><span data-term-state>等待开始</span></span>
          </div>
          <div class="terminal-body" data-cap-logs>
            <div class="log-idle">
              <div class="li-prompt">${icon("terminal", 15)}</div>
              <div class="li-body">
                <div class="li-title">等待开始抓取<span class="cursor-blink" style="margin-left:6px"></span></div>
                <div class="li-line"># 本地抓包代理 · <b data-proxy-addr>${proxyAddr()}</b>（端口可配置，默认 ${DEFAULT_PORT}）</div>
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
          <div class="mt12">${powerFilterBarHtml()}</div>
          <div data-current-targets class="mt12">${skeletonRows(3)}</div>
        </div>
      </div>
    </div>
  `;

  bindShellEvents(root);
  bindPortEvents(root);
  bindCaptureMode(root);
  bindPowerFilter(root, (filter) => {
    currentFilter = filter;
    renderCurrent();
  });
  await Promise.allSettled([loadSettings(), refreshStatus(), loadCreds(), loadTargetHistory(), loadCurrent(), applyDataDir()]);
  applyPortUi();

  pollTimer = setInterval(() => {
    if (!rootEl || !rootEl.isConnected) {
      cleanup();
      return;
    }
    refreshStatus({ silent: true });
  }, 1500);
  store.registerCleanup(cleanup);
}

/* ------------------------------------------------------------------ */
/* 端口配置                                                           */
/* ------------------------------------------------------------------ */
async function loadSettings() {
  try {
    const settings = await api.settings();
    loadGameClientCard();

    const port = validPort(settings?.capture_port);
    if (port) {
      currentPort = setCapturePort(port);
    }
    const adbPathEl = rootEl?.querySelector("[data-adb-path]");
    const serialEl = rootEl?.querySelector("[data-adb-serial]");
    const packageEl = rootEl?.querySelector("[data-emu-package]");
    if (adbPathEl && settings?.emulator_adb_path) adbPathEl.value = settings.emulator_adb_path;
    if (serialEl && settings?.emulator_serial) serialEl.value = settings.emulator_serial;
    if (packageEl && settings?.emulator_package) packageEl.value = settings.emulator_package;
    if (packageEl && !packageEl.value.trim()) packageEl.value = "tw.txwy.and.snqx";
    markCapturePortLoaded();
  } catch {
    /* 设置读取失败时保持默认端口 */
  }
  applyPortUi();
}

function applyPortUi() {
  if (!rootEl || !rootEl.isConnected) return;
  rootEl.querySelectorAll("[data-port]").forEach((node) => {
    node.textContent = String(currentPort);
  });
  rootEl.querySelectorAll("[data-port-badge]").forEach((node) => {
    node.textContent = String(currentPort);
  });
  rootEl.querySelectorAll("[data-proxy-addr]").forEach((node) => {
    node.textContent = proxyAddr();
  });
  const input = rootEl.querySelector("[data-port-input]");
  if (input && document.activeElement !== input && !isCaptureActive()) {
    input.value = String(currentPort);
  }
  const hint = rootEl.querySelector("[data-port-hint]");
  if (hint) {
    hint.innerHTML = `当前端口 <b class="mono-inline">${currentPort}</b> · 修改后点保存，下一次「开始抓取」生效`;
  }
}

function isCaptureActive() {
  const state = captureStatus?.state;
  return state === "running" || state === "starting";
}

function bindPortEvents(root) {
  const input = root.querySelector("[data-port-input]");
  if (!input) return;
  const validate = () => {
    const port = validPort(input.value);
    if (port === null) {
      input.classList.add("invalid");
      const hint = root.querySelector("[data-port-hint]");
      if (hint) hint.innerHTML = `<span class="text-red">端口需为 ${PORT_MIN}-${PORT_MAX} 的整数</span>`;
      return null;
    }
    input.classList.remove("invalid");
    return port;
  };
  input.addEventListener("input", validate);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      root.querySelector('[data-act="save-port"]')?.click();
    }
  });
  root.querySelector('[data-act="save-port"]')?.addEventListener("click", async (event) => {
    if (portSaveBusy) return;
    const port = validate();
    if (port === null) {
      toastErr("端口不合法", `请输入 ${PORT_MIN}-${PORT_MAX} 之间的整数。`);
      return;
    }
    const button = event.currentTarget;
    portSaveBusy = true;
    setBusy(button, true, "保存中…");
    try {
      await api.saveSettings({ capture_port: port });
      currentPort = setCapturePort(port);
      applyPortUi();
      if (isCaptureActive() && captureStatus?.port !== port) {
        toast({ title: `端口已保存为 ${port}`, text: "当前抓取仍运行在旧端口，下次开始抓取时生效。", type: "warn" });
      } else {
        toastOk(`抓包端口已保存为 ${port}`, "下一次「开始抓取」将使用该端口。");
      }
    } catch (err) {
      toastErr("保存失败", err.message);
    } finally {
      portSaveBusy = false;
      setBusy(button, false);
      applyPortUi();
    }
  });
}

/* ------------------------------------------------------------------ */
/* 事件绑定                                                           */
/* ------------------------------------------------------------------ */
function bindCaptureMode(root) {
  const modeEl = root.querySelector("[data-capture-mode]");
  const regionEl = root.querySelector("[data-capture-region]");
  const box = root.querySelector("[data-emulator-box]");
  const hint = root.querySelector("[data-capture-mode-hint]");
  const gameClient = root.querySelector("[data-game-client]");
  const modeCard = root.querySelector(".capture-mode-card");
  // 抓包模式在游戏客户端之上；模拟器模式不需要 PC 客户端目录
  if (modeCard && gameClient && modeCard.compareDocumentPosition(gameClient) & Node.DOCUMENT_POSITION_PRECEDING) {
    gameClient.before(modeCard);
  }
  const sync = () => {
    const emu = modeEl?.value === "emulator";
    if (box) box.style.display = emu ? "" : "none";
    if (gameClient) gameClient.style.display = emu ? "none" : "";
    if (hint) {
      hint.textContent = emu
        ? "模拟器模式：不需要 PC 客户端目录；用 ADB + CA + 本机反向代理抓包。"
        : "国服 PC 模式：沿用系统代理 + 本地 127.0.0.1 端口。";
    }
    const wizard = root.querySelector("[data-wizard]");
    if (wizard) wizard.style.display = emu ? "none" : "";
    // 区服始终可切换：选到模拟器区服会自动切到模拟器模式
    if (regionEl) regionEl.disabled = false;
  };
  modeEl?.addEventListener("change", sync);
  regionEl?.addEventListener("change", sync);
  sync();
  const packageEl = root.querySelector("[data-emu-package]");
  const adbPathEl = root.querySelector("[data-adb-path]");
  const serialEl = root.querySelector("[data-adb-serial]");
  const hintEl = root.querySelector("[data-adb-detect-hint]");
  const regionPackages = {
    tw: "tw.txwy.and.snqx",
    cn: "",
    cn_revival: "com.sunborn.girlsfrontline.pt",
    jp: "com.sunborn.girlsfrontline",
    custom: "",
  };
  const regionModes = { cn: "pc", cn_revival: "emulator", tw: "emulator", jp: "emulator", custom: "emulator" };
  const applyRegionPackage = () => {
    if (!packageEl) return;
    const wanted = regionPackages[regionEl?.value] || "";
    if (wanted) packageEl.value = wanted;
  };
  regionEl?.addEventListener("change", () => {
    const wantedMode = regionModes[regionEl.value];
    if (modeEl && wantedMode) modeEl.value = wantedMode;
    sync();
    applyRegionPackage();
  });
  root.querySelector('[data-act="detect-adb"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "检测中…");
    try {
      const data = await api.emulatorDetect();
      const candidates = data.candidates || [];
      const picked = data.default || candidates[0];
      if (!picked) {
        if (hintEl) hintEl.textContent = "未发现 ADB；请手动填写路径。";
        toastErr("未检测到 ADB", "MuMu/雷电/夜神/BlueStacks 的 adb.exe 路径不同。");
        return;
      }
      if (adbPathEl) adbPathEl.value = picked.path || "";
      const serial = data.default_serial || (picked.devices || [{}])[0]?.serial || "";
      if (serialEl) serialEl.value = serial;
      applyRegionPackage();
      const names = candidates.map((item) => `${item.name}${(item.devices || []).length ? `(${item.devices.length})` : ""}`).join(" / ");
      if (hintEl) hintEl.textContent = serial ? `已选：${picked.name} ${serial}` : `发现 ${names}，但没有在线设备，请先启动模拟器。`;
      toastOk("ADB 检测完成", serial ? `${picked.name} · ${serial}` : "需要先启动模拟器并开启 ADB。");
    } catch (err) {
      toastErr("检测失败", err.message);
    } finally {
      setBusy(button, false);
    }
  });
  root.querySelector('[data-act="emu-setup"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const portValue = validPort(root.querySelector("[data-emu-port]")?.value);
    if (portValue === null) {
      toastErr("端口不合法", `请输入 ${PORT_MIN}-${PORT_MAX} 之间的整数。`);
      return;
    }
    const body = {
      region: regionEl?.value || "tw",
      adb_path: adbPathEl?.value.trim() || "",
      serial: serialEl?.value.trim() || "",
      package: packageEl?.value.trim() || "",
      port: portValue,
    };
    const ok = await confirmDialog({
      title: "安装 CA / 设置代理 / 重启游戏",
      message: "将对模拟器执行 adb reverse、安装系统 CA、设置 HTTP 代理，并强制重启游戏。",
      detail: "这需要模拟器 ADB 已连接且开启 root；重启后请在游戏里登录。抓包结束后请点「完成并关闭代理」。",
      confirmText: "开始配置",
    });
    if (!ok) return;
    setBusy(button, true, "配置中…");
    try {
      const result = await api.emulatorSetup(body);
      if (!result.ok) {
        toastErr("配置未完全成功", (result.error || "请查看返回结果").slice(0, 300));
      } else {
        toastOk("模拟器配置完成", "CA/代理已设置，游戏正在重启。请登录到主界面。");
      }
      await refreshStatus();
    } catch (err) {
      toastErr("配置失败", err.message + (err.hint ? `（${err.hint}）` : ""));
    } finally {
      setBusy(button, false);
    }
  });
  root.querySelector('[data-act="download-ca"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "生成中…");
    try {
      const data = await api.captureCa();
      const blob = new Blob([data.pem || ""], { type: "application/x-x509-ca-cert" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || "targetforge-mitm-ca.crt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toastOk("CA 已下载", "请装进模拟器的系统证书目录（Android 7+ 需 root/Magisk）。");
    } catch (err) {
      toastErr("CA 生成失败", err.message + (err.hint ? `（${err.hint}）` : ""));
    } finally {
      setBusy(button, false);
    }
  });
}

function bindShellEvents(root) {
  const credsBody = root.querySelector("[data-creds-body]");
  const credsToggle = root.querySelector('[data-act="toggle-creds"]');
  const applyCollapsed = (collapsed) => {
    if (!credsBody || !credsToggle) return;
    credsBody.style.display = collapsed ? "none" : "";
    credsToggle.textContent = collapsed ? "展开" : "收起";
    try { localStorage.setItem("tf_creds_collapsed", collapsed ? "1" : "0"); } catch (e) {}
  };
  let credsCollapsed = false;
  try { credsCollapsed = localStorage.getItem("tf_creds_collapsed") === "1"; } catch (e) {}
  credsToggle?.addEventListener("click", () => {
    credsCollapsed = !credsCollapsed;
    applyCollapsed(credsCollapsed);
  });
  applyCollapsed(credsCollapsed);
  root.querySelector('[data-act="save-target-history"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "保存中…");
    try {
      const result = await api.saveTargetHistory();
      if (result.ok) {
        toastOk("靶机批次已保存", `${result.item?.count || 0} 个靶机 · ${result.item?.name || ""}`);
        await loadTargetHistory();
      } else {
        toastErr("保存失败", "后端未返回有效结果");
      }
    } catch (err) {
      toastErr("保存失败", err.message + (err.hint ? `（${err.hint}）` : ""));
    } finally {
      setBusy(button, false);
    }
  });
  root.querySelector("[data-target-history-list]")?.addEventListener("click", async (event) => {
    const actionEl = event.target.closest("[data-history-act]");
    if (!actionEl) return;
    const item = actionEl.closest("[data-history-name]");
    const name = item?.dataset.historyName;
    if (!name) return;
    const action = actionEl.dataset.historyAct;
    if (action === "append") {
      setBusy(actionEl, true, "加入中…");
      try {
        const result = await api.appendTargetHistory(name);
        await refreshSequence();
        const missing = (result.missing || []).length;
        toastOk("已加入当前序列", `请求 ${result.requested} 个，实际新增 ${result.added} 个${missing ? `，${missing} 个不在 catalog` : ""}`);
      } catch (err) {
        toastErr("加入失败", err.message + (err.hint ? `（${err.hint}）` : ""));
      } finally {
        setBusy(actionEl, false);
      }
      return;
    }
    if (action === "delete") {
      const ok = await confirmDialog({
        title: "删除历史靶机配置",
        message: `确定删除 ${name}？`,
        detail: "只删除本地存档，不影响游戏内收藏标靶。",
        confirmText: "删除",
        danger: true,
      });
      if (!ok) return;
      try {
        const result = await api.deleteTargetHistory(name);
        toastOk("已删除", name);
        if (result.history) {
          historyData = result.history;
          renderTargetHistory();
        }
      } catch (err) {
        toastErr("删除失败", err.message);
      }
    }
  });
  root.querySelectorAll('[data-act="refresh"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      setBusy(target, true, "刷新中…");
      try {
        await Promise.allSettled([loadSettings(), refreshStatus(), loadCreds(), loadCurrent(), refreshHealth()]);
      } finally {
        setBusy(target, false);
      }
    }),
  );
  root.querySelectorAll('[data-act="start"]').forEach((button) =>
    button.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const inputPort = validPort(root.querySelector("[data-port-input]")?.value);
      if (inputPort === null) {
        toastErr("端口不合法", `请输入 ${PORT_MIN}-${PORT_MAX} 之间的整数。`);
        return;
      }
      if (inputPort !== currentPort) {
        // 输入框里改了但没点保存：直接用当前输入值启动，并顺手保存
        try {
          await api.saveSettings({ capture_port: inputPort });
          currentPort = setCapturePort(inputPort);
          applyPortUi();
          toast({ title: `抓包端口已切换为 ${currentPort}`, type: "info" });
        } catch (err) {
          toastErr("保存端口失败", err.message);
          return;
        }
      }
      setBusy(target, true, "启动中…");
      try {
        const mode = root.querySelector("[data-capture-mode]")?.value || "pc";
        const region = root.querySelector("[data-capture-region]")?.value || "cn";
        if (mode === "emulator") {
          const emuPort = validPort(root.querySelector("[data-emu-port]")?.value);
          if (emuPort === null) {
            toastErr("端口不合法", `请输入 ${PORT_MIN}-${PORT_MAX} 之间的整数。`);
            return;
          }
          const listenHost = root.querySelector("[data-listen-host]")?.value || "0.0.0.0";
          const status = await api.captureStart({
            mode: "emulator",
            region,
            port: emuPort,
            listen_host: listenHost,
            set_proxy: false,
            auto_restore_proxy: false,
          });
          applyStatus(status);
          if (status.error) {
            toastErr("模拟器抓包启动失败", status.error);
          } else {
            toastOk("模拟器抓包已启动", `监听 ${listenHost}:${emuPort}。请在模拟器 Wi-Fi 代理填写 PC 局域网 IP:${emuPort} 并安装 CA。`);
          }
          return;
        }
        const status = await api.captureStart({ port: currentPort, mode: "pc", set_proxy: true, auto_restore_proxy: true });
        applyStatus(status);
        toastOk("抓包代理已启动", `端口 ${currentPort}。下一步：设置代理并重启游戏，然后登录到主界面。`);
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
        message: `将把系统代理指向 ${proxyAddr()}，强杀游戏进程并重新启动。`,
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
  const activeSession = state === "running" || state === "starting";
  // 端口来源：抓取进行中用 status.port；空闲时以 /api/settings 的 capture_port 为准
  // （gflh 的 capture_status 在 idle 时会回落到默认 18080，不能用它覆盖用户设置）
  const statusPort = activeSession ? validPort(status.port) || currentPort : currentPort;
  if (activeSession && validPort(status.port) && status.port !== currentPort) {
    currentPort = setCapturePort(status.port);
    applyPortUi();
  }
  const emulatorMode = status.mode === "emulator";
  const proxyText = !status.proxy_active
    ? "未开启"
    : emulatorMode
      ? `${status.listen_host || "0.0.0.0"}:${statusPort}`
      : proxyAddr(statusPort);

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
  setText("[data-cap-proxy]", proxyText, status.proxy_active ? "warn" : "idle");
  const elapsedEl = rootEl.querySelector("[data-cap-elapsed]");
  if (elapsedEl) elapsedEl.textContent = `ELAPSED ${fmtDuration(status.elapsed_s)}`;
  const portEl = rootEl.querySelector("[data-cap-port]");
  if (portEl) portEl.textContent = String(statusPort);

  // 端口输入框：抓取进行中禁用并显示实际端口，空闲时显示用户设置值
  const input = rootEl.querySelector("[data-port-input]");
  if (input) {
    input.disabled = activeSession;
    if (!activeSession && document.activeElement !== input) {
      input.value = String(currentPort);
    } else if (activeSession) {
      input.value = String(statusPort);
    }
  }
  const savePortBtn = rootEl.querySelector('[data-act="save-port"]');
  if (savePortBtn) savePortBtn.disabled = activeSession;

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
  rootEl.querySelectorAll('[data-act="start"]').forEach((button) => {
    button.disabled = state === "running" || state === "starting";
  });
  rootEl.querySelectorAll('[data-act="restart-game"]').forEach((button) => {
    button.disabled = emulatorMode || !(state === "running" || state === "starting");
  });
  rootEl.querySelectorAll('[data-act="stop"]').forEach((button) => {
    button.disabled = !(state === "running" || state === "starting");
  });
  const hintEl = rootEl.querySelector("[data-cap-hint]");
  if (hintEl) {
    if (state === "running" && !status.uid) {
      hintEl.innerHTML = `${icon("info", 12)} 抓包代理运行中（${esc(proxyAddr(statusPort))}）。请点「设置代理并重启游戏」，然后在游戏里正常登录到主界面。`;
    } else if (state === "running" && status.uid && !status.targets_captured) {
      hintEl.innerHTML = `${icon("info", 12)} 已抓到 uid=${esc(status.uid)}，正在读取收藏标靶列表…`;
    } else if (status.targets_captured && state !== "stopped") {
      hintEl.innerHTML = `${icon("check", 12)} 抓取完成：uid=${esc(status.uid)} · 靶机 ${status.targets_count} 条。点「完成并关闭代理」写入凭证。`;
    } else if (state === "stopped") {
      hintEl.innerHTML = `${icon("check", 12)} 抓取已完成、代理已关闭。可以去关卡图鉴挑队伍，或到序列页执行注入。`;
    } else {
      hintEl.innerHTML = `${icon("info", 12)} 提示：8080 常被其它程序占用，抓包端口默认 ${DEFAULT_PORT}，可在上方修改（${PORT_MIN}-${PORT_MAX}）。如果游戏进不去，先检查 Windows 系统代理是否已关闭（可能残留 ${esc(proxyAddr(statusPort))}）。`;
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
async function loadTargetHistory() {
  try {
    const data = await api.targetHistory();
    historyData = data.history || [];
    historyDir = data.dir || "";
    const dirEl = rootEl?.querySelector("[data-history-dir]");
    if (dirEl && historyDir) dirEl.textContent = historyDir;
    renderTargetHistory();
  } catch (err) {
    const listEl = rootEl?.querySelector("[data-target-history-list]");
    if (listEl) listEl.innerHTML = `<div class="plan-empty" style="padding:12px">历史靶机配置读取失败：${esc(err.message)}</div>`;
  }
}

function renderTargetHistory() {
  const listEl = rootEl?.querySelector("[data-target-history-list]");
  if (!listEl) return;
  const items = historyData || [];
  if (!items.length) {
    listEl.innerHTML = `<div class="plan-empty" style="padding:12px">暂无历史批次。抓到当前靶机后点「保存当前靶机批次」。</div>`;
    return;
  }
  listEl.innerHTML = items.map((item) => `
    <div class="target-history-item" data-history-name="${esc(item.name)}" style="padding:9px 10px;border:1px solid var(--line);border-radius:8px;margin-bottom:7px;background:rgba(8,16,34,.5)">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="badge mono">${esc(item.created_at || item.name)}</span>
        <span style="font-size:11px" class="text-mute">${Number(item.count) || 0} 个靶机</span>
        ${item.uid ? `<span style="font-size:10.5px" class="text-mute">uid ${esc(item.uid)}</span>` : ""}
      </div>
      <div style="font-size:10.5px;margin-top:4px;word-break:break-all" class="text-mute">${esc(item.base_url || item.name)}</div>
      <div style="display:flex;gap:6px;margin-top:6px">
        <button class="btn btn-xs btn-cyan" type="button" data-history-act="append">${icon("plus", 10)} 全部加入序列</button>
        <button class="btn btn-xs btn-ghost" type="button" data-history-act="delete">${icon("trash", 10)} 删除</button>
      </div>
    </div>
  `).join("");
}

async function loadCreds() {
  try {
    const data = await api.credProfiles();
    credsData = data.profiles || [];
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
    listEl.innerHTML = `<div class="plan-empty" style="padding:16px">暂无分类凭证，先完成一次登录抓取。</div>`;
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
          <span class="cred-name">${esc(cred.title || cred.name)}</span>
          <span class="cred-sub">
            <span>uid ${esc(cred.uid || "—")}</span>
            <span>${cred.targets_count ?? 0} 个靶机</span>
            <span>${esc(cred.updated_at ? timeAgo(cred.updated_at) : "—")}</span>
          </span>
        </span>
        <span class="badge green">最新</span>
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

async function applyDataDir() {
  if (!rootEl || !rootEl.isConnected) return;
  let dir = store.health?.data_dir || "";
  if (!dir) {
    try {
      const health = await refreshHealth();
      dir = health?.data_dir || "";
    } catch {
      dir = "";
    }
  }
  const el = rootEl.querySelector("[data-data-dir]");
  if (el) el.textContent = dir || "默认 <GF Forge>/dataMiner/derived/targetforge（TARGETFORGE_DATA_DIR 可覆盖）";
}

/* ------------------------------------------------------------------ */
/* 当前靶机 + 效能筛选（先补齐队伍数据，再本地筛选/排序）             */
/* ------------------------------------------------------------------ */
async function loadCurrent() {
  const areaEl = rootEl?.querySelector("[data-current-targets]");
  if (!areaEl) return;
  try {
    const data = await refreshCurrent("auto");
    currentData = data;
    renderCurrent();
    ensureTargetData(data.targets || []);
  } catch (err) {
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
    const pfMeta = rootEl?.querySelector("[data-pf-meta]");
    if (pfMeta) pfMeta.textContent = "";
  }
}

function targetEntries() {
  const targets = currentData?.targets || [];
  return targets.map((item) => ({
    order: item.order,
    team: item.team,
    data: teamCache.get(Number(item.team)) || null,
  }));
}

function currentSortValue(entry) {
  const disp = powerDisplay(entry.data?.power, entry.data?.power_known);
  return disp.known ? disp.value : null;
}

function filterCurrentEntries(entries, state) {
  const mode = state?.mode || "all";
  const min = state?.min === "" || state?.min === undefined ? null : Number(state.min);
  const max = state?.max === "" || state?.max === undefined ? null : Number(state.max);
  let filtered = entries;
  if (mode === "known") {
    filtered = entries.filter((entry) => currentSortValue(entry) !== null);
  } else if (mode === "custom") {
    filtered = entries.filter((entry) => {
      const value = currentSortValue(entry);
      if (value === null) return false;
      if (min !== null && Number.isFinite(min) && value < min) return false;
      if (max !== null && Number.isFinite(max) && value > max) return false;
      return true;
    });
  }
  const sort = state?.sort || "default";
  const sorted = filtered.slice();
  if (sort === "power_desc") {
    sorted.sort((a, b) => (currentSortValue(b) ?? -Infinity) - (currentSortValue(a) ?? -Infinity));
  } else if (sort === "power_asc") {
    sorted.sort((a, b) => (currentSortValue(a) ?? Infinity) - (currentSortValue(b) ?? Infinity));
  } else if (sort === "hp_desc") {
    sorted.sort((a, b) => (Number(b.data?.hp_total) || 0) - (Number(a.data?.hp_total) || 0));
  } else if (sort === "units_desc") {
    sorted.sort((a, b) => (Number(b.data?.units) || 0) - (Number(a.data?.units) || 0));
  }
  return sorted;
}

function targetsNeedData(entries) {
  const filterActive = currentFilter.mode !== "all" || (currentFilter.sort && currentFilter.sort !== "default");
  if (!filterActive) return entries.filter((entry) => !entry.data).length > 0;
  return entries.some((entry) => entry.data === undefined || entry.data === null);
}

async function ensureTargetData(targets) {
  if (targetDataLoading) return;
  const ids = [...new Set((targets || []).map((item) => Number(item.team)))].filter(
    (id) => Number.isFinite(id) && !teamCache.has(id),
  );
  if (!ids.length) return;
  targetDataLoading = true;
  try {
    const queue = ids.slice();
    const worker = async () => {
      while (queue.length) {
        const teamId = queue.shift();
        if (teamCache.has(teamId)) continue;
        try {
          const team = await api.team(teamId);
          teamCache.set(teamId, team);
        } catch {
          teamCache.set(teamId, null);
        }
      }
    };
    await Promise.all(Array.from({ length: 5 }, worker));
  } finally {
    targetDataLoading = false;
  }
  if (rootEl && rootEl.isConnected) renderCurrent();
}

function renderCurrent() {
  const areaEl = rootEl?.querySelector("[data-current-targets]");
  if (!areaEl) return;
  const targets = currentData?.targets || [];
  const countEl = rootEl?.querySelector("[data-current-count]");
  if (countEl) countEl.textContent = `${targets.length} / 35`;
  const pfMeta = rootEl?.querySelector("[data-pf-meta]");
  if (!targets.length) {
    if (pfMeta) pfMeta.textContent = "";
    areaEl.innerHTML = emptyState({
      iconName: "target",
      title: "当前靶机列表为空",
      desc: "抓取成功但游戏内没有收藏标靶，可以直接编排序列后使用「追加」模式。",
    });
    return;
  }

  const entries = targetEntries();
  const missing = targetsNeedData(entries);
  if (missing && (currentFilter.mode !== "all" || (currentFilter.sort && currentFilter.sort !== "default"))) {
    if (pfMeta) pfMeta.textContent = "正在读取当前靶机的效能数据…";
    areaEl.innerHTML = skeletonRows(3);
    ensureTargetData(targets);
    return;
  }

  const filtered = filterCurrentEntries(entries, currentFilter);
  if (pfMeta) {
    const modeText = { all: "全部", known: "仅看有标注", custom: "自定义效能区间" }[currentFilter.mode] || "全部";
    pfMeta.textContent = `${modeText} · 当前显示 ${filtered.length} / ${targets.length}`;
  }
  if (!filtered.length) {
    areaEl.innerHTML = emptyState({
      iconName: "search",
      title: "没有符合效能条件的靶机",
      desc: "当前靶机大多未标注效能（常规队伍），试试切回「全部」或缩小筛选范围。",
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
      ${filtered
        .map((entry) => {
          const team = entry.data;
          const disp = powerDisplay(team?.power, team?.power_known);
          const species = (team?.species || []).slice(0, 1).map((item) => item.name).join("");
          const extra = team
            ? `${disp.known ? `效能 ${disp.text}` : "未标注效能"}${species ? ` · ${species}` : ""}`
            : "…";
          return `
        <div class="target-item ${duplicates[entry.order] ? "dup" : ""}" data-current-team="${entry.team}">
          <span class="target-order">${esc(entry.order)}</span>
          <span class="target-team">team ${esc(entry.team)}</span>
          <span class="target-extra ${disp.negative ? "neg" : ""}" ${disp.negative ? 'title="积分关卡数据，可能为负"' : ""}>${esc(extra)}</span>
        </div>`;
        })
        .join("")}
    </div>
    <div class="param-note" style="margin-top:10px">
      uid ${esc(currentData?.uid || "—")} · 来源 ${esc(currentData?.source || "—")}
      ${currentData?.captured_at ? ` · 抓取于 ${esc(fmtTime(currentData.captured_at, true))}` : ""}
      · 上限 ${currentData?.max_targets || 35} · 效能口径：0 = 未标注（常规队伍），负值来自积分关卡数据
    </div>
  `;
  areaEl.querySelectorAll("[data-current-team]").forEach((el) => {
    el.addEventListener("click", () => {
      window.location.hash = `#/teams/${el.dataset.currentTeam}`;
    });
  });
}

/* ------------------------------------------------------------------ */
/* 游戏客户端卡片：显示路径/来源/进程状态，支持自动检测/浏览/应用并重建 */
/* ------------------------------------------------------------------ */
async function loadGameClientCard() {
  const host = rootEl?.querySelector("[data-game-client]");
  if (!host) return;
  try {
    const status = await fetchGameStatus();
    host.innerHTML = gameClientCardHtml(status);
    if (status && status.missing?.length) {
      const el = host.querySelector("[data-game-error]");
      if (el) {
        el.textContent = gameErrorMessage(null);
        el.classList.remove("hidden");
      }
    }
    bindGameClientCard(host, status);
  } catch (err) {
    host.innerHTML = gameClientCardHtml(null);
    const el = host.querySelector("[data-game-error]");
    if (el) {
      el.textContent = gameErrorMessage(err, "读取游戏客户端状态失败");
      el.classList.remove("hidden");
    }
  }
}

function setGameCardError(host, message) {
  const el = host.querySelector("[data-game-error]");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("hidden", !message);
}

function bindGameClientCard(host, status) {
  if (!host || !status) return;
  const input = host.querySelector("[data-game-path-input]");
  const detectBtn = host.querySelector("[data-game-detect]");
  const pickBtn = host.querySelector("[data-game-pick]");
  const applyBtn = host.querySelector("[data-game-apply]");

  detectBtn?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "检测中…");
    setGameCardError(host, "");
    try {
      const data = await detectGameClient();
      const candidates = Array.isArray(data.candidates) ? data.candidates : [];
      const detected = data.detected;
      const detectedPath =
        (typeof detected === "string" ? detected : detected?.path) ||
        candidates.find((item) => item.valid !== false)?.path ||
        "";
      if (detectedPath) {
        if (input) input.value = detectedPath;
        toastOk("已检测到客户端", detectedPath);
      } else {
        toastErr("未检测到候选", "没有自动检测到客户端目录，请点「浏览…」手动选择。");
        setGameCardError(host, "自动检测未找到客户端目录，请点「浏览…」选择或手动输入。");
      }
    } catch (err) {
      const msg = gameErrorMessage(err, "自动检测失败");
      setGameCardError(host, `自动检测失败：${msg}`);
      toastErr("自动检测失败", msg);
    } finally {
      setBusy(button, false);
    }
  });

  pickBtn?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "打开选择框…");
    setGameCardError(host, "");
    try {
      const data = await pickGameClient();
      const path = String(data.path || "").trim();
      if (!path) throw new Error("未返回文件夹路径");
      if (input) input.value = path;
      toastOk("已选择文件夹，点「应用并重建数据」生效");
    } catch (err) {
      const msg = /取消|cancel/i.test(gameErrorMessage(err, "")) ? "已取消选择文件夹" : gameErrorMessage(err, "无法打开文件夹选择框");
      setGameCardError(host, msg);
      toastErr("浏览文件夹失败", msg);
    } finally {
      setBusy(button, false);
    }
  });

  applyBtn?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const path = String(input?.value || "").trim();
    if (!path) {
      setGameCardError(host, "请输入游戏客户端目录，或点「浏览…」选择。");
      toastErr("请选择客户端目录", "路径不能为空。");
      return;
    }
    setBusy(button, true, "校验中…");
    setGameCardError(host, "");
    try {
      const next = await confirmGameClient(path);
      if (next.valid === false && next.missing?.length) {
        throw Object.assign(new Error(gameErrorMessage(null)), { payload: { missing: next.missing } });
      }
      toastOk("游戏客户端已保存", "正在重建游戏数据索引…");
      const ready = await refreshCatalogForGame();
      try {
        await refreshHealth();
        await loadChapters();
      } catch {
        /* 忽略 */
      }
      await loadGameClientCard();
      if (ready) toastOk("游戏数据已刷新", "目录已更新，数据索引已就绪。");
      else toastErr("数据重建超时", "游戏数据索引可能仍在构建，请稍后点顶栏刷新状态。");
    } catch (err) {
      const msg = gameErrorMessage(err, "客户端目录无效，请重新选择");
      setGameCardError(host, msg);
      toastErr("客户端目录无效", msg);
    } finally {
      setBusy(button, false);
    }
  });
}
