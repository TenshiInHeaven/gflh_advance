/* tutorial-overlay.js —— 首次访问的新手引导 overlay */
import { store, saveTutorial } from "../store.js";
import { icon, butterflySvg } from "../ui.js";
import { esc } from "../util.js";
import { OVERLAY_STEPS } from "../tutorial-data.js";

let activeOverlay = null;

export function maybeShowTutorialOverlay() {
  const tutorial = store.tutorial;
  if (!tutorial) return;
  const completed = new Set(tutorial.completed || []);
  const allDone = OVERLAY_STEPS.every((step) => completed.has(step.id));
  if (tutorial.dismissed || allDone) return;
  showTutorialOverlay({ startIndex: 0 });
}

export function showTutorialOverlay(options = {}) {
  closeTutorialOverlay();
  const { startIndex = 0, onClose = null } = options;
  const view = { index: Math.min(startIndex, OVERLAY_STEPS.length - 1), noMore: false, finished: false };
  const overlay = document.createElement("div");
  overlay.className = "tut-overlay";
  overlay.innerHTML = `
    <div class="tut-overlay-card" role="dialog" aria-modal="true">
      <div class="tut-overlay-head">
        <span class="toh-badge">// NEW PLAYER GUIDE</span>
        <span class="toh-bf">${butterflySvg({ size: 30, opacity: 0.7, className: "float" })}</span>
        <span class="toh-progress" data-progress></span>
      </div>
      <div class="tut-overlay-body" data-body></div>
      <div class="tut-overlay-foot">
        <div class="tut-dots" data-dots></div>
        <span class="spacer"></span>
        <label class="tut-nomore"><input type="checkbox" data-nomore /> 不再提示</label>
        <button class="tut-skip" type="button" data-skip>跳过引导</button>
        <button class="btn btn-ghost btn-sm" type="button" data-prev>上一步</button>
        <button class="btn btn-primary btn-sm" type="button" data-next>下一步</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  activeOverlay = overlay;

  const bodyEl = overlay.querySelector("[data-body]");
  const dotsEl = overlay.querySelector("[data-dots]");
  const progressEl = overlay.querySelector("[data-progress]");
  const prevBtn = overlay.querySelector("[data-prev]");
  const nextBtn = overlay.querySelector("[data-next]");
  const skipBtn = overlay.querySelector("[data-skip]");
  const noMoreInput = overlay.querySelector("[data-nomore]");

  function render() {
    const step = OVERLAY_STEPS[view.index];
    progressEl.textContent = `${view.index + 1} / ${OVERLAY_STEPS.length}`;
    bodyEl.innerHTML = `
      <h3><span class="toi">${icon(step.icon, 20)}</span>${esc(step.title)}</h3>
      <p>${step.body}</p>
      <div class="tut-overlay-points">
        ${step.points.map((point) => `<div class="tut-overlay-point">${esc(point)}</div>`).join("")}
      </div>
    `;
    dotsEl.innerHTML = OVERLAY_STEPS.map(
      (item, index) =>
        `<i class="${index === view.index ? "active" : index < view.index ? "done" : ""}" data-dot="${index}" title="第 ${index + 1} 步"></i>`,
    ).join("");
    prevBtn.disabled = view.index === 0;
    nextBtn.textContent = view.index === OVERLAY_STEPS.length - 1 ? "开始使用" : "下一步";
    nextBtn.innerHTML =
      view.index === OVERLAY_STEPS.length - 1
        ? `${icon("check", 13)} 开始使用`
        : `下一步 ${icon("chevronRight", 13)}`;
    noMoreInput.checked = view.noMore;
  }

  async function finish(saveCompleted) {
    overlay.remove();
    activeOverlay = null;
    const patch = {};
    if (saveCompleted) patch.completed = OVERLAY_STEPS.map((step) => step.id);
    if (view.noMore) patch.dismissed = true;
    if (Object.keys(patch).length) {
      try {
        await saveTutorial(patch);
      } catch {
        /* 保存失败不影响关闭 */
      }
    }
    if (onClose) onClose();
  }

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      finish(false);
    }
  });
  dotsEl.addEventListener("click", (event) => {
    const dot = event.target.closest("[data-dot]");
    if (!dot) return;
    view.index = Number(dot.dataset.dot);
    render();
  });
  prevBtn.addEventListener("click", () => {
    if (view.index > 0) {
      view.index -= 1;
      render();
    }
  });
  nextBtn.addEventListener("click", () => {
    if (view.index < OVERLAY_STEPS.length - 1) {
      view.index += 1;
      render();
    } else {
      finish(true);
    }
  });
  skipBtn.addEventListener("click", () => finish(false));
  noMoreInput.addEventListener("change", () => {
    view.noMore = noMoreInput.checked;
  });

  render();
  return { close: () => finish(view.noMore) };
}

export function closeTutorialOverlay() {
  if (activeOverlay) {
    activeOverlay.remove();
    activeOverlay = null;
  }
}

export function isTutorialOverlayOpen() {
  return Boolean(activeOverlay);
}
