/* components/settlement.js —— 关卡结算形式展示（积分结算 / 普通结算 + 积分榜） */
import { icon } from "../ui.js";
import { esc } from "../util.js";

/**
 * 归一化后端 settlement 字段（缺失/异常时返回 null，调用方优雅降级）。
 * {"type":"score"|"normal","event_score":{"mode","params"}|null,
 *  "score_prize":{"raw","tiers"}|null,
 *  "rank":{"id","name","title","type","score_rewards"}|null}
 */
export function normalizeSettlement(stage) {
  const raw = stage?.settlement;
  if (!raw || typeof raw !== "object") return null;
  const type = raw.type === "score" ? "score" : raw.type === "normal" ? "normal" : null;
  if (!type) return null;
  const eventScore = raw.event_score && typeof raw.event_score === "object" ? raw.event_score : null;
  const prize = raw.score_prize && typeof raw.score_prize === "object" ? raw.score_prize : null;
  const rank = raw.rank && typeof raw.rank === "object" ? raw.rank : null;
  const mode = eventScore?.mode ?? null;
  const params = Number.isFinite(Number(eventScore?.params)) ? Number(eventScore.params) : null;
  const rankTitle = (rank?.title || rank?.name || "").trim() || null;
  const hasPrize = Boolean(prize && (prize.raw === undefined || String(prize.raw || "").trim() !== "" || Number(prize.tiers) > 0));
  return {
    type,
    isScore: type === "score",
    mode,
    params,
    hasPrize,
    prize,
    rank,
    rankTitle,
    eventScore,
  };
}

/** 一行摘要（不带 HTML 前缀）：积分结算 · 模式 1 · 24 项参数 · 积分奖励 有 · 积分榜 <title> */
export function settlementSummary(settlement) {
  if (!settlement) return "结算形式未标注";
  if (!settlement.isScore) return "普通结算";
  const parts = ["积分结算"];
  parts.push(`模式 ${settlement.mode ?? "—"}`);
  parts.push(`${settlement.params ?? "—"} 项参数`);
  parts.push(`积分奖励 ${settlement.hasPrize ? "有" : "无"}`);
  parts.push(`积分榜 ${settlement.rankTitle || "—"}`);
  return parts.join(" · ");
}

/** 章节详情：关卡行右侧小徽标（score 金色描边；normal 淡色；缺失不显示） */
export function settlementBadgeHtml(stage) {
  const settlement = normalizeSettlement(stage);
  if (!settlement) return "";
  if (settlement.isScore) {
    const tooltip = settlementSummary(settlement);
    return `<span class="settle-badge score" title="${esc(tooltip)}">${icon("spark", 10)} 积分结算</span>`;
  }
  return `<span class="settle-badge normal" title="普通结算 · 无 event_score 积分结算配置">普通结算</span>`;
}

/** 关卡队伍页 header：结算形式信息行 */
export function settlementLineHtml(stage) {
  const settlement = normalizeSettlement(stage);
  if (!settlement) {
    return `<div class="settle-line"><span class="settle-label">${icon("flag", 12)} 结算形式</span><span class="settle-muted">未标注（数据解析后显示）</span></div>`;
  }
  if (!settlement.isScore) {
    return `<div class="settle-line"><span class="settle-label">${icon("flag", 12)} 结算形式</span><span class="settle-pill normal">普通结算</span><span class="settle-detail">该关卡没有 event_score 积分结算配置</span></div>`;
  }
  const tooltip = settlementSummary(settlement);
  return `<div class="settle-line score">
    <span class="settle-label">${icon("spark", 12)} 结算形式</span>
    <span class="settle-pill score" title="${esc(tooltip)}">积分结算</span>
    <span class="settle-detail">event_score 模式 <b>${esc(settlement.mode ?? "—")}</b> · <b>${esc(settlement.params ?? "—")}</b> 项参数 · 积分奖励 <b>${settlement.hasPrize ? "有" : "无"}</b> · 积分榜 <b>${esc(settlement.rankTitle || "—")}</b></span>
  </div>`;
}

/** 章节卡 tooltip（score 章） */
export function chapterSettlementHint(chapter) {
  if (!chapter) return "";
  const isScore = chapter.category === "score" || chapter.kind === "score";
  return isScore ? "该章节关卡带 event_score 积分结算配置" : "";
}

/** 结算徽标数量（自检用 data 属性） */
export function settlementBadgeCountHint(settlement) {
  return settlement?.isScore ? "score" : settlement ? "normal" : "";
}
