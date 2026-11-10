/* views/team-page.js —— 队伍详情独立页（路由 #/teams/{id}，与抽屉共用渲染） */
import { api } from "../api.js";
import { addTeam } from "../store.js";
import { icon, pageHeadHtml, skeletonRows, handleViewError, toastOk, toastErr, setBusy } from "../ui.js";
import { esc, fmtNum, factionColor, factionClass, navigate, powerDisplay, isSupportTeam, isReserveTeam } from "../util.js";
import { teamDetailBodyHtml } from "../components/team-drawer.js";

export async function render(root, { params }) {
  const teamId = params.id;
  let backTo = "/chapters";
  try {
    backTo = sessionStorage.getItem("tf:last-list") || "/chapters";
  } catch {
    backTo = "/chapters";
  }
  root.innerHTML = pageHeadHtml({
    crumbs: [{ label: "队伍详情" }, { label: `#${teamId}` }],
    title: `队伍 #${teamId}`,
    sub: "正在读取队伍数值…",
  }) + `<div data-body>${skeletonRows(5)}</div>`;

  try {
    const detail = await api.team(teamId);
    const powerDisp = powerDisplay(detail.power, detail.power_known);
    root.innerHTML = `
      ${pageHeadHtml({
        crumbs: [
          { label: "队伍详情" },
          { label: `#${detail.id}` },
        ],
        title: `队伍 #${detail.id}`,
        badge: isSupportTeam(detail) ? "SUPPORT TEAM" : "ENEMY TEAM",
        sub: `${esc(detail.faction || "其它")} · 效能 <b class="mono-inline">${powerDisp.known ? powerDisp.text : "未标注"}</b> · ${detail.units} 个单位 · 总血量 <b class="mono-inline">${fmtNum(detail.hp_total)}</b>。本页只展示数值 / 编制 / 参数 / 关卡出处。`,
        actions: `
          <button class="btn btn-ghost" type="button" data-act="back">${icon("chevronLeft", 14)} 返回</button>
          <button class="btn btn-primary" type="button" data-act="add">${icon("plus", 14)} 加入序列</button>
        `,
      })}
      <div class="capture-panel" style="margin-bottom:20px">
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;position:relative;padding-left:12px">
          <span style="position:absolute;left:0;top:2px;bottom:2px;width:3px;background:${factionColor(detail.faction)}"></span>
          <span class="faction-chip ${factionClass(detail.faction)}"><i></i>${esc(detail.faction || "其它")}</span>
          ${isSupportTeam(detail) ? `<span class="badge support">${icon("shield", 9)} 支援队伍</span>` : ""}
          ${isReserveTeam(detail) ? (detail.reserve_source === "manual"
            ? `<span class="badge reserve" title="固定怪组表 / 刷怪表">${icon("list", 9)} ${detail.appeared === false ? "实际未出现" : esc(detail.actual_kind || "可能刷怪")}</span>`
            : `<span class="badge reserve" title="推断：同系列未入场怪组，STC 无显式机场刷新映射">${icon("refresh", 9)} 可能刷怪（推断）</span>`) : ""}
          ${detail.gray_zone ? '<span class="badge cyan">灰域队伍</span>' : ""}
          ${detail.orphan ? '<span class="badge violet">无固定关卡</span>' : ""}
          ${(detail.tags || []).map((tag) => `<span class="tag amber">${esc(tag)}</span>`).join("")}
          <span style="flex:1"></span>
          <span class="mono-inline text-mute" style="font-size:10.5px">team_id ${esc(detail.id)}</span>
        </div>
        <div class="drawer-stats" style="margin-top:16px">
          <div class="ds-item"><b class="amber ${powerDisp.known ? (powerDisp.negative ? "neg" : "") : ""}">${powerDisp.known ? powerDisp.text : "未标注"}</b><span>${powerDisp.negative ? "效能（可能为负）" : "效能"}</span></div>
          <div class="ds-item"><b>${fmtNum(detail.units)}</b><span>单位数</span></div>
          <div class="ds-item"><b>${fmtNum(detail.hp_total)}</b><span>总血量</span></div>
          <div class="ds-item"><b class="cyan">${fmtNum((detail.members || []).length)}</b><span>编制组</span></div>
          <div class="ds-item"><b>${fmtNum((detail.appearances || []).length)}</b><span>关卡出处</span></div>
          <div class="ds-item"><b>${fmtNum((detail.species || []).length)}</b><span>关联怪种</span></div>
        </div>
      </div>
      <div class="panel panel-pad" style="--fc:${factionColor(detail.faction)}">
        ${teamDetailBodyHtml(detail)}
      </div>
    `;

    root.querySelector('[data-act="back"]')?.addEventListener("click", () => navigate(backTo));
    const addBtn = root.querySelector('[data-act="add"]');
    addBtn?.addEventListener("click", async () => {
      setBusy(addBtn, true, "加入中…");
      try {
        await addTeam(detail.id);
        toastOk("已加入序列", `队伍 #${detail.id}${Number(detail.power) > 0 ? ` · 效能 ${fmtNum(detail.power)}` : ""}`);
        addBtn.innerHTML = `${icon("check", 14)} 已在序列中`;
        addBtn.disabled = true;
      } catch (err) {
        toastErr("加入失败", err.message);
        setBusy(addBtn, false);
      }
    });
  } catch (err) {
    handleViewError(root, err, () => render(root, { params }));
  }
}
