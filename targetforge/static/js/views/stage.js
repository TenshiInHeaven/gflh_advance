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
import { esc, fmtNum, navigate, bindSearch, isSupportTeam, supportCountOf, isReserveTeam, reserveCountOf } from "../util.js";

const state = { page: 1, pageSize: 24, query: "", faction: "", filter: defaultPowerFilter(), reserveOpen: false, reserveVisible: 12 };
let rootEl = null;
let loaded = null;
let filteredTeams = [];

/** 统一队伍列表：敌方在前，支援队伍次之（机场刷新候选在下方折叠区，也属于同一列表体系） */
function buildTeamList(stageObj, rawTeams, rawSupports) {
  const dedupe = new Map();
  const push = (team, kind) => {
    if (!team || team.id === undefined || team.id === null) return;
    const id = Number(team.id);
    if (dedupe.has(id)) {
      const existing = dedupe.get(id);
      dedupe.set(id, {
        ...existing,
        support: existing.support || kind === "support",
        reserve: existing.reserve || kind === "reserve",
        roles: existing.roles || (kind === "support" ? ["support"] : kind === "reserve" ? ["reserve"] : undefined),
        inferred: existing.inferred || team.inferred,
      });
      return;
    }
    const support = kind === "support" || isSupportTeam(team);
    const reserve = kind === "reserve" || isReserveTeam(team);
    dedupe.set(id, {
      ...team,
      support,
      reserve,
      inferred: reserve ? true : team.inferred,
      roles: team.roles || (support ? ["support"] : reserve ? ["reserve"] : undefined),
    });
  };
  (rawTeams || []).forEach((team) => push(team, isSupportTeam(team) ? "support" : "enemy"));
  (rawSupports || []).forEach((team) => push(team, "support"));
  return [...dedupe.values()];
}

