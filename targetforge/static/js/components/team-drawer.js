/* team-drawer.js —— 队伍详情抽屉（只展示数值/编制/参数/出处，绝不展示技能信息） */
import { api } from "../api.js";
import { store, addTeam } from "../store.js";
import { icon, openDrawer, toast, toastErr, toastOk, setBusy, errorState, skeletonRows, speciesIconHtml } from "../ui.js";
import { esc, fmtNum, fmtFloat, factionColor, factionClass, navigate, powerDisplay, isSupportTeam, isReserveTeam } from "../util.js";

const unitName = (member) => member.name || member.code || "未知单位";

function statCell(value, { digits = 1, cls = "", title = "" } = {}) {
  const text = value === null || value === undefined ? "—" : digits === 0 ? fmtNum(value) : fmtFloat(value, digits);
  return `<td class="num ${cls}"${title ? ` title="${esc(title)}"` : ""}>${text}</td>`;
}

export function teamDetailBodyHtml(detail) {
  const fc = factionColor(detail.faction);
  const powerDisp = powerDisplay(detail.power, detail.power_known);
  const support = isSupportTeam(detail);
  const params = detail.params || {};
  const members = detail.members || [];
  const appearances = detail.appearances || [];
  const species = detail.species || [];
  const effectPower = Number(params.effect_ext ?? detail.power) || 0;
  const paramCells = [
    ["效能 effect_ext", effectPower === 0 ? "0（未标注）" : fmtNum(effectPower)],
    ["单位数 units", fmtNum(detail.units)],
    ["总血量 hp_total", fmtNum(detail.hp_total)],
    ["战斗类型 fight_type", params.fight_type ?? "—"],
    ["占地 use_building", params.use_building || "—"],
    ["批次上限 batch_max", params.batch_max ?? "—"],
    ["灰域关卡数", params.gray_zone_missions ?? 0],
    ["出处关卡数", params.mission_count ?? appearances.length],
  ];

  return `
    <div class="subhead">${icon("sliders", 12)} 队伍参数</div>
    <div class="param-grid">
      ${paramCells
        .map(
          ([label, value]) => `
        <div class="param-cell">
          <div class="pc-label">${esc(label)}</div>
          <div class="pc-value">${esc(String(value))}</div>
        </div>`,
        )
        .join("")}
    </div>
    ${params.note ? `<div class="param-note">${esc(params.note)}</div>` : ""}

    <div class="subhead">${icon("users", 12)} 单位聚合表 <span class="badge mono">${members.length} 组</span></div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>单位</th>
            <th class="num">等级</th>
            <th class="num">编制</th>
            <th class="num">数量</th>
            <th class="num">坐标</th>
            <th class="num">HP</th>
            <th class="num">火力</th>
            <th class="num">命中</th>
            <th class="num">回避</th>
            <th class="num">护甲</th>
            <th class="num">穿甲</th>
            <th class="num">射程</th>
            <th class="num">移速</th>
            <th class="num">护盾</th>
            <th class="num">满力场</th>
            <th class="num">初始力场</th>
            <th class="num">初始减伤</th>
          </tr>
        </thead>
        <tbody>
          ${
            members.length
              ? members
                  .map((member) => {
                    const stats = member.stats || {};
                    const defPercent = Number(member.def_percent ?? 0);
                    const ffMax = Number(stats.def);
                    const ffKnown = Number.isFinite(ffMax) && ffMax > 0 && ffMax < 99999;
                    const ffInitial = ffKnown
                      ? ffMax * Math.max(0, Math.min(100, defPercent)) / 100
                      : null;
                    const ffReduction = ffKnown
                      ? Math.max(0, Math.min(100, ffInitial / ffMax * 100))
                      : null;
                    const ffMaxText = ffKnown
                      ? fmtNum(ffMax)
                      : (Number.isFinite(ffMax) && ffMax >= 99999 ? "无" : "—");
                    const ffTitle = "满力场 = def；初始力场 = 满力场 × 初始力场%；初始减伤 = 初始力场 / 满力场（满力场时 100%）";
                    return `
              <tr>
                <td class="name"><span class="unit-cell">${speciesIconHtml(member, { size: 24, variant: "mini", fallbackFaction: detail.faction })}<span class="unit-name">${esc(unitName(member))}</span><span class="unit-code">${esc(member.code || "")}</span></span></td>
                <td class="num">${member.level ?? "—"}</td>
                <td class="num">${member.number ?? "—"}</td>
                <td class="num">${member.count ?? "—"}</td>
                <td class="num">${fmtFloat(member.x, 1)}, ${fmtFloat(member.y, 1)}</td>
                ${statCell(stats.maxlife, { digits: 0, cls: "stat-hi" })}
                ${statCell(stats.pow, { digits: 1, cls: "stat-red" })}
                ${statCell(stats.hit)}
                ${statCell(stats.dodge)}
                ${statCell(stats.armor)}
                ${statCell(stats.armor_piercing)}
                ${statCell(stats.range, { digits: 0 })}
                ${statCell(stats.speed, { digits: 0 })}
                ${statCell(stats.shield, { digits: 0, cls: "stat-cyan" })}
                <td class="num stat-green" title="${ffTitle}">${ffMaxText}</td>
                <td class="num stat-green" title="${ffTitle}">${ffKnown ? fmtNum(ffInitial) : "—"}</td>
                <td class="num stat-green" title="${ffTitle}">${ffKnown ? `${fmtFloat(ffReduction, 0)}%` : "—"}</td>
              </tr>`;
                  })
                  .join("")
              : `<tr><td colspan="17" style="text-align:center;padding:22px;color:var(--text-mute)">该队伍没有可展示的编制数据</td></tr>`
          }
        </tbody>
      </table>
    </div>
    <div class="param-note">数值为按队伍等级缩放后的展示口径；力场三列：满力场 = def，初始力场 = 满力场 × 初始力场%，初始减伤 = 初始力场 / 满力场（满力场时 100%）。</div>

    <div class="subhead">${icon("map", 12)} 本怪组出现位置 <span class="badge mono">${appearances.length}${appearances.length >= 24 ? "+" : ""}</span><span class="subhead-hint">同一怪组可能在多个关卡/活动中以敌方或支援身份出现</span></div>
    <div class="appear-list">
      ${
        appearances.length
          ? appearances
              .map((item) => {
                const role =
                  item.role === "support" || item.support || item.is_support || item.support_team
                    ? "support"
                    : item.role === "reserve"
                      ? "reserve"
                      : item.role === "enemy" || item.enemy
                        ? "enemy"
                        : support
                          ? "support"
                          : reserve
                            ? "reserve"
                            : "enemy";
                return `
          <button class="appear-item" type="button" data-stage-detail="${esc(item.mission_id)}">
            <span class="ai-code">${esc(item.code || item.mission_id)}</span>
            <span class="ai-title">${esc(item.chapter_title || "")} · ${esc(item.stage_title || "")} <span class="tag ${role}">${role === "support" ? "支援" : role === "reserve" ? "可能刷怪" : "敌方"}</span></span>
            <span class="ai-diff">${item.difficulty ? `难度 ${fmtNum(item.difficulty)}` : ""}</span>
            ${icon("chevronRight", 12)}
          </button>`;
              })
              .join("")
          : '<div class="appear-empty">该队伍没有固定关卡出处（灰域 / 活动临时队伍）</div>'
      }
    </div>

    <div class="subhead">${icon("crosshair", 12)} 关联怪种 <span class="badge mono">${species.length}</span></div>
    <div class="tag-row">
      ${
        species.length
          ? species
              .map(
                (item) => `
          <button class="sp-chip" type="button" data-species-detail="${esc(item.codex_no)}" style="--fc:${factionColor(item.faction)};height:23px;padding:0 8px;font-size:10.5px" title="查看怪种图鉴">
            ${speciesIconHtml(item, { size: 17, variant: "mini", fallbackFaction: detail.faction })}
            <span class="sp-chip-name">${esc(item.name)}</span>
            <span style="color:var(--text-mute);font-family:var(--font-mono)">#${String(item.codex_no).padStart(3, "0")}</span>
          </button>`,
              )
              .join("")
          : '<span class="text-mute">无</span>'
      }
    </div>
  `;
}

