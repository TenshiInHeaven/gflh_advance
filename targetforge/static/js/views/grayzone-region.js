/* views/grayzone-region.js —— 灰域区域 / 装甲突击 / 特殊区域：节点列表（节点 → 节点内小怪） */
import { api } from "../api.js";
import {
  icon,
  pageHeadHtml,
  skeletonRows,
  handleViewError,
  emptyState,
  renderPager,
  bindPager,
  speciesIconHtml,
} from "../ui.js";
import { esc, fmtNum, navigate, bindSearch } from "../util.js";
import { normalizeGrayMeta, grayHomeModel } from "../components/grayzone-meta.js";

const PAGE_SIZE = 30;
const SORT_OPTIONS = [
  ["id_asc", "编号 ↑"],
  ["id_desc", "编号 ↓"],
  ["teams_desc", "队伍数 ↓"],
  ["difficulty_desc", "难度 ↓"],
];
const state = {
  regionId: "",
  region: null,
  page: 1,
  query: "",
  sort: "id_asc",
  total: 0,
  items: [],
  loading: false,
};
let rootEl = null;
let reqToken = 0;

function normalizeNode(item) {
  return {
    id: item.mission_id ?? item.stage_id ?? item.id ?? "",
    title: String(item.title ?? item.stage_title ?? "").trim(),
    location: String(item.location ?? item.area_title ?? item.area ?? "").trim(),
    region_id: item.region_id ?? "",
    region_title: item.region_title ?? "",
    difficulty: Number(item.difficulty) || 0,
    team_count: Number(item.team_count) || 0,
    species_count: Number(item.species_count) || 0,
    topSpecies: Array.isArray(item.top_species) ? item.top_species : Array.isArray(item.species) ? item.species : [],
    tags: Array.isArray(item.tags) ? item.tags : [],
  };
}

