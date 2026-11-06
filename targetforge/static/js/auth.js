/* auth.js —— 本机 API 访问 token 的本地保存与 URL 引导 */
const KEY = "tf_api_token";

export function getToken() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function saveToken(token) {
  const value = String(token || "").trim();
  try {
    if (value) localStorage.setItem(KEY, value);
    else localStorage.removeItem(KEY);
  } catch {
    // localStorage 不可用时保持内存值
    memoryToken = value;
  }
  return value;
}

let memoryToken = "";

export function rememberTokenFromUrl() {
  let token = "";
  try {
    const url = new URL(window.location.href);
    token = url.searchParams.get("token") || url.searchParams.get("t") || "";
    if (token) {
      saveToken(token);
      url.searchParams.delete("token");
      url.searchParams.delete("t");
      const clean = url.pathname + (url.searchParams.toString() ? `?${url.searchParams}` : "") + url.hash;
      window.history.replaceState(null, "", clean);
    }
  } catch {
    token = "";
  }
  return token || getToken() || memoryToken;
}

export function currentToken() {
  return getToken() || memoryToken;
}
