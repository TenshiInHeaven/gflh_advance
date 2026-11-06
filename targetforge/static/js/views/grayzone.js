/* views/grayzone.js —— 灰域区域：队伍分页 + 搜索 */
import { api } from "../api.js";
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
  sortTeamsByPower,
} from "../ui.js";
import { esc, fmtNum, navigate, bindSearch } from "../util.js";

const PAGE_SIZE = 30;
const state = { page: 1, query: "", total: 0, items: [], area: null, loading: false };
let rootEl = null;
let searchTimer = null;

export async function render(root, { params }) {
  rootEl = root;
  const areaId = params.area;
  state.page = 1;
  state.query = "";
  state.items = [];
  state.total = 0;

  root.innerHTML = pageHeadHtml({
    crumbs: [
      { label: "关卡图鉴", nav: "/chapters" },
      { label: "灰域探查", nav: "/chapters/grayzone" },
      { label: areaId },
    ],
    title: areaId,
    badge: "GRAY ZONE",
    sub: "灰域区域内的可收藏队伍。灰域不逐节点列举关卡，这里按区域分页浏览，支持搜索队伍 id。",
    actions: `<button class="btn btn-primary" type="button" data-act="add-page" disabled>${icon("plus", 14)} 本页全部加入序列</button>`,
  }) + `
    <div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索队伍 id…" data-gz-search />
      </div>
      <button class="btn btn-ghost" type="button" data-act="reload">${icon("refresh", 13)} 刷新</button>
      <span class="spacer"></span>
      <span class="tb-meta" data-gz-meta>${icon("radar", 11)} 读取中…</span>
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
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: state.query,
      });
      state.total = data.total || 0;
      state.items = sortTeamsByPower(data.items || []);
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
    if (!state.items.length) {
      areaEl.innerHTML = emptyState({
        iconName: state.query ? "search" : "users",
        title: state.query ? "没有匹配的队伍" : "该区域暂无队伍",
        desc: state.query ? `没有找到包含「${state.query}」的队伍 id，换个关键词试试。` : "换一个灰域区域看看。",
      });
      return;
    }
    areaEl.innerHTML = `
      <div class="team-grid">${state.items.map((team) => teamCardHtml(team)).join("")}</div>
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

  root.querySelector('[data-act="reload"]')?.addEventListener("click", () => load(state.page));

  load(1);
}
