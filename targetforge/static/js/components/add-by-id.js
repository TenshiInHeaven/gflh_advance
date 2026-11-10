/* components/add-by-id.js —— 按队伍编号加入序列（全局搜索 / 序列页 / 序列面板共用） */
import { api } from "../api.js";
import { addTeams, sequenceStats, store } from "../store.js";
import { icon, toastErr, toastOk } from "../ui.js";

/** 解析编号输入：支持 6363006 / #6363006（去掉前缀与空白） */
export function parseTeamIdInput(raw) {
  const text = String(raw ?? "").trim().replace(/^#+/, "");
  if (!/^\d{1,9}$/.test(text)) return null;
  const id = Number(text);
  return Number.isFinite(id) && id > 0 ? id : null;
}

/** 通过编号直接加入序列：先校验队伍存在且 collectable，再 POST 加入 */
export async function addTeamById(raw) {
  const id = typeof raw === "number" ? raw : parseTeamIdInput(raw);
  if (!id) {
    toastErr("编号无效", "请输入数字编号，例如 6363006 或 #6363006。");
    return false;
  }
  const before = sequenceStats();
  if (before.count >= before.max) {
    toastErr("序列已满", `序列上限 ${before.max}，请先移除一些队伍再按编号加入。`);
    return false;
  }
  const draft = store.sequence?.draft || [];
  if (draft.some((team) => Number(team.id) === id)) {
    toastErr("已在序列中", `队伍 #${id} 已经在序列里了。`);
    return false;
  }
  let detail = null;
  try {
    detail = await api.team(id);
  } catch (err) {
    toastErr("找不到队伍", `没有找到编号 #${id} 的队伍，或该队伍不可收藏。`);
    return false;
  }
  if (detail && detail.collectable === false) {
    toastErr("不可加入", `队伍 #${id} 不可收藏，无法加入收藏序列。`);
    return false;
  }
  try {
    const after = await addTeams([id]);
    toastOk("已加入序列", `队伍 #${id} 已加入 · 当前 ${after.count}/${after.max}`);
    return true;
  } catch (err) {
    toastErr("加入失败", err.message || `队伍 #${id} 加入序列失败。`);
    return false;
  }
}

/** 「按编号加入」输入框 HTML（序列页 / 序列面板共用；compact 用于窄面板） */
export function addByIdHtml({ compact = false } = {}) {
  return `<div class="add-by-id ${compact ? "compact" : ""}" data-add-by-id>
    <span class="abi-ico" aria-hidden="true">${icon("crosshair", 12)}</span>
    <input class="abi-input" type="text" inputmode="numeric" autocomplete="off" spellcheck="false"
      placeholder="按编号加入，如 6363006 / #6363006" data-add-id-input aria-label="按队伍编号加入序列" />
    <button class="btn btn-sm btn-cyan abi-btn" type="button" data-add-id-submit>${icon("plus", 11)} 加入</button>
  </div>`;
}

/** 绑定容器内所有「按编号加入」输入框（回车或点按钮提交） */
export function bindAddById(container) {
  const root = container || document;
  root.querySelectorAll("[data-add-by-id]").forEach((group) => {
    if (group.dataset.bound === "1") return;
    group.dataset.bound = "1";
    const input = group.querySelector("[data-add-id-input]");
    const submit = group.querySelector("[data-add-id-submit]");
    const run = async () => {
      const raw = input?.value || "";
      const ok = await addTeamById(raw);
      if (ok && input) {
        input.value = "";
        input.focus();
      }
    };
    submit?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      run();
    });
    input?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        run();
      }
    });
  });
}