export function teamDetailHeadHtml(detail) {
  const fc = factionColor(detail.faction);
  const powerDisp = powerDisplay(detail.power, detail.power_known);
  const support = isSupportTeam(detail);
  const reserve = isReserveTeam(detail);
  const flags = [];
  if (support) flags.push(`<span class="badge support">${icon("shield", 9)} 支援队伍</span>`);
  if (reserve) {
    const manual = detail.reserve_source === "manual";
    if (manual) {
      flags.push(`<span class="badge reserve" title="固定怪组表 / 刷怪表">${icon("list", 9)} ${detail.appeared === false ? "实际未出现" : esc(detail.actual_kind || "可能刷怪")}</span>`);
    } else {
      flags.push(`<span class="badge reserve" title="推断：同系列未入场怪组，STC 无显式机场刷新映射">${icon("refresh", 9)} 可能刷怪（推断）</span>`);
    }
  }
  if (detail.gray_zone) flags.push('<span class="badge cyan">灰域队伍</span>');
  if (detail.orphan) flags.push('<span class="badge violet">无固定关卡</span>');
  return `
    <div class="drawer-title-row">
      <span class="drawer-title">#${esc(detail.id)}<small>${support ? "SUPPORT TEAM" : "ENEMY TEAM"}</small></span>
      <button class="modal-close" type="button" data-close-drawer style="margin-left:auto" aria-label="关闭">${icon("close", 17)}</button>
    </div>
    <div class="drawer-tags">
      <span class="faction-chip ${factionClass(detail.faction)}"><i></i>${esc(detail.faction || "其它")}</span>
      ${flags.join("")}
      ${(detail.tags || []).map((tag) => `<span class="tag amber">${esc(tag)}</span>`).join("")}
    </div>
    <div class="drawer-stats">
      <div class="ds-item"><b class="amber ${powerDisp.known ? (powerDisp.negative ? "neg" : "") : ""}"${powerDisp.negative ? ' title="积分关卡数据，可能为负"' : ""}>${powerDisp.known ? powerDisp.text : "未标注"}</b><span>${powerDisp.negative ? "效能（可能为负）" : "效能"}</span></div>
      <div class="ds-item"><b>${fmtNum(detail.units)}</b><span>单位数</span></div>
      <div class="ds-item"><b>${fmtNum(detail.hp_total)}</b><span>总血量</span></div>
      <div class="ds-item"><b class="cyan">${fmtNum((detail.members || []).length)}</b><span>编制组</span></div>
      <div class="ds-item"><b>${fmtNum((detail.appearances || []).length)}</b><span>关卡出处</span></div>
      <div class="ds-item"><b>${fmtNum((detail.species || []).length)}</b><span>关联怪种</span></div>
    </div>
  `;
}

