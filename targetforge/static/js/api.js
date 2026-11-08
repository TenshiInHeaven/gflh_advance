/* api.js —— 后端 API 客户端（同源 fetch；?mock=1 时走本地 mock 层） */
import { mockRequest } from "./mock.js";
import { currentToken } from "./auth.js";

export const IS_MOCK = new URLSearchParams(window.location.search).get("mock") === "1";
const MOCK_LATENCY_MIN = 0;

export class ApiError extends Error {
  constructor(status, payload, fallbackMessage) {
    const message = (payload && (payload.error || payload.message)) || fallbackMessage || `HTTP ${status}`;
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload || {};
    this.detail = payload?.detail || "";
    this.hint = payload?.hint || "";
  }
}

/* 抓包端口是运行时设置（默认 18080，可在登录抓取页修改，持久化到 /api/settings） */
const runtime = { capturePort: 18080, capturePortLoaded: false };

export function setCapturePort(port) {
  const value = Number(port);
  if (Number.isInteger(value) && value >= 1024 && value <= 65535) {
    runtime.capturePort = value;
    return value;
  }
  return runtime.capturePort;
}

export function getCapturePort() {
  return runtime.capturePort;
}

export function markCapturePortLoaded() {
  runtime.capturePortLoaded = true;
}

export function isCapturePortLoaded() {
  return runtime.capturePortLoaded;
}

function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request(method, path, body) {
  if (IS_MOCK) {
    await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MIN));
    try {
      return await mockRequest(method, path, body || {});
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError(err.status || 500, err.payload || { error: err.message }, err.message);
    }
  }
  const token = currentToken();
  const options = {
    method,
    cache: "no-store",
    headers: { Accept: "application/json", "X-TargetForge-Client": "1" },
  };
  if (token) options.headers["X-TargetForge-Token"] = token;
  if (method !== "GET" && body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new ApiError(0, { error: "无法连接本地服务", hint: "确认 python -m targetforge 正在运行，然后刷新页面。" }, String(err));
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: `服务返回了非 JSON 内容（HTTP ${response.status}）`, detail: text.slice(0, 400) };
    }
  }
  if (!response.ok) {
    const err = new ApiError(response.status, payload, `HTTP ${response.status}`);
    if (response.status === 401) {
      try {
        window.dispatchEvent(new CustomEvent("tf:unauthorized"));
      } catch {
        // ignore
      }
    }
    throw err;
  }
  return payload;
}

function get(path, params) {
  return request("GET", path + buildQuery(params));
}

function post(path, body) {
  return request("POST", path, body === undefined ? {} : body);
}

export const api = {
  mock: IS_MOCK,

  health: () => get("/api/health"),
  meta: () => get("/api/meta"),

  chapters: () => get("/api/chapters"),
  chapter: (chapterId, params = {}) =>
    get(`/api/chapters/${encodeURIComponent(chapterId)}`, { offset: 0, limit: 60, q: "", ...params }),
  stage: (missionId) => get(`/api/stages/${encodeURIComponent(missionId)}`),
  team: (teamId) => get(`/api/teams/${encodeURIComponent(teamId)}`),
  teams: (params = {}) =>
    get("/api/teams", {
      q: "",
      chapter: "",
      species: "",
      role: "",
      collectable: "",
      power_known: "",
      power_min: "",
      power_max: "",
      units_min: "",
      units_max: "",
      sort: "id_asc",
      offset: 0,
      limit: 50,
      ...params,
    }),

  grayzoneAreas: () => get("/api/grayzone/areas"),
  grayzoneNodes: (params = {}) =>
    get("/api/grayzone/nodes", {
      region: "",
      offset: 0,
      limit: 30,
      q: "",
      sort: "id_asc",
      ...params,
    }),
  grayzoneTeams: (params = {}) =>
    get("/api/grayzone/teams", { area: "", offset: 0, limit: 60, q: "", ...params }),

  species: ({ q = "", faction = "", category = "all", offset = 0, limit = 60 } = {}) =>
    get("/api/species", { q, faction, category, offset, limit }),
  speciesDetail: (codexNo, params = {}) =>
    get(`/api/species/${encodeURIComponent(codexNo)}`, { offset: 0, limit: 60, q: "", ...params }),
  search: (q, limit = 20) => get("/api/search", { q, limit }),

  current: (source = "auto") => get("/api/current", { source }),
  creds: () => get("/api/creds"),
  loadCreds: (name) => post("/api/creds/load", { name }),
  player: () => get("/api/player"),

  sequence: () => get("/api/sequence"),
  sequenceAction: (body) => post("/api/sequence", body),

  preview: (body) => post("/api/execute/preview", body),
  execute: (body) => post("/api/execute", body),
  job: (jobId) => get(`/api/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId) => post(`/api/jobs/${encodeURIComponent(jobId)}/cancel`),

  captureStatus: () => get("/api/capture/status"),
  captureRegions: () => get("/api/capture/regions"),
  captureCa: () => get("/api/capture/ca"),
  targetHistory: () => get("/api/target-history"),
  saveTargetHistory: (body = {}) => post("/api/target-history", { action: "save", ...body }),
  deleteTargetHistory: (name) => post("/api/target-history", { action: "delete", name }),
  appendTargetHistory: (name) => post("/api/target-history", { action: "append", name }),
  emulatorDetect: () => get("/api/emulator/detect"),
  emulatorSetup: (body = {}) => post("/api/emulator/setup", body),
  captureStart: (body = {}) =>
    post("/api/capture/start", {
      port: runtime.capturePort,
      set_proxy: true,
      auto_restore_proxy: true,
      ...body,
    }),
  captureStop: () => post("/api/capture/stop", {}),
  captureRestartGame: () => post("/api/capture/restart_game", {}),
  restartGame: (body = { wait_ready: true }) => post("/api/game/restart", body),

  tutorial: () => get("/api/tutorial"),
  saveTutorial: (body) => post("/api/tutorial", body),
  settings: () => get("/api/settings"),
  saveSettings: (body) => post("/api/settings", body),

  catalogRefresh: () => post("/api/catalog/refresh", {}),
  gameStatus: () => get("/api/game/status"),
  gameDetect: () => post("/api/game/detect", {}),
  gamePick: () => post("/api/game/pick", {}),
  gameConfirm: (path) => post("/api/game/confirm", { path }),

  setSystemProxy: (enable, addr = `127.0.0.1:${runtime.capturePort}`) =>
    post("/api/system/proxy", { enable, addr }),
};

/** 把任意异常转成 ApiError */
export function toApiError(err) {
  if (err instanceof ApiError) return err;
  const apiError = new ApiError(0, { error: err?.message || String(err) });
  return apiError;
}
