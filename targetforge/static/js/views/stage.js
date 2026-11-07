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
  factionChip,
  speciesIconHtml,
} from "../ui.js";
import { settlementLineHtml } from "../components/settlement.js";
import {
  filterAndSortTeams,
  bindPowerFilter,
  powerFilterBarHtml,
  powerFilterMeta,
  defaultPowerFilter,
} from "../components/power-filter.js";
import { esc, fmtNum, navigate, bindSearch, isSupportTeam, supportCountOf, isReserveTeam, reserveCountOf, powerDisplay } from "../util.js";

const state = { page: 1, pageSize: 24, query: "", faction: "", filter: defaultPowerFilter(), reserveOpen: false, reserveVisible: 24, absentOpen: true };
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
  const manual = team.reserve_source === "manual" || team.inferred === false;
  return {
    ...team,
    reserve: true,
    inferred: !manual,
    manual,
    reserve_source: manual ? "manual" : "inferred",
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
    loaded.reserveMeta = loaded.reserve_meta || stageObj.reserve_meta || {};
    loaded.manualReserve = loaded.reserveMeta.method === "manual";
    // 三段式分类：场上已存在（上方主列表）/ 可能刷怪（固定·刷怪表或推断）/ 实际未出现（表外）
    loaded.spawnTeams = loaded.reserveTeams.filter((team) => !(team.manual && team.appeared === false));
    loaded.absentTeams = loaded.reserveTeams.filter((team) => team.manual && team.appeared === false);
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
  // 灰域节点：面包屑 灰域探查 / 区域 / 节点
  let grayRegion = null;
  try {
    grayRegion = JSON.parse(sessionStorage.getItem("tf:gray-region") || "null");
  } catch {
    grayRegion = null;
  }
  const isGrayNode = Boolean(stage.gray_zone) || stage.category === "grayzone" || stage.chapter_id === "grayzone";
  const grayCrumbs = [
    { label: "关卡图鉴", nav: "/chapters" },
    { label: "灰域探查", nav: "/chapters/grayzone" },
    ...(grayRegion && grayRegion.title
      ? [{ label: grayRegion.title, nav: `/grayzone/region/${encodeURIComponent(grayRegion.id || "")}` }]
      : []),
    { label: stage.title || `#${stage.id}` },
  ];
  const enemyCount = loaded.enemyTeams?.length ?? teams.length;
  const supportCount = loaded.supportCount ?? 0;
  const reserveCount = loaded.reserveCount ?? 0;
  const manualReserve = loaded.manualReserve;
  const spawnCount = loaded.spawnTeams?.length ?? 0;
  const absentCount = loaded.absentTeams?.length ?? 0;
  const reserveChip = manualReserve
    ? `<span class="team-side-chip reserve" title="固定怪组表 + 刷怪表里、不在上方场上的怪组">${icon("list", 10)} 可能刷怪 <b>${spawnCount}</b></span>
       ${absentCount ? `<span class="team-side-chip absent" title="同系列可收藏，但固定/刷怪表中没有">${icon("list", 10)} 实际未出现 <b>${absentCount}</b></span>` : ""}`
    : `<span class="team-side-chip reserve" title="推断：同系列未入场怪组，STC 无显式机场刷新映射">${icon("refresh", 10)} 可能刷怪 <b>${reserveCount}</b></span>`;
  const factions = [...new Set(teams.map((team) => team.faction).filter(Boolean))];
  const sideChips = `
    <span class="team-side-chip enemy">场上已存在 <b>${enemyCount}</b></span>
    ${supportCount ? `<span class="team-side-chip support">${icon("shield", 10)} 支援 <b>${supportCount}</b></span>` : ""}
    ${manualReserve || reserveCount ? reserveChip : ""}
  `;
  const reserveMergeHint = manualReserve
    ? "（下方分两段：可能刷怪 = 固定/刷怪表；实际未出现 = 表中没有的同系列怪组）"
    : "（支援 / 可能刷怪候选已并入下方列表，卡面带角色徽标）";

  rootEl.innerHTML = `
    ${pageHeadHtml({
      crumbs: isGrayNode
        ? grayCrumbs
        : [
            { label: "关卡图鉴", nav: "/chapters" },
            { label: "关卡队伍" },
            { label: stage.code || `#${stage.id}` },
          ],
      title: stage.title || "未命名关卡",
      badge: isGrayNode ? `GRAY NODE${grayRegion && grayRegion.title ? ` · ${grayRegion.title}` : ""}` : stage.code ? String(stage.code) : `#${stage.id}`,
      sub: isGrayNode
        ? `灰域节点 · ${grayRegion && grayRegion.title ? `区域：${esc(grayRegion.title)} · ` : ""}${grayRegion && grayRegion.location ? `地点：${esc(grayRegion.location)} · ` : ""}mission #${esc(stage.id)} · 难度 <b class="mono-inline">${fmtNum(stage.difficulty)}</b> · ${sideChips}${supportCount || reserveCount ? reserveMergeHint : ""}。点卡片看详情，或直接加入右侧序列。`
        : `mission #${esc(stage.id)} · 难度 <b class="mono-inline">${fmtNum(stage.difficulty)}</b>${stage.recommend_level ? ` · 推荐等级 ${stage.recommend_level}` : ""} · ${sideChips}${supportCount || reserveCount ? reserveMergeHint : ""}。点卡片看详情，或直接加入右侧序列。`,
      actions: `
        <button class="btn btn-ghost" type="button" data-nav-back>${icon("chevronLeft", 14)} ${isGrayNode && grayRegion ? "返回节点列表" : "返回章节"}</button>
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
    rootEl.querySelector("[data-team-meta]").innerHTML =
      `${icon("users", 11)} 场上已存在：显示 <b>${pageItems.length}</b> / ${fmtNum(total)} 支队伍${supportInPage ? `（含支援 <b>${supportInPage}</b>）` : ""} · 每页 ${state.pageSize}`;
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

  const applyFilters = (items) => {
    const query = state.query.trim();
    let filtered = items;
    if (query) filtered = filtered.filter((team) => String(team.id).includes(query));
    if (state.faction) filtered = filtered.filter((team) => team.faction === state.faction);
    return filterAndSortTeams(filtered, state.filter);
  };

  /** 「实际未出现」表格：与全怪组总表同款的高密度列表（编号/效能/单位·总血/阵营/怪种/代表出处） */
  const absentTableHtml = (teams) => {
    const row = (team) => {
      const disp = powerDisplay(team.power, team.power_known);
      const powerCell = disp.known
        ? `<b class="mono ${disp.negative ? "neg" : ""}" ${disp.negative ? 'title="积分关卡数据，可能为负"' : ""}>${disp.text}</b>`
        : `<span class="dim">未标注</span>`;
      const species = Array.isArray(team.species) ? team.species : [];
      const shown = species.slice(0, 6);
      const rest = species.length - shown.length;
      const speciesCell = shown.length
        ? `<span class="roster-species">${shown
            .map(
              (item) => `<span class="rs-ico" title="${esc(item.name || "")} #${String(item.codex_no || "").padStart(3, "0")}">${speciesIconHtml(
                item,
                { size: 16, variant: "mini", fallbackFaction: team.faction },
              )}</span>`,
            )
            .join("")}${rest > 0 ? `<span class="rs-more" title="共 ${species.length} 个怪种">+${rest}</span>` : ""}</span>`
        : `<span class="text-mute">—</span>`;
      const originTitle = team.stage
        ? [team.stage.title, team.stage.stage_title, team.stage.code].filter(Boolean).join(" · ")
        : "";
      const origin = team.stage
        ? `<span class="roster-chapters" title="${esc(originTitle)}">${esc(team.stage.title || "")}${team.stage.stage_title ? ` · ${esc(team.stage.stage_title)}` : ""}${team.stage.code ? ` <span class="dim">${esc(team.stage.code)}</span>` : ""}</span>`
        : `<span class="text-mute">无固定关卡</span>`;
      return `<tr class="roster-row" data-team-detail="${esc(team.id)}" tabindex="0" aria-label="队伍 #${esc(team.id)}" title="同系列可收藏，固定/刷怪表中没有">
        <td class="roster-id">#${esc(team.id)}</td>
        <td class="num">${powerCell}</td>
        <td class="num roster-uh" title="单位数 / 总血量"><b>${fmtNum(team.units)}</b><span class="roster-hp"> / ${fmtNum(team.hp_total)}</span></td>
        <td>${team.faction ? factionChip(team.faction, { small: true }) : "—"}</td>
        <td>${speciesCell}</td>
        <td>${origin}</td>
        <td class="roster-actions">
          <button class="btn btn-xs btn-ghost" type="button" title="查看详情" data-team-detail="${esc(team.id)}">${icon("eye", 12)}</button>
          <button class="btn btn-xs btn-cyan" type="button" title="加入序列" data-add-team="${esc(team.id)}">${icon("plus", 12)}</button>
        </td>
      </tr>`;
    };
    return `<div class="absent-table-wrap"><table class="data-table absent-table">
      <thead><tr>
        <th scope="col">编号</th>
        <th scope="col">效能</th>
        <th scope="col">单位/总血</th>
        <th scope="col">阵营</th>
        <th scope="col">怪种</th>
        <th scope="col">代表出处</th>
        <th scope="col" class="ta-r">操作</th>
      </tr></thead>
      <tbody>${teams.map(row).join("")}</tbody>
    </table></div>`;
  };

  const renderReserveStrip = () => {
    if (!reserveAreaEl) return;
    if (!loaded.reserveTeams.length) {
      reserveAreaEl.innerHTML = "";
      return;
    }
    const filtering = Boolean(state.query.trim() || state.faction || state.filter.mode !== "all");
    const manual = Boolean(loaded.manualReserve);
    const possibleCount = Number(loaded.reserveMeta?.possible_count || 0);
    const inStageCount = Number(loaded.reserveMeta?.in_stage_count || 0);

    // ---- 段一：可能刷怪（固定/刷怪表内、不在场上；或推断候选）----
    const spawnAll = applyFilters(loaded.spawnTeams);
    const spawnTotal = loaded.spawnTeams.length;
    const spawnExpanded = state.reserveOpen || (filtering && spawnAll.length > 0);
    const shown = spawnExpanded ? spawnAll.slice(0, state.reserveVisible) : [];
    const remain = Math.max(0, spawnAll.length - shown.length);
    const spawnTitle = `可能刷怪 <b>${filtering ? spawnAll.length : spawnTotal}</b> 支${filtering && spawnAll.length !== spawnTotal ? `（共 ${spawnTotal}）` : ""}${manual && possibleCount ? ` · 全部 ${possibleCount}${inStageCount ? `（含上方 ${inStageCount}）` : ""}` : ""}`;
    const spawnHint = manual
      ? "固定怪组表 + 刷怪表（无烟花/烟花强化）里、不在上方场上的怪组；与上方卡片同尺寸，点详情看编成"
      : "机场/后续刷新候选：同系列未入场怪组，STC 无显式机场刷新映射（推断）";
    const spawnFoot = manual
      ? "以上为固定怪组表 + 刷怪表中的怪组（卡面带 固定/无烟花/烟花强化 小标签），可加入序列。"
      : "以上为推断候选，不是确定出场；同样可加入序列，卡面带「可能刷怪（推断）」徽标。";

    // ---- 段二：实际未出现（仅 manual；紧凑行列表）----
    const absentAll = applyFilters(loaded.absentTeams);
    const absentTotal = loaded.absentTeams.length;
    const absentExpanded = state.absentOpen || (filtering && absentAll.length > 0);
    const absentTitle = `实际未出现 <b>${filtering ? absentAll.length : absentTotal}</b> 支${filtering && absentAll.length !== absentTotal ? `（共 ${absentTotal}）` : ""}`;
    const absentHint = "同系列可收藏，但固定怪组表/刷怪表中没有；表格列出（含怪种与代表出处），仅供查看/收藏";

    reserveAreaEl.innerHTML = `
      ${spawnTotal ? `
      <section class="reserve-strip" data-reserve-strip>
        <button class="reserve-toggle ${spawnExpanded ? "open" : ""}" type="button" data-reserve-toggle
          aria-expanded="${spawnExpanded}" title="${esc(spawnHint)}">
          <span class="reserve-flag">${icon(manual ? "list" : "refresh", 11)} ${manual ? "固定/刷怪表" : "推断"}</span>
          <span class="reserve-toggle-title">${spawnTitle}</span>
          <span class="reserve-toggle-hint">${esc(spawnHint)}</span>
          <span class="reserve-toggle-action">${icon(spawnExpanded ? "chevronUp" : "chevronDown", 13)} ${spawnExpanded ? "收起" : "展开"}</span>
        </button>
        ${
          spawnExpanded
            ? `<div class="reserve-grid-wrap">
                 <div class="team-grid reserve-grid">${shown.map((team) => teamCardHtml(team)).join("")}</div>
                 <div class="reserve-foot">
                   <span class="reserve-foot-hint">${spawnFoot}</span>
                   ${
                     remain > 0
                       ? `<button class="btn btn-sm btn-ghost" type="button" data-reserve-more>${icon("chevronDown", 12)} 再显示更多（剩余 ${remain}）</button>`
                       : shown.length > 24
                         ? `<button class="btn btn-sm btn-ghost" type="button" data-reserve-less>${icon("chevronUp", 12)} 收起候选</button>`
                         : ""
                   }
                 </div>
               </div>`
            : ""
        }
      </section>` : ""}
      ${absentTotal ? `
      <section class="reserve-strip absent-strip" data-absent-strip>
        <button class="reserve-toggle ${absentExpanded ? "open" : ""}" type="button" data-absent-toggle
          aria-expanded="${absentExpanded}" title="${esc(absentHint)}">
          <span class="reserve-flag absent">${icon("list", 11)} 表外</span>
          <span class="reserve-toggle-title">${absentTitle}</span>
          <span class="reserve-toggle-hint">${esc(absentHint)}</span>
          <span class="reserve-toggle-action">${icon(absentExpanded ? "chevronUp" : "chevronDown", 13)} ${absentExpanded ? "收起" : "展开"}</span>
        </button>
        ${
          absentExpanded
            ? `<div class="reserve-grid-wrap absent-wrap">
                 ${absentTableHtml(absentAll)}
                 <div class="reserve-foot">
                   <span class="reserve-foot-hint">这些怪组该系列可收藏，但本关固定/刷怪表均未出现；仍可查看详情或加入序列。</span>
                 </div>
               </div>`
            : ""
        }
      </section>` : ""}`;

    reserveAreaEl.querySelector("[data-reserve-toggle]")?.addEventListener("click", () => {
      state.reserveOpen = !state.reserveOpen;
      state.reserveVisible = 24;
      renderReserveStrip();
    });
    reserveAreaEl.querySelector("[data-reserve-more]")?.addEventListener("click", () => {
      state.reserveVisible += 24;
      state.reserveOpen = true;
      renderReserveStrip();
    });
    reserveAreaEl.querySelector("[data-reserve-less]")?.addEventListener("click", () => {
      state.reserveOpen = false;
      state.reserveVisible = 24;
      renderReserveStrip();
    });
    reserveAreaEl.querySelector("[data-absent-toggle]")?.addEventListener("click", () => {
      state.absentOpen = !state.absentOpen;
      renderReserveStrip();
    });
  };
  renderReserveStrip();

  bindSearch(rootEl.querySelector("[data-team-search]"), (value) => {
    state.query = value;
    state.page = 1;
    state.reserveVisible = 24;
    renderList();
    renderReserveStrip();
  });

  bindPowerFilter(rootEl, (filter) => {
    state.filter = filter;
    state.page = 1;
    state.reserveVisible = 24;
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
    state.reserveVisible = 24;
    renderList();
    renderReserveStrip();
  });

  rootEl.querySelector("[data-nav-back]")?.addEventListener("click", () => {
    if (isGrayNode && grayRegion && grayRegion.id) {
      navigate(`/grayzone/region/${encodeURIComponent(grayRegion.id)}`);
      return;
    }
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
