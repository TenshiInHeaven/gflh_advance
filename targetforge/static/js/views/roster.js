/* views/roster.js —— 全怪组总表：分页表格 + 多条件筛选（章节 / 怪种 AND / 角色 / 单位数 / 效能）+ 排序 */
import { api } from "../api.js";
import { store, loadChapters } from "../store.js";
import {
  icon,
  pageHeadHtml,
  emptyState,
  renderPager,
  bindPager,
  speciesIconHtml,
  toastOk,
  toastErr,
} from "../ui.js";
import { esc, fmtNum, powerDisplay, bindSearch, isSupportTeam, isReserveTeam, factionClass } from "../util.js";

const PAGE_SIZES = [50, 100, 200];
const COL_COUNT = 8;
const COL_MIN = 44;
const COL_WIDTHS_KEY = "roster.colWidths.v1";
const SORT_OPTIONS = [
  ["id_asc", "序号 ↑"],
  ["id_desc", "序号 ↓"],
  ["units_desc", "单位数 ↓"],
  ["units_asc", "单位数 ↑"],
  ["hp_desc", "总血 ↓"],
  ["species_desc", "怪种数 ↓"],
];
const SORT_COLS = {
  id: { desc: "id_desc", asc: "id_asc" },
  units: { desc: "units_desc", asc: "units_asc" },
  hp: { desc: "hp_desc", asc: "id_asc" },
  species: { desc: "species_desc", asc: "id_asc" },
};

const defaultFilters = () => ({
  q: "",
  chapter: "",
  role: "",
  species: new Map(),
  faction: "",
  boss: "",
  collectable: "",
  teamIds: "",
  hpMin: "",
  hpMax: "",
  unitsMin: "",
  unitsMax: "",
});
const ROSTER_STATE_KEY = "tf:roster.state.v1";

const state = {
  page: 1,
  limit: 50,
  sort: "id_asc",
  filters: defaultFilters(),
  total: 0,
  speciesOptions: [],
  chapters: [],
  loading: false,
};
let rootEl = null;
let reqToken = 0;
let outsideClickBound = false;
let rosterScrollBound = false;

function rosterScroller() {
  return rootEl ? rootEl.closest(".main") : null;
}