function nodeRowHtml(node) {
  const species = node.topSpecies.slice(0, 4);
  return `<button class="node-row" type="button" data-node-id="${esc(node.id)}">
    <span class="node-main">
      <span class="node-title">${esc(node.title || `#${node.id}`)}</span>
      <span class="node-loc">${icon("map", 10)} ${esc(node.location || "灰域节点")}</span>
      ${node.tags.length ? `<span class="node-tags">${node.tags.slice(0, 3).map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</span>` : ""}
    </span>
    <span class="node-species">${
      species.length
        ? species.map((item) => `<span class="node-sp" title="${esc(item.name || "")}">${speciesIconHtml(item, { size: 20, variant: "mini" })}</span>`).join("")
        : `<span class="text-mute">—</span>`
    }</span>
    <span class="node-stats">
      <span><b>${fmtNum(node.team_count)}</b> 队伍</span>
      <span><b>${fmtNum(node.species_count)}</b> 怪种</span>
      <span><b>${fmtNum(node.difficulty)}</b> 难度</span>
    </span>
    <span class="node-go">${icon("chevronRight", 14)}</span>
  </button>`;
}

function headHtml(region, total) {
  const title = region?.title || state.regionId;
  const isArmor = region?.isTower || region?.kind === "tower" || /装甲突击/.test(`${state.regionId} ${title}`);
  const isSpecial = region?.isSpecial || state.regionId === "special" || /特殊区域/.test(title);
  return pageHeadHtml({
    crumbs: [
      { label: "关卡图鉴", nav: "/chapters" },
      { label: "灰域探查", nav: "/chapters/grayzone" },
      { label: title },
    ],
    title: total ? `${title} · ${fmtNum(total)} 个节点` : title,
    badge: isArmor ? "TOWER · 爬塔关卡" : isSpecial ? "SPECIAL REGION" : "GRAY REGION",
    sub: isArmor
      ? `装甲突击（爬塔关卡）共 ${fmtNum(total)} 个节点 · 点节点查看该节点可收藏队伍（含支援 / 机场推断）。`
      : isSpecial
        ? `特殊区域（组 5/6 等客户端无区域名的节点集合）共 ${fmtNum(total)} 个节点 · 点节点查看该节点可收藏队伍。`
        : `${esc(title)} 共 ${fmtNum(total)} 个节点 · 节点按地点（mission 前缀）分布，点节点查看该节点可收藏队伍（含支援 / 机场推断）。`,
    actions: `<button class="btn btn-ghost" type="button" data-nav="/chapters/grayzone">${icon("chevronLeft", 14)} 返回灰域</button>`,
  });
}

export async function render(root, { params }) {
  rootEl = root;
  state.regionId = String(params.region || "").trim();
  state.page = 1;
  state.query = "";
  state.sort = "id_asc";
  state.items = [];
  state.total = 0;

  root.innerHTML =
    headHtml(null, 0) +
    `<div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索节点标题 / 地点 / 编号…" data-node-search />
      </div>
      <select class="rf-select" data-node-sort>${SORT_OPTIONS.map(
        ([value, label]) => `<option value="${value}" ${value === state.sort ? "selected" : ""}>${label}</option>`,
      ).join("")}</select>
      <span class="spacer"></span>
      <span class="tb-meta" data-node-meta>${icon("flag", 11)} 读取中…</span>
    </div>
    <div data-node-list>${skeletonRows(8)}</div>`;

  // 区域信息（标题 / 爬塔标记 / 特殊标记）
  try {
    const meta = normalizeGrayMeta(await api.grayzoneAreas());
    const home = grayHomeModel(meta.regions, meta.areas);
    state.region =
      home.mainRegions.find((region) => region.id === state.regionId) ||
      (home.armor && (home.armor.id === state.regionId || home.armor.title === state.regionId) ? home.armor : null) ||
      (home.special && (home.special.id === state.regionId || home.special.title === state.regionId) ? home.special : null) ||
      meta.regions.find((region) => region.id === state.regionId || region.title === state.regionId) ||
      { id: state.regionId, title: state.regionId };
  } catch {
    state.region = { id: state.regionId, title: state.regionId };
  }

  bindEvents();
  await loadNodes();
}

function bindEvents() {
  bindSearch(rootEl.querySelector("[data-node-search]"), (value) => {
    state.query = value;
    state.page = 1;
    loadNodes();
  });
  rootEl.querySelector("[data-node-sort]")?.addEventListener("change", (event) => {
    state.sort = event.target.value;
    state.page = 1;
    loadNodes();
  });
}

async function loadNodes() {
  const token = ++reqToken;
  const listEl = rootEl.querySelector("[data-node-list]");
  const metaEl = rootEl.querySelector("[data-node-meta]");
  if (!listEl) return;
  listEl.innerHTML = skeletonRows(8);
  try {
    const data = await api.grayzoneNodes({
      region: state.regionId,
      offset: (state.page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
      q: state.query,
      sort: state.sort,
    });
    if (token !== reqToken) return;
    state.total = Number(data.total) || 0;
    state.items = (data.items || []).map(normalizeNode);
    if (!state.region?.title && data.region_title) state.region = { ...(state.region || {}), id: state.regionId, title: data.region_title };

    // 头部标题带实际节点数
    const headHost = rootEl.querySelector(".page-head");
    if (headHost) {
      const regionForHead = state.region || { id: state.regionId, title: data.region_title || state.regionId };
      const wrapper = document.createElement("div");
      wrapper.innerHTML = headHtml(regionForHead, state.total);
      const newHead = wrapper.firstElementChild;
      if (newHead) headHost.replaceWith(newHead);
    }
    if (metaEl) {
      metaEl.innerHTML = `${icon("flag", 11)} 共 <b>${fmtNum(state.total)}</b> 个节点 · 第 ${state.page} / ${Math.max(1, Math.ceil(state.total / PAGE_SIZE))} 页`;
    }
    if (!state.items.length) {
      listEl.innerHTML = emptyState({
        iconName: state.query ? "search" : "flag",
        title: state.query ? "没有匹配的节点" : "该区域暂无节点",
        desc: state.query ? "换个关键词试试。" : "换一个区域或稍后重试。",
      });
      return;
    }
    listEl.innerHTML = `<div class="node-list">${state.items.map((node) => nodeRowHtml(node)).join("")}</div>
      ${renderPager({ page: state.page, total: state.total, pageSize: PAGE_SIZE })}`;
    bindPager(listEl, {
      page: state.page,
      total: state.total,
      pageSize: PAGE_SIZE,
      onChange: (page) => {
        state.page = page;
        loadNodes();
        listEl.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    });
    listEl.querySelectorAll("[data-node-id]").forEach((row) => {
      row.addEventListener("click", () => {
        const node = state.items.find((item) => String(item.id) === String(row.dataset.nodeId));
        try {
          sessionStorage.setItem(
            "tf:gray-region",
            JSON.stringify({
              id: state.regionId,
              title: state.region?.title || state.regionId,
              location: node?.location || "",
            }),
          );
        } catch {
          /* ignore */
        }
        navigate(`/stages/${encodeURIComponent(row.dataset.nodeId)}`);
      });
    });
  } catch (err) {
    if (token !== reqToken) return;
    if (metaEl) metaEl.textContent = "";
    listEl.innerHTML = `<div class="empty" style="padding:40px 20px">
      <div class="em-ico">${icon("alert", 26)}</div>
      <h4>节点列表读取失败</h4>
      <p>${esc(err.message || "未知错误")}${err.status === 404 ? "（/api/grayzone/nodes 接口尚未就绪，稍后重试）" : ""}</p>
      <div style="margin-top:14px"><button class="btn btn-sm btn-cyan" type="button" data-node-retry>${icon("refresh", 12)} 重试</button></div>
    </div>`;
    listEl.querySelector("[data-node-retry]")?.addEventListener("click", () => loadNodes());
  }
}
