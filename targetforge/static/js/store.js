/* store.js —— 全局状态 / 数据获取 / 事件总线 */
import { api, toApiError } from "./api.js";
import { createEmitter } from "./util.js";

const emitter = createEmitter();

const state = {
  health: null,
  meta: null,
  chapters: null, // /api/chapters 结果缓存
  sequence: null,
  current: null,
  tutorial: null,
  settings: null,
  seqOpen: true,
  healthTimer: 0,
  currentFetched: false,
  cleanupFns: [],
};

export const store = {
  get health() { return state.health; },
  get meta() { return state.meta; },
  get chapters() { return state.chapters; },
  get sequence() { return state.sequence; },
  get current() { return state.current; },
  get tutorial() { return state.tutorial; },
  get settings() { return state.settings; },
  get seqOpen() { return state.seqOpen; },
  get currentFetched() { return state.currentFetched; },

  on(event, fn) {
    return emitter.on(event, fn);
  },
  emit(event, payload) {
    emitter.emit(event, payload);
  },

  setSequence(sequence) {
    state.sequence = sequence;
    emitter.emit("sequence", sequence);
    if (sequence) {
      const badge = document.querySelector("[data-seq-count]");
      if (badge) badge.textContent = sequence.count;
    }
    return sequence;
  },

  setHealth(health) {
    state.health = health;
    emitter.emit("health", health);
    return health;
  },

  setCurrent(current) {
    state.current = current;
    emitter.emit("current", current);
    return current;
  },

  registerCleanup(fn) {
    state.cleanupFns.push(fn);
  },
  runCleanups() {
    state.cleanupFns.forEach((fn) => {
      try {
        fn();
      } catch (err) {
        console.error("[cleanup]", err);
      }
    });
    state.cleanupFns = [];
    if (state.healthTimer) {
      clearInterval(state.healthTimer);
      state.healthTimer = 0;
    }
  },
  setSeqOpen(open) {
    state.seqOpen = open;
    emitter.emit("seq-open", open);
  },
  toggleSeq() {
    this.setSeqOpen(!state.seqOpen);
  },
};

/* ------------------------------------------------------------------ */
/* 数据加载                                                           */
/* ------------------------------------------------------------------ */
export async function refreshHealth() {
  const health = await api.health();
  return store.setHealth(health);
}

export async function refreshMeta() {
  if (state.meta) return state.meta;
  try {
    state.meta = await api.meta();
  } catch (err) {
    if (err.status !== 503) throw err;
    state.meta = null;
  }
  return state.meta;
}

export async function loadChapters(force = false) {
  if (state.chapters && !force) return state.chapters;
  state.chapters = await api.chapters();
  emitter.emit("chapters", state.chapters);
  return state.chapters;
}

let sequenceInflight = null;

/** 取序列（并发去重：boot 与右侧序列面板同时初始化时只发一次请求） */
export async function refreshSequence() {
  if (sequenceInflight) return sequenceInflight;
  sequenceInflight = api
    .sequence()
    .then((sequence) => store.setSequence(sequence))
    .finally(() => {
      sequenceInflight = null;
    });
  return sequenceInflight;
}

export async function refreshCurrent(source = "auto") {
  const current = await api.current(source);
  return store.setCurrent(current);
}

export async function loadTutorial() {
  state.tutorial = await api.tutorial();
  return state.tutorial;
}

export async function saveTutorial(patch) {
  state.tutorial = await api.saveTutorial(patch);
  return state.tutorial;
}

export async function loadSettings() {
  state.settings = await api.settings();
  return state.settings;
}

/* ------------------------------------------------------------------ */
/* 序列操作                                                           */
/* ------------------------------------------------------------------ */
export async function sequenceAction(body) {
  const sequence = await api.sequenceAction(body);
  return store.setSequence(sequence);
}

export async function addTeams(teamIds) {
  const ids = (Array.isArray(teamIds) ? teamIds : [teamIds]).map(Number).filter(Number.isFinite);
  if (!ids.length) return store.sequence;
  return sequenceAction({ action: "add_many", team_ids: ids });
}

export async function addTeam(teamId) {
  return addTeams([teamId]);
}

export async function removeTeam(teamId) {
  return sequenceAction({ action: "remove", team_id: Number(teamId) });
}

export async function moveTeam(from, to) {
  return sequenceAction({ action: "move", from, to });
}

export async function clearSequence() {
  return sequenceAction({ action: "clear" });
}

export async function importCurrentSequence() {
  return sequenceAction({ action: "import_current" });
}

export function sequenceStats(sequence = state.sequence) {
  if (!sequence) return { count: 0, max: 35, power: 0, hp: 0, units: 0, powerKnown: 0, powerUnknown: 0 };
  const draft = sequence.draft || [];
  let power = 0;
  let powerKnown = 0;
  let powerUnknown = 0;
  draft.forEach((team) => {
    const num = Number(team.power);
    const known = typeof team.power_known === "boolean" ? team.power_known : Number.isFinite(num) && num !== 0;
    if (known) {
      power += Number.isFinite(num) ? num : 0;
      powerKnown += 1;
    } else {
      powerUnknown += 1;
    }
  });
  return {
    count: draft.length,
    max: sequence.max || 35,
    power,
    hp: draft.reduce((acc, team) => acc + (Number(team.hp_total) || 0), 0),
    units: draft.reduce((acc, team) => acc + (Number(team.units) || 0), 0),
    powerKnown,
    powerUnknown,
  };
}

export function isTeamInSequence(teamId, sequence = state.sequence) {
  if (!sequence) return false;
  return (sequence.draft || []).some((team) => Number(team.id) === Number(teamId));
}

/* ------------------------------------------------------------------ */
/* 健康状态轮询（顶栏）                                               */
/* ------------------------------------------------------------------ */
export function startHealthPolling(intervalMs = 15000) {
  if (state.healthTimer) clearInterval(state.healthTimer);
  state.healthTimer = setInterval(async () => {
    try {
      await refreshHealth();
    } catch {
      /* 忽略轮询失败 */
    }
  }, intervalMs);
}

/** 读一次当前靶机：失败不抛出（未抓取时接口可能 503/Missing） */
export async function tryRefreshCurrent() {
  try {
    return await refreshCurrent("auto");
  } catch (err) {
    if (err.status === 503) return null;
    if (err.status >= 400 && err.status < 500) return null;
    return null;
  } finally {
    state.currentFetched = true;
  }
}

/** 基础数据是否都已有过一次加载（用于避免页面自己重复请求） */
export function hasBaseData() {
  return Boolean(state.health && state.sequence && state.chapters && state.currentFetched);
}

export function handleError(err) {
  return toApiError(err);
}
