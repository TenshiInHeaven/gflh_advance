/* views/sequence-page.js —— 序列编排页：拖拽排序 / 模式选择 / 预览与执行入口 */
import { store, refreshSequence, sequenceStats, removeTeam, moveTeam, clearSequence, importCurrentSequence } from "../store.js";
import {
  icon,
  pageHeadHtml,
  sectionHeadHtml,
  toast,
  toastOk,
  toastErr,
  confirmDialog,
  setBusy,
  skeletonRows,
} from "../ui.js";
import { esc, fmtNum, factionColor, navigate, powerDisplay } from "../util.js";
import { bindDragSort } from "../components/drag-sort.js";
import { addByIdHtml, bindAddById } from "../components/add-by-id.js";
import { openExecuteModal } from "../components/execute-modal.js";

const MODES = [
  { id: "append", title: "追加", desc: "接在现有最大编号后面，已存在队伍自动跳过。" },
  { id: "replace", title: "按序号替换", desc: "草稿第 i 个替换收藏標靶i，多出的保留。" },
  { id: "rebuild", title: "清空重排", desc: "删光现有靶机后按 1..N 全量重建。" },
];

let rootEl = null;
let selectedMode = "append";
let unsub = null;
let dragCleanup = null;

export async function render(root) {
  rootEl = root;
  if (unsub) unsub();
  if (dragCleanup) dragCleanup();

  root.innerHTML = pageHeadHtml({
    crumbs: [{ label: "序列编排" }],
    title: "序列编排",
    badge: "SEQUENCE",
    sub: "序列就是执行后「收藏标靶」的编号顺序：拖拽条目排序，最多 35 个。序列仅是草稿，执行向导里预览确认后才会真正写入游戏。",
    actions: `
      <div class="page-head-add">${addByIdHtml()}</div>
      <button class="btn btn-ghost" type="button" data-act="import">${icon("download", 14)} 从当前靶机导入</button>
      <button class="btn btn-cyan" type="button" data-nav="/chapters">${icon("map", 14)} 去选队伍</button>
      <button class="btn btn-primary" type="button" data-act="execute">${icon("play", 14)} 执行注入</button>
    `,
  }) + `<div data-seq-page>${skeletonRows(5)}</div>`;

  try {
    await refreshSequence();
  } catch (err) {
    if (err.status === 503 || err.status === 0) {
      const { showBuildOverlay } = await import("../ui.js");
      showBuildOverlay(err.detail || err.message, () => render(root));
      return;
    }
  }

  // 页头按钮只绑定一次（renderPage 只替换 data-seq-page 内部，避免重复绑定）
  bindAddById(root.querySelector(".page-head"));
  root.querySelectorAll(".page-head [data-act]").forEach((button) => {
    if (button.dataset.act === "execute") {
      button.addEventListener("click", openExec);
    } else if (button.dataset.act === "import") {
      button.addEventListener("click", (event) => doImport(event.currentTarget));
    }
  });

  unsub = store.on("sequence", () => {
    if (root.isConnected) renderPage();
  });
  store.registerCleanup(() => {
    if (unsub) unsub();
    if (dragCleanup) dragCleanup();
    unsub = null;
    dragCleanup = null;
  });
  renderPage();
}

function openExec() {
  openExecuteModal({ mode: selectedMode });
}

async function doImport(button) {
  setBusy(button, true, "导入中…");
  try {
    await importCurrentSequence();
    toastOk("已从当前靶机导入", "序列已被替换为游戏内现有收藏标靶顺序");
  } catch (err) {
    toastErr("导入失败", err.message);
  } finally {
    setBusy(button, false);
  }
}

