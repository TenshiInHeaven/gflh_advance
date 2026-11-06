/* components/power-filter.js —— 效能筛选 / 排序控件（服务端分页与本地列表共用） */
import { icon } from "../ui.js";
import { esc, fmtNum, powerDisplay } from "../util.js";

export const POWER_SORT_OPTIONS = [
  { id: "default", label: "默认排序" },
  { id: "power_desc", label: "效能 高→低" },
  { id: "power_asc", label: "效能 低→高" },
  { id: "hp_desc", label: "总血 高→低" },
  { id: "units_desc", label: "单位数 多→少" },
];

const SORT_IDS = new Set(POWER_SORT_OPTIONS.map((item) => item.id));

export function defaultPowerFilter() {
  return { mode: "all", min: "", max: "", sort: "default" };
}

/** 筛选条 HTML（放在页面工具栏内） */
export function powerFilterBarHtml() {
  return `
    <div class="power-filter" data-power-filter>
      <div class="pf-group">
        <span class="pf-label">${icon("zap", 11)} 效能</span>
        <select class="select pf-select" data-pf-mode aria-label="效能筛选">
          <option value="all">全部</option>
          <option value="known">有标注</option>
          <option value="custom">自定义范围</option>
        </select>
        <span class="pf-range hidden" data-pf-range>
          <input type="number" class="pf-input" data-pf-min placeholder="min" step="any" aria-label="效能下限" />
          <span class="pf-dash">~</span>
          <input type="number" class="pf-input" data-pf-max placeholder="max" step="any" aria-label="效能上限" />
        </span>
      </div>
      <div class="pf-group">
        <span class="pf-label">${icon("sliders", 11)} 排序</span>
        <select class="select pf-select" data-pf-sort aria-label="排序方式">
          ${POWER_SORT_OPTIONS.map((item) => `<option value="${item.id}">${item.label}</option>`).join("")}
        </select>
      </div>
      <span class="pf-meta" data-pf-meta></span>
      <button class="btn btn-sm btn-ghost" type="button" data-pf-reset>重置</button>
    </div>
  `;
}

/** 从容器读取筛选状态 */
export function readPowerFilter(container) {
  const box = container?.querySelector("[data-power-filter]");
  if (!box) return defaultPowerFilter();
  const mode = box.querySelector("[data-pf-mode]")?.value || "all";
  const sort = box.querySelector("[data-pf-sort]")?.value || "default";
  return {
    mode: ["all", "known", "custom"].includes(mode) ? mode : "all",
    min: box.querySelector("[data-pf-min]")?.value?.trim?.() ?? "",
    max: box.querySelector("[data-pf-max]")?.value?.trim?.() ?? "",
    sort: SORT_IDS.has(sort) ? sort : "default",
  };
}

/** 绑定变更事件；返回解绑函数。onChange(state) */
export function bindPowerFilter(container, onChange, { debounceMs = 260 } = {}) {
  const box = container?.querySelector("[data-power-filter]");
  if (!box) return () => {};
  const modeSel = box.querySelector("[data-pf-mode]");
  const sortSel = box.querySelector("[data-pf-sort]");
  const range = box.querySelector("[data-pf-range]");
  const minInput = box.querySelector("[data-pf-min]");
  const maxInput = box.querySelector("[data-pf-max]");
  const resetBtn = box.querySelector("[data-pf-reset]");

  const syncRange = () => {
    const custom = modeSel.value === "custom";
    range.classList.toggle("hidden", !custom);
    if (custom && !minInput.value && !maxInput.value) {
      // 自定义模式默认展示全部有标注队伍，不强制填值
    }
  };
  let timer = 0;
  const fire = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      syncRange();
      onChange(readPowerFilter(container));
    }, debounceMs);
  };
  const fireNow = () => {
    clearTimeout(timer);
    syncRange();
    onChange(readPowerFilter(container));
  };
  modeSel.addEventListener("change", fireNow);
  sortSel.addEventListener("change", fireNow);
  minInput.addEventListener("input", fire);
  maxInput.addEventListener("input", fire);
  resetBtn.addEventListener("click", () => {
    modeSel.value = "all";
    sortSel.value = "default";
    minInput.value = "";
    maxInput.value = "";
    syncRange();
    onChange(readPowerFilter(container));
  });
  syncRange();
  return () => {
    clearTimeout(timer);
    modeSel.removeEventListener("change", fireNow);
    sortSel.removeEventListener("change", fireNow);
    minInput.removeEventListener("input", fire);
    maxInput.removeEventListener("input", fire);
  };
}

