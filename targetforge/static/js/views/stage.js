/* views/stage.js —— 关卡详情：该关的可收藏队伍列表（含支援队伍，本地效能筛选/排序） */
import { api } from "../api.js";
import { addTeams, sequenceStats } from "../store.js";
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
import { settlementLineHtml } from "../components/settlement.js";
import {
  filterAndSortTeams,
  bindPowerFilter,
  powerFilterBarHtml,
  powerFilterMeta,
  defaultPowerFilter,
} from "../components/power-filter.js";
import { esc, fmtNum, navigate, bindSearch, isSupportTeam, supportCountOf } from "../util.js";

const state = { page: 1, pageSize: 24, query: "", faction: "", filter: defaultPowerFilter() };
let rootEl = null;
let loaded = null;
let filteredTeams = [];

/** 统一队伍列表：敌方在前，支援队伍在后（同一列表展示，不单独分区） */
function buildTeamList(stageObj, rawTeams, rawSupports) {
  const dedupe = new Map();
  const push = (team, support) => {
    if (!team || team.id === undefined || team.id === null) return;
    const id = Number(team.id);
    if (dedupe.has(id)) {
      if (!support) return;
      const existing = dedupe.get(id);
      dedupe.set(id, { ...existing, support: true, roles: existing.roles || ["support"] });
      return;
    }
    dedupe.set(id, { ...team, support: support || isSupportTeam(team), roles: team.roles || (support ? ["support"] : undefined) });
  };
  (rawTeams || []).forEach((team) => push(team, isSupportTeam(team)));
  (rawSupports || []).forEach((team) => push(team, true));
  return [...dedupe.values()];
}

export async function render(root, { params }) {
  rootEl = root;
  state.page = 1;
  state.query = "";
  state.faction = "";
  state.filter = defaultPowerFilter();
  const missionId = params.id;
  root.innerHTML =
    pageHeadHtml({
      crumbs: [{ label: "关卡图鉴", nav: "/chapters" }, { label: "关卡" }, { label: `mission #${missionId}` }],
      title: "关卡队伍",
      sub: "正在读取关卡数据…",
    }) + `<div data-body>${skeletonCards(8)}</div>`;

  try {
    loaded = await api.stage(missionId);
    const stageObj = loaded.stage || {};
    const rawTeams = Array.isArray(loaded.teams) ? loaded.teams : [];
    const rawSupport = Array.isArray(loaded.support_teams)
      ? loaded.support_teams
      : Array.isArray(stageObj.support_teams)
        ? stageObj.support_teams
        : [];
    loaded.allTeams = buildTeamList(stageObj, rawTeams, rawSupport);
    loaded.enemyTeams = loaded.allTeams.filter((team) => !isSupportTeam(team));
    loaded.supportTeams = loaded.allTeams.filter((team) => isSupportTeam(team));
    loaded.supportCount = supportCountOf(stageObj, loaded.supportTeams) || loaded.supportTeams.length;
    renderPage();
  } catch (err) {
    handleViewError(root, err, () => render(root, { params }));
  }
}

