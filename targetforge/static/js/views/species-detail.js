/* views/species-detail.js —— 怪种详情：所有怪组（服务端分页 + 搜索） */
import { api } from "../api.js";
import { sequenceStats, addTeams } from "../store.js";
import {
  icon,
  pageHeadHtml,
  sectionHeadHtml,
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
  tagsHtml,
  sortTeamsByPower,
} from "../ui.js";
import { esc, fmtNum, factionColor, navigate, bindSearch } from "../util.js";

const PAGE_SIZE = 48;

export async function render(root, { params }) {
  const codexNo = params.codex;
  root.innerHTML = pageHeadHtml({
    crumbs: [{ label: "怪种图鉴", nav: "/species" }, { label: `#${codexNo}` }],
    title: "怪种详情",
    sub: "正在读取怪种数据…",
  }) + `<div data-body>${skeletonCards(8)}</div>`;

  try {
    const data = await api.speciesDetail(codexNo, { offset: 0, limit: PAGE_SIZE });
    renderPage(root, codexNo, data, data.species || {});
  } catch (err) {
    handleViewError(root, err, () => render(root, { params }));
  }
}

function renderPage(root, codexNo, firstPage, species) {
  const fc = factionColor(species.faction);
  const categoryLabel = { normal: "有固定关卡", grayzone: "灰域专属", orphan: "无固定关卡" }[species.category] || "未知分类";
  const view = {
    page: 1,
    query: "",
    total: firstPage.total ?? firstPage.teams_total ?? species.team_count ?? 0,
    items: firstPage.teams || [],
    pageSize: PAGE_SIZE,
  };

  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [
        { label: "怪种图鉴", nav: "/species" },
        { label: `#${String(species.codex_no || codexNo).padStart(3, "0")}` },
      ],
      title: species.name || `怪种 #${codexNo}`,
      badge: `#${String(species.codex_no || codexNo).padStart(3, "0")}`,
      sub: `图鉴编号 ${esc(species.codex_no || codexNo)} · 共 <b class="mono-inline">${fmtNum(species.team_count)}</b> 支可收藏队伍，按怪组分页展示。点队伍看数值详情，或直接加入序列。`,
      actions: `
        <button class="btn btn-ghost" type="button" data-nav-back>${icon("chevronLeft", 14)} 返回怪种列表</button>
      `,
    })}

    <div class="capture-panel" style="display:flex;align-items:center;gap:22px;margin-bottom:22px;flex-wrap:wrap">
      <span class="sp-avatar" style="--fc:${fc};width:76px;height:76px;font-size:29px;flex:none">${esc((species.name || "?").slice(0, 1))}</span>
      <div style="flex:1;min-width:220px">
        <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">
          <span style="font-size:22px;font-weight:700;letter-spacing:1px">${esc(species.name || "")}</span>
          <span class="mono-inline text-mute">#${String(species.codex_no || codexNo).padStart(3, "0")}</span>
          ${factionChip(species.faction)}
          <span class="badge ${species.capturable ? "green" : "red"}">${species.capturable ? "可契约捕获" : "不可捕获"}</span>
          <span class="badge cyan">${esc(categoryLabel)}</span>
          <span class="badge mono">TYPE ${esc(species.type ?? "—")}</span>
        </div>
        <div class="tag-row mt8">${tagsHtml(species.tags, { max: 6 }) || '<span class="text-mute" style="font-size:11px">暂无标签</span>'}</div>
      </div>
      <div class="drawer-stats" style="margin:0;gap:24px">
        <div class="ds-item"><b class="amber">${fmtNum(species.team_count)}</b><span>全部队伍</span></div>
        <div class="ds-item"><b class="cyan">${fmtNum(species.gray_zone_team_count)}</b><span>灰域队伍</span></div>
        <div class="ds-item"><b>${fmtNum(species.orphan_team_count)}</b><span>无固定关卡</span></div>
      </div>
    </div>

    <section class="section">
      ${sectionHeadHtml("怪组列表", { hint: "同一怪种的多个可收藏队伍 · 数值各不相同", iconName: "users" })}
      <div class="toolbar">
        <div class="input-wrap">
          <span class="in-ico">${icon("search", 14)}</span>
          <input type="text" placeholder="搜索队伍 id / 阵营 / 成员…" data-sp-team-search />
        </div>
        <span class="spacer"></span>
        <span class="tb-meta" data-sp-meta>${icon("users", 11)} 读取中…</span>
        <button class="btn btn-primary btn-sm" type="button" data-act="add-page">${icon("plus", 12)} 本页全部加入序列</button>
      </div>
      <div data-sp-teams>${skeletonCards(8)}</div>
    </section>
  `;

  const listEl = root.querySelector("[data-sp-teams]");
  const metaEl = root.querySelector("[data-sp-meta]");
  const addPageBtn = root.querySelector('[data-act="add-page"]');

  const renderList = () => {
    if (metaEl) {
      metaEl.innerHTML = `${icon("users", 11)} 匹配 <b>${fmtNum(view.total)}</b> 支队伍 · 每页 ${PAGE_SIZE}`;
    }
    if (!view.items.length) {
      listEl.innerHTML = emptyState({
        iconName: "users",
        title: view.query ? "没有匹配的队伍" : "该怪种暂无可收藏队伍",
        desc: view.query ? "换个关键词试试。" : "怪种可能只出现在不可收藏的队伍里。",
      });
      return;
    }
    listEl.innerHTML = `
      <div class="team-grid">${view.items.map((team) => teamCardHtml(team)).join("")}</div>
      ${renderPager({ page: view.page, total: view.total, pageSize: PAGE_SIZE })}
    `;
    bindPager(listEl, {
      page: view.page,
      total: view.total,
      pageSize: PAGE_SIZE,
      onChange: (page) => load(page).then(() => listEl.scrollIntoView({ behavior: "smooth", block: "start" })),
    });
  };

  const load = async (page = 1, query = view.query) => {
    listEl.innerHTML = skeletonCards(8);
    try {
      const data = await api.speciesDetail(codexNo, {
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: query,
      });
      view.items = sortTeamsByPower(data.teams || []);
      view.total = data.total ?? data.teams_total ?? 0;
      view.page = page;
      view.query = query;
      renderList();
    } catch (err) {
      handleViewError(listEl, err, () => load(page, query));
    }
  };

  renderList();

  bindSearch(root.querySelector("[data-sp-team-search]"), (value) => load(1, value));

  root.querySelector("[data-nav-back]")?.addEventListener("click", () => navigate("/species"));

  addPageBtn?.addEventListener("click", async () => {
    if (!view.items.length) return;
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
    setBusy(addPageBtn, true, "加入中…");
    try {
      const sequence = await addTeams(toAdd.map((team) => team.id));
      toastOk("已加入序列", `成功加入 ${toAdd.length} 支队伍 · 当前序列 ${sequence.count}/${sequence.max}`);
    } catch (err) {
      toastErr("加入失败", err.message);
    } finally {
      setBusy(addPageBtn, false);
    }
  });
}