function powerValueOf(team) {
  const disp = powerDisplay(team?.power, team?.power_known);
  return disp.known ? disp.value : null;
}

/** 本地过滤 + 排序（服务端分页接口也可对当前页做一次保险过滤） */
export function filterAndSortTeams(teams, state) {
  const list = Array.isArray(teams) ? teams.slice() : [];
  const mode = state?.mode || "all";
  const min = state?.min === "" || state?.min === undefined ? null : Number(state.min);
  const max = state?.max === "" || state?.max === undefined ? null : Number(state.max);
  let filtered = list;
  if (mode === "known") {
    filtered = list.filter((team) => powerValueOf(team) !== null);
  } else if (mode === "custom") {
    filtered = list.filter((team) => {
      const value = powerValueOf(team);
      if (value === null) return false;
      if (min !== null && Number.isFinite(min) && value < min) return false;
      if (max !== null && Number.isFinite(max) && value > max) return false;
      return true;
    });
  }
  const sort = state?.sort || "default";
  if (sort === "power_desc") {
    filtered.sort((a, b) => (powerValueOf(b) ?? -Infinity) - (powerValueOf(a) ?? -Infinity));
  } else if (sort === "power_asc") {
    filtered.sort((a, b) => (powerValueOf(a) ?? Infinity) - (powerValueOf(b) ?? Infinity));
  } else if (sort === "hp_desc") {
    filtered.sort((a, b) => (Number(b?.hp_total) || 0) - (Number(a?.hp_total) || 0));
  } else if (sort === "units_desc") {
    filtered.sort((a, b) => (Number(b?.units) || 0) - (Number(a?.units) || 0));
  }
  return filtered;
}

/** 供服务端分页接口使用的查询参数 */
export function serverPowerParams(state) {
  const params = {};
  if (!state) return params;
  if (state.mode === "known") params.power_known = 1;
  if (state.mode === "custom") {
    params.power_known = 1;
    if (state.min !== "" && Number.isFinite(Number(state.min))) params.power_min = Number(state.min);
    if (state.max !== "" && Number.isFinite(Number(state.max))) params.power_max = Number(state.max);
  }
  if (state.sort && state.sort !== "default") params.sort = state.sort;
  return params;
}

/** 是否处于「需要先拿到队伍数据」的筛选/排序状态 */
export function powerFilterActive(state) {
  return Boolean(state && (state.mode !== "all" || (state.sort && state.sort !== "default")));
}

/** 统计过滤条右侧提示 */
export function powerFilterMeta(state, total, shown) {
  if (!state || (state.mode === "all" && (!state.sort || state.sort === "default"))) {
    return `共 ${fmtNum(total)} 支`;
  }
  const modeText = { known: "仅看有标注", custom: "自定义效能区间" }[state.mode] || "全部";
  const sortText = POWER_SORT_OPTIONS.find((item) => item.id === state.sort)?.label || "默认排序";
  const shownText = shown === undefined ? "" : ` · 当前显示 ${fmtNum(shown)}`;
  return `${esc(modeText)} · ${esc(sortText)}${shownText} · 共 ${fmtNum(total)} 支`;
}

/** 统一的效能徽标 HTML（0=未标注，负值 amber + tooltip） */
export function powerBadgeHtml(team) {
  const disp = powerDisplay(team?.power, team?.power_known);
  if (!disp.known) {
    return '<b class="dim">未标注</b><span>效能</span>';
  }
  const tooltip = disp.negative ? ' title="积分关卡数据，可能为负"' : "";
  return `<b class="${disp.negative ? "neg" : ""}"${tooltip}>${disp.text}</b><span>效能</span>`;
}
