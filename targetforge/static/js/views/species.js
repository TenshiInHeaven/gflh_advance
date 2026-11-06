/* views/species.js —— 怪种图鉴：分页 / 搜索 / 阵营与分类筛选 */
import { api } from "../api.js";
import {
  icon,
  pageHeadHtml,
  speciesCardHtml,
  skeletonCards,
  handleViewError,
  emptyState,
  renderPager,
  bindPager,
} from "../ui.js";
import { esc, fmtNum, navigate, bindSearch } from "../util.js";

const PAGE_SIZE = 48;
const CATEGORIES = [
  { id: "all", label: "全部" },
  { id: "normal", label: "固定关卡" },
  { id: "grayzone", label: "灰域" },
  { id: "orphan", label: "无固定关卡" },
];
const FACTIONS = ["", "铁血", "军方", "帕拉蒂斯", "其它"];

const state = { page: 1, total: 0, query: "", faction: "", category: "all", items: [], loading: false };
let rootEl = null;

export async function render(root) {
  rootEl = root;
  state.page = 1;
  state.query = "";
  state.faction = "";
  state.category = "all";
  state.items = [];
  state.total = 0;

  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [{ label: "怪种图鉴" }],
      title: "怪种图鉴",
      badge: "SPECIES",
      sub: "264 个图鉴怪种及其全部可收藏队伍。支持按名称 / 编号搜索，按阵营与出现分类筛选；点卡片查看所有怪组。",
    })}
    <div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索怪种名称 / 图鉴编号…" data-sp-search />
      </div>
      <select class="select" data-sp-faction>
        ${FACTIONS.map((faction) => `<option value="${esc(faction)}">${faction ? esc(faction) : "全部阵营"}</option>`).join("")}
      </select>
      <div class="segmented" data-sp-cat>
        ${CATEGORIES.map(
          (category, index) =>
            `<button type="button" class="${index === 0 ? "active" : ""}" data-cat="${category.id}">${category.label}</button>`,
        ).join("")}
      </div>
      <span class="spacer"></span>
      <span class="tb-meta" data-sp-meta>${icon("crosshair", 11)} 读取中…</span>
    </div>
    <div data-sp-area>${skeletonCards(12, { height: 78, minWidth: 232 })}</div>
  `;

  const areaEl = root.querySelector("[data-sp-area]");

  const load = async (page = 1) => {
    if (state.loading) return;
    state.loading = true;
    areaEl.innerHTML = skeletonCards(12, { height: 78, minWidth: 232 });
    try {
      const data = await api.species({
        q: state.query,
        faction: state.faction,
        category: state.category,
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      state.total = data.total || 0;
      state.items = data.items || [];
      state.page = page;
      renderList();
    } catch (err) {
      handleViewError(areaEl, err, () => render(root));
    } finally {
      state.loading = false;
    }
  };

  const renderList = () => {
    const metaEl = root.querySelector("[data-sp-meta]");
    if (metaEl) {
      metaEl.innerHTML = `${icon("crosshair", 11)} 匹配 <b>${fmtNum(state.total)}</b> / 264 个怪种 · 每页 ${PAGE_SIZE}`;
    }
    if (!state.items.length) {
      areaEl.innerHTML = emptyState({
        iconName: "crosshair",
        title: "没有匹配的怪种",
        desc: "换个关键词、阵营或分类再试试。",
      });
      return;
    }
    areaEl.innerHTML = `
      <div class="species-grid">${state.items.map((item) => speciesCardHtml(item)).join("")}</div>
      ${renderPager({ page: state.page, total: state.total, pageSize: PAGE_SIZE })}
    `;
    bindPager(areaEl, {
      page: state.page,
      total: state.total,
      pageSize: PAGE_SIZE,
      onChange: (page) => {
        load(page).then(() => areaEl.scrollIntoView({ behavior: "smooth", block: "start" }));
      },
    });
    areaEl.querySelectorAll("[data-species-detail]").forEach((card) => {
      card.addEventListener("click", () => navigate(`/species/${card.dataset.speciesDetail}`));
    });
  };

  bindSearch(root.querySelector("[data-sp-search]"), (value) => {
    state.query = value;
    load(1);
  });
  root.querySelector("[data-sp-faction]").addEventListener("change", (event) => {
    state.faction = event.target.value;
    load(1);
  });
  root.querySelector("[data-sp-cat]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-cat]");
    if (!button) return;
    root.querySelectorAll("[data-sp-cat] button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.category = button.dataset.cat;
    load(1);
  });

  load(1);
}