function renderPage() {
  const seq = store.sequence;
  const stats = sequenceStats(seq);
  const draft = seq?.draft || [];
  const pageEl = rootEl.querySelector("[data-seq-page]");
  if (!pageEl) return;

  pageEl.innerHTML = `
    <div class="seq-page-cols">
      <section>
        ${sectionHeadHtml("当前序列", {
          hint: "拖拽排序 · 顺序即收藏标靶编号",
          iconName: "layers",
          actions: `<span class="badge mono">${stats.count} / ${stats.max}</span>`,
        })}
        ${
          draft.length
            ? `<div class="seq-big-list" data-seq-big-list>${draft.map((team, index) => seqBigItemHtml(team, index, draft.length)).join("")}</div>`
            : `<div class="empty" style="padding:56px 24px">
                 <div class="em-ico">${icon("layers", 26)}</div>
                 <h4>序列还是空的</h4>
                 <p>去「关卡图鉴」按章节找队伍，或到「怪种图鉴」按怪种找队伍，点「加入序列」后回到这里拖动排序。</p>
                 <div style="display:flex;gap:8px;margin-top:16px">
                   <button class="btn btn-primary" type="button" data-nav="/chapters">${icon("map", 14)} 关卡图鉴</button>
                   <button class="btn" type="button" data-nav="/species">${icon("crosshair", 14)} 怪种图鉴</button>
                 </div>
               </div>`
        }
        ${
          draft.length
            ? `<div class="seq-hint mt12">${icon("info", 12)} 拖拽条目可排序（拖动时会出现冰蓝色指示线），也可用右侧 ↑ ↓ 按钮微调；第 1 条对应收藏標靶1。</div>`
            : ""
        }
      </section>

      <aside class="seq-summary-panel">
        <div class="summary-box">
          <h3>${icon("radar", 13)} 序列摘要</h3>
          <div class="summary-big"><b>${stats.count}</b><span>/ ${stats.max}</span></div>
          <div class="summary-sub">上限 35 个收藏标靶 · ${stats.count > 0 ? `还可加入 ${stats.max - stats.count} 个` : "建议先配好一整套再执行"}</div>
          <div class="summary-rows">
            <div class="summary-row"><span>总效能（已标注）</span><b class="amber">${stats.powerKnown ? fmtNum(stats.power) : "—"}</b></div>
            <div class="summary-row"><span>效能标注情况</span><b>${stats.powerKnown} 有 · ${stats.powerUnknown} 无</b></div>
            <div class="summary-row"><span>总单位</span><b>${fmtNum(stats.units)}</b></div>
            <div class="summary-row"><span>总血量</span><b>${fmtNum(stats.hp)}</b></div>
            <div class="summary-row"><span>草稿更新时间</span><b>${esc(seq?.updated_at ? new Date(seq.updated_at).toLocaleTimeString("zh-CN") : "—")}</b></div>
          </div>
        </div>

        <div class="summary-box">
          <h3>${icon("sliders", 13)} 选择执行模式</h3>
          <div class="mode-list">
            ${MODES.map(
              (mode) => `
              <button class="mode-option ${selectedMode === mode.id ? "active" : ""}" type="button" data-mode="${mode.id}" data-act="mode">
                <span class="mo-radio"></span>
                <span class="mo-body">
                  <span class="mo-title">${mode.title}<span class="mo-code">${mode.id}</span></span>
                  <span class="mo-desc">${mode.desc}</span>
                </span>
              </button>`,
            ).join("")}
          </div>
          <div class="check-row mt12" style="border-color:rgba(245,165,36,.28)">
            <span class="dot warn pulse"></span>
            <span style="flex:1">执行前会先弹出预览：删除 / 新增 / 保留 / 最终列表。</span>
          </div>
          <div class="mt12" style="display:flex;flex-direction:column;gap:7px">
            <button class="btn btn-primary btn-lg btn-block" type="button" data-act="execute">
              ${icon("play", 14)} ${draft.length ? "预览并执行" : "执行注入（序列为空）"}
            </button>
            <div style="display:flex;gap:7px">
              <button class="btn btn-ghost btn-sm" style="flex:1" type="button" data-act="import">${icon("download", 12)} 从当前导入</button>
              <button class="btn btn-ghost btn-sm" style="flex:1" type="button" data-act="clear" ${draft.length ? "" : "disabled"}>${icon("trash", 12)} 清空草稿</button>
            </div>
          </div>
        </div>

        <div class="summary-box" style="border-color:rgba(239,83,80,.22);background:rgba(239,83,80,.035)">
          <h3 style="color:#ff9a97">${icon("alert", 13)} 危险操作</h3>
          <p style="font-size:11px;color:var(--text-mute);line-height:1.7;margin:0 0 10px">「清空游戏靶机」会删除游戏内全部收藏标靶，不新增内容。清空后必须大退重登，否则进入靶机界面可能卡死。</p>
          <button class="btn btn-danger btn-sm btn-block" type="button" data-act="clear-game" ${seq === null ? "disabled" : ""}>
            ${icon("trash", 12)} 清空游戏内全部靶机
          </button>
        </div>
      </aside>
    </div>
  `;

  bindBodyEvents(pageEl, draft);
}

