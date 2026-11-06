/* execute-modal.js —— 执行向导：模式选择 → 预览计划 → 执行 job → 大退重登引导 */
import { api } from "../api.js";
import { store, refreshSequence, tryRefreshCurrent, sequenceStats } from "../store.js";
import { icon, openModal, setBusy, toast, toastOk, toastErr, confirmDialog, logLineHtml } from "../ui.js";
import { esc, fmtNum, fmtTime, fmtDate } from "../util.js";

const MODES = [
  {
    id: "append",
    title: "追加",
    code: "append",
    desc: "不动现有靶机，接在最大编号后面；已存在的队伍自动跳过。",
  },
  {
    id: "replace",
    title: "按序号替换",
    code: "replace",
    desc: "草稿第 1 个替换收藏標靶1、第 2 个替换 2…；当前多出的保留，草稿更长则追加到末尾。",
  },
  {
    id: "rebuild",
    title: "清空重排",
    code: "rebuild",
    desc: "先删光现有靶机，再按草稿 1..N 全量重建；编号最干净，推荐一次配好整套。",
  },
];

const SOURCES = [
  { id: "auto", label: "自动（优先最新凭证）" },
  { id: "creds", label: "凭证文件 creds_latest.json" },
  { id: "state", label: "本地注入状态 state" },
];

