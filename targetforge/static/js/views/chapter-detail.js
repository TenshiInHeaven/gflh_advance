/* views/chapter-detail.js —— 章节详情：关卡列表 / 灰域区域列表 / 无固定关卡队伍（服务端分页） */
import { api } from "../api.js";
import {
  icon,
  pageHeadHtml,
  sectionHeadHtml,
  skeletonRows,
  handleViewError,
  emptyState,
  tagsHtml,
  teamCardHtml,
  renderPager,
  bindPager,
} from "../ui.js";
import { settlementBadgeHtml } from "../components/settlement.js";
import {
  filterAndSortTeams,
  bindPowerFilter,
  powerFilterBarHtml,
  powerFilterMeta,
  serverPowerParams,
  defaultPowerFilter,
} from "../components/power-filter.js";
import { esc, fmtNum, navigate, bindSearch } from "../util.js";

const ORPHAN_PAGE_SIZE = 30;

export async function render(root, { params }) {
  const chapterId = params.id;
  root.innerHTML = pageHeadHtml({
    crumbs: [{ label: "关卡图鉴", nav: "/chapters" }, { label: "加载中…" }],
    title: "章节详情",
    sub: "正在读取章节数据…",
  }) + `<div data-body>${skeletonRows(6)}</div>`;

  try {
    const data = await api.chapter(chapterId, { offset: 0, limit: ORPHAN_PAGE_SIZE });
    const chapter = data.chapter || {};
    const isGray = chapter.category === "grayzone";
    const isOrphan = chapter.category === "orphan" || Array.isArray(data.teams);
    const stages = data.stages || [];
    const areas = data.areas || chapter.areas || [];

    root.innerHTML = `
      ${pageHeadHtml({
        crumbs: [{ label: "关卡图鉴", nav: "/chapters" }, { label: chapter.title || chapterId }],
        title: chapter.title || chapterId,
        badge: isGray ? "GRAY ZONE" : isOrphan ? "ORPHAN" : "CHAPTER",
        sub: isGray
          ? `${esc(chapter.subtitle || "灰域按区域分组")} · 灰域不逐节点列举关卡，点区域进入队伍列表。`
          : isOrphan
            ? `没有固定关卡的 ${fmtNum(chapter.team_count)} 支可收藏队伍，直接按队伍列出；支持搜索与分页。`
            : `${esc(chapter.subtitle || "")} 共 ${fmtNum(stages.length)} 个关卡、${fmtNum(chapter.team_count)} 支可收藏队伍、${fmtNum(chapter.species_count)} 个怪种。`,
        actions: `
          <button class="btn btn-ghost" type="button" data-nav="/chapters">${icon("chevronLeft", 14)} 返回图鉴</button>
          ${isOrphan ? `<button class="btn btn-primary" type="button" data-act="add-orphan">${icon("plus", 14)} 本页全部加入序列</button>` : ""}
        `,
      })}
      <div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:24px">
        ${
          isGray
            ? `<div class="stat-tile"><div class="st-label">${icon("radar", 12)} 区域数量</div><div class="st-value cyan">${fmtNum(areas.length)}</div><div class="st-sub">灰域按区域分组</div></div>
               <div class="stat-tile"><div class="st-label">${icon("users", 12)} 可收藏队伍</div><div class="st-value">${fmtNum(chapter.team_count)}</div><div class="st-sub">全部区域合计</div></div>
               <div class="stat-tile"><div class="st-label">${icon("crosshair", 12)} 怪种</div><div class="st-value">${fmtNum(chapter.species_count)}</div><div class="st-sub">区域合计</div></div>
               <div class="stat-tile"><div class="st-label">${icon("flag", 12)} 节点</div><div class="st-value">${fmtNum(chapter.stage_count)}</div><div class="st-sub">仅计数，不逐节点列举</div></div>`
            : isOrphan
              ? `<div class="stat-tile"><div class="st-label">${icon("users", 12)} 可收藏队伍</div><div class="st-value amber">${fmtNum(chapter.team_count)}</div><div class="st-sub">直接按队伍列出</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("crosshair", 12)} 怪种</div><div class="st-value">${fmtNum(chapter.species_count)}</div><div class="st-sub">本章出现</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("flag", 12)} 固定关卡</div><div class="st-value" style="color:var(--text-mute)">0</div><div class="st-sub">灰域 / 活动临时队伍</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("layers", 12)} 浏览方式</div><div class="st-value" style="font-size:17px;color:var(--cyan)">搜索 + 分页</div><div class="st-sub">每页 ${ORPHAN_PAGE_SIZE} 支</div></div>`
              : `<div class="stat-tile"><div class="st-label">${icon("flag", 12)} 关卡数</div><div class="st-value amber">${fmtNum(stages.length)}</div><div class="st-sub">本章可浏览关卡</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("users", 12)} 可收藏队伍</div><div class="st-value">${fmtNum(chapter.team_count)}</div><div class="st-sub">本章各关卡合计</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("crosshair", 12)} 怪种</div><div class="st-value">${fmtNum(chapter.species_count)}</div><div class="st-sub">本章出现</div></div>
                 <div class="stat-tile"><div class="st-label">${icon("zap", 12)} 效能范围</div><div class="st-value" style="font-size:18px">${fmtNum(chapter.difficulty_min)}-${fmtNum(chapter.difficulty_max)}</div><div class="st-sub">关卡难度区间</div></div>`
        }
      </div>

      ${
        isGray
          ? `<section class="section">
              ${sectionHeadHtml("灰域区域", { hint: `${areas.length} 个区域 · 点区域查看队伍（支持搜索 / 分页）`, iconName: "radar" })}
              <div class="area-grid">
                ${areas
                  .map(
                    (area, index) => `
                  <button class="area-card" type="button" data-area-detail="${esc(String(area.id || "").trim())}">
                    <div class="area-code">SECTOR ${String(index + 1).padStart(2, "0")} // GZ-${String(index + 1).padStart(2, "0")}</div>
                    <div class="area-name">${esc(String(area.title || area.id || "").trim())}</div>
                    <div class="area-stats">
                      <div><b>${fmtNum(area.team_count)}</b><span>可收藏队伍</span></div>
                      <div><b>${fmtNum(area.species_count)}</b><span>怪种</span></div>
                      <div><b>${fmtNum(area.stage_count)}</b><span>节点</span></div>
                    </div>
                    <span class="area-go">${icon("chevronRight", 17)}</span>
                  </button>`,
                  )
                  .join("")}
              </div>
            </section>`
          : isOrphan
            ? `<section class="section">
                ${sectionHeadHtml("队伍列表", { hint: "没有固定关卡的可收藏队伍 · 服务端搜索 + 分页", iconName: "users" })}
                <div class="toolbar">
                  <div class="input-wrap">
                    <span class="in-ico">${icon("search", 14)}</span>
                    <input type="text" placeholder="搜索队伍 id / 阵营 / 怪种…" data-orphan-search />
                  </div>
                  <span class="spacer"></span>
                  <span class="tb-meta" data-orphan-meta>${icon("users", 11)} 读取中…</span>
                  <div style="flex-basis:100%">${powerFilterBarHtml()}</div>
                </div>
                <div data-orphan-list>${skeletonRows(5)}</div>
              </section>`
            : `<section class="section">
                ${sectionHeadHtml("关卡列表", { hint: `难度 ${fmtNum(chapter.difficulty_min)} ~ ${fmtNum(chapter.difficulty_max)} · 点关卡查看队伍`, iconName: "flag" })}
                ${
                  stages.length
                    ? `<div class="stage-list">${stages.map((stage) => stageRowHtmlLocal(stage, chapter)).join("")}</div>`
                    : emptyState({ iconName: "flag", title: "本章暂无关卡", desc: "该章节没有可浏览的关卡数据，换一个章节试试。" })
                }
              </section>`
      }
    `;

    root.querySelectorAll("[data-stage-detail]").forEach((row) => {
      row.addEventListener("click", () => {
        try {
          sessionStorage.setItem("tf:last-chapter", chapterId);
        } catch {
          /* ignore */
        }
        navigate(`/stages/${row.dataset.stageDetail}`);
      });
    });
    root.querySelectorAll("[data-area-detail]").forEach((card) => {
      card.addEventListener("click", () => {
        const areaId = String(card.dataset.areaDetail || "").trim();
        navigate(`/grayzone/${encodeURIComponent(areaId)}`);
      });
    });
    if (isOrphan) initOrphanSection(root, chapterId, chapter);
  } catch (err) {
    handleViewError(root, err, () => render(root, { params }));
  }
}