function seqBigItemHtml(team, index, total) {
  const fc = factionColor(team.faction);
  const disp = powerDisplay(team.power, team.power_known);
  return `
    <div class="seq-big-item" draggable="true" data-drag-index="${index}" data-team-detail="${team.id}">
      <span class="sbi-idx">${String(index + 1).padStart(2, "0")}</span>
      <span class="sbi-drag">${icon("grip", 15)}</span>
      <div class="sbi-main">
        <div class="sbi-top">
          <span class="sbi-team">#${esc(team.id)}</span>
          <span class="badge ${team.gray_zone ? "cyan" : ""}" style="height:18px;font-size:9.5px">${team.gray_zone ? "灰域" : team.orphan ? "无固定关卡" : "固定关卡"}</span>
          <span class="sbi-power ${disp.known ? (disp.negative ? "neg" : "") : "unknown"}"${disp.negative ? ' title="积分关卡数据，可能为负"' : ""}>${disp.known ? disp.text : "未标注"}</span>
        </div>
        <div class="sbi-sub">
          <span><i class="seq-faction-dot" style="background:${fc};display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:5px"></i>${esc(team.faction || "其它")}</span>
          <span>${team.units ?? "?"} 单位</span>
          <span>总血 ${fmtNum(team.hp_total)}</span>
          <span>${(team.species || []).slice(0, 4).map((item) => esc(item.name)).join(" · ")}${(team.species || []).length > 4 ? " …" : ""}</span>
        </div>
      </div>
      <div class="sbi-actions">
        <button type="button" data-seq-act="up" title="上移" ${index === 0 ? "disabled" : ""}>${icon("chevronUp", 14)}</button>
        <button type="button" data-seq-act="down" title="下移" ${index === total - 1 ? "disabled" : ""}>${icon("chevronDown", 14)}</button>
        <button type="button" data-seq-act="remove" title="移除">${icon("trash", 13)}</button>
      </div>
    </div>
  `;
}

function bindBodyEvents(scope, draft) {
  if (dragCleanup) dragCleanup();
  const list = scope.querySelector("[data-seq-big-list]");
  if (list) {
    dragCleanup = bindDragSort(list, {
      onMove: async (from, to) => {
        try {
          await moveTeam(from, to);
        } catch (err) {
          toastErr("排序失败", err.message);
        }
      },
    });
    list.addEventListener("click", async (event) => {
      const actionBtn = event.target.closest("[data-seq-act]");
      if (!actionBtn) return;
      event.stopPropagation();
      event.preventDefault();
      const item = actionBtn.closest("[data-drag-index]");
      if (!item) return;
      const index = Number(item.dataset.dragIndex);
      const teamId = Number(item.dataset.teamDetail);
      const action = actionBtn.dataset.seqAct;
      try {
        if (action === "remove") {
          await removeTeam(teamId);
          toast({ title: `已移除队伍 #${teamId}`, type: "info", duration: 1800 });
        } else if (action === "up" && index > 0) await moveTeam(index, index - 1);
        else if (action === "down" && index < draft.length - 1) await moveTeam(index, index + 1);
      } catch (err) {
        toastErr("操作失败", err.message);
      }
    });
  }

  scope.querySelectorAll('[data-act="mode"]').forEach((button) => {
    button.addEventListener("click", () => {
      selectedMode = button.dataset.mode;
      renderPage();
    });
  });

  scope.querySelectorAll('[data-act="execute"]').forEach((button) => button.addEventListener("click", openExec));
  scope.querySelectorAll('[data-act="import"]').forEach((button) =>
    button.addEventListener("click", (event) => doImport(event.currentTarget)),
  );

  scope.querySelector('[data-act="clear"]')?.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "清空序列草稿",
      message: "只会清空本应用里的序列草稿，不会动游戏中的收藏标靶。",
      confirmText: "清空序列",
      danger: true,
    });
    if (!ok) return;
    try {
      await clearSequence();
      toastOk("序列已清空");
    } catch (err) {
      toastErr("清空失败", err.message);
    }
  });

  scope.querySelector('[data-act="clear-game"]')?.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "清空游戏内全部收藏标靶",
      message: "这会删除游戏内当前全部收藏标靶，且不可撤销。",
      detail: "清空后必须大退重登游戏，否则进入靶机界面可能卡死。建议先用「演练模式」确认计划。",
      confirmText: "继续进入预览",
      danger: true,
    });
    if (!ok) return;
    openExecuteModal({ clearEntry: true });
  });
}