function renderPage() {
  const stage = loaded.stage || {};
  const teams = loaded.allTeams || [];
  const enemyCount = loaded.enemyTeams?.length ?? teams.length;
  const supportCount = loaded.supportCount ?? 0;
  const factions = [...new Set(teams.map((team) => team.faction).filter(Boolean))];
  const sideChips = supportCount
    ? `<span class="team-side-chip enemy">敌方 <b>${enemyCount}</b></span> <span class="team-side-chip support">${icon("shield", 10)} 支援 <b>${supportCount}</b></span>`
    : `<span class="team-side-chip enemy">队伍 <b>${enemyCount}</b></span>`;

  rootEl.innerHTML = `
    ${pageHeadHtml({
      crumbs: [
        { label: "关卡图鉴", nav: "/chapters" },
        { label: "关卡队伍" },
        { label: stage.code || `#${stage.id}` },
      ],
      title: stage.title || "未命名关卡",
      badge: stage.code ? String(stage.code) : `#${stage.id}`,
      sub: `mission #${esc(stage.id)} · 难度 <b class="mono-inline">${fmtNum(stage.difficulty)}</b>${stage.recommend_level ? ` · 推荐等级 ${stage.recommend_level}` : ""} · ${sideChips}${supportCount ? "（支援队伍已并入下方列表，卡面带「支援队伍」徽标）" : ""}。点卡片看详情，或直接加入右侧序列。`,
      actions: `
        <button class="btn btn-ghost" type="button" data-nav-back>${icon("chevronLeft", 14)} 返回章节</button>
        <button class="btn btn-primary" type="button" data-act="add-all">${icon("plus", 14)} 全部加入序列 <span class="mono-inline" style="opacity:.75">(${teams.length})</span></button>
      `,
    })}
    ${settlementLineHtml(stage)}
    <div class="toolbar">
      <div class="input-wrap">
        <span class="in-ico">${icon("search", 14)}</span>
        <input type="text" placeholder="搜索队伍 id…" data-team-search value="" />
      </div>
      <div class="segmented" data-faction-tabs>
        <button class="active" type="button" data-faction="">全部 <span class="cnt">${teams.length}</span></button>
        ${factions
          .map(
            (faction) =>
              `<button type="button" data-faction="${esc(faction)}">${esc(faction)} <span class="cnt">${teams.filter((team) => team.faction === faction).length}</span></button>`,
          )
          .join("")}
      </div>
      <span class="spacer"></span>
      <span class="tb-meta" data-team-meta></span>
      <div style="flex-basis:100%">${powerFilterBarHtml()}</div>
    </div>
    <div data-team-area></div>
  `;

  const areaEl = rootEl.querySelector("[data-team-area]");

  const renderList = () => {
    const query = state.query.trim();
    let filtered = teams;
    if (query) filtered = filtered.filter((team) => String(team.id).includes(query));
    if (state.faction) filtered = filtered.filter((team) => team.faction === state.faction);
    filtered = filterAndSortTeams(filtered, state.filter);
    filteredTeams = filtered;
    const total = filtered.length;
    const maxPage = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > maxPage) state.page = maxPage;
    const start = (state.page - 1) * state.pageSize;
    const pageItems = filtered.slice(start, start + state.pageSize);

    const supportInPage = pageItems.filter((team) => isSupportTeam(team)).length;
    rootEl.querySelector("[data-team-meta]").innerHTML =
      `${icon("users", 11)} 显示 <b>${pageItems.length}</b> / ${fmtNum(total)} 支队伍${supportInPage ? `（含支援 <b>${supportInPage}</b>）` : ""} · 每页 ${state.pageSize}`;
    const pfMeta = rootEl.querySelector("[data-pf-meta]");
    if (pfMeta) pfMeta.textContent = powerFilterMeta(state.filter, teams.length, total);

    if (!total) {
      areaEl.innerHTML = emptyState({
        iconName: "users",
        title: query || state.faction || state.filter.mode !== "all" ? "没有匹配的队伍" : "本关暂无可收藏队伍",
        desc: query || state.faction || state.filter.mode !== "all" ? "换个关键词、阵营或效能条件试试。" : "该关卡没有可注入的可收藏队伍。",
      });
      return;
    }
    areaEl.innerHTML = `
      <div class="team-grid">${pageItems.map((team) => teamCardHtml(team)).join("")}</div>
      ${renderPager({ page: state.page, total, pageSize: state.pageSize })}
    `;
    bindPager(areaEl, {
      page: state.page,
      total,
      pageSize: state.pageSize,
      onChange: (page) => {
        state.page = page;
        renderList();
        areaEl.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    });
  };

  renderList();

  bindSearch(rootEl.querySelector("[data-team-search]"), (value) => {
    state.query = value;
    state.page = 1;
    renderList();
  });

  bindPowerFilter(rootEl, (filter) => {
    state.filter = filter;
    state.page = 1;
    renderList();
  });

  rootEl.querySelector("[data-faction-tabs]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-faction]");
    if (!button) return;
    rootEl.querySelectorAll("[data-faction-tabs] button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.faction = button.dataset.faction;
    state.page = 1;
    renderList();
  });

  rootEl.querySelector("[data-nav-back]")?.addEventListener("click", () => {
    let chapterId = stage.chapter_id || "";
    if (!chapterId) {
      try {
        chapterId = sessionStorage.getItem("tf:last-chapter") || "";
      } catch {
        chapterId = "";
      }
    }
    if (chapterId) navigate(`/chapters/${encodeURIComponent(chapterId)}`);
    else navigate("/chapters");
  });

  rootEl.querySelector('[data-act="add-all"]').addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const source = filteredTeams.length ? filteredTeams : teams;
    if (!source.length) return;
    const remaining = 35 - sequenceStats().count;
    if (remaining <= 0) {
      toastErr("序列已满", "序列上限 35，请先移除一些队伍。");
      return;
    }
    let toAdd = source;
    if (source.length > remaining) {
      const ok = await confirmDialog({
        title: "加入全部队伍",
        message: `当前筛选结果共 ${source.length} 支队伍，序列剩余 ${remaining} 个位置。`,
        detail: `将把前 ${remaining} 支加入序列，剩余 ${source.length - remaining} 支需要先清出位置。`,
        confirmText: `加入前 ${remaining} 支`,
      });
      if (!ok) return;
      toAdd = source.slice(0, remaining);
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
  });
}
