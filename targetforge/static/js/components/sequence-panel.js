/* sequence-panel.js —— 右侧常驻「序列」面板（可收起 / 拖拽排序 / n/35 进度） */
import { store, refreshSequence, sequenceStats, removeTeam, moveTeam, clearSequence, importCurrentSequence } from "../store.js";
import { icon, toast, toastErr, toastOk, confirmDialog, butterflySvg } from "../ui.js";
import { esc, fmtNum, factionColor, navigate, powerDisplay } from "../util.js";
import { bindDragSort } from "./drag-sort.js";
import { addByIdHtml, bindAddById } from "./add-by-id.js";
import { openExecuteModal } from "./execute-modal.js";

let rootEl = null;
let currentDragCleanup = null;

export function initSequencePanel(root) {
  rootEl = root;
  root.classList.toggle("collapsed", !store.seqOpen);

  store.on("sequence", () => render());
  store.on("seq-open", (open) => root.classList.toggle("collapsed", !open));

  render();
  if (!store.sequence) {
    refreshSequence().catch((err) => {
      if (err.status === 503 || err.status === 0) return; // catalog 构建中，静默
      toastErr("序列加载失败", err.message);
    });
  }
}

function progressBlocks(count, max) {
  const blocks = [];
  for (let i = 1; i <= max; i += 1) {
    blocks.push(`<i class="${i <= count ? "on" : ""}"></i>`);
  }
  return blocks.join("");
}

function render() {
  if (!rootEl) return;
  const seq = store.sequence;
  const stats = sequenceStats(seq);
  const draft = seq?.draft || [];
  const metaLoadFailed = seq === null;

  rootEl.innerHTML = `
    <button class="seq-toggle" type="button" data-act="toggle" aria-label="收起/展开序列面板" title="收起 / 展开">
      ${icon("chevronRight", 12)}
    </button>
    <div class="seq-head">
      <div class="seq-head-row">
        <span class="seq-title">序列编排</span>
        <span class="seq-count"><b>${stats.count}</b><span class="max"> / ${stats.max}</span></span>
        <button class="btn btn-icon btn-ghost btn-sm" type="button" data-act="refresh" title="刷新序列" style="margin-left:4px">${icon("refresh", 13)}</button>
      </div>
      <div class="seq-progress">${progressBlocks(stats.count, stats.max)}</div>
      <div class="seq-summary">
        <span>总效能 <b>${stats.powerKnown ? fmtNum(stats.power) : "—"}</b></span>
        <span>已标注 <b>${stats.powerKnown}</b> / 未标注 <b>${stats.powerUnknown}</b></span>
      </div>
    </div>
    <div class="seq-list-wrap">
      ${
        metaLoadFailed
          ? `<div class="seq-empty"><span class="spinner" style="margin:0 auto 10px"></span><span>正在读取序列…</span></div>`
          : draft.length === 0
            ? `<div class="seq-empty">
                 <div class="se-ico">${butterflySvg({ size: 46, opacity: 0.5, className: "float-slow" })}</div>
                 <b>序列还是空的</b>
                 <span>去关卡或怪种图鉴挑队伍，<br>点「加入序列」后在这里拖动排序。</span>
                 <button class="btn btn-sm btn-cyan" type="button" data-act="go-chapters">${icon("map", 12)} 去选队伍</button>
               </div>`
            : `<ul class="seq-list">${draft.map((team, index) => seqItemHtml(team, index)).join("")}</ul>`
      }
    </div>
    <div class="seq-foot">
      <div class="seq-add-row">${addByIdHtml({ compact: true })}</div>
      <button class="btn btn-primary btn-block btn-lg" type="button" data-act="execute" ${draft.length ? "" : "disabled"}>
        ${icon("play", 14)} 执行注入
      </button>
      <div class="seq-foot-row">
        <button class="btn btn-ghost btn-sm" type="button" data-act="import">${icon("download", 12)} 从当前导入</button>
        <button class="btn btn-ghost btn-sm" type="button" data-act="clear" ${draft.length ? "" : "disabled"}>${icon("trash", 12)} 清空</button>
      </div>
      <div class="seq-hint">${icon("info", 12)} 拖拽排序，也可用 ↑ ↓ 按钮微调顺序</div>
    </div>
  `;

  bindEvents(draft);
  bindAddById(rootEl);
}