/** 机场刷新候选统一标记（role=reserve / inferred=true / reserve_reason） */
function prepareReserveTeam(team) {
  return {
    ...team,
    reserve: true,
    inferred: true,
    role: "reserve",
    roles: team.roles && team.roles.length ? team.roles : ["reserve"],
  };
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
    const rawReserve = Array.isArray(loaded.reserve_teams)
      ? loaded.reserve_teams
      : Array.isArray(stageObj.reserve_teams)
        ? stageObj.reserve_teams
        : [];
    loaded.allTeams = buildTeamList(stageObj, rawTeams, rawSupport);
    loaded.enemyTeams = loaded.allTeams.filter((team) => !isSupportTeam(team));
    loaded.supportTeams = loaded.allTeams.filter((team) => isSupportTeam(team));
    loaded.reserveTeams = rawReserve.map((team) => prepareReserveTeam(team));
    loaded.supportCount = supportCountOf(stageObj, loaded.supportTeams) || loaded.supportTeams.length;
    loaded.reserveCount = reserveCountOf(stageObj, loaded.reserveTeams) || loaded.reserveTeams.length;
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
  const reserveCount = loaded.reserveCount ?? 0;
  const factions = [...new Set(teams.map((team) => team.faction).filter(Boolean))];
  const sideChips = `
    <span class="team-side-chip enemy">敌方 <b>${enemyCount}</b></span>
    ${supportCount ? `<span class="team-side-chip support">${icon("shield", 10)} 支援 <b>${supportCount}</b></span>` : ""}
    ${reserveCount ? `<span class="team-side-chip reserve" title="推断：同系列未入场怪组，STC 无显式机场刷新映射">${icon("refresh", 10)} 可能刷新 <b>${reserveCount}</b></span>` : ""}
  `;

  rootEl.innerHTML = `
    ${pageHeadHtml({
      crumbs: [
        { label: "关卡图鉴", nav: "/chapters" },
        { label: "关卡队伍" },
        { label: stage.code || `#${stage.id}` },
      ],
      title: stage.title || "未命名关卡",
      badge: stage.code ? String(stage.code) : `#${stage.id}`,
      sub: `mission #${esc(stage.id)} · 难度 <b class="mono-inline">${fmtNum(stage.difficulty)}</b>${stage.recommend_level ? ` · 推荐等级 ${stage.recommend_level}` : ""} · ${sideChips}${supportCount || reserveCount ? "（支援 / 机场刷新候选已并入下方列表，卡面带角色徽标）" : ""}。点卡片看详情，或直接加入右侧序列。`,
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
    <div data-reserve-area></div>
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
    const reserveInPage = pageItems.filter((team) => isReserveTeam(team)).length;
    rootEl.querySelector("[data-team-meta]").innerHTML =
      `${icon("users", 11)} 显示 <b>${pageItems.length}</b> / ${fmtNum(total)} 支队伍${supportInPage ? `（含支援 <b>${supportInPage}</b>` : ""}${reserveInPage ? `${supportInPage ? " · " : "（"}可能刷新 <b>${reserveInPage}</b>` : ""}${supportInPage || reserveInPage ? "）" : ""} · 每页 ${state.pageSize}`;
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

  const reserveAreaEl = rootEl.querySelector("[data-reserve-area]");
  const renderReserveStrip = () => {
    if (!reserveAreaEl) return;
    if (!loaded.reserveTeams.length) {
      reserveAreaEl.innerHTML = "";
      return;
    }
    const query = state.query.trim();
    let reserves = loaded.reserveTeams;
    if (query) reserves = reserves.filter((team) => String(team.id).includes(query));
    if (state.faction) reserves = reserves.filter((team) => team.faction === state.faction);
    reserves = filterAndSortTeams(reserves, state.filter);
    const filteredCount = reserves.length;
    const total = loaded.reserveCount || loaded.reserveTeams.length;
    const filtering = Boolean(query || state.faction || state.filter.mode !== "all");
    const expanded = state.reserveOpen || (filtering && filteredCount > 0);
    const shown = expanded ? reserves.slice(0, state.reserveVisible) : [];
    const remain = Math.max(0, filteredCount - shown.length);
    reserveAreaEl.innerHTML = `
      <section class="reserve-strip" data-reserve-strip>
        <button class="reserve-toggle ${expanded ? "open" : ""}" type="button" data-reserve-toggle
          aria-expanded="${expanded}" title="推断：同系列未入场怪组，STC 无显式机场刷新映射">
          <span class="reserve-flag">${icon("refresh", 11)} 推断</span>
          <span class="reserve-toggle-title">可能刷新 <b>${filtering ? filteredCount : total}</b> 支${filtering && filteredCount !== total ? `（共 ${total}）` : ""}</span>
          <span class="reserve-toggle-hint">机场/后续刷新候选：同系列未入场怪组，STC 无显式机场刷新映射</span>
          <span class="reserve-toggle-action">${icon(expanded ? "chevronUp" : "chevronDown", 13)} ${expanded ? "收起" : "展开"}</span>
        </button>
        ${
          expanded
            ? `<div class="reserve-grid-wrap">
                 <div class="team-grid reserve-grid">${shown.map((team) => teamCardHtml(team)).join("")}</div>
                 <div class="reserve-foot">
                   <span class="reserve-foot-hint">以上为推断候选，不是确定出场；同样可加入序列，卡面带「机场可能刷新（推断）」徽标。</span>
                   ${
                     remain > 0
                       ? `<button class="btn btn-sm btn-ghost" type="button" data-reserve-more>${icon("chevronDown", 12)} 再显示更多（剩余 ${remain}）</button>`
                       : `<button class="btn btn-sm btn-ghost" type="button" data-reserve-less>${icon("chevronUp", 12)} 收起候选</button>`
                   }
                 </div>
               </div>`
            : ""
        }
      </section>`;
    reserveAreaEl.querySelector("[data-reserve-toggle]")?.addEventListener("click", () => {
      state.reserveOpen = !state.reserveOpen;
      state.reserveVisible = 12;
      renderReserveStrip();
    });
    reserveAreaEl.querySelector("[data-reserve-more]")?.addEventListener("click", () => {
      state.reserveVisible += 12;
      state.reserveOpen = true;
      renderReserveStrip();
    });
    reserveAreaEl.querySelector("[data-reserve-less]")?.addEventListener("click", () => {
      state.reserveOpen = false;
      state.reserveVisible = 12;
      renderReserveStrip();
    });
  };
  renderReserveStrip();

  bindSearch(rootEl.querySelector("[data-team-search]"), (value) => {
    state.query = value;
    state.page = 1;
    state.reserveVisible = 12;
    renderList();
    renderReserveStrip();
  });

  bindPowerFilter(rootEl, (filter) => {
    state.filter = filter;
    state.page = 1;
    state.reserveVisible = 12;
    renderList();
    renderReserveStrip();
  });

  rootEl.querySelector("[data-faction-tabs]").addEventListener("click", (event) => {
    const button = event.target.closest("[data-faction]");
    if (!button) return;
    rootEl.querySelectorAll("[data-faction-tabs] button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.faction = button.dataset.faction;
    state.page = 1;
    state.reserveVisible = 12;
    renderList();
    renderReserveStrip();
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
