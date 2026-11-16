/* theme.js — light / dark mode for TargetForge (classic script, loaded before body) */
const KEY = "tf:theme";
const root = document.documentElement;

function applyTheme(theme) {
  const value = theme === "dark" ? "dark" : "light";
  root.dataset.theme = value;
  root.style.colorScheme = value;
  try {
    localStorage.setItem(KEY, value);
  } catch {
    /* localStorage unavailable */
  }
  const button = document.getElementById("theme-toggle");
  if (button) {
    button.setAttribute("aria-label", value === "dark" ? "切换到浅色模式" : "切换到深色模式");
    button.title = value === "dark" ? "切换到浅色模式" : "切换到深色模式";
  }
}

function bindToggle() {
  const button = document.getElementById("theme-toggle");
  if (!button || button.dataset.themeBound === "1") return;
  button.dataset.themeBound = "1";
  button.addEventListener("click", () => {
    applyTheme(root.dataset.theme === "dark" ? "light" : "dark");
  });
}

function init() {
  let theme = "light";
  try {
    theme = localStorage.getItem(KEY) || "light";
  } catch {
    theme = "light";
  }
  applyTheme(theme);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindToggle, { once: true });
  } else {
    bindToggle();
  }
}

init();