/* ------------------------------------------------------------------ */
/* 无固定关卡章节：队伍服务端分页 + 搜索                               */
/* ------------------------------------------------------------------ */
function initOrphanSection(root, chapterId, chapter) {
  const listEl = root.querySelector("[data-orphan-list]");
  const metaEl = root.querySelector("[data-orphan-meta]");
  const addBtn = root.querySelector('[data-act="add-orphan"]');
  const view = { page: 1, query: "", total: chapter.team_count || 0, items: [], filter: defaultPowerFilter() };

  const renderList = () => {
    if (metaEl) {
      metaEl.innerHTML = `${icon("users", 11)} 共 <b>${fmtNum(view.total)}</b> 支队伍 · 每页 ${ORPHAN_PAGE_SIZE}${view.query ? ` · 搜索「${esc(view.query)}」` : ""}`;
    }
    const pfMeta = root.querySelector("[data-pf-meta]");
    if (pfMeta) pfMeta.textContent = powerFilterMeta(view.filter, view.total, view.items.length);
    if (!view.items.length) {
      listEl.innerHTML = emptyState({
        iconName: view.query || view.filter.mode !== "all" ? "search" : "users",
        title: view.query || view.filter.mode !== "all" ? "没有匹配的队伍" : "暂无队伍",
        desc: view.query || view.filter.mode !== "all" ? "换个关键词或效能条件试试。" : "该章节没有可收藏队伍。",
      });
      return;
    }
    listEl.innerHTML = `
      <div class="team-grid">${view.items.map((team) => teamCardHtml(team)).join("")}</div>
      ${renderPager({ page: view.page, total: Math.max(view.total, view.items.length), pageSize: ORPHAN_PAGE_SIZE })}
    `;
    bindPager(listEl, {
      page: view.page,
      total: view.total,
      pageSize: ORPHAN_PAGE_SIZE,
      onChange: (page) => {
        load(page).then(() => listEl.scrollIntoView({ behavior: "smooth", block: "start" }));
      },
    });
  };

  const load = async (page = 1, query = view.query) => {
    listEl.innerHTML = skeletonRows(5);
    try {
      const data = await api.chapter(chapterId, {
        offset: (page - 1) * ORPHAN_PAGE_SIZE,
        limit: ORPHAN_PAGE_SIZE,
        q: query,
        ...serverPowerParams(view.filter),
      });
      view.page = page;
      view.query = query;
      view.items = filterAndSortTeams(data.teams || [], view.filter);
      view.total = data.teams_total ?? data.total ?? chapter.team_count ?? 0;
      renderList();
    } catch (err) {
      if (err.status === 503 || err.status === 0) {
        handleViewError(listEl, err, () => load(page, query));
      } else {
        listEl.innerHTML = emptyState({ iconName: "users", title: "队伍加载失败", desc: err.message });
      }
    }
  };

  bindSearch(root.querySelector("[data-orphan-search]"), (value) => load(1, value));
  bindPowerFilter(root, (filter) => {
    view.filter = filter;
    load(1, view.query);
  });

  if (addBtn) {
    addBtn.addEventListener("click", async () => {
      if (!view.items.length) return;
      const { sequenceStats, addTeams: addTeamsStore } = await import("../store.js");
      const { confirmDialog, toastOk, toastErr, setBusy } = await import("../ui.js");
      const left = 35 - sequenceStats().count;
      if (left <= 0) {
        toastErr("序列已满", "序列上限 35，请先移除一些队伍。");
        return;
      }
      let toAdd = view.items;
      if (toAdd.length > left) {
        const ok = await confirmDialog({
          title: "加入本页队伍",
          message: `本页 ${toAdd.length} 支队伍，序列剩余 ${left} 个位置。`,
          detail: `将把前 ${left} 支加入序列。`,
          confirmText: `加入前 ${left} 支`,
        });
        if (!ok) return;
        toAdd = toAdd.slice(0, left);
      }
      setBusy(addBtn, true, "加入中…");
      try {
        const sequence = await addTeamsStore(toAdd.map((team) => team.id));
        toastOk("已加入序列", `成功加入 ${toAdd.length} 支队伍 · 当前序列 ${sequence.count}/${sequence.max}`);
      } catch (err) {
        toastErr("加入失败", err.message);
      } finally {
        setBusy(addBtn, false);
      }
    });
  }

  load(1);
}

