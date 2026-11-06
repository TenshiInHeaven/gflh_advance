/* components/grayzone-meta.js —— 灰域层级：区域（regions 5：沙尘带/风暴带/硅状带/结晶带/特殊区域）与地点（areas 14） */
import { fmtNum } from "../util.js";

function text(value) {
  return String(value ?? "").trim();
}

/** 归一化 region_ids / region_id / regions 多种后端/旧格式 */
export function normalizeRegionIds(area) {
  if (!area || typeof area !== "object") return [];
  const raw = area.region_ids ?? area.regionIds ?? area.region_id ?? area.regionId ?? area.regions;
  if (Array.isArray(raw)) {
    return raw.map((item) => (typeof item === "object" ? text(item.id ?? item.title ?? item.name) : text(item))).filter(Boolean);
  }
  if (raw && typeof raw === "object") {
    const value = text(raw.id ?? raw.title ?? raw.name);
    return value ? [value] : [];
  }
  if (typeof raw === "string") {
    return raw
      .split(/[,，|/]/)
      .map((item) => text(item))
      .filter(Boolean);
  }
  return [];
}

/** 把 /api/grayzone/areas 的 {regions, areas} 或旧 {areas} 归一化 */
export function normalizeGrayMeta(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const rawRegions = Array.isArray(source.regions) ? source.regions : [];
  const rawAreas = Array.isArray(source.areas) ? source.areas : Array.isArray(source) ? source : [];
  const regions = rawRegions
    .map((region) => {
      const id = text(region.id ?? region.title ?? region.name);
      return {
        id,
        title: text(region.title ?? region.name ?? id),
        stage_count: Number(region.stage_count ?? region.stageCount ?? 0) || 0,
        team_count: Number(region.team_count ?? region.teamCount ?? 0) || 0,
        species_count: Number(region.species_count ?? region.speciesCount ?? 0) || 0,
        area_ids: Array.isArray(region.area_ids) ? region.area_ids.map(text) : [],
      };
    })
    .filter((region) => region.id || region.title);
  const areas = rawAreas
    .map((area) => ({
      ...area,
      id: text(area.id ?? area.title ?? area.name),
      title: text(area.title ?? area.name ?? area.id),
      region_ids: normalizeRegionIds(area),
    }))
    .filter((area) => area.id || area.title);
  return { regions, areas, hasRegions: regions.length > 0 };
}

/** 区域名（若干） */
export function areaRegionNames(area, regions) {
  const ids = area?.region_ids || [];
  const lookup = new Map((regions || []).map((region) => [region.id, region.title]));
  const names = ids.map((id) => lookup.get(id) || id).filter(Boolean);
  return [...new Set(names)];
}

/** 区域统计（后端未给 counts 时用所属地点求和兜底） */
export function regionStats(region, areas) {
  const own = (areas || []).filter((area) => (area.region_ids || []).includes(region.id));
  const stage = region.stage_count || own.reduce((acc, area) => acc + (Number(area.stage_count) || 0), 0);
  const teams = region.team_count || own.reduce((acc, area) => acc + (Number(area.team_count) || 0), 0);
  const species = region.species_count || own.reduce((acc, area) => acc + (Number(area.species_count) || 0), 0);
  return { areas: own.length, stage_count: stage, team_count: teams, species_count: species };
}

/** 灰域统计数字（区域/地点/队伍/怪种/节点） */
export function grayStats(chapter, meta) {
  const areas = meta?.areas || [];
  const regions = meta?.regions || [];
  const sum = (key) => areas.reduce((acc, area) => acc + (Number(area[key]) || 0), 0);
  const num = (value) => (Number.isFinite(Number(value)) ? Number(value) : null);
  return {
    region_count: regions.length,
    area_count: areas.length,
    team_count: num(chapter?.team_count) ?? sum("team_count"),
    species_count: num(chapter?.species_count) ?? sum("species_count"),
    stage_count: num(chapter?.stage_count) ?? sum("stage_count"),
  };
}

export function grayStatTiles(stats) {
  return [
    { label: "区域数量", icon: "radar", value: stats.region_count || "—", sub: "沙尘带 / 风暴带 / 硅状带 / 结晶带 / 特殊区域", accent: "cyan" },
    { label: "地点数量", icon: "map", value: stats.area_count, sub: "区域内的地点（不是区域）" },
    { label: "可收藏队伍", icon: "users", value: fmtNum(stats.team_count), sub: "全部地点合计" },
    { label: "怪种", icon: "crosshair", value: fmtNum(stats.species_count), sub: "地点合计" },
    { label: "节点", icon: "flag", value: fmtNum(stats.stage_count), sub: "仅计数，不逐节点列举" },
  ];
}
