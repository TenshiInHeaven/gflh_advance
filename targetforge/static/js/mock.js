/* mock.js —— 前端自测假数据层（?mock=1 启用）
 * 结构与 contract.md §2.3 / §4 完全一致；不依赖后端即可完整点通所有页面。
 * 数据用固定种子生成，保证每次刷新视觉一致。
 */
import { hash32, mulberry32, randInt, pick, shuffle, sleep } from "./util.js";

const NOW = "2026-11-06T18:20:00+08:00";
const BUILT_AT = "2026-11-06T18:20:00+08:00";
const VERSION = "1.0.0-mock";

const FACTIONS = ["铁血", "军方", "帕拉蒂斯", "其它"];

const SPECIES_NAMES = [
  "稻草人", "圣盾", "破坏者", "梦想家", "炼金术士", "法官", "建筑师", "计量官",
  "代理人", "干扰者", "衔尾蛇", "天狼星", "猎手", "兵蚁", "劫掠者", "狂热者",
  "巡游者", "驱逐者", "守卫者", "狙击手", "突击者", "巡逻者", "侦察者", "工程师",
  "执法者", "要塞", "哨兵", "收割者", "潜行者", "毁灭者", "撕裂者", "吞噬者",
  "枪手", "盾卫", "火炮", "坦克", "蜘蛛", "蝎子", "螳螂", "蜂群",
  "蝰蛇", "野狼", "黑豹", "白鲨", "苍鹰", "幽灵", "幻影", "伪装者",
];

const UNIT_PAIRS = [
  ["Aegis_GA", "圣盾_GA"], ["Striker", "突击者"], ["Guardian", "守护者"],
  ["Raptor", "猛禽"], ["Centaure", "半人马"], ["Tarantula", "塔兰图拉"],
  ["Scarecrow", "稻草人"], ["Dreamer", "梦想家"], ["Alchemist", "炼金术士"],
  ["Judge", "法官"], ["Architect", "建筑师"], ["Intruder", "入侵者"],
  ["Ouroboros", "衔尾蛇"], ["Sirius", "天狼星"], ["Hunter", "猎手"],
  ["Executioner", "处刑者"], ["Goliath", "歌利亚"], ["Nemeum", "涅墨亚"],
  ["Manticore", "蝎尾狮"], ["Behemoth", "巨兽"],
];

const STAGE_TITLES = [
  "演习训练", "前哨阵地", "废弃工厂", "城市废墟", "军事基地", "雪原防线",
  "沙漠公路", "港口仓储", "山谷隘口", "地下通道", "实验设施", "数据中心",
  "防空阵地", "跨河桥梁", "边境村落", "热带丛林", "沼泽地带", "废弃矿区",
  "地铁车站", "临时机场", "指挥中心", "补给中转站", "雷达站", "要塞外围",
  "核心控制区", "装甲走廊", "坍塌街区", "隔离墙", "旧工业区", "无人区",
];

const EVENT_NAMES = [
  "自画像", "异构体", "坍缩点", "有序紊流", "双联乱数", "裂变链接", "镜像论", "熵减焓增",
  "深度异象", "沙罗蚀相", "临界角", "静风点", "纵向应变", "捩浪人", "控制区",
  "暗金潮", "雪夜行军", "铁血浪潮", "协议的终末", "归零重启", "逆流行动",
  "潮汐锁定", "反演螺旋", "无声剧场", "浊流彼岸", "破晓之前", "白夜极光",
  "深层回响", "寂静前线", "边境迷航", "断章余烬", "黎明裂缝", "钢之挽歌",
  "终焉坐标", "未竟之路",
];

const TUTORIAL_NAMES = ["人形教学", "基础操作", "战斗教学", "行进教学", "夜战教学", "靶机指引"];

const GRAYZONE_AREAS = [
  "共生净土", "晶团挖掘点", "旅团商道", "放射区", "人形复制工厂", "废弃居民区",
  "秘密通道", "交易地", "最终贮藏地", "图腾圣所", "地坛遗迹", "装甲突击",
  "庇护所旧址", "坍缩狭缝",
];

const TAGS_POOL = [
  ["BOSS"], ["精英"], ["满力场"], ["装甲"], ["机械"], ["夜战"], ["昼战"],
  ["高回避"], ["高火力"], ["低速"], ["高速"], ["重甲"], ["多单位"], ["远程"],
];