/* 让抽屉/页面里的交互按钮跑起来 */
export function bindTeamDetail(root, detail) {
  root.style.setProperty("--fc", factionColor(detail.faction));
  root.querySelectorAll("[data-close-drawer]").forEach((button) => {
    button.addEventListener("click", () => {
      const drawer = document.querySelector(".drawer");
      const backdrop = document.querySelector(".drawer-backdrop");
      drawer?.remove();
      backdrop?.remove();
    });
  });
}

export function openTeamDrawer(teamId, options = {}) {
  const drawer = openDrawer({
    head: `<div class="drawer-title-row"><span class="drawer-title">#${esc(teamId)}<small>ENEMY TEAM</small></span><span style="margin-left:auto" class="spinner"></span></div>`,
    body: skeletonRows(4),
    footer: `
      <button class="btn btn-ghost" type="button" data-act="close">关闭</button>
      <div style="flex:1"></div>
      <button class="btn btn-primary" type="button" data-act="add" disabled>${icon("plus", 14)} 加入序列</button>
    `,
    width: 880,
    onClose: options.onClose || null,
  });

  const headEl = drawer.head;
  const bodyEl = drawer.body;
  const footEl = drawer.foot;

  const closeBtn = () => {
    drawer.close();
  };
  headEl.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-drawer]")) closeBtn();
  });
  footEl.querySelector('[data-act="close"]')?.addEventListener("click", closeBtn);

  (async () => {
    headEl.style.setProperty("--fc", "#5ee1ff");
    try {
      const detail = await api.team(teamId);
      headEl.innerHTML = teamDetailHeadHtml(detail);
      headEl.style.setProperty("--fc", factionColor(detail.faction));
      bodyEl.innerHTML = teamDetailBodyHtml(detail);
      bodyEl.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", closeBtn));
      bindTeamDetail(bodyEl, detail);

      const addBtn = footEl.querySelector('[data-act="add"]');
      addBtn.disabled = false;
      addBtn.addEventListener("click", async () => {
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
      headEl.innerHTML = `
        <div class="drawer-title-row">
          <span class="drawer-title">#${esc(teamId)}</span>
          <button class="modal-close" type="button" data-close-drawer style="margin-left:auto">${icon("close", 17)}</button>
        </div>`;
      headEl.querySelector("[data-close-drawer]").addEventListener("click", closeBtn);
      bodyEl.innerHTML = errorState({ error: err });
      bodyEl.querySelector("#retry-btn")?.addEventListener("click", () => {
        drawer.close();
        openTeamDrawer(teamId, options);
      });
    }
  })();

  return drawer;
}