function stageRowHtmlLocal(stage, chapter) {
  const min = chapter.difficulty_min || 0;
  const max = chapter.difficulty_max || 1;
  const span = Math.max(1, max - min);
  const width = Math.max(4, Math.min(100, ((stage.difficulty - min) / span) * 100));
  return `
    <button class="stage-row" type="button" data-stage-detail="${stage.id}">
      <span class="stage-code">${esc(stage.code || stage.id)}</span>
      <span class="stage-name"><b>${esc(stage.title || "未命名关卡")}</b>
        <span>mission #${esc(stage.id)}${stage.recommend_level ? ` · 推荐等级 ${stage.recommend_level}` : ""}</span>
      </span>
      <span class="diff-meter">
        <span class="diff-bar"><i style="--w:${width.toFixed(1)}%"></i></span>
        <span class="diff-val">难度 ${fmtNum(stage.difficulty)}</span>
      </span>
      <span class="stage-counts"><span><b>${stage.team_count ?? 0}</b> 支队伍</span><span>${stage.species_count ?? 0} 个怪种</span></span>
      <span class="stage-tags">${tagsHtml(stage.tags, { max: 3 })}</span>
      <span class="stage-settle">${settlementBadgeHtml(stage)}</span>
      <span class="stage-row-arrow">${icon("chevronRight", 15)}</span>
    </button>
  `;
}