/* ------------------------------------------------------------------ */
/* 基础生成工具                                                       */
/* ------------------------------------------------------------------ */
function mockIconUri(faction, seed) {
  const palette = { 铁血: "#ff7a6e", 军方: "#a3b86b", 帕拉蒂斯: "#b98cff", 其它: "#8aa0c4" };
  const color = palette[faction] || "#8aa0c4";
  const shape = Number(seed || 0) % 3;
  const inner =
    shape === 0
      ? `<ellipse cx="32" cy="30" rx="12" ry="15" fill="${color}"/><circle cx="32" cy="16" r="8" fill="${color}"/><path d="M20 40 6 32M44 40l14-8M22 48 10 56M42 48l12 8" stroke="${color}" stroke-width="4" stroke-linecap="round" fill="none"/>`
      : shape === 1
        ? `<rect x="16" y="20" width="32" height="26" rx="5" fill="${color}"/><rect x="22" y="8" width="20" height="13" rx="4" fill="${color}"/><rect x="26" y="12" width="12" height="4" rx="2" fill="#0a1228" opacity=".65"/><rect x="8" y="26" width="6" height="12" rx="2" fill="${color}"/><rect x="50" y="26" width="6" height="12" rx="2" fill="${color}"/>`
        : `<path d="M32 4 40 18 56 16 48 30 58 42 42 44 32 60 22 44 6 42 16 30 8 16 24 18Z" fill="${color}"/><circle cx="24" cy="30" r="3" fill="#0a1228" opacity=".65"/><circle cx="40" cy="30" r="3" fill="#0a1228" opacity=".65"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="${color}" opacity=".14"/>${inner}</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function seedOf(text) {
  return hash32(`tf-mock:${text}`);
}

function speciesName(codex) {
  const base = SPECIES_NAMES[(codex - 1) % SPECIES_NAMES.length];
  const round = Math.floor((codex - 1) / SPECIES_NAMES.length);
  const suffix = ["", "·改", "·精英", "·II", "·特化", "·残响"][round % 6];
  return `${base}${suffix}`;
}

function factionByCodex(codex) {
  return FACTIONS[(codex + Math.floor(codex / 4)) % FACTIONS.length];
}

function tagsFor(seed) {
  const rng = mulberry32(seed);
  const count = randInt(rng, 1, 3);
  const pool = shuffle(rng, TAGS_POOL);
  return pool.slice(0, count).map((tag) => tag[0]);
}

function makeStage(chapterSeed, ordinal, chapter) {
  const rng = mulberry32(hash32(`stage:${chapterSeed}:${ordinal}`));
  const stageId = 100000 + (chapterSeed % 900) * 1000 + ordinal + 1;
  const diffSpan = Math.max(1, chapter.difficulty_max - chapter.difficulty_min);
  const ratio = (ordinal + 1) / Math.max(1, chapter.stage_count);
  const difficulty = Math.round(chapter.difficulty_min + diffSpan * ratio);
  const tags = [];
  if (rng() > 0.72) tags.push("紧急");
  if (rng() > 0.82) tags.push("BOSS");
  if (rng() > 0.88) tags.push("夜战");
  if (!tags.length) tags.push("普通");
  return {
    id: stageId,
    title: `${pick(rng, STAGE_TITLES)}`,
    code: chapter.code_prefix ? `${chapter.code_prefix}${ordinal + 1}` : `${ordinal + 1}`,
    difficulty,
    recommend_level: randInt(rng, 0, 120),
    team_count: randInt(rng, 6, 14),
    species_count: randInt(rng, 6, 26),
    tags,
    order: ordinal,
  };
}

/* ------------------------------------------------------------------ */
/* 章节 / 关卡                                                        */
/* ------------------------------------------------------------------ */
const GROUP_DEFS = [
  { id: "main", title: "主线", category: "main", count: 13, tag: "主线" },
  { id: "event", title: "活动", category: "event", count: 46, tag: "活动" },
  { id: "score", title: "积分关卡", category: "score", count: 6, tag: "积分关卡" },
  { id: "tutorial", title: "教学", category: "tutorial", count: 6, tag: "教学" },
  { id: "simulation", title: "模拟作战", category: "simulation", count: 1, tag: "靶场" },
  { id: "grayzone", title: "灰域探查", category: "grayzone", count: 1, tag: "打灰" },
  { id: "orphan", title: "无固定关卡", category: "orphan", count: 1, tag: "无固定关卡" },
];

const state = {
  chaptersById: new Map(),
  stagesByChapter: new Map(),
  stageOwners: new Map(),
  groups: null,
  speciesList: null,
  areas: null,
  currentTeamIds: null,
  currentCreds: "creds_latest.json",
  sequence: loadMockSequence(),
  tutorial: loadMockTutorial(),
  capture: null,
  jobs: new Map(),
  settings: {
    capture_port: 18080,
    auto_restore_proxy: true,
    preferred_creds: "creds_latest.json",
    append_skip_existing: true,
  },
};

/* mock 模式下用 sessionStorage 持久化序列，模拟真实后端（整页刷新不丢） */
function loadMockSequence() {
  try {
    const raw = window.sessionStorage.getItem("tf-mock-sequence");
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(Number).filter(Number.isFinite).slice(0, 35) : [];
  } catch {
    return [];
  }
}

function saveMockSequence() {
  try {
    window.sessionStorage.setItem("tf-mock-sequence", JSON.stringify(state.sequence));
  } catch {
    /* ignore */
  }
}

/* mock 模式下教程状态也持久化，避免整页刷新后反复弹新手引导 */
function loadMockTutorial() {
  try {
    const raw = window.sessionStorage.getItem("tf-mock-tutorial");
    if (!raw) return { completed: [], dismissed: false };
    const parsed = JSON.parse(raw);
    return {
      completed: Array.isArray(parsed.completed) ? parsed.completed : [],
      dismissed: Boolean(parsed.dismissed),
    };
  } catch {
    return { completed: [], dismissed: false };
  }
}

function saveMockTutorial() {
  try {
    window.sessionStorage.setItem("tf-mock-tutorial", JSON.stringify(state.tutorial));
  } catch {
    /* ignore */
  }
}

function buildChapter(groupDef, ordinal) {
  const rng = mulberry32(hash32(`chapter:${groupDef.id}:${ordinal}`));
  let title;
  let subtitle = "";
  let chapterId;
  let codePrefix = "";
  if (groupDef.id === "main") {
    chapterId = `main-${ordinal}`;
    title = ordinal === 0 ? "序章" : `第${ordinal}章`;
    subtitle = "";
    codePrefix = `${Math.max(0, ordinal) + 1}-`;
  } else if (groupDef.id === "event") {
    chapterId = `event-${ordinal}`;
    const eventName = EVENT_NAMES[ordinal % EVENT_NAMES.length];
    title = `${eventName}·第${(ordinal % 4) + 1}章`;
    subtitle = `大型活动「${eventName}」`;
    codePrefix = `E${(ordinal % 4) + 1}-`;
  } else if (groupDef.id === "rerun") {
    chapterId = `rerun-${ordinal}`;
    title = `往期活动·第${ordinal + 1}章`;
    subtitle = `复刻活动「${EVENT_NAMES[(ordinal + 7) % EVENT_NAMES.length]}」`;
    codePrefix = `R${ordinal + 1}-`;
  } else if (groupDef.id === "tutorial") {
    chapterId = `tutorial-${ordinal}`;
    title = TUTORIAL_NAMES[ordinal % TUTORIAL_NAMES.length];
    subtitle = "教学关卡";
    codePrefix = `T${ordinal + 1}-`;
  } else if (groupDef.id === "special") {
    chapterId = `special-${ordinal}`;
    title = `特殊作战 ${-(ordinal + 1) * 103}`;
    subtitle = `${EVENT_NAMES[(ordinal + 13) % EVENT_NAMES.length]} 特别行动`;
    codePrefix = `S${ordinal + 1}-`;
  } else if (groupDef.id === "score") {
    chapterId = `score-${ordinal}`;
    title = `积分关卡·第${ordinal + 1}期`;
    subtitle = "积分关卡 · 队伍效能有标注（可能为负）";
    codePrefix = `S${ordinal + 1}-`;
  } else if (groupDef.id === "simulation") {
    chapterId = "simulation";
    title = "模拟作战·靶场";
    subtitle = "常驻模拟作战";
    codePrefix = "SIM-";
  } else if (groupDef.id === "orphan") {
    chapterId = "orphan";
    title = "无固定关卡";
    subtitle = "4381 支队伍";
    codePrefix = "";
  } else {
    chapterId = "grayzone";
    title = "灰域探查";
    subtitle = "12 个区域 · 1288 个节点";
    codePrefix = "GZ-";
  }

  const stageCount =
    groupDef.id === "grayzone"
      ? 1288
      : groupDef.id === "simulation"
        ? 9
        : groupDef.id === "orphan"
          ? 0
          : groupDef.id === "score"
            ? randInt(rng, 4, 10)
            : randInt(rng, 8, 24);
  const teamCount =
    groupDef.id === "grayzone" ? 3352 : groupDef.id === "orphan" ? 4381 : stageCount * randInt(rng, 14, 30);
  const speciesCount = groupDef.id === "grayzone" ? 199 : groupDef.id === "orphan" ? 211 : randInt(rng, 18, 96);
  const difficultyMin =
    groupDef.id === "orphan"
      ? 0
      : groupDef.id === "score"
        ? randInt(rng, 1200, 9000)
        : groupDef.id === "main" || groupDef.id === "tutorial"
          ? 200 + ordinal * 400
          : 2000 + ordinal * 700;
  const difficultyMax = groupDef.id === "orphan" ? 0 : difficultyMin + randInt(rng, 2400, 42000);

  const chapter = {
    id: chapterId,
    category: groupDef.category,
    title,
    subtitle,
    stage_count: stageCount,
    team_count: teamCount,
    species_count: speciesCount,
    difficulty_min: difficultyMin,
    difficulty_max: difficultyMax,
    tags: [groupDef.tag, ...(rng() > 0.6 ? ["高难"] : [])],
    code_prefix: codePrefix,
  };
  if (groupDef.id === "grayzone") {
    chapter.areas = getAreas();
    chapter.subtitle = `${GRAYZONE_AREAS.length} 个区域 · ${stageCount} 个节点`;
  }
  state.chaptersById.set(chapterId, chapter);
  return chapter;
}

function ensureChapters() {
  if (state.groups) return state.groups;
  const groups = [];
  GROUP_DEFS.forEach((def) => {
    const chapters = [];
    for (let i = 0; i < def.count; i += 1) {
      chapters.push(buildChapter(def, i));
    }
    groups.push({ id: def.id, title: def.title, chapters });
  });
  state.groups = groups;
  return groups;
}

function getAreas() {
  if (state.areas) return state.areas;
  state.areas = GRAYZONE_AREAS.map((name, idx) => {
    const rng = mulberry32(hash32(`area:${name}`));
    return {
      id: name,
      title: name,
      stage_count: randInt(rng, 32, 240),
      team_count: [197, 240, 320, 410, 512, 620, 758, 880, 940, 1000, 1050, 1104][idx],
      species_count: randInt(rng, 30, 150),
    };
  });
  return state.areas;
}

function chapterStages(chapter) {
  if (chapter.category === "orphan") return [];
  if (state.stagesByChapter.has(chapter.id)) return state.stagesByChapter.get(chapter.id);
  const stages = [];
  const chapterSeed = hash32(`chapter-uid:${chapter.id}`);
  const count = Math.min(chapter.stage_count, 26);
  for (let i = 0; i < count; i += 1) {
    const stage = makeStage(chapterSeed, i, { ...chapter, stage_count: count, code_prefix: chapter.code_prefix });
    stages.push(stage);
    state.stageOwners.set(stage.id, chapter.id);
  }
  state.stagesByChapter.set(chapter.id, stages);
  return stages;
}

function findStage(stageId) {
  ensureChapters();
  for (const group of state.groups) {
    for (const chapter of group.chapters) {
      const stages = chapterStages(chapter);
      const found = stages.find((stage) => stage.id === Number(stageId));
      if (found) return { stage: found, chapter };
    }
  }
  const stage = {
    id: Number(stageId),
    title: "未知关卡",
    code: "?-?",
    difficulty: 1000,
    recommend_level: 0,
    team_count: 12,
    species_count: 10,
    tags: ["普通"],
    order: 0,
  };
  return { stage, chapter: { id: "main-1", title: "第1章" } };
}

/* ------------------------------------------------------------------ */
/* 队伍摘要 / 详情                                                    */
/* ------------------------------------------------------------------ */
function makeTeamSummary(teamId, options = {}) {
  const rng = mulberry32(seedOf(`team:${teamId}`));
  const faction = options.faction || pick(rng, FACTIONS);
  const grayZone = options.gray_zone ?? false;
  const orphan = options.orphan ?? false;
  const units = randInt(rng, 4, 9);
  // 只有积分关卡/部分特殊队伍有标注效能（约 18%），其余为 0 = 未标注；偶发负值
  const knownRoll = rng();
  const powerKnown = options.power_known ?? knownRoll < 0.18;
  const power = powerKnown
    ? (rng() < 0.12 ? -randInt(rng, 100, 4200) : randInt(rng, 18000, 176000))
    : 0;
  const hpTotal = Math.round(randInt(rng, 9000, 150000) * (units / 6));
  const speciesCount = randInt(rng, 2, 8);
  const species = [];
  const usedCodex = new Set();
  if (options.codex_no) {
    species.push({ codex_no: options.codex_no, name: speciesName(options.codex_no), icon: mockIconUri(factionByCodex(options.codex_no), options.codex_no) });
    usedCodex.add(options.codex_no);
  }
  while (species.length < speciesCount) {
    const codex = randInt(rng, 1, 264);
    if (usedCodex.has(codex)) continue;
    usedCodex.add(codex);
    species.push({ codex_no: codex, name: speciesName(codex), icon: mockIconUri(factionByCodex(codex), codex) });
  }
  const members = [];
  const usedUnits = new Set();
  const memberCount = randInt(rng, 2, 6);
  while (members.length < memberCount) {
    const unit = pick(rng, UNIT_PAIRS);
    if (usedUnits.has(unit[0])) continue;
    usedUnits.add(unit[0]);
    members.push({
      code: unit[0],
      name: unit[1],
      number: randInt(rng, 1, 5),
      count: randInt(rng, 1, 4),
      icon: mockIconUri(faction, hash32(unit[0])),
    });
  }
  let stage = null;
  if (!grayZone && !orphan) {
    const stagePool = options.stagePool || defaultStagePool();
    if (stagePool.length) {
      const item = stagePool[hash32(`stage-of:${teamId}`) % stagePool.length];
      stage = {
        chapter_id: item.chapter_id,
        title: item.chapter_title,
        stage_title: item.title,
        code: item.code,
      };
    }
  }
  return {
    id: teamId,
    power,
    power_known: powerKnown,
    units,
    hp_total: hpTotal,
    faction,
    tags: options.tags || tagsFor(seedOf(`tags:${teamId}`)),
    species: species.slice(0, 8),
    members: members.slice(0, 6),
    gray_zone: grayZone,
    orphan,
    stage,
  };
}

let cachedStagePool = null;
function defaultStagePool() {
  if (cachedStagePool) return cachedStagePool;
  const groups = ensureChapters();
  const pool = [];
  groups.forEach((group) => {
    if (group.id === "grayzone" || group.id === "orphan") return;
    group.chapters.slice(0, 8).forEach((chapter) => {
      chapterStages(chapter).slice(0, 3).forEach((stage) => {
        pool.push({
          mission_id: stage.id,
          chapter_id: chapter.id,
          chapter_title: chapter.title,
          title: stage.title,
          code: stage.code,
          difficulty: stage.difficulty,
          gray_zone: false,
        });
      });
    });
  });
  cachedStagePool = pool;
  return pool;
}

/* 无固定关卡章节的队伍（服务端分页语义） */
const ORPHAN_TOTAL = 4381;
let orphanIdCache = null;

function orphanTeamIds() {
  if (orphanIdCache) return orphanIdCache;
  const ids = [];
  for (let i = 0; i < ORPHAN_TOTAL; i += 1) ids.push(5000000 + i * 3);
  orphanIdCache = ids;
  return ids;
}

function orphanTeamsPage(offset, limit, queryObj = {}) {
  const ids = orphanTeamIds();
  const query = typeof queryObj === "string" ? { q: queryObj } : queryObj || {};
  const q = String(query.q || "").trim().toLowerCase();
  const filterRequested = Boolean(q) || query.power_known || query.power_min || query.power_max || query.sort;
  if (filterRequested) {
    const teams = ids.map((teamId) => makeTeamSummary(teamId, { orphan: true, stagePool: [] }));
    const result = applyMockTeamQuery(teams, query);
    return { total: result.total, offset, limit, items: result.items.slice(offset, offset + limit) };
  }
  const slice = ids.slice(offset, offset + limit);
  return {
    total: ids.length,
    offset,
    limit,
    items: slice.map((teamId) => makeTeamSummary(teamId, { orphan: true, stagePool: [] })),
  };
}

function makeTeamDetail(teamId) {
  const summary = makeTeamSummary(teamId);
  const rng = mulberry32(seedOf(`detail:${teamId}`));
  const appearances = [];
  const pool = defaultStagePool();
  const count = randInt(rng, 3, 12);
  const used = new Set();
  while (appearances.length < count && appearances.length < pool.length) {
    const item = pool[randInt(rng, 0, pool.length - 1)];
    if (used.has(item.mission_id)) continue;
    used.add(item.mission_id);
    appearances.push({
      mission_id: item.mission_id,
      chapter_id: item.chapter_id,
      chapter_title: item.chapter_title,
      stage_title: item.title,
      code: item.code,
      difficulty: item.difficulty,
      gray_zone: false,
    });
  }
  const species = summary.species.map((item) => ({
    ...item,
    icon: item.icon || mockIconUri(item.faction || factionByCodex(item.codex_no), item.codex_no),
    faction: factionByCodex(item.codex_no),
    type: (item.codex_no % 3) + 1,
  }));
  const members = summary.members.map((member) => {
    const unitRng = mulberry32(seedOf(`unit:${teamId}:${member.code}`));
    const level = randInt(unitRng, 90, 150);
    const baseLife = randInt(unitRng, 600, 1800);
    const basePow = randInt(unitRng, 8, 40);
    const mult = 1 + (level - 90) * 0.021;
    const stats = {
      maxlife: Math.round(baseLife * mult),
      pow: Number((basePow * mult).toFixed(1)),
      hit: Number(randInt(unitRng, 300, 900) / 10),
      dodge: Number(randInt(unitRng, 0, 400) / 10),
      armor: Number(randInt(unitRng, 0, 600) / 10),
      armor_piercing: Number(randInt(unitRng, 0, 300) / 10),
      range: randInt(unitRng, 1, 6),
      speed: randInt(unitRng, 12, 60),
      shield: randInt(unitRng, 0, 600),
      def: randInt(unitRng, 0, 99999),
      crit: Number(randInt(unitRng, 0, 30) / 10),
      crit_dmg: Number(randInt(unitRng, 100, 180) / 10),
      tenacity: randInt(unitRng, 0, 30),
    };
    return {
      type_id: 11000 + (hash32(member.code) % 800),
      code: member.code,
      name: member.name,
      codex_no: summary.species[0]?.codex_no || 1,
      level,
      number: member.number,
      count: member.count,
      def_percent: randInt(unitRng, -30, 30),
      batch: randInt(unitRng, 0, 2),
      x: Number(randInt(unitRng, 0, 16) / 2),
      y: Number(randInt(unitRng, 0, 16) / 2),
      stats,
      base_stats: { ...stats, maxlife: baseLife, pow: basePow },
    };
  });
  return {
    id: summary.id,
    power: summary.power,
    power_known: summary.power_known,
    units: summary.units,
    hp_total: summary.hp_total,
    faction: summary.faction,
    tags: summary.tags,
    gray_zone: summary.gray_zone,
    orphan: summary.orphan,
    params: {
      effect_ext: summary.power,
      fight_type: randInt(rng, 0, 2),
      use_building: rng() > 0.5 ? "1" : "",
      batch_max: randInt(rng, 0, 4),
      gray_zone_missions: summary.gray_zone ? randInt(rng, 1, 6) : 0,
      mission_count: appearances.length,
      note: "数值按队伍等级缩放（单位实测口径）",
    },
    appearances,
    species,
    members,
  };
}

/* ------------------------------------------------------------------ */
/* 怪种                                                               */
/* ------------------------------------------------------------------ */
function ensureSpecies() {
  if (state.speciesList) return state.speciesList;
  const list = [];
  for (let codex = 1; codex <= 264; codex += 1) {
    const rng = mulberry32(seedOf(`species:${codex}`));
    const normalCount = randInt(rng, 0, 30);
    const grayCount = randInt(rng, 0, 9);
    const orphanCount = randInt(rng, 0, 5);
    let category = "normal";
    if (normalCount === 0 && grayCount > 0) category = "grayzone";
    else if (normalCount === 0 && grayCount === 0) category = "orphan";
    const tags = [];
    if (rng() > 0.55) tags.push("契约捕获");
    if (rng() > 0.82) tags.push("BOSS");
    if (rng() > 0.9) tags.push("精英");
    list.push({
      codex_no: codex,
      name: speciesName(codex),
      icon: mockIconUri(factionByCodex(codex), codex),
      faction: factionByCodex(codex),
      type: (codex % 3) + 1,
      team_count: normalCount + grayCount + orphanCount,
      gray_zone_team_count: grayCount,
      orphan_team_count: orphanCount,
      capturable: rng() > 0.1,
      tags,
      category,
    });
  }
  state.speciesList = list;
  return list;
}

function speciesDetail(codexNo, offset = 0, limit = 60, query = "", queryObj = {}) {
  const list = ensureSpecies();
  const species = list.find((item) => item.codex_no === Number(codexNo)) || list[0];
  const allIds = [];
  for (let i = 0; i < species.team_count; i += 1) {
    allIds.push(6100000 + Number(codexNo) * 131 + i * 17);
  }
  const allTeams = allIds.map((teamId, index) =>
    makeTeamSummary(teamId, {
      faction: species.faction,
      codex_no: species.codex_no,
      gray_zone: species.category === "grayzone",
      orphan: species.category === "orphan",
      tags: index === 0 ? ["BOSS", ...tagsFor(seedOf(`st:${codexNo}:${index}`))] : undefined,
    }),
  );
  const result = applyMockTeamQuery(allTeams, { ...queryObj, q: query || "" });
  return {
    species,
    total: result.total,
    teams_total: result.total,
    offset,
    limit,
    teams: result.items.slice(offset, offset + limit),
  };
}

/* ------------------------------------------------------------------ */
/* 通用队伍筛选/排序（与服务端 _apply_team_query 同口径）              */
/* ------------------------------------------------------------------ */
function mockTeamMatches(team, q) {
  if (!q) return true;
  const haystack = [
    String(team.id),
    String(team.power),
    String(team.faction),
    String(team.hp_total),
    String(team.units),
    ...(team.species || []).map((item) => `${item.codex_no} ${item.name}`),
    ...(team.members || []).map((item) => `${item.code} ${item.name}`),
    ...(team.tags || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

function applyMockTeamQuery(items, query = {}) {
  let list = items.slice();
  const q = String(query.q || "").trim().toLowerCase();
  if (q) list = list.filter((team) => mockTeamMatches(team, q));
  const knownRaw = String(query.power_known ?? "").trim().toLowerCase();
  const knownOnly = ["1", "true", "yes"].includes(knownRaw);
  const min = query.power_min !== undefined && query.power_min !== "" ? Number(query.power_min) : null;
  const max = query.power_max !== undefined && query.power_max !== "" ? Number(query.power_max) : null;
  if (knownOnly) list = list.filter((team) => team.power_known);
  if (min !== null && Number.isFinite(min)) {
    list = list.filter((team) => team.power_known && Number(team.power) >= min);
  }
  if (max !== null && Number.isFinite(max)) {
    list = list.filter((team) => team.power_known && Number(team.power) <= max);
  }
  const sort = String(query.sort || "default");
  const powerOf = (team) => (team.power_known ? Number(team.power) || 0 : null);
  if (sort === "power_desc") list.sort((a, b) => (powerOf(b) ?? -Infinity) - (powerOf(a) ?? -Infinity));
  else if (sort === "power_asc") list.sort((a, b) => (powerOf(a) ?? Infinity) - (powerOf(b) ?? Infinity));
  else if (sort === "hp_desc") list.sort((a, b) => (Number(b.hp_total) || 0) - (Number(a.hp_total) || 0));
  else if (sort === "units_desc") list.sort((a, b) => (Number(b.units) || 0) - (Number(a.units) || 0));
  return { total: list.length, items: list };
}

/* ------------------------------------------------------------------ */
/* 灰域队伍分页                                                       */
/* ------------------------------------------------------------------ */
function grayzoneTeams(areaId, offset, limit, query) {
  const areas = getAreas();
  const area = areas.find((item) => item.id === areaId) || areas[0];
  const total = area.team_count;
  const ids = [];
  const areaIndex = areas.indexOf(area);
  for (let i = 0; i < total; i += 1) {
    ids.push(7000000 + areaIndex * 100000 + i * 13);
  }
  const queryObj = typeof query === "string" ? { q: query } : query || {};
  const q = String(queryObj.q || "").trim().toLowerCase();
  const filterRequested = Boolean(q) || queryObj.power_known || queryObj.power_min || queryObj.power_max || queryObj.sort;
  let teams;
  if (filterRequested) {
    teams = ids.map((teamId) => makeTeamSummary(teamId, { gray_zone: true, stagePool: [] }));
    const result = applyMockTeamQuery(teams, queryObj);
    return { total: result.total, offset, items: result.items.slice(offset, offset + limit) };
  }
  const slice = ids.slice(offset, offset + limit);
  const items = slice.map((teamId) =>
    makeTeamSummary(teamId, {
      gray_zone: true,
      stagePool: [],
    }),
  );
  return { total: ids.length, offset, items };
}

/* ------------------------------------------------------------------ */
/* 当前靶机 / 凭证                                                    */
/* ------------------------------------------------------------------ */
function ensureCurrentTeamIds() {
  if (state.currentTeamIds) return state.currentTeamIds;
  const ids = [];
  for (let i = 0; i < 30; i += 1) ids.push(6549244 + i * 37);
  state.currentTeamIds = ids;
  return ids;
}

function currentTargets(name = "creds_latest.json") {
  const ids = ensureCurrentTeamIds();
  return {
    source: "creds",
    creds_file: name,
    uid: "100000001",
    base_url: "http://gfcn-game.avocado.games",
    captured_at: "2026-11-06T17:58:12+08:00",
    targets: ids.map((teamId, index) => ({ order: index + 1, team: teamId })),
    duplicate_orders: {},
    max_targets: 35,
    warnings: [],
  };
}

function credsList() {
  return [
    {
      name: "creds_latest.json",
      path: "dataMiner/derived/targetforge/creds_latest.json",
      updated_at: "2026-11-06T17:58:12+08:00",
      uid: "100000001",
      base_url: "http://gfcn-game.avocado.games",
      targets_count: 30,
    },
    {
      name: "creds_20261106_batch.json",
      path: "dataMiner/derived/targetforge/creds_20261106_batch.json",
      updated_at: "2026-11-06T16:32:08+08:00",
      uid: "100000001",
      base_url: "http://gfcn-game.avocado.games",
      targets_count: 35,
    },
    {
      name: "creds_20261105_batch.json",
      path: "dataMiner/derived/targetforge/creds_20261105_batch.json",
      updated_at: "2026-11-05T23:10:41+08:00",
      uid: "551203",
      base_url: "http://gfcn-game.avocado.games",
      targets_count: 12,
    },
  ];
}

/* ------------------------------------------------------------------ */
/* capture / player                                                   */
/* ------------------------------------------------------------------ */
function playerStatus() {
  const port = state.capture?.port || state.settings.capture_port || 18080;
  return {
    game_running: true,
    pid: 12345,
    game_window_title: "少女前线",
    system_proxy: state.capture?.proxy_active ? `127.0.0.1:${port}` : null,
    gflzirc_ok: true,
  };
}

function capturePort() {
  return state.capture?.port || state.settings.capture_port || 18080;
}

function captureStatus() {
  const port = capturePort();
  if (!state.capture) {
    return {
      state: "idle",
      port,
      proxy_active: false,
      system_proxy_on: false,
      auto_restore_proxy: true,
      uid: null,
      sign_set: false,
      base_url: "",
      targets_count: 0,
      login_captured: false,
      targets_captured: false,
      started_at: null,
      elapsed_s: 0,
      creds_path: null,
      logs: [
        { t: NOW, level: "info", text: `等待开始抓取 · 代理端口 ${port}` },
      ],
    };
  }
  const cap = state.capture;
  const elapsed = cap.started_at ? (Date.now() - cap.startedAt) / 1000 : 0;
  const logs = cap.logs.slice();
  const addr = `127.0.0.1:${port}`;
  const milestones = [
    [0.2, "info", `启动本地抓包代理 ${addr}`],
    [0.8, "info", `设置系统代理 -> ${addr}`],
    [1.4, "info", "等待游戏重新登录…"],
    [2.6, "warn", "检测到游戏进程已启动，等待 index/index 请求"],
    [4.0, "info", "捕获 index/index · 正在读取登录信息"],
    [5.2, "info", "已拿到 uid=100000001"],
    [6.4, "info", "已拿到 sign（有效期至本次登录结束）"],
    [7.6, "info", "读取 targettrain_collect_user_info…"],
    [8.8, "info", "已抓到当前收藏标靶 30 条"],
    [9.6, "info", "凭证已写入 creds_latest.json（等待「完成并关闭代理」落盘）"],
  ];
  milestones.forEach(([at, level, text]) => {
    if (elapsed >= at && !logs.some((line) => line.text === text)) {
      logs.push({ t: new Date(cap.startedAt + at * 1000).toISOString(), level, text });
    }
  });
  const done = elapsed >= 9.6;
  return {
    state: cap.state,
    port,
    proxy_active: cap.state === "running",
    system_proxy_on: cap.state === "running",
    auto_restore_proxy: true,
    uid: elapsed >= 5.2 ? "100000001" : null,
    sign_set: elapsed >= 6.4,
    base_url: elapsed >= 5.2 ? "http://gfcn-game.avocado.games" : "",
    targets_count: elapsed >= 8.8 ? 30 : 0,
    login_captured: elapsed >= 5.2,
    targets_captured: elapsed >= 8.8,
    started_at: cap.startedAtIso,
    elapsed_s: Number(elapsed.toFixed(1)),
    creds_path: done ? "dataMiner/derived/targetforge/creds_latest.json" : null,
    logs: logs.slice(-120),
  };
}

/* ------------------------------------------------------------------ */
/* 序列                                                               */
/* ------------------------------------------------------------------ */
function sequencePayload() {
  const draft = state.sequence.map((teamId) => makeTeamSummary(teamId));
  return {
    draft,
    count: draft.length,
    max: 35,
    missing: [],
    updated_at: NOW,
  };
}

function sequenceAction(body) {
  const action = String(body.action || "");
  if (action === "add" || action === "add_many") {
    let ids = body.team_ids;
    if (!ids && body.team_id !== undefined) ids = [body.team_id];
    ids = (ids || []).map(Number).filter((id) => Number.isFinite(id));
    ids.forEach((teamId) => {
      if (state.sequence.includes(teamId)) return;
      if (state.sequence.length >= 35) return;
      const position = Number(body.position);
      if (Number.isInteger(position) && position >= 0 && position <= state.sequence.length) {
        state.sequence.splice(position, 0, teamId);
      } else {
        state.sequence.push(teamId);
      }
    });
  } else if (action === "remove") {
    state.sequence = state.sequence.filter((id) => id !== Number(body.team_id));
  } else if (action === "move") {
    const from = Number(body.from);
    const to = Number(body.to);
    if (from >= 0 && from < state.sequence.length && to >= 0 && to < state.sequence.length) {
      const [item] = state.sequence.splice(from, 1);
      state.sequence.splice(to, 0, item);
    }
  } else if (action === "set") {
    const ids = (body.team_ids || []).map(Number).filter((id) => Number.isFinite(id));
    state.sequence = ids.slice(0, 35);
  } else if (action === "clear") {
    state.sequence = [];
  } else if (action === "import_current") {
    state.sequence = currentTargets().targets.map((item) => item.team).slice(0, 35);
  }
  saveMockSequence();
  return sequencePayload();
}

/* ------------------------------------------------------------------ */
/* 执行计划 / job                                                     */
/* ------------------------------------------------------------------ */
function buildPlan(mode, draftIds, current) {
  const currentTargetsList = current.targets || [];
  const currentOrders = new Map(currentTargetsList.map((item) => [item.order, item.team]));
  const currentTeams = new Set(currentTargetsList.map((item) => item.team));
  const maxOrder = currentTargetsList.reduce((acc, item) => Math.max(acc, item.order), 0);
  const deletes = [];
  const adds = [];
  const kept = [];
  const final = [];
  const warnings = [];
  if (mode === "append") {
    currentTargetsList.forEach((item) => {
      kept.push({ order: item.order, team: item.team });
      final.push({ order: item.order, team: item.team });
    });
    let order = maxOrder;
    draftIds.forEach((teamId) => {
      if (currentTeams.has(teamId)) {
        warnings.push(`队伍 ${teamId} 已存在，追加模式自动跳过`);
        return;
      }
      order += 1;
      adds.push({ order, team: teamId });
      final.push({ order, team: teamId });
    });
  } else if (mode === "replace") {
    const draftLen = draftIds.length;
    draftIds.forEach((teamId, index) => {
      const order = index + 1;
      if (currentOrders.has(order)) {
        const oldTeam = currentOrders.get(order);
        if (oldTeam !== teamId) deletes.push({ order, team: oldTeam });
      }
      adds.push({ order, team: teamId });
    });
    currentTargetsList.forEach((item) => {
      if (item.order > draftLen) {
        kept.push({ order: item.order, team: item.team });
      }
    });
    if (draftLen > maxOrder) {
      warnings.push(`序列比当前 ${maxOrder} 个靶机更长，多出的 ${draftLen - maxOrder} 个将追加到末尾`);
    }
    deletes.forEach((del) => {
      if (currentTeams.has(del.team) && !adds.some((add) => add.team === del.team)) {
        warnings.push(`队伍 ${del.team} 在其它编号已存在，先删除旧项再放到目标编号`);
      }
    });
    const finalMap = new Map();
    currentTargetsList.forEach((item) => finalMap.set(item.order, item.team));
    adds.forEach((item) => finalMap.set(item.order, item.team));
    [...finalMap.entries()].sort((a, b) => a[0] - b[0]).forEach(([order, team]) => final.push({ order, team }));
  } else if (mode === "rebuild") {
    currentTargetsList.forEach((item) => deletes.push({ order: item.order, team: item.team }));
    draftIds.slice(0, 35).forEach((teamId, index) => {
      adds.push({ order: index + 1, team: teamId });
      final.push({ order: index + 1, team: teamId });
    });
  } else if (mode === "clear") {
    currentTargetsList.forEach((item) => deletes.push({ order: item.order, team: item.team }));
  }
  if (mode !== "clear" && !draftIds.length) warnings.push("序列是空的");
  if (draftIds.length > 35) warnings.push("序列超过 35 上限，已截断");
  const seen = new Set();
  draftIds.forEach((teamId) => {
    if (seen.has(teamId)) warnings.push(`序列中存在重复队伍 ${teamId}`);
    seen.add(teamId);
  });
  return {
    mode,
    deletes,
    adds,
    kept,
    skipped: [],
    final,
    warnings,
    valid: warnings.length === 0 || (mode !== "clear" && draftIds.length > 0 && draftIds.length <= 35),
    current: {
      duplicate_orders: {},
      warnings: [],
    },
  };
}

function previewPlan(body) {
  const mode = String(body.mode || "append");
  const draftIds = state.sequence.slice();
  const current = currentTargets();
  const plan = buildPlan(mode, draftIds, current);
  plan.mode = mode;
  plan.current = {
    ...current,
    source: "creds",
  };
  plan.draft = draftIds.map((teamId) => makeTeamSummary(teamId));
  return plan;
}

const JOB_SCRIPT = {
  append: [
    [0.1, "info", "读取登录凭证 creds_latest.json（uid=100000001）"],
    [0.4, "info", "读取当前收藏标靶 30 条"],
    [0.8, "info", "追加模式：跳过已存在队伍，编号从 31 继续"],
    [1.3, "info", "发送 Targettrain/addCollect × 3"],
    [2.0, "info", "addCollect order=31 team=6549244 成功"],
    [2.6, "info", "addCollect order=32 team=6549281 成功"],
    [3.2, "info", "addCollect order=33 team=6549318 成功"],
    [3.9, "info", "本地状态已更新 dataMiner/derived/target_injection_state.json"],
    [4.4, "done", "执行完成：删除 0 · 新增 3 · 失败 0"],
  ],
  replace: [
    [0.1, "info", "读取登录凭证 creds_latest.json（uid=100000001）"],
    [0.4, "info", "读取当前收藏标靶 30 条"],
    [0.8, "info", "按序号替换：草稿 3 个 → 目标编号 1..3"],
    [1.2, "info", "发送 Targettrain/delCollect × 3（先删旧项）"],
    [1.9, "info", "发送 Targettrain/addCollect × 3"],
    [2.7, "info", "替换 order=1 team=6549244 成功"],
    [3.3, "info", "替换 order=2 team=6549281 成功"],
    [3.9, "info", "替换 order=3 team=6549318 成功"],
    [4.4, "done", "执行完成：删除 3 · 新增 3 · 失败 0"],
  ],
  rebuild: [
    [0.1, "info", "读取登录凭证 creds_latest.json（uid=100000001）"],
    [0.4, "warn", "清空重排：即将删除当前全部 30 条靶机"],
    [0.9, "info", "发送 Targettrain/delCollect × 30（按 order 倒序）"],
    [1.8, "info", "delCollect 30/30 完成"],
    [2.3, "info", "按草稿顺序全量填充 1..3"],
    [3.1, "info", "addCollect order=1 team=6549244 成功"],
    [3.7, "info", "addCollect order=2 team=6549281 成功"],
    [4.3, "info", "addCollect order=3 team=6549318 成功"],
    [4.8, "done", "执行完成：删除 30 · 新增 3 · 失败 0"],
  ],
  clear: [
    [0.1, "info", "读取登录凭证 creds_latest.json（uid=100000001）"],
    [0.5, "warn", "危险操作：清空当前全部收藏标靶"],
    [1.0, "info", "发送 Targettrain/delCollect × 30（按 order 倒序）"],
    [2.1, "info", "delCollect 30/30 完成"],
    [2.6, "done", "清空完成：删除 30 · 新增 0 · 失败 0"],
  ],
};

function createJob(mode, dryRun) {
  const jobId = `mock${Date.now().toString(16)}`;
  const plan = buildPlan(mode, state.sequence.slice(), currentTargets());
  const job = {
    id: jobId,
    kind: "execute",
    mode,
    dryRun,
    createdAt: Date.now(),
    logs: [],
    state: "running",
    plan,
    result: null,
    error: null,
  };
  state.jobs.set(jobId, job);
  return jobId;
}

function jobPayload(jobId) {
  const job = state.jobs.get(jobId);
  if (!job) {
    return {
      id: jobId,
      kind: "execute",
      state: "error",
      created_at: NOW,
      finished_at: NOW,
      logs: [{ t: NOW, level: "error", text: "job 不存在（mock）" }],
      result: null,
      error: "job 不存在",
    };
  }
  const elapsed = (Date.now() - job.createdAt) / 1000;
  const script = JOB_SCRIPT[job.mode || "append"] || JOB_SCRIPT.append;
  const total = job.dryRun ? 2.2 : 4.8;
  script.forEach(([at, level, text]) => {
    const realAt = job.dryRun ? at * 0.42 : at;
    if (elapsed >= realAt && !job.logs.some((line) => line.text === text)) {
      job.logs.push({ t: new Date(job.createdAt + realAt * 1000).toISOString(), level, text });
    }
  });
  if (job.dryRun && elapsed > 0.3) {
    const text = "演练模式：只生成计划，不发送任何请求";
    if (!job.logs.some((line) => line.text === text)) {
      job.logs.push({ t: new Date(job.createdAt + 250).toISOString(), level: "warn", text });
    }
  }
  if (elapsed >= total) {
    job.state = "done";
    if (!job.result) {
      const plan = job.plan;
      job.result = {
        plan,
        execution: {
          ok: true,
          mode: job.mode,
          dry_run: job.dryRun,
          deleted: job.dryRun ? 0 : plan.deletes.length,
          added: job.dryRun ? 0 : plan.adds.length,
          failed: [],
          final: plan.final,
          creds_file: "dataMiner/derived/targetforge/creds_latest.json",
          restart_required: !job.dryRun,
        },
      };
      job.logs.push({
        t: new Date(job.createdAt + total * 1000).toISOString(),
        level: "done",
        text: job.dryRun ? "演练结束：未做任何修改" : "执行完成 · 请大退重登游戏同步",
      });
    }
    if (!job.dryRun) {
      // 同步刷新当前靶机
      ensureCurrentTeamIds();
      state.currentTeamIds = job.plan.final.slice(0, 35).map((item) => item.team);
      if (state.currentTeamIds.length < 30) state.currentTeamIds = ensureCurrentTeamIds();
    }
  }
  return {
    id: job.id,
    kind: job.kind,
    state: job.state,
    created_at: new Date(job.createdAt).toISOString(),
    finished_at: job.state === "done" ? new Date(job.createdAt + total * 1000).toISOString() : null,
    logs: job.logs,
    result: job.result,
    error: job.error,
  };
}

/* ------------------------------------------------------------------ */
/* 路由分发                                                           */
/* ------------------------------------------------------------------ */
function ok(payload) {
  return payload;
}

export async function mockRequest(method, path, body = {}) {
  await sleep(70 + Math.floor(Math.random() * 80));
  const url = new URL(path, "http://mock.local");
  const route = url.pathname;
  const query = Object.fromEntries(url.searchParams.entries());

  if (route === "/api/health") {
    ensureChapters();
    return ok({
      ok: true,
      app: "TargetForge",
      version: VERSION,
      now: new Date().toISOString(),
      catalog: {
        state: "ready",
        built_at: BUILT_AT,
        counts: counts(),
        elapsed_s: 23.4,
        error: null,
        detail: "",
      },
      gflzirc_ok: true,
      game: playerStatus(),
      data_dir: "dataMiner/derived/targetforge",
    });
  }
  if (route === "/api/meta") {
    return ok({ version: VERSION, built_at: BUILT_AT, counts: counts(), max_targets: 35, now: new Date().toISOString() });
  }
  if (route === "/api/chapters") {
    const groups = ensureChapters().map((group) => ({
      id: group.id,
      title: group.title,
      chapters: group.chapters.map(stripChapter),
    }));
    return ok({ built_at: BUILT_AT, counts: counts(), groups });
  }
  let match = route.match(/^\/api\/chapters\/([^/]+)$/);
  if (match) {
    const chapterId = decodeURIComponent(match[1]);
    const chapter = state.chaptersById.get(chapterId);
    if (!chapter) throw makeError(404, `没有章节 ${chapterId}`);
    if (chapter.category === "grayzone") {
      return ok({ chapter: stripChapter(chapter), stages: [], areas: getAreas() });
    }
    if (chapter.category === "orphan") {
      const offset = Number(query.offset || 0);
      const limit = Number(query.limit || 60);
      const page = orphanTeamsPage(offset, limit, query);
      return ok({
        chapter: stripChapter(chapter),
        stages: [],
        teams: page.items,
        teams_total: page.total,
        offset,
        limit,
      });
    }
    const stages = chapterStages(chapter);
    return ok({ chapter: stripChapter(chapter), stages });
  }
  match = route.match(/^\/api\/stages\/(\d+)$/);
  if (match) {
    const stageId = Number(match[1]);
    const { stage, chapter } = findStage(stageId);
    const teams = [];
    const rng = mulberry32(hash32(`stage-teams:${stageId}`));
    const teamCount = randInt(rng, 5, 12);
    for (let i = 0; i < teamCount; i += 1) {
      teams.push(
        makeTeamSummary(9000000 + stageId * 17 + i * 131, {
          stagePool: [
            {
              mission_id: stage.id,
              chapter_id: chapter.id,
              chapter_title: chapter.title,
              title: stage.title,
              code: stage.code,
            },
          ],
        }),
      );
    }
    return ok({ stage: { ...stage, chapter_title: chapter.title }, teams });
  }
  match = route.match(/^\/api\/teams\/(\d+)$/);
  if (match) {
    return ok(makeTeamDetail(Number(match[1])));
  }
  if (route === "/api/grayzone/areas") {
    return ok({ areas: getAreas() });
  }
  if (route === "/api/grayzone/teams") {
    return ok(grayzoneTeams(query.area || "", Number(query.offset || 0), Number(query.limit || 60), query));
  }
  if (route === "/api/species") {
    const list = ensureSpecies();
    let filtered = list;
    const q = (query.q || "").trim().toLowerCase();
    if (q) {
      filtered = filtered.filter(
        (item) => item.name.toLowerCase().includes(q) || String(item.codex_no).includes(q),
      );
    }
    if (query.faction) filtered = filtered.filter((item) => item.faction === query.faction);
    if (query.category && query.category !== "all") {
      filtered = filtered.filter((item) => item.category === query.category);
    }
    const offset = Number(query.offset || 0);
    const limit = Number(query.limit || 60);
    return ok({ total: filtered.length, items: filtered.slice(offset, offset + limit) });
  }
  match = route.match(/^\/api\/species\/(\d+)$/);
  if (match) {
    return ok(
      speciesDetail(
        Number(match[1]),
        Number(query.offset || 0),
        Number(query.limit || 60),
        query.q || "",
        query,
      ),
    );
  }
  if (route === "/api/search") {
    const q = (query.q || "").trim();
    if (!q) return ok({ teams: [], stages: [], species: [] });
    const speciesMatches = ensureSpecies()
      .filter((item) => item.name.includes(q) || String(item.codex_no) === q)
      .slice(0, 6);
    const stageMatches = [];
    const pool = defaultStagePool();
    pool.forEach((item) => {
      if (stageMatches.length >= 6) return;
      if (item.title.includes(q) || String(item.mission_id).includes(q) || item.code.includes(q)) {
        stageMatches.push({
          id: item.mission_id,
          title: item.title,
          code: item.code,
          chapter_title: item.chapter_title,
        });
      }
    });
    const teamMatches = [];
    const currentIds = ensureCurrentTeamIds();
    currentIds.forEach((teamId) => {
      if (teamMatches.length >= 6) return;
      if (String(teamId).includes(q)) teamMatches.push(makeTeamSummary(teamId));
    });
    return ok({ teams: teamMatches, stages: stageMatches, species: speciesMatches });
  }
  if (route === "/api/current") {
    return ok(currentTargets(state.currentCreds));
  }
  if (route === "/api/creds") {
    return ok({ creds: credsList() });
  }
  if (route === "/api/creds/load") {
    state.currentCreds = body.name || "creds_latest.json";
    return ok({ ok: true, current: currentTargets(state.currentCreds) });
  }
  if (route === "/api/player") {
    return ok(playerStatus());
  }
  if (route === "/api/sequence") {
    if (method === "POST") return ok(sequenceAction(body));
    return ok(sequencePayload());
  }
  if (route === "/api/execute/preview") {
    return ok(previewPlan(body));
  }
  if (route === "/api/execute") {
    const jobId = createJob(String(body.mode || "append"), Boolean(body.dry_run));
    return ok({ job_id: jobId, plan: previewPlan(body) });
  }
  match = route.match(/^\/api\/jobs\/([0-9a-z]+)$/);
  if (match) {
    return ok(jobPayload(match[1]));
  }
  match = route.match(/^\/api\/jobs\/([0-9a-z]+)\/cancel$/);
  if (match) {
    jobPayload(match[1]);
    return ok({ job_id: match[1], cancel_requested: true });
  }
  if (route === "/api/capture/status") {
    return ok(captureStatus());
  }
  if (route === "/api/capture/start") {
    const port = Number(body.port) >= 1024 && Number(body.port) <= 65535
      ? Number(body.port)
      : state.settings.capture_port || 18080;
    if (!state.capture || state.capture.state !== "running") {
      state.capture = {
        state: "running",
        port,
        startedAt: Date.now(),
        startedAtIso: new Date().toISOString(),
        logs: [],
      };
    }
    return ok(captureStatus());
  }
  if (route === "/api/capture/stop") {
    if (state.capture) state.capture.state = "stopped";
    const status = captureStatus();
    return ok({ ...status, ok: true, hint: "代理已关闭，系统代理已恢复；凭证已写入 creds_latest.json" });
  }
  if (route === "/api/capture/restart_game") {
    const port = capturePort();
    return ok({
      ok: true,
      steps: [`设置系统代理 127.0.0.1:${port}`, "强杀游戏进程", "重新启动游戏"],
      hint: "游戏已重启，请在游戏内重新登录到主界面，等待抓取到 uid/sign。",
    });
  }
  if (route === "/api/game/restart") {
    return ok({ ok: true, restarted: true, game_running: true, hint: "游戏已重启，请重新登录并进入主界面。" });
  }
  if (route === "/api/system/proxy") {
    const port = capturePort();
    return ok({ ok: true, system_proxy: body.enable ? `127.0.0.1:${port}` : null });
  }
  if (route === "/api/settings") {
    if (method === "POST") {
      Object.assign(state.settings, body);
      const port = Number(state.settings.capture_port);
      if (!(Number.isInteger(port) && port >= 1024 && port <= 65535)) {
        state.settings.capture_port = 18080;
      }
      return ok({ ...state.settings });
    }
    return ok({ ...state.settings });
  }
  if (route === "/api/tutorial") {
    if (method === "POST") {
      if (Array.isArray(body.completed)) state.tutorial.completed = body.completed.map(String);
      if (body.dismissed !== undefined) state.tutorial.dismissed = Boolean(body.dismissed);
      saveMockTutorial();
      return ok({ ...state.tutorial });
    }
    return ok({ ...state.tutorial });
  }
  if (route === "/api/settings") {
    if (method === "POST") {
      Object.assign(state.settings, body);
      return ok({ ...state.settings });
    }
    return ok({ ...state.settings });
  }
  if (route === "/api/catalog/refresh") {
    const jobId = `mockcat${Date.now().toString(16)}`;
    state.jobs.set(jobId, {
      id: jobId,
      kind: "catalog-refresh",
      mode: "append",
      dryRun: true,
      createdAt: Date.now(),
      logs: [
        { t: new Date().toISOString(), level: "info", text: "开始重建 catalog（mock 不实际执行）" },
        { t: new Date().toISOString(), level: "done", text: "mock 模式：catalog 数据固定，无需重建" },
      ],
      state: "done",
      plan: null,
      result: { counts: counts() },
      error: null,
    });
    return ok({ job_id: jobId });
  }
  throw makeError(404, `mock 未实现：${method} ${route}`);
}

function stripChapter(chapter) {
  const copy = { ...chapter };
  delete copy.code_prefix;
  return copy;
}

function counts() {
  return {
    chapters: ensureChapters().reduce((acc, group) => acc + group.chapters.length, 0),
    stages: 2345,
    teams: 13700,
    species: 264,
    missions: 2512,
  };
}

function makeError(status, message) {
  const error = new Error(message);
  error.status = status;
  error.payload = { error: message };
  return error;
}
