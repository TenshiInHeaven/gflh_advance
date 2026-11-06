/* views/grayzone.js —— 灰域区域：队伍服务端分页 + 搜索 + 效能筛选/排序 */
import { api } from "../api.js";
import { normalizeGrayMeta, areaRegionNames } from "../components/grayzone-meta.js";
import { store, sequenceStats, addTeams } from "../store.js";
import {
  icon,
  pageHeadHtml,
  teamCardHtml,
  skeletonCards,
  handleViewError,
  emptyState,
  renderPager,
  bindPager,
  toastOk,
  toastErr,
  confirmDialog,
  setBusy,
} from "../ui.js";
import {
  filterAndSortTeams,
  bindPowerFilter,
  powerFilterBarHtml,
  powerFilterMeta,
  serverPowerParams,
  defaultPowerFilter,
} from "../components/power-filter.js";
import { esc, fmtNum, navigate, bindSearch } from "../util.js";

const PAGE_SIZE = 30;
const state = {
  page: 1,
  query: "",
  total: 0,
  items: [],
  area: null,
  loading: false,
  filter: defaultPowerFilter(),
};
let rootEl = null;

export async function render(root, { params, query }) {
  rootEl = root;
  const areaId = (params.area || "").trim();
  state.page = 1;
  state.query = "";
  state.items = [];
  state.total = 0;
  state.filter = defaultPowerFilter();

  // 灰域层级：区域（沙尘带/风暴带/硅状带/结晶带/特殊区域）→ 地点（14 个）
  let grayMeta = { regions: [], areas: [], hasRegions: false };
  try {
    grayMeta = normalizeGrayMeta(await api.grayzoneAreas());
  } catch {
    grayMeta = { regions: [], areas: [], hasRegions: false };
  }
  const areaMeta = (grayMeta.areas || []).find((area) => area.id === areaId || area.title === areaId);
  const areaTitle = (areaMeta?.title || areaId).trim();
  const regionNames = areaRegionNames(areaMeta || {}, grayMeta.regions || []);
  const regionParam = String((query && query.region) || "").trim();
  const selectedRegionName = (grayMeta.regions || []).find(
    (region) => region.id === regionParam || region.title === regionParam,
  )?.title || regionParam;
  const crumbs = [
    { label: "关卡图鉴", nav: "/chapters" },
    { label: "灰域探查", nav: "/chapters/grayzone" },
  ];
  if (selectedRegionName) crumbs.push({ label: selectedRegionName });
  crumbs.push({ label: areaTitle });

  root.innerHTML = pageHeadHtml({
    crumbs,
    title: areaTitle,
    badge: "GRAY ZONE",
    sub: `${regionNames.length ? `区域：${esc(regionNames.join(" / "))} · ` : ""}灰域地点内的可收藏队伍。灰域不逐节点列举关卡，这里按地点分页浏览，支持搜索队伍 id 与效能筛选/排序。`,
    actions: `<button class="btn btn-primary" type="button" data-act="add-page" disabled>${icon("plus", 14)} 本页全部加入序列</button>`,
  }) + `
    <div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索队伍 id / 阵营 / 怪种…" data-gz-search />
      </div>
      <button class="btn btn-ghost" type="button" data-act="reload">${icon("refresh", 13)} 刷新</button>
      <span class="spacer"></span>
      <span class="tb-meta" data-gz-meta>${icon("radar", 11)} 读取中…</span>
      <div style="flex-basis:100%">${powerFilterBarHtml()}</div>
    </div>
    <div data-gz-area>${skeletonCards(8)}</div>
  `;

  const areaEl = root.querySelector("[data-gz-area]");
  const addPageBtn = root.querySelector('[data-act="add-page"]');
  if (addPageBtn) addPageBtn.addEventListener("click", () => addPageToSequence(addPageBtn));

  const load = async (page = 1) => {
    if (state.loading) return;
    state.loading = true;
    try {
      const data = await api.grayzoneTeams({
        area: areaId,
        region: regionParam || (areaMeta?.region_ids || [])[0] || "",
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: state.query,
        ...serverPowerParams(state.filter),
      });
      state.total = data.total || 0;
      state.items = filterAndSortTeams(data.items || [], state.filter);
      state.page = page;
      renderList();
    } catch (err) {
      if (err.status === 503 || err.status === 0) handleViewError(areaEl, err, () => render(root, { params }));
      else {
        areaEl.innerHTML = emptyState({
          iconName: "users",
          title: "区域队伍加载失败",
          desc: err.message || "未知错误",
        });
      }
    } finally {
      state.loading = false;
    }
  };

  const renderList = () => {
    const metaEl = root.querySelector("[data-gz-meta]");
    if (metaEl) {
      metaEl.innerHTML = `${icon("users", 11)} 共 <b>${fmtNum(state.total)}</b> 支可收藏队伍 · 每页 ${PAGE_SIZE}`;
    }
    const pfMeta = root.querySelector("[data-pf-meta]");
    if (pfMeta) pfMeta.textContent = powerFilterMeta(state.filter, state.total, state.items.length);
    if (!state.items.length) {
      const filtering = state.query || state.filter.mode !== "all";
      areaEl.innerHTML = emptyState({
        iconName: filtering ? "search" : "users",
        title: filtering ? "没有匹配的队伍" : state.total === 0 ? "该地点暂无可收藏队伍" : "该地点暂无队伍",
        desc: filtering
          ? "换个关键词或效能条件试试。"
          : state.total === 0
            ? "该地点在 mission 表里有节点，但没有可收藏队伍，这里只作为地点展示；换一个地点看看。"
            : "换一个灰域地点看看。",
      });
      return;
    }
    areaEl.innerHTML = `
      <div class="team-grid">${state.items.map((team) => teamCardHtml(team)).join("")}</div>
      ${renderPager({ page: state.page, total: Math.max(state.total, state.items.length), pageSize: PAGE_SIZE })}
    `;
    bindPager(areaEl, {
      page: state.page,
      total: state.total,
      pageSize: PAGE_SIZE,
      onChange: (page) => {
        load(page).then(() => areaEl.scrollIntoView({ behavior: "smooth", block: "start" }));
      },
    });
    if (addPageBtn) {
      addPageBtn.disabled = false;
      addPageBtn.innerHTML = `${icon("plus", 14)} 本页全部加入序列 <span class="mono-inline" style="opacity:.75">(${state.items.length})</span>`;
    }
  };

  const addPageToSequence = async (button) => {
    if (!state.items.length) return;
    const remaining = 35 - sequenceStats().count;
    if (remaining <= 0) {
      toastErr("序列已满", "序列上限 35，请先移除一些队伍。");
      return;
    }
    let toAdd = state.items;
    if (toAdd.length > remaining) {
      const ok = await confirmDialog({
        title: "加入本页队伍",
        message: `本页 ${toAdd.length} 支队伍，序列剩余 ${remaining} 个位置。`,
        detail: `将把前 ${remaining} 支加入序列。`,
        confirmText: `加入前 ${remaining} 支`,
      });
      if (!ok) return;
      toAdd = toAdd.slice(0, remaining);
    }
    setBusy(button, true, "加入中…");
    try {
      const sequence = await addTeams(toAdd.map((team) => team.id));
      toastOk("已加入序列", `成功加入 ${toAdd.length} 支队伍 · 当前序列 ${sequence.count}/${sequence.max}`);
    } catch (err) {
      toastErr("加入失败", err.message);
    } finally {
      setBusy(button, false);
    }
  };

  bindSearch(root.querySelector("[data-gz-search]"), (value) => {
    state.query = value;
    load(1);
  });

  bindPowerFilter(root, (filter) => {
    state.filter = filter;
    state.page = 1;
    load(1);
  });

  root.querySelector('[data-act="reload"]')?.addEventListener("click", () => load(state.page));

  load(1);
}