export function openExecuteModal(options = {}) {
  const clearEntry = Boolean(options.clearEntry);
  const view = {
    step: "config", // config | preview | job | done
    mode: clearEntry ? "clear" : MODES.some((mode) => mode.id === options.mode) ? options.mode : "append",
    source: "auto",
    dryRun: false,
    plan: null,
    jobId: null,
    job: null,
    timer: 0,
    restartBusy: false,
    clearAck: false,
    error: "",
  };

  const handle = openModal({
    title: clearEntry ? "清空游戏内全部收藏标靶" : "执行注入 · 靶机编排",
    subtitle: clearEntry ? "危险操作 · 需二次确认" : "预览计划 → 选择模式 → 执行 → 大退重登",
    iconName: clearEntry ? "alert" : "play",
    width: "wide",
    body: '<div data-exec-body></div>',
    footer: '<div class="spacer"></div>',
    onClose: () => {
      if (view.timer) clearInterval(view.timer);
    },
  });

  const bodyEl = handle.body.querySelector("[data-exec-body]");

  function stopPolling() {
    if (view.timer) {
      clearInterval(view.timer);
      view.timer = 0;
    }
  }

  function seqSummary() {
    const stats = sequenceStats();
    const draft = store.sequence?.draft || [];
    const hasInvalid = draft.some((team) => !team || !team.id);
    return { ...stats, hasInvalid };
  }

  function errorBox() {
    if (!view.error) return "";
    return `<div class="warn-box" style="border-color:rgba(239,83,80,.4);border-left-color:var(--red);background:rgba(239,83,80,.07);color:#ffb3b1">
      <b>${icon("alert", 12)} 操作失败</b>${esc(view.error)}
    </div>`;
  }

  /* ---------------- 步骤 1：配置 ---------------- */
  function renderConfig() {
    const summary = seqSummary();
    const empty = summary.count === 0;
    const modeHtml = MODES.map(
      (mode) => `
      <button class="mode-option ${view.mode === mode.id ? "active" : ""}" type="button" data-mode="${mode.id}" ${clearEntry ? "disabled" : ""}>
        <span class="mo-radio"></span>
        <span class="mo-body">
          <span class="mo-title">${mode.title}<span class="mo-code">${mode.code}</span></span>
          <span class="mo-desc">${mode.desc}</span>
        </span>
      </button>`,
    ).join("");

    bodyEl.innerHTML = `
      ${
        clearEntry
          ? `<div class="warn-box" style="margin:0 0 16px;border-left-color:var(--red);border-color:rgba(239,83,80,.45);background:rgba(239,83,80,.07);color:#ffb3b1">
               <b>${icon("alert", 12)} 危险操作</b>
               这会向游戏发送 <b>Targettrain/delCollect</b>，删除当前全部收藏标靶。
               删除后 <b>必须强退游戏（大退）再重新登录</b>，否则进入靶机界面可能卡死。
             </div>`
          : ""
      }
      <div class="subhead">${icon("layers", 12)} 序列草稿 <span class="badge amber">${summary.count} / ${summary.max}</span></div>
      <div class="plan-grid" style="grid-template-columns:repeat(3,1fr)">
        <div class="plan-stat"><div class="ps-label">${icon("layers", 11)} 草稿队伍</div><div class="ps-value" style="color:var(--text)">${summary.count}</div></div>
        <div class="plan-stat"><div class="ps-label">${icon("zap", 11)} 总效能</div><div class="ps-value" style="color:var(--amber);font-size:20px">${fmtNum(summary.power)}</div></div>
        <div class="plan-stat"><div class="ps-label">${icon("users", 11)} 总单位</div><div class="ps-value" style="color:var(--text-2);font-size:20px">${summary.units}</div></div>
      </div>
      ${empty && !clearEntry ? `<div class="warn-box"><b>序列是空的</b>先去关卡图鉴或怪种图鉴挑选队伍加入序列，再来执行。</div>` : ""}

      <div class="subhead">${icon("sliders", 12)} 执行模式</div>
      ${
        clearEntry
          ? `<div class="mode-option danger active"><span class="mo-radio"></span><span class="mo-body"><span class="mo-title">清空全部<a class="mo-code">clear</a></span><span class="mo-desc">删除当前全部收藏标靶（不新增）。</span></span></div>`
          : `<div class="mode-list">${modeHtml}</div>`
      }

      <div class="subhead">${icon("database", 12)} 数据来源</div>
      <select class="select" data-source style="width:100%;height:34px">
        ${SOURCES.map((source) => `<option value="${source.id}" ${view.source === source.id ? "selected" : ""}>${source.label}</option>`).join("")}
      </select>
      <div class="param-note">「当前靶机」来自登录抓取得到的凭证或本地注入状态；只有拿到真实靶机列表，才能计算删除 / 保留。</div>

      <div class="check-row" style="margin-top:14px">
        <input type="checkbox" id="exec-dry" ${view.dryRun ? "checked" : ""}/>
        <label for="exec-dry" style="flex:1;cursor:pointer"><b>演练模式（dry-run）</b><br><span style="font-size:10.5px;color:var(--text-mute)">只生成计划并打印日志，不发送任何请求。强烈建议第一次先演练。</span></label>
        <span class="check-hint">不发请求</span>
      </div>

      ${
        clearEntry
          ? `<label class="check-row" style="margin-top:10px;border-color:rgba(239,83,80,.35)">
               <input type="checkbox" data-clear-ack ${view.clearAck ? "checked" : ""}/>
               <span style="flex:1"><b style="color:#ffb3b1">我明白这会删除游戏内全部收藏标靶</b><br><span style="font-size:10.5px;color:var(--text-mute)">删除后需要大退重登游戏同步。</span></span>
             </label>`
          : ""
      }
      ${errorBox()}
    `;

    bodyEl.querySelectorAll("[data-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        view.mode = button.dataset.mode;
        view.error = "";
        renderConfig();
      });
    });
    bodyEl.querySelector("[data-source]")?.addEventListener("change", (event) => {
      view.source = event.target.value;
    });
    bodyEl.querySelector("#exec-dry")?.addEventListener("change", (event) => {
      view.dryRun = event.target.checked;
    });
    bodyEl.querySelector("[data-clear-ack]")?.addEventListener("change", (event) => {
      view.clearAck = event.target.checked;
      renderFoot();
    });

    renderFoot();
  }

  function renderFoot() {
    if (view.step === "config") {
      const summary = seqSummary();
      const disabled = (!clearEntry && summary.count === 0) || (clearEntry && !view.clearAck);
      handle.foot.innerHTML = `
        <button class="btn btn-ghost" type="button" data-act="close">取消</button>
        <div class="spacer"></div>
        <button class="btn btn-primary" type="button" data-act="preview" ${disabled ? "disabled" : ""}>
          ${icon("eye", 14)} 预览执行计划
        </button>
      `;
      handle.foot.querySelector('[data-act="close"]').addEventListener("click", () => handle.close());
      handle.foot.querySelector('[data-act="preview"]').addEventListener("click", () => doPreview());
    }
  }

  /* ---------------- 步骤 2：预览 ---------------- */
  async function doPreview() {
    const button = handle.foot.querySelector('[data-act="preview"]');
    setBusy(button, true, "计算中…");
    view.error = "";
    try {
      const plan = await api.preview({ mode: view.mode, source: view.source });
      view.plan = plan;
      view.step = "preview";
      renderPreview();
    } catch (err) {
      view.error = err.message + (err.hint ? `（${err.hint}）` : "");
      setBusy(button, false);
      renderConfigError();
    }
  }

  function renderConfigError() {
    // 保持在配置步骤，仅刷新错误提示
    const box = bodyEl.querySelector(".warn-box:last-child");
    bodyEl.insertAdjacentHTML("beforeend", errorBox());
    if (box) box.remove();
    renderFoot();
  }

  function planListHtml(items, cls, orderKey = "order", teamKey = "team") {
    if (!items || !items.length) return '<div class="plan-empty">无</div>';
    return items
      .map(
        (item) => `
        <div class="plan-item ${cls}">
          <span class="pi-order">#${esc(item[orderKey])}</span>
          <span class="pi-team">team ${esc(item[teamKey])}</span>
        </div>`,
      )
      .join("");
  }

  function finalListHtml(items) {
    if (!items || !items.length) return '<div class="plan-empty">无</div>';
    return items
      .map(
        (item) => `
        <div class="plan-item keep">
          <span class="pi-order">${esc(item.order)}</span>
          <span class="pi-team">收藏標靶${esc(item.order)}</span>
          <span class="pi-tag text-mute">team ${esc(item.team)}</span>
        </div>`,
      )
      .join("");
  }

  function renderPreview() {
    const plan = view.plan || {};
    const warnings = plan.warnings || [];
    const valid = plan.valid !== false;
    const current = plan.current || {};
    const modeInfo = MODES.find((mode) => mode.id === view.mode);
    const clear = view.mode === "clear";
    const planDeletes = plan.deletes || [];
    const planAdds = plan.adds || [];
    const planKept = plan.kept || [];
    const planFinal = plan.final || [];

    bodyEl.innerHTML = `
      <div class="info-strip">
        ${icon("eye", 14)}
        <span>模式 <b>${clear ? "清空全部" : esc(modeInfo?.title || view.mode)}</b> · 数据来源 <b>${esc(view.source)}</b> · 当前靶机 <b>${(current.targets || []).length}</b> 条${view.dryRun ? ' · <b style="color:var(--amber)">演练模式</b>' : ""}</span>
        <span class="spacer"></span>
        <span class="mono-inline" style="font-size:10px;color:var(--text-mute)">凭证 ${esc(current.creds_file || "—")} · uid ${esc(current.uid || "—")}</span>
      </div>
      ${
        current.duplicate_orders && Object.keys(current.duplicate_orders).length
          ? `<div class="warn-box"><b>当前靶机存在重复编号</b>${Object.entries(current.duplicate_orders)
              .slice(0, 6)
              .map(([order, teams]) => `编号 ${esc(order)}：team ${esc((teams || []).join(", "))}`)
              .join("；")}。建议用「清空重排」修复。</div>`
          : ""
      }
      <div class="plan-grid">
        <div class="plan-stat del"><div class="ps-label">${icon("trash", 11)} 将删除</div><div class="ps-value">${planDeletes.length}</div></div>
        <div class="plan-stat add"><div class="ps-label">${icon("plus", 11)} 将新增</div><div class="ps-value">${planAdds.length}</div></div>
        <div class="plan-stat keep"><div class="ps-label">${icon("check", 11)} 保留</div><div class="ps-value">${planKept.length}</div></div>
      </div>
      <div class="plan-cols">
        <div class="plan-block">
          <div class="plan-block-head">${icon("trash", 11)} 删除（delCollect）<span class="cnt">${planDeletes.length} 条</span></div>
          <div class="plan-list">${planListHtml(planDeletes, "del")}</div>
        </div>
        <div class="plan-block">
          <div class="plan-block-head">${icon("plus", 11)} 新增（addCollect）<span class="cnt">${planAdds.length} 条</span></div>
          <div class="plan-list">${planListHtml(planAdds, "add")}</div>
        </div>
        <div class="plan-block">
          <div class="plan-block-head">${icon("check", 11)} 保留现有<span class="cnt">${planKept.length} 条</span></div>
          <div class="plan-list">${planListHtml(planKept, "keep")}</div>
        </div>
        <div class="plan-block">
          <div class="plan-block-head">${icon("flag", 11)} 执行后最终列表<span class="cnt">${planFinal.length} 条</span></div>
          <div class="plan-list">${finalListHtml(planFinal)}</div>
        </div>
      </div>
      ${
        warnings.length
          ? `<div class="warn-box"><b>${icon("alert", 12)} 注意事项（${warnings.length}）</b><ul>${warnings
              .slice(0, 8)
              .map((text) => `<li>${esc(text)}</li>`)
              .join("")}</ul></div>`
          : ""
      }
      ${
        !valid
          ? `<div class="warn-box" style="border-left-color:var(--red);border-color:rgba(239,83,80,.4);background:rgba(239,83,80,.07);color:#ffb3b1"><b>计划不合法，无法执行</b>请先修正序列或改用其它模式。</div>`
          : ""
      }
      ${errorBox()}
    `;

    handle.foot.innerHTML = `
      <button class="btn btn-ghost" type="button" data-act="back">${icon("chevronLeft", 13)} 返回修改</button>
      <div class="spacer"></div>
      <button class="btn ${view.dryRun ? "btn-cyan" : clear ? "btn-danger" : "btn-primary"}" type="button" data-act="run" ${valid ? "" : "disabled"}>
        ${icon("play", 14)} ${view.dryRun ? "开始演练" : clear ? "确认清空" : "确认执行"}
      </button>
    `;
    handle.foot.querySelector('[data-act="back"]').addEventListener("click", () => {
      view.step = "config";
      view.error = "";
      renderConfig();
    });
    handle.foot.querySelector('[data-act="run"]').addEventListener("click", (event) => doExecute(event.currentTarget));
  }

  /* ---------------- 步骤 3：执行中 ---------------- */
  async function doExecute(button) {
    setBusy(button, true, "提交中…");
    view.error = "";
    try {
      const body = { mode: view.mode, source: view.source, dry_run: view.dryRun };
      const response = await api.execute(body);
      view.jobId = response.job_id;
      view.step = "job";
      view.job = {
        id: response.job_id,
        state: "running",
        logs: [{ t: new Date().toISOString(), level: "info", text: "任务已提交，等待执行…" }],
      };
      renderJob();
      startPolling();
    } catch (err) {
      view.error = err.message + (err.hint ? `（${err.hint}）` : "");
      setBusy(button, false);
      if (view.step === "preview") renderPreview();
      else renderConfigError();
    }
  }

  function startPolling() {
    stopPolling();
    view.timer = setInterval(async () => {
      if (!view.jobId) return;
      try {
        const job = await api.job(view.jobId);
        view.job = job;
        updateJobUi(job);
        if (job.state !== "running") {
          stopPolling();
          if (job.state === "done") {
            view.step = "done";
            renderDone(job);
            refreshSequence().catch(() => {});
            tryRefreshCurrent();
            store.emit("executed", job);
          } else {
            view.error = job.error || "执行失败";
            renderJobError(job);
          }
        }
      } catch (err) {
        view.error = err.message;
        renderJobError(view.job);
        stopPolling();
      }
    }, 700);
  }

  function jobProgress(job) {
    if (!job) return 0;
    if (job.state === "done") return 100;
    const logs = job.logs || [];
    return Math.min(92, 10 + logs.length * 9);
  }

  function jobConsoleHtml(job) {
    const logs = job.logs || [];
    if (!logs.length) return '<div class="log-empty">等待日志输出…</div>';
    return logs.map((log) => logLineHtml(log)).join("");
  }

  function jobStatusChip(job) {
    if (!job || job.state === "running") return `<span class="job-status-chip running"><span class="spinner"></span> 执行中</span>`;
    if (job.state === "done") return `<span class="job-status-chip done">${icon("check", 12)} 已完成</span>`;
    return `<span class="job-status-chip error">${icon("alert", 12)} 失败</span>`;
  }

  function renderJob() {
    const job = view.job || { state: "running", logs: [] };
    bodyEl.innerHTML = `
      <div class="job-panel">
        <div class="job-status-row">
          ${jobStatusChip(job)}
          <div class="job-progress"><i style="width:${jobProgress(job)}%"></i></div>
          <span class="job-elapsed">job ${esc(view.jobId || "")}</span>
        </div>
        <div class="job-console" data-job-console>${jobConsoleHtml(job)}</div>
        <div class="seq-hint mt12">${icon("info", 12)} ${view.dryRun ? "演练模式不会发送真实请求" : "执行期间请不要操作游戏；完成后需要大退重登同步"}</div>
      </div>
      ${errorBox()}
    `;
    scrollConsole();
    handle.foot.innerHTML = `
      <button class="btn btn-ghost" type="button" data-act="cancel-job">${icon("close", 13)} 取消执行</button>
      <div class="spacer"></div>
      <button class="btn btn-ghost" type="button" data-act="hide">关闭窗口（后台继续）</button>
    `;
    handle.foot.querySelector('[data-act="hide"]').addEventListener("click", () => handle.close());
    handle.foot.querySelector('[data-act="cancel-job"]').addEventListener("click", async () => {
      const ok = await confirmDialog({
        title: "取消执行",
        message: "会在当前步骤结束后停止；已经删除 / 新增的靶机不会回滚。",
        confirmText: "请求取消",
        danger: true,
      });
      if (!ok) return;
      try {
        await api.cancelJob(view.jobId);
        toast({ title: "已请求取消", text: "等待当前步骤结束", type: "warn" });
      } catch (err) {
        toastErr("取消失败", err.message);
      }
    });
  }

  function updateJobUi(job) {
    const consoleEl = bodyEl.querySelector("[data-job-console]");
    const progressEl = bodyEl.querySelector(".job-progress i");
    const statusEl = bodyEl.querySelector(".job-status-row .job-status-chip");
    if (consoleEl) {
      consoleEl.innerHTML = jobConsoleHtml(job);
      scrollConsole();
    }
    if (progressEl) progressEl.style.width = `${jobProgress(job)}%`;
    if (statusEl) {
      const tmp = document.createElement("div");
      tmp.innerHTML = jobStatusChip(job);
      statusEl.replaceWith(tmp.firstElementChild);
    }
  }

  function scrollConsole() {
    const consoleEl = bodyEl.querySelector("[data-job-console]");
    if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function renderJobError(job) {
    bodyEl.insertAdjacentHTML("beforeend", errorBox());
    handle.foot.innerHTML = `
      <button class="btn btn-ghost" type="button" data-act="close">关闭</button>
      <div class="spacer"></div>
      <button class="btn btn-primary" type="button" data-act="retry">返回配置重试</button>
    `;
    handle.foot.querySelector('[data-act="close"]').addEventListener("click", () => handle.close());
    handle.foot.querySelector('[data-act="retry"]').addEventListener("click", () => {
      view.step = "config";
      view.error = "";
      renderConfig();
    });
    updateJobUi(job || { state: "error", logs: [] });
  }

  /* ---------------- 步骤 4：完成 ---------------- */
  function renderDone(job) {
    const result = job.result?.execution || job.result || {};
    const plan = job.result?.plan || view.plan || {};
    const deleted = result.deleted ?? (plan.deletes || []).length;
    const added = result.added ?? (plan.adds || []).length;
    const failed = result.failed || [];
    const restartRequired = !view.dryRun && result.restart_required !== false;
    bodyEl.innerHTML = `
      <div class="plan-grid" style="grid-template-columns:repeat(3,1fr)">
        <div class="plan-stat del"><div class="ps-label">已删除</div><div class="ps-value">${deleted}</div></div>
        <div class="plan-stat add"><div class="ps-label">已新增</div><div class="ps-value">${added}</div></div>
        <div class="plan-stat ${failed.length ? "del" : "keep"}"><div class="ps-label">失败</div><div class="ps-value" style="color:${failed.length ? "var(--red)" : "var(--green)"}">${failed.length}</div></div>
      </div>
      ${
        failed.length
          ? `<div class="warn-box" style="border-left-color:var(--red);border-color:rgba(239,83,80,.4);background:rgba(239,83,80,.07);color:#ffb3b1"><b>部分步骤失败</b><ul>${failed
              .slice(0, 8)
              .map((item) => `<li>${esc(item.step || "")} team ${esc(item.team ?? "")}：${esc(item.error || "")}</li>`)
              .join("")}</ul></div>`
          : ""
      }
      ${
        view.dryRun
          ? `<div class="restart-callout done" style="margin-top:16px"><h4>${icon("check", 16)} 演练完成</h4><p>演练模式没有发送任何真实请求，游戏内靶机保持不变。确认计划无误后可以关闭演练模式正式执行。</p></div>`
          : `<div class="restart-callout" style="margin-top:16px">
               <h4>${icon("alert", 17)} 大退重登游戏同步</h4>
               <p>靶机数据已写入服务器，但游戏客户端需要 <b>强退并重新登录</b> 才会刷新。
               请回到游戏，长按任务栏图标关闭游戏（或点下面的按钮强杀并重启），再重新登录；
               之后在 <b>靶机专训 → 收藏标靶</b> 里查看结果。</p>
               <div class="rc-actions">
                 <button class="btn btn-primary" type="button" data-act="restart-game">${icon("power", 14)} 重启游戏</button>
                 <span class="text-mute" style="font-size:10.5px;align-self:center">会强杀游戏进程（二次确认）</span>
               </div>
             </div>`
      }
      <div class="seq-hint mt12">${icon("info", 12)} 执行时间 ${esc(fmtTime(job.finished_at || new Date().toISOString(), true))} · 最终 ${(result.final || []).length} 条靶机</div>
      ${restartRequired ? "" : ""}
      ${errorBox()}
    `;
    handle.foot.innerHTML = `
      <button class="btn btn-ghost" type="button" data-act="done-close">完成</button>
      <div class="spacer"></div>
      <button class="btn btn-cyan" type="button" data-act="view-final">查看当前靶机</button>
    `;
    handle.foot.querySelector('[data-act="done-close"]').addEventListener("click", () => handle.close());
    handle.foot.querySelector('[data-act="view-final"]').addEventListener("click", () => {
      handle.close();
      window.location.hash = "#/overview";
    });
    bodyEl.querySelector('[data-act="restart-game"]')?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      if (view.restartBusy) return;
      const ok = await confirmDialog({
        title: "重启游戏",
        message: "将强杀 GrilsFrontLine.exe 进程并通过 Steam 重新启动游戏。请确认当前没有未保存的游戏进度。",
        detail: "如果游戏正在战斗中，重启可能导致战斗中断；建议先回到主界面。",
        confirmText: "强杀并重启",
        danger: true,
      });
      if (!ok) return;
      view.restartBusy = true;
      setBusy(button, true, "重启中…");
      try {
        const response = await api.restartGame({ wait_ready: true });
        toastOk("游戏已重启", response?.hint || "请在游戏内重新登录并进入主界面");
        button.outerHTML = `<span class="badge green" style="height:26px">${icon("check", 12)} 已发送重启指令</span>`;
      } catch (err) {
        toastErr("重启失败", err.message);
        setBusy(button, false);
      } finally {
        view.restartBusy = false;
      }
    });
  }

  // 首次渲染
  renderConfig();
  return handle;
}