function readRosterState() {
  try {
    const raw = sessionStorage.getItem(ROSTER_STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveRosterState() {
  if (!rootEl) return;
  try {
    const data = {
      filters: {
        ...state.filters,
        species: [...state.filters.species.values()],
      },
      page: state.page,
      limit: state.limit,
      sort: state.sort,
    };
    sessionStorage.setItem(ROSTER_STATE_KEY, JSON.stringify(data));
  } catch {
    /* storage unavailable */
  }
}

function clearRosterState() {
  try {
    sessionStorage.removeItem(ROSTER_STATE_KEY);
  } catch {
    /* ignore */
  }
}

function chapterOptionsHtml() {
  const groups = state.chapters || [];
  if (!groups.length) return `<option value="">全部章节（未加载）</option>`;
  return `<option value="">全部章节（${groups.reduce((acc, group) => acc + (group.chapters || []).length, 0)} 章）</option>` +
    groups
      .map((group) => {
        const list = group.chapters || [];
        if (!list.length) return "";
        return `<optgroup label="${esc(group.title || group.id)}">${list
          .map((chapter) => `<option value="${esc(chapter.id)}">${esc(group.title || group.id)} · ${esc(chapter.title || chapter.id)}</option>`)
          .join("")}</optgroup>`;
      })
      .join("");
}

function speciesMenuHtml(keyword = "") {
  const q = keyword.trim().toLowerCase();
  const selected = state.filters.species;
  const options = state.speciesOptions.filter((item) => {
    if (!q) return selected.size < 120;
    return `${item.codex_no} ${item.name || ""}`.toLowerCase().includes(q);
  });
  if (!options.length) return `<div class="sp-menu-empty">没有匹配的怪种</div>`;
  return options
    .slice(0, 40)
    .map(
      (item) => `<button class="sp-opt ${selected.has(item.codex_no) ? "selected" : ""}" type="button" data-sp-opt="${item.codex_no}">
        ${speciesIconHtml(item, { size: 20, variant: "mini" })}
        <span class="sp-opt-name">${esc(item.name || `#${item.codex_no}`)}</span>
        <span class="sp-opt-code">#${String(item.codex_no).padStart(3, "0")}</span>
        ${selected.has(item.codex_no) ? icon("check", 12) : ""}
      </button>`,
    )
    .join("");
}

function pickedSpeciesHtml() {
  const picked = [...state.filters.species.values()];
  if (!picked.length) return `<span class="sp-picked-empty">未选择（多选 = 同时包含）</span>`;
  return picked
    .map(
      (item) => `<span class="sp-chip-picked" title="同时包含：${esc(item.name || "")}">
        ${speciesIconHtml(item, { size: 16, variant: "mini" })}
        ${esc(item.name || `#${item.codex_no}`)}
        <button type="button" data-sp-remove="${item.codex_no}" aria-label="移除">${icon("close", 9)}</button>
      </span>`,
    )
    .join("");
}

function roleOptionsHtml() {
  return [
    ["", "全部角色"],
    ["enemy", "敌方"],
    ["support", "支援"],
    ["reserve", "可能刷怪（推断）"],
  ]
    .map(([value, label]) => `<option value="${value}">${label}</option>`)
    .join("");
}

function buildQuery() {
  const f = state.filters;
  const params = {
    q: f.q.trim(),
    chapter: f.chapter,
    species: [...f.species.keys()].join(","),
    role: f.role,
    faction: f.faction,
    has_boss: f.boss,
    collectable: f.collectable,
    team_ids: f.teamIds.trim(),
    hp_min: f.hpMin,
    hp_max: f.hpMax,
    units_min: f.unitsMin,
    units_max: f.unitsMax,
    sort: state.sort,
    offset: (state.page - 1) * state.limit,
    limit: state.limit,
  };
  Object.keys(params).forEach((key) => {
    if (params[key] === "" || params[key] === undefined || params[key] === null) delete params[key];
  });
  return params;
}

function roleBadgesHtml(team) {
  const badges = [];
  const roles = Array.isArray(team.roles) ? team.roles.map((role) => String(role).toLowerCase()) : [];
  if (roles.includes("support") || isSupportTeam(team)) {
    badges.push(`<span class="badge support">${icon("shield", 9)} 支援</span>`);
  }
  if (roles.includes("reserve") || isReserveTeam(team)) {
    badges.push(`<span class="badge reserve" title="可能刷怪（推断）：同系列未入场怪组，STC 无显式机场刷新映射">${icon("refresh", 9)} 可能刷怪</span>`);
  }
  if (!roles.includes("support") && !roles.includes("reserve")) {
    badges.push(`<span class="badge mono">敌方</span>`);
  }
  if (team.orphan) badges.push(`<span class="badge violet" title="无固定关卡">无关卡</span>`);
  return badges.join(" ");
}

function speciesCellHtml(team) {
  const species = team.species || [];
  if (!species.length) return `<span class="text-mute">—</span>`;
  const shown = species.slice(0, 6);
  const rest = species.length - shown.length;
  return `<span class="roster-species">${shown
    .map(
      (item) => `<span class="rs-ico" title="${esc(item.name || "")} #${String(item.codex_no || "").padStart(3, "0")}">${speciesIconHtml(
        item,
        { size: 16, variant: "mini", fallbackFaction: team.faction },
      )}</span>`,
    )
    .join("")}${rest > 0 ? `<span class="rs-more" title="共 ${species.length} 个怪种">+${rest}</span>` : ""}</span>`;
}

function chaptersCellHtml(team) {
  const titles = Array.isArray(team.chapter_titles) && team.chapter_titles.length
    ? team.chapter_titles
    : (team.appearances || []).map((item) => item.chapter_title).filter(Boolean);
  const total = Number(team.appearance_count) || titles.length;
  if (!titles.length) return `<span class="text-mute">—</span>`;
  const shown = titles.slice(0, 2);
  return `<span class="roster-chapters" title="${esc(titles.join(" · "))}">${shown.map((title) => esc(title)).join(" · ")}${
    total > shown.length ? ` <span class="rs-more">+${total - shown.length}</span>` : ""
  }</span>`;
}

function rowHtml(team) {
  const disp = powerDisplay(team.power, team.power_known);
  const powerCell = disp.known
    ? `<b class="mono ${disp.negative ? "neg" : ""}" ${disp.negative ? 'title="积分关卡数据，可能为负"' : ""}>${disp.text}</b>`
    : `<span class="dim">未标注</span>`;
  const inSeq = (store.sequence?.draft || []).some((item) => Number(item.id) === Number(team.id));
  return `<tr class="roster-row ${team.collectable === false ? "is-locked-row" : "is-collectable-row"}" data-team-detail="${esc(team.id)}" tabindex="0" aria-label="队伍 #${esc(team.id)}">
    <td class="roster-id">#${esc(team.id)} ${team.collectable === false ? `<span class="badge danger">仅展示</span>` : `<span class="badge cyan">可加入</span>`}</td>
    <td class="num">${powerCell}</td>
    <td class="num roster-uh" title="单位数 / 总血量"><b>${fmtNum(team.units)}</b><span class="roster-hp"> / ${fmtNum(team.hp_total)}</span></td>
    <td>${team.faction ? `<span class="faction-chip ${factionClass(team.faction)}"><i></i>${esc(team.faction)}</span>` : "—"}</td>
    <td class="roster-roles">${roleBadgesHtml(team)}</td>
    <td>${speciesCellHtml(team)}</td>
    <td>${chaptersCellHtml(team)}</td>
    <td class="roster-actions">
      <button class="btn btn-xs btn-ghost" type="button" title="查看详情" data-team-detail="${esc(team.id)}">${icon("eye", 12)}</button>
      <button class="btn btn-xs btn-cyan" type="button" title="${inSeq ? "已在序列" : "加入序列"}" data-add-team="${esc(team.id)}" ${inSeq ? "disabled" : ""}>${icon(inSeq ? "check" : "plus", 12)}</button>
    </td>
  </tr>`;
}

function loadColWidths() {
  try {
    const raw = JSON.parse(localStorage.getItem(COL_WIDTHS_KEY) || "null");
    return Array.isArray(raw) && raw.length === COL_COUNT && raw.some((w) => Number(w) > 0) ? raw : null;
  } catch {
    return null;
  }
}

function applyColWidths(widths) {
  const table = rootEl?.querySelector(".roster-table");
  if (!table) return;
  const cols = [...table.querySelectorAll("col")];
  if (cols.length !== COL_COUNT) return;
  cols.forEach((col, i) => {
    col.style.width = `${Math.max(COL_MIN, Math.round(widths[i]))}px`;
  });
  table.style.minWidth = "0";
  table.style.width = `${widths.reduce((acc, w) => acc + Math.max(COL_MIN, Math.round(w)), 0)}px`;
}

function resetColWidths() {
  try {
    localStorage.removeItem(COL_WIDTHS_KEY);
  } catch {
    /* ignore */
  }
  const table = rootEl?.querySelector(".roster-table");
  if (!table) return;
  table.querySelectorAll("col").forEach((col) => {
    col.style.width = "";
  });
  table.style.minWidth = "";
  table.style.width = "";
}

function bindColResize() {
  const table = rootEl?.querySelector(".roster-table");
  if (!table) return;
  const ths = [...table.querySelectorAll("thead th")];
  table.querySelectorAll("[data-col-resize]").forEach((handle) => {
    const idx = Number(handle.dataset.colResize);
    handle.addEventListener("click", (event) => event.stopPropagation());
    handle.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      resetColWidths();
    });
    handle.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startW = ths[idx].getBoundingClientRect().width;
      // 进入手动模式：先冻结所有列当前像素宽，再拖目标列
      const manual = ths.map((th) => Math.max(COL_MIN, Math.round(th.getBoundingClientRect().width)));
      handle.classList.add("active");
      const onMove = (ev) => {
        manual[idx] = Math.max(COL_MIN, Math.round(startW + ev.clientX - startX));
        applyColWidths(manual);
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        handle.classList.remove("active");
        try {
          localStorage.setItem(COL_WIDTHS_KEY, JSON.stringify(manual));
        } catch {
          /* ignore */
        }
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
}

function tableHeadHtml() {
  const handle = (i) => `<span class="col-resize" data-col-resize="${i}" title="拖拽调整列宽 · 双击恢复默认"></span>`;
  const sortCell = (col, label, i) => {
    const cfg = SORT_COLS[col];
    const active = cfg && (state.sort === cfg.desc || state.sort === cfg.asc);
    const arrow = cfg && state.sort === cfg.desc ? "↓" : cfg && state.sort === cfg.asc ? "↑" : "↕";
    return `<th class="sortable ${active ? "active" : ""}" data-sort-col="${col}" scope="col">${label}<span class="si">${arrow}</span>${handle(i)}</th>`;
  };
  return `<thead><tr>
    ${sortCell("id", "编号", 0)}
    <th scope="col">效能${handle(1)}</th>
    ${sortCell("units", "单位/总血", 2)}
    <th scope="col">阵营${handle(3)}</th>
    <th scope="col">角色${handle(4)}</th>
    ${sortCell("species", "怪种", 5)}
    <th scope="col">出现章节${handle(6)}</th>
    <th scope="col" class="ta-r">操作${handle(7)}</th>
  </tr></thead>`;
}

function tagChip(value, label, active, attr) {
  return `<button class="rf-tag-chip ${active ? "is-active" : ""}" type="button" ${attr}="${esc(value)}">${esc(label)}</button>`;
}

function activeFilterChipsHtml() {
  const f = state.filters;
  const chips = [];
  const add = (kind, key, label) => chips.push(
    `<span class="rf-picked-chip"><span>${esc(label)}</span><button type="button" data-roster-clear="${kind}" data-clear-key="${esc(key)}" aria-label="移除">×</button></span>`,
  );
  if (f.q.trim()) add("q", "q", `搜索：${f.q.trim()}`);
  if (f.teamIds.trim()) add("teamIds", "teamIds", `编号：${f.teamIds.trim()}`);
  if (f.chapter) add("chapter", "chapter", `章节：${f.chapter}`);
  if (f.role) add("role", "role", `角色：${f.role}`);
  if (f.faction) add("faction", "faction", `阵营：${f.faction}`);
  if (f.boss === "1") add("boss", "boss", "只含 BOSS");
  if (f.boss === "0") add("boss", "boss", "不含 BOSS");
  if (f.collectable === "1") add("collectable", "collectable", "可作靶机");
  if (f.collectable === "0") add("collectable", "collectable", "仅展示");
  if (f.hpMin || f.hpMax) add("hp", "hp", `总血：${f.hpMin || "0"} ~ ${f.hpMax || "∞"}`);
  if (f.unitsMin || f.unitsMax) add("units", "units", `单位数：${f.unitsMin || "0"} ~ ${f.unitsMax || "∞"}`);
  [...f.species.values()].forEach((item) => chips.push(
    `<span class="rf-picked-chip"><span>${esc(item.name || `#${item.codex_no}`)}</span><button type="button" data-roster-clear="species" data-clear-key="${item.codex_no}" aria-label="移除">×</button></span>`,
  ));
  if (!chips.length) return `<span class="rf-picked-empty">还没有筛选 tag。选怪种、阵营或条件后会自动出现在这里。</span>`;
  return `${chips.join("")}<button class="rf-clear-all" type="button" data-roster-clear-all>${icon("close", 11)} 一键清除全部</button>`;
}

function filterPanelHtml() {
  const f = state.filters;
  const factions = ["铁血", "军方", "帕拉蒂斯", "其它"];
  return `<div class="roster-filter-card">
    <div class="rf-row rf-top-row">
      <div class="input-wrap rf-search">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索编号 / 名称 / 怪种…" data-roster-q value="${esc(f.q)}" />
      </div>
      <label class="rf-mini-field">队伍编号
        <input type="text" placeholder="如 7301601,6630191" data-roster-team-ids value="${esc(f.teamIds)}" />
      </label>
      <select class="rf-select" data-roster-chapter>${chapterOptionsHtml()}</select>
      <select class="rf-select" data-roster-role>${roleOptionsHtml()}</select>
      <select class="rf-select" data-roster-sort>${SORT_OPTIONS.map(
        ([value, label]) => `<option value="${value}" ${value === state.sort ? "selected" : ""}>${label}</option>`,
      ).join("")}</select>
      <select class="rf-select" data-roster-limit>${PAGE_SIZES.map(
        (size) => `<option value="${size}" ${size === state.limit ? "selected" : ""}>每页 ${size}</option>`,
      ).join("")}</select>
      <button class="btn btn-ghost btn-sm" type="button" data-roster-reset>${icon("rotate", 12)} 重置</button>
    </div>

    <div class="rf-tag-groups">
      <div class="rf-tag-group">
        <span class="rf-tag-label">${icon("shield", 11)} 阵营</span>
        ${tagChip("", "全部", !f.faction, "data-roster-faction")}
        ${factions.map((faction) => tagChip(faction, faction, f.faction === faction, "data-roster-faction")).join("")}
      </div>
      <div class="rf-tag-group">
        <span class="rf-tag-label">${icon("alert", 11)} BOSS</span>
        ${tagChip("", "全部", !f.boss, "data-roster-boss")}
        ${tagChip("1", "含 BOSS", f.boss === "1", "data-roster-boss")}
        ${tagChip("0", "不含 BOSS", f.boss === "0", "data-roster-boss")}
      </div>
      <div class="rf-tag-group">
        <span class="rf-tag-label">${icon("plus", 11)} 靶机</span>
        ${tagChip("", "全部", !f.collectable, "data-roster-collect")}
        ${tagChip("1", "可作靶机", f.collectable === "1", "data-roster-collect")}
        ${tagChip("0", "仅展示", f.collectable === "0", "data-roster-collect")}
      </div>
    </div>

    <div class="rf-row rf-row-2">
      <div class="species-picker" data-sp-picker>
        <div class="sp-picked" data-sp-picked>${pickedSpeciesHtml()}</div>
        <div class="sp-input-wrap">
          <span class="in-ico">${icon("filter", 12)}</span>
          <input type="text" placeholder="搜索怪种 tag 加入筛选（多选 = 同时包含）" data-sp-search autocomplete="off" />
        </div>
        <div class="sp-menu" data-sp-menu>${speciesMenuHtml()}</div>
      </div>
      <div class="rf-ranges">
        <label class="rf-range">单位数 <input type="number" min="0" placeholder="min" data-roster-units-min value="${esc(f.unitsMin)}" /> – <input type="number" min="0" placeholder="max" data-roster-units-max value="${esc(f.unitsMax)}" /></label>
        <label class="rf-range">总血量 <input type="number" min="0" placeholder="min" data-roster-hp-min value="${esc(f.hpMin)}" /> – <input type="number" min="0" placeholder="max" data-roster-hp-max value="${esc(f.hpMax)}" /></label>
        <span class="rf-meta" data-roster-meta>${icon("list", 12)} 共 — 支怪组</span>
      </div>
    </div>

    <div class="rf-picked-row" data-roster-picked>${activeFilterChipsHtml()}</div>
  </div>`;
}

function shellHtml() {
  return `${pageHeadHtml({
    crumbs: [{ label: "全怪组" }],
    title: "全怪组",
    badge: "ROSTER",
    sub: "全部敌人队伍总表：按编号 / 怪种 tag / 阵营 / BOSS / 可作靶机 / 总血量 / 单位数 / 出场章节筛选与排序。筛选条件会在返回本页时保留，可一键清除。机场候选为推断数据，标「可能刷怪」。",
  })}
  ${filterPanelHtml()}
  <div class="roster-table-wrap">
    <table class="data-table roster-table"><colgroup>${"<col>".repeat(COL_COUNT)}</colgroup>${tableHeadHtml()}<tbody data-roster-tbody>
      <tr><td colspan="8"><div class="roster-loading"><span class="spinner"></span> 正在加载怪组…</div></td></tr>
    </tbody></table>
  </div>
  <div data-roster-pager class="roster-pager"></div>`;
}

function pagerHtml(total) {
  const maxPage = Math.max(1, Math.ceil(total / state.limit));
  return `<div class="roster-pager-row">
    <span class="tb-meta">${icon("list", 12)} 第 <b>${state.page}</b> / ${maxPage} 页</span>
    ${renderPager({ page: state.page, total, pageSize: state.limit })}
  </div>`;
}

function emptyHtml() {
  return `<div class="roster-empty">${emptyState({
    iconName: "search",
    title: "没有符合条件的怪组",
    desc: "试试放宽关键词、编号、阵营、BOSS、靶机、怪种、总血量或单位数筛选，或点击一键清除。",
  })}<div class="roster-empty-actions"><button class="btn btn-sm btn-cyan" type="button" data-roster-reset>${icon("rotate", 12)} 重置筛选条件</button></div></div>`;
}

export async function render(root) {
  rootEl = root;
  const saved = readRosterState();
  state.page = Math.max(1, Number(saved?.page) || 1);
  state.limit = PAGE_SIZES.includes(Number(saved?.limit)) ? Number(saved.limit) : 50;
  state.sort = SORT_OPTIONS.some(([value]) => value === saved?.sort) ? saved.sort : "id_asc";
  state.filters = defaultFilters();
  if (saved?.filters && typeof saved.filters === "object") {
    for (const key of ["q", "chapter", "role", "faction", "boss", "collectable", "teamIds", "hpMin", "hpMax", "unitsMin", "unitsMax"]) {
      if (typeof saved.filters[key] === "string") state.filters[key] = saved.filters[key];
    }
    if (Array.isArray(saved.filters.species)) {
      for (const item of saved.filters.species) {
        const codex = Number(item?.codex_no);
        if (Number.isFinite(codex)) state.filters.species.set(codex, item);
      }
    }
  }
  state.total = 0;
  root.innerHTML = `<div data-roster-body>${shellHtml()}</div>`;

  // 章节下拉：复用 /api/chapters（按 7 组 optgroup）
  try {
    await loadChapters();
  } catch {
    /* 章节加载失败时退化为「全部章节」 */
  }
  state.chapters = store.chapters?.groups || [];
  const chapterSelect = rootEl.querySelector("[data-roster-chapter]");
  if (chapterSelect) chapterSelect.innerHTML = chapterOptionsHtml();

  // 怪种多选：一次加载 264 个怪种（供本地搜索过滤，不随总表分页）
  try {
    const data = await api.species({ limit: 400, offset: 0 });
    state.speciesOptions = (data.items || []).slice().sort((a, b) => Number(a.codex_no) - Number(b.codex_no));
  } catch {
    state.speciesOptions = [];
  }
  const spMenu = rootEl.querySelector("[data-sp-menu]");
  if (spMenu) spMenu.innerHTML = speciesMenuHtml();

  bindEvents();
  bindColResize();
  const savedWidths = loadColWidths();
  if (savedWidths) applyColWidths(savedWidths);
  await loadTeams();
  if (saved && Number(saved.scroll) > 0) {
    requestAnimationFrame(() => {
      const scroller = rosterScroller();
      if (scroller) scroller.scrollTop = Number(saved.scroll) || 0;
    });
  }
}

function bindEvents() {
  const root = rootEl;
  if (!root) return;

  bindSearch(root.querySelector("[data-roster-q]"), (value) => {
    state.filters.q = value;
    state.page = 1;
    refreshFilterUi();
    loadTeams();
  });

  const teamIdInput = root.querySelector("[data-roster-team-ids]");
  if (teamIdInput) {
    let timer = null;
    teamIdInput.addEventListener("input", () => {
      state.filters.teamIds = teamIdInput.value.trim();
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.page = 1;
        refreshFilterUi();
        loadTeams();
      }, 380);
    });
  }

  root.querySelector("[data-roster-chapter]")?.addEventListener("change", (event) => {
    state.filters.chapter = event.target.value;
    state.page = 1;
    refreshFilterUi();
    loadTeams();
  });
  root.querySelector("[data-roster-role]")?.addEventListener("change", (event) => {
    state.filters.role = event.target.value;
    state.page = 1;
    refreshFilterUi();
    loadTeams();
  });
  root.querySelector("[data-roster-sort]")?.addEventListener("change", (event) => {
    state.sort = event.target.value;
    state.page = 1;
    loadTeams();
  });
  root.querySelector("[data-roster-limit]")?.addEventListener("change", (event) => {
    state.limit = Number(event.target.value) || 50;
    state.page = 1;
    loadTeams();
  });

  const numericFields = [
    ["[data-roster-units-min]", "unitsMin"],
    ["[data-roster-units-max]", "unitsMax"],
    ["[data-roster-hp-min]", "hpMin"],
    ["[data-roster-hp-max]", "hpMax"],
  ];
  numericFields.forEach(([selector, key]) => {
    const input = root.querySelector(selector);
    if (!input) return;
    let timer = null;
    input.addEventListener("input", () => {
      state.filters[key] = input.value.trim();
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.page = 1;
        refreshFilterUi();
        loadTeams();
      }, 420);
    });
  });

  root.querySelectorAll("[data-roster-reset]").forEach((button) => {
    button.addEventListener("click", () => resetFilters());
  });

  // Taobao-style tag choices
  root.querySelectorAll("[data-roster-faction]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters.faction = button.dataset.rosterFaction || "";
      state.page = 1;
      refreshFilterUi();
      loadTeams();
    });
  });
  root.querySelectorAll("[data-roster-boss]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters.boss = button.dataset.rosterBoss || "";
      state.page = 1;
      refreshFilterUi();
      loadTeams();
    });
  });
  root.querySelectorAll("[data-roster-collect]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters.collectable = button.dataset.rosterCollect || "";
      state.page = 1;
      refreshFilterUi();
      loadTeams();
    });
  });

  // Remove one tag / clear all tags
  root.querySelector("[data-roster-picked]")?.addEventListener("click", (event) => {
    const clearAll = event.target.closest("[data-roster-clear-all]");
    if (clearAll) {
      resetFilters();
      return;
    }
    const clear = event.target.closest("[data-roster-clear]");
    if (!clear) return;
    const kind = clear.dataset.rosterClear;
    if (kind === "species") {
      state.filters.species.delete(Number(clear.dataset.clearKey));
    } else if (kind === "hp") {
      state.filters.hpMin = "";
      state.filters.hpMax = "";
      syncInput("[data-roster-hp-min]", "");
      syncInput("[data-roster-hp-max]", "");
    } else if (kind === "units") {
      state.filters.unitsMin = "";
      state.filters.unitsMax = "";
      syncInput("[data-roster-units-min]", "");
      syncInput("[data-roster-units-max]", "");
    } else if (kind === "q") {
      state.filters.q = "";
      syncInput("[data-roster-q]", "");
    } else if (kind === "teamIds") {
      state.filters.teamIds = "";
      syncInput("[data-roster-team-ids]", "");
    } else if (kind === "chapter") {
      state.filters.chapter = "";
      syncInput("[data-roster-chapter]", "");
    } else if (kind === "role") {
      state.filters.role = "";
      syncInput("[data-roster-role]", "");
    } else {
      state.filters[kind] = "";
    }
    state.page = 1;
    refreshFilterUi();
    loadTeams();
  });

  // Table header sorting
  root.querySelectorAll("th[data-sort-col]").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.sortCol;
      const cfg = SORT_COLS[col];
      if (!cfg) return;
      state.sort = state.sort === cfg.desc ? cfg.asc : cfg.desc;
      syncInput("[data-roster-sort]", state.sort);
      state.page = 1;
      loadTeams();
    });
  });

  // Species picker
  const spInput = root.querySelector("[data-sp-search]");
  const spMenu = root.querySelector("[data-sp-menu]");
  const spPicker = root.querySelector("[data-sp-picker]");
  const openMenu = () => {
    spMenu?.classList.add("open");
    spMenu.innerHTML = speciesMenuHtml(spInput?.value || "");
  };
  spInput?.addEventListener("focus", openMenu);
  spInput?.addEventListener("input", () => {
    if (spMenu) spMenu.innerHTML = speciesMenuHtml(spInput.value);
    openMenu();
  });
  spInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      spMenu?.querySelector("[data-sp-opt]")?.click();
    } else if (event.key === "Escape") {
      spMenu?.classList.remove("open");
    }
  });
  spPicker?.addEventListener("click", (event) => {
    const opt = event.target.closest("[data-sp-opt]");
    if (opt) {
      const codex = Number(opt.dataset.spOpt);
      const item = state.speciesOptions.find((species) => Number(species.codex_no) === codex);
      if (!item) return;
      if (state.filters.species.has(codex)) state.filters.species.delete(codex);
      else state.filters.species.set(codex, item);
      if (spInput) spInput.value = "";
      refreshFilterUi();
      state.page = 1;
      loadTeams();
      return;
    }
    const remove = event.target.closest("[data-sp-remove]");
    if (remove) {
      event.stopPropagation();
      state.filters.species.delete(Number(remove.dataset.spRemove));
      refreshFilterUi();
      state.page = 1;
      loadTeams();
    }
  });
  if (!outsideClickBound) {
    outsideClickBound = true;
    document.addEventListener("click", (event) => {
      if (!event.target.closest("[data-sp-picker]")) {
        document.querySelector("[data-sp-menu]")?.classList.remove("open");
      }
    });
  }

  // Remember the scroll position for "back to roster".
  if (!rosterScrollBound) {
    const scroller = rosterScroller();
    if (scroller) {
      let scrollTimer = null;
      scroller.addEventListener("scroll", () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
          try {
            const raw = sessionStorage.getItem(ROSTER_STATE_KEY);
            const data = raw ? JSON.parse(raw) : {};
            data.scroll = scroller.scrollTop;
            sessionStorage.setItem(ROSTER_STATE_KEY, JSON.stringify(data));
          } catch {
            /* ignore */
          }
        }, 180);
      }, { passive: true });
      rosterScrollBound = true;
    }
  }

  bindPagerDelegation();
}

function syncInput(selector, value) {
  const el = rootEl?.querySelector(selector);
  if (el) el.value = value;
}

function refreshFilterUi() {
  const picked = rootEl?.querySelector("[data-roster-picked]");
  if (picked) picked.innerHTML = activeFilterChipsHtml();
  const speciesPicked = rootEl?.querySelector("[data-sp-picked]");
  if (speciesPicked) speciesPicked.innerHTML = pickedSpeciesHtml();
  const menu = rootEl?.querySelector("[data-sp-menu]");
  if (menu) menu.innerHTML = speciesMenuHtml(rootEl?.querySelector("[data-sp-search]")?.value || "");
  rootEl?.querySelectorAll("[data-roster-faction]").forEach((button) => {
    button.classList.toggle("is-active", (button.dataset.rosterFaction || "") === state.filters.faction);
  });
  rootEl?.querySelectorAll("[data-roster-boss]").forEach((button) => {
    button.classList.toggle("is-active", (button.dataset.rosterBoss || "") === state.filters.boss);
  });
  rootEl?.querySelectorAll("[data-roster-collect]").forEach((button) => {
    button.classList.toggle("is-active", (button.dataset.rosterCollect || "") === state.filters.collectable);
  });
}

function resetFilters() {
  clearRosterState();
  state.filters = defaultFilters();
  state.sort = "id_asc";
  state.page = 1;
  const root = rootEl;
  if (!root) return;
  syncInput("[data-roster-q]", "");
  syncInput("[data-roster-team-ids]", "");
  syncInput("[data-roster-chapter]", "");
  syncInput("[data-roster-role]", "");
  syncInput("[data-roster-sort]", state.sort);
  syncInput("[data-roster-units-min]", "");
  syncInput("[data-roster-units-max]", "");
  syncInput("[data-roster-hp-min]", "");
  syncInput("[data-roster-hp-max]", "");
  refreshFilterUi();
  loadTeams();
}

function bindPagerDelegation() {
  const pagerHost = rootEl.querySelector("[data-roster-pager]");
  if (!pagerHost) return;
  pagerHost.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (!button || button.disabled) return;
    const page = Number(button.dataset.page);
    if (!Number.isFinite(page) || page === state.page) return;
    state.page = page;
    loadTeams();
  });
}

async function loadTeams() {
  const token = ++reqToken;
  saveRosterState();
  const tbody = rootEl.querySelector("[data-roster-tbody]");
  const pagerHost = rootEl.querySelector("[data-roster-pager]");
  if (!tbody) return;
  state.loading = true;
  tbody.innerHTML = `<tr><td colspan="8"><div class="roster-loading"><span class="spinner"></span> 正在加载怪组…</div></td></tr>`;
  try {
    const data = await api.teams(buildQuery());
    if (token !== reqToken) return;
    state.total = Number(data.total) || 0;
    const items = data.items || [];
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="8">${emptyHtml()}</td></tr>`;
      if (pagerHost) pagerHost.innerHTML = "";
      updateMeta(true);
      return;
    }
    tbody.innerHTML = items.map(rowHtml).join("");
    if (pagerHost) pagerHost.innerHTML = pagerHtml(state.total);
    updateMeta(false);
  } catch (err) {
    if (token !== reqToken) return;
    tbody.innerHTML = `<tr><td colspan="8"><div class="roster-error">${icon("alert", 16)} 读取怪组总表失败：${esc(err.message || "未知错误")}${
      err.status === 404 ? "（/api/teams 接口尚未就绪）" : ""
    }<button class="btn btn-sm btn-cyan" type="button" data-roster-retry>${icon("refresh", 12)} 重试</button></div></td></tr>`;
    rootEl.querySelector("[data-roster-retry]")?.addEventListener("click", () => loadTeams());
    if (pagerHost) pagerHost.innerHTML = "";
  } finally {
    state.loading = false;
  }
}

function updateMeta(isEmpty) {
  const meta = rootEl.querySelector("[data-roster-meta]");
  if (!meta) return;
  const speciesCount = state.filters.species.size;
  const parts = [`共 <b>${fmtNum(state.total)}</b> 支怪组`];
  if (speciesCount) parts.push(`同时包含 <b>${speciesCount}</b> 个怪种`);
  if (state.filters.faction) parts.push(`阵营 ${esc(state.filters.faction)}`);
  if (state.filters.boss) parts.push(state.filters.boss === "1" ? "含 BOSS" : "不含 BOSS");
  if (state.filters.collectable) parts.push(state.filters.collectable === "1" ? "可作靶机" : "仅展示");
  if (state.filters.teamIds) parts.push(`编号 ${esc(state.filters.teamIds)}`);
  if (state.filters.hpMin || state.filters.hpMax) parts.push("已按总血量过滤");
  if (state.filters.chapter) parts.push("已按章节出现位置过滤");
  meta.innerHTML = `${icon("list", 12)} ${parts.join(" · ")}${isEmpty ? "（无结果）" : ""}`;
}
