/* util.js —— 无依赖工具函数 */

/** HTML 转义 */
export function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** 数字千分位；无效值返回占位符 */
export function fmtNum(n, fallback = "—") {
  if (n === null || n === undefined || n === "" || Number.isNaN(Number(n))) return fallback;
  const num = Number(n);
  if (!Number.isFinite(num)) return fallback;
  return Math.round(num).toLocaleString("en-US");
}

export function fmtFloat(n, digits = 1, fallback = "—") {
  if (n === null || n === undefined || n === "" || Number.isNaN(Number(n))) return fallback;
  const num = Number(n);
  if (!Number.isFinite(num)) return fallback;
  return num.toFixed(digits);
}

/** 效能展示：stc 里 effect_ext 为 0 表示「未标注效能」（12183 支队伍），显示 — 而不是 0 */
export function fmtPower(power, fallback = "—") {
  const num = Number(power);
  if (!Number.isFinite(num) || num <= 0) return fallback;
  return fmtNum(num);
}

/** 力场 def=99999 是 STC「无防护」哨兵，展示成「无」 */
export function fmtForceField(value, fallback = "—") {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  if (num >= 99999) return "无";
  return fmtNum(num);
}

/** 紧凑数字：10,000 -> 10k，1,400 -> 1.4k，用于卡片窄位置 */
export function fmtCompact(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  if (Math.abs(num) >= 10000) {
    const k = num / 1000;
    return `${Number.isInteger(k) ? k : k.toFixed(1)}k`;
  }
  if (Math.abs(num) >= 1000) {
    const k = num / 1000;
    return `${k.toFixed(1)}k`;
  }
  return fmtNum(num);
}

export function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

/** 字符串哈希（FNV-1a 变体），用于稳定假数据/颜色 */
export function hash32(str) {
  let h = 2166136261;
  const text = String(str);
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** 可复现伪随机数发生器 */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randInt(rng, min, max) {
  return Math.floor(rng() * (max - min + 1)) + min;
}

export function pick(rng, list) {
  return list[Math.floor(rng() * list.length)];
}

export function shuffle(rng, list) {
  const arr = list.slice();
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export function debounce(fn, wait = 220) {
  let timer = 0;
  return function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 本地 ISO 时间 -> HH:MM:SS */
export function fmtTime(iso, withDate = false) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const pad = (v) => String(v).padStart(2, "0");
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  if (!withDate) return time;
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${time}`;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const pad = (v) => String(v).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function timeAgo(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 10) return "刚刚";
  if (seconds < 60) return `${seconds} 秒前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return fmtDate(iso);
}

export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
  const total = Math.max(0, Math.floor(Number(seconds)));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

const FACTION_CLASS = {
  铁血: "iron",
  军方: "military",
  帕拉蒂斯: "paradeus",
  其它: "other",
  其他: "other",
};

export function factionClass(faction) {
  return FACTION_CLASS[faction] || "other";
}

export function factionColor(faction) {
  const map = {
    铁血: "#e05a4e",
    军方: "#8a9a5b",
    帕拉蒂斯: "#b07cd6",
    其它: "#7f8ea3",
    其他: "#7f8ea3",
  };
  return map[faction] || "#7f8ea3";
}

/** 造一个 DOM 节点；children 支持字符串/节点/数组 */
export function el(tag, className, children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  appendChildren(node, children);
  return node;
}

export function appendChildren(node, children) {
  if (children === null || children === undefined) return node;
  if (Array.isArray(children)) {
    children.forEach((child) => appendChildren(node, child));
    return node;
  }
  if (children instanceof Node) node.appendChild(children);
  else node.appendChild(document.createTextNode(String(children)));
  return node;
}

export function escapeAttr(value) {
  return esc(value);
}

/** 生成唯一 id */
let uidCounter = 0;
export function uid(prefix = "id") {
  uidCounter += 1;
  return `${prefix}-${uidCounter}`;
}

/** 相对/绝对链接跳转（hash 路由） */
export function navigate(path) {
  const target = path.startsWith("#") ? path : `#${path.startsWith("/") ? path : `/${path}`}`;
  if (window.location.hash === target) {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    return;
  }
  window.location.hash = target;
}

export function currentPath() {
  return (window.location.hash || "#/").slice(1) || "/";
}

/** 解析 hash 里的查询串： #/species?q=x&page=2 */
export function parseRoute(hash) {
  const raw = (hash || window.location.hash || "#/").replace(/^#/, "") || "/";
  const [pathPart, queryPart] = raw.split("?");
  const segments = pathPart.split("/").filter(Boolean).map((seg) => {
    try {
      return decodeURIComponent(seg);
    } catch {
      return seg;
    }
  });
  const query = {};
  if (queryPart) {
    new URLSearchParams(queryPart).forEach((value, key) => {
      query[key] = value;
    });
  }
  // 注意：path 必须返回解码后的路径，否则 /grayzone/共生净土 这类中文参数会二次编码
  const decodedPath = `/${segments.join("/")}`;
  return { path: decodedPath || "/", segments, query };
}

/** 防抖处理输入框 */
export function bindSearch(input, handler, wait = 240) {
  if (!input) return () => {};
  const fire = debounce(handler, wait);
  const listener = (event) => fire(event.target.value.trim());
  input.addEventListener("input", listener);
  input.addEventListener("search", listener);
  return () => input.removeEventListener("input", listener);
}

/** 简易事件总线 */
export function createEmitter() {
  const listeners = new Map();
  return {
    on(event, fn) {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event).add(fn);
      return () => listeners.get(event)?.delete(fn);
    },
    emit(event, payload) {
      listeners.get(event)?.forEach((fn) => {
        try {
          fn(payload);
        } catch (err) {
          console.error("[emitter]", err);
        }
      });
    },
  };
}

export function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand("copy");
  } finally {
    area.remove();
  }
  return Promise.resolve();
}
