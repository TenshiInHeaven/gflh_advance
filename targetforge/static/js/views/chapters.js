/* views/chapters.js —— 关卡图鉴：7 个分组章节卡片 */
import { store, loadChapters } from "../store.js";
import { icon, pageHeadHtml, skeletonCards, handleViewError, emptyState } from "../ui.js";
import { esc, fmtNum, fmtCompact, navigate, bindSearch } from "../util.js";

const state = { group: "all", query: "" };
let container = null;
let groupsCache = null;

export async function render(root) {
  container = root;
  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [{ label: "关卡图鉴" }],
      title: "关卡图鉴",
      badge: "CHAPTERS",
      sub: "按章节浏览全部可选择的关卡；点章节进入关卡列表，再点关卡查看该关的可收藏队伍。灰域章节按 12 个区域分组，不逐节点列举。",
    })}
    <div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索章节 / 活动名…" data-chapter-search value="${esc(state.query)}" />
      </div>
      <span class="spacer"></span>
      <span class="tb-meta" data-chapter-meta>—</span>
    </div>
    <div class="group-tabs" data-group-tabs></div>
    <div data-chapter-grid>${skeletonCards(8)}</div>
  `;

  try {
    const data = store.chapters || (await loadChapters());
    groupsCache = data.groups || [];
    renderTabs();
    renderGrid();
    bindSearch(root.querySelector("[data-chapter-search]"), (value) => {
      state.query = value;
      renderGrid();
    });
    root.querySelector("[data-group-tabs]").addEventListener("click", (event) => {
      const button = event.target.closest("[data-group]");
      if (!button) return;
      state.group = button.dataset.group;
      renderTabs();
      renderGrid();
    });
    // 卡片点击交给全局 data-chapter-detail 处理
  } catch (err) {
    handleViewError(root, err, () => render(root));
  }
}

function chapterCounts() {
  return groupsCache.map((group) => ({ id: group.id, title: group.title, count: group.chapters.length }));
}

function renderTabs() {
  const tabsEl = container?.querySelector("[data-group-tabs]");
  if (!tabsEl) return;
  const total = groupsCache.reduce((acc, group) => acc + group.chapters.length, 0);
  const tabs = [
    `<button class="group-tab ${state.group === "all" ? "active" : ""}" type="button" data-group="all">全部<span class="gt-count">${total}</span></button>`,
    ...chapterCounts().map(
      (group) =>
        `<button class="group-tab ${state.group === group.id ? "active" : ""}" type="button" data-group="${esc(group.id)}">${esc(group.title)}<span class="gt-count">${group.count}</span></button>`,
    ),
  ];
  tabsEl.innerHTML = tabs.join("");
  const metaEl = container.querySelector("[data-chapter-meta]");
  if (metaEl) {
    const stages = groupsCache.reduce(
      (acc, group) => acc + group.chapters.reduce((sum, chapter) => sum + (chapter.stage_count || 0), 0),
      0,
    );
    metaEl.innerHTML = `${icon("database", 11)} 共 <b>${fmtNum(total)}</b> 章节 · ${fmtNum(stages)} 个关卡`;
  }
}

function visibleChapters() {
  const groups = state.group === "all" ? groupsCache : groupsCache.filter((group) => group.id === state.group);
  const query = state.query.trim().toLowerCase();
  const items = [];
  groups.forEach((group) => {
    group.chapters.forEach((chapter, index) => {
      const haystack = `${chapter.title} ${chapter.subtitle || ""} ${group.title}`.toLowerCase();
      if (query && !haystack.includes(query)) return;
      items.push({ chapter, group, index });
    });
  });
  return items;
}

function chapterCardHtml({ chapter, group, index }) {
  const isGray = chapter.category === "grayzone";
  const isOrphan = chapter.category === "orphan";
  const areaCount = (chapter.areas || []).length;
  const diffMin = chapter.difficulty_min || 0;
  const diffMax = chapter.difficulty_max || 0;
  const badge = isGray ? '<span class="badge cyan mono">GRAY ZONE</span>' : isOrphan ? '<span class="badge violet mono">ORPHAN</span>' : "";
  return `
    <button class="chapter-card ${isGray ? "grayzone" : ""} ${isOrphan ? "orphan" : ""}" type="button" data-chapter-detail="${esc(chapter.id)}">
      <div class="cc-top">
        <span class="cc-cat">${esc(group.title)}</span>
        ${badge}
        <span class="cc-index">${String(index + 1).padStart(2, "0")}</span>
      </div>
      <div class="cc-title">${esc(chapter.title)}</div>
      <div class="cc-sub">${esc(chapter.subtitle || (isGray ? `${areaCount} 个区域` : isOrphan ? "没有固定关卡的可收藏队伍" : "点击查看关卡列表"))}</div>
      <div class="cc-stats">
        ${
          isGray
            ? `
          <div class="cc-stat"><b>${fmtNum(areaCount)}</b><span>区域</span></div>
          <div class="cc-stat"><b>${fmtNum(chapter.team_count)}</b><span>队伍</span></div>
          <div class="cc-stat"><b>${fmtNum(chapter.species_count)}</b><span>怪种</span></div>
          <div class="cc-stat gray"><b>${fmtNum(chapter.stage_count)}</b><span>节点</span></div>`
            : isOrphan
              ? `
          <div class="cc-stat"><b>${fmtNum(chapter.team_count)}</b><span>队伍</span></div>
          <div class="cc-stat"><b>${fmtNum(chapter.species_count)}</b><span>怪种</span></div>
          <div class="cc-stat gray" style="grid-column:span 2"><b>无固定关卡</b><span>直接按队伍列出</span></div>`
              : `
          <div class="cc-stat"><b>${fmtNum(chapter.stage_count)}</b><span>关卡</span></div>
          <div class="cc-stat"><b>${fmtNum(chapter.team_count)}</b><span>队伍</span></div>
          <div class="cc-stat"><b>${fmtNum(chapter.species_count)}</b><span>怪种</span></div>
          <div class="cc-stat gray"><b>${fmtCompact(diffMin)}-${fmtCompact(diffMax)}</b><span>效能范围</span></div>`
        }
      </div>
      <div class="cc-foot">
        ${(chapter.tags || []).slice(0, 3).map((tag) => `<span class="tag ${isGray ? "cyan" : isOrphan ? "violet" : "amber"}">${esc(tag)}</span>`).join("")}
        ${isGray ? `<span class="area-dots">${Array.from({ length: 12 }, (_, i) => `<i></i>`).join("")}</span>` : ""}
        <span class="cc-arrow">${icon("chevronRight", 16)}</span>
      </div>
    </button>
  `;
}

function renderGrid() {
  const gridEl = container?.querySelector("[data-chapter-grid]");
  if (!gridEl) return;
  const items = visibleChapters();
  if (!items.length) {
    gridEl.innerHTML = emptyState({
      iconName: "search",
      title: "没有匹配的章节",
      desc: `没有找到包含「${state.query}」的章节，换个关键词或切换分组试试。`,
    });
    return;
  }
  gridEl.innerHTML = `<div class="chapter-grid">${items.map(chapterCardHtml).join("")}</div>`;
  gridEl.querySelectorAll("[data-chapter-detail]").forEach((card) => {
    card.addEventListener("click", () => navigate(`/chapters/${encodeURIComponent(card.dataset.chapterDetail)}`));
  });
}