function seqItemHtml(team, index) {
  const fc = factionColor(team.faction);
  const disp = powerDisplay(team.power, team.power_known);
  const isGray = team.gray_zone;
  const isOrphan = team.orphan;
  return `
    <li class="seq-item" draggable="true" data-drag-index="${index}" data-team-detail="${team.id}">
      <span class="seq-idx">${String(index + 1).padStart(2, "0")}</span>
      <div class="seq-body">
        <div class="seq-line1">
          <span class="seq-team-id">#${esc(team.id)}</span>
          <span class="seq-power ${disp.known ? (disp.negative ? "neg" : "") : "unknown"}"${disp.negative ? ' title="积分关卡数据，可能为负"' : ""}>${disp.known ? disp.text : "未标注"}</span>
        </div>
        <div class="seq-line2">
          <i class="seq-faction-dot" style="background:${fc}"></i>
          <span>${esc(team.faction || "其它")}</span>
          <span>·</span>
          <span>${team.units ?? "?"} 单位</span>
          ${isGray ? '<span class="tag cyan" style="height:15px;font-size:9px">灰域</span>' : ""}
          ${isOrphan ? '<span class="tag" style="height:15px;font-size:9px">无固定</span>' : ""}
        </div>
      </div>
      <div class="seq-actions">
        <button type="button" data-seq-act="up" title="上移">${icon("chevronUp", 12)}</button>
        <button type="button" data-seq-act="down" title="下移">${icon("chevronDown", 12)}</button>
        <button type="button" data-seq-act="remove" title="移除">${icon("close", 11)}</button>
      </div>
    </li>
  `;
}

function bindEvents(draft) {
  const list = rootEl.querySelector(".seq-list");

  rootEl.querySelector('[data-act="toggle"]')?.addEventListener("click", () => store.toggleSeq());
  rootEl.querySelector('[data-act="go-chapters"]')?.addEventListener("click", () => navigate("/chapters"));
  rootEl.querySelector('[data-act="refresh"]')?.addEventListener("click", async () => {
    try {
      await refreshSequence();
      toastOk("序列已刷新");
    } catch (err) {
      toastErr("刷新失败", err.message);
    }
  });
  rootEl.querySelector('[data-act="execute"]')?.addEventListener("click", () => openExecuteModal());
  rootEl.querySelector('[data-act="import"]')?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await importCurrentSequence();
      toastOk("已从当前靶机导入", "序列已被替换为游戏内现有收藏标靶顺序");
    } catch (err) {
      toastErr("导入失败", err.message);
    } finally {
      button.disabled = false;
    }
  });
  rootEl.querySelector('[data-act="clear"]')?.addEventListener("click", async () => {
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

  rootEl.querySelector(".seq-list")?.addEventListener("click", async (event) => {
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
        toast({ title: `已移除队伍 #${teamId}`, type: "info", duration: 2000 });
      } else if (action === "up" && index > 0) {
        await moveTeam(index, index - 1);
      } else if (action === "down" && index < draft.length - 1) {
        await moveTeam(index, index + 1);
      }
    } catch (err) {
      toastErr("操作失败", err.message);
    }
  });

  if (list) {
    if (currentDragCleanup) currentDragCleanup();
    currentDragCleanup = bindDragSort(list, {
      onMove: async (from, to) => {
        try {
          await moveTeam(from, to);
        } catch (err) {
          toastErr("排序失败", err.message);
        }
      },
    });
  }
}
