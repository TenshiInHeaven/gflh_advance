/* drag-sort.js —— 通用 HTML5 拖拽排序绑定（列表内元素需带 data-drag-index） */

export function bindDragSort(listEl, options = {}) {
  if (!listEl) return () => {};
  const {
    itemSelector = "[data-drag-index]",
    onMove,
    beforeClass = "drop-before",
    afterClass = "drop-after",
    draggingClass = "dragging",
  } = options;

  let dragIndex = null;
  let dropSlot = null;

  const clearMarks = () => {
    listEl.querySelectorAll(`.${beforeClass}, .${afterClass}`).forEach((node) => {
      node.classList.remove(beforeClass, afterClass);
    });
  };

  const onDragStart = (event) => {
    const item = event.target.closest(itemSelector);
    if (!item || !listEl.contains(item)) return;
    dragIndex = Number(item.dataset.dragIndex);
    if (!Number.isFinite(dragIndex)) return;
    item.classList.add(draggingClass);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      try {
        event.dataTransfer.setData("text/plain", String(dragIndex));
      } catch {
        /* ignore */
      }
    }
  };

  const onDragOver = (event) => {
    if (dragIndex === null) return;
    const item = event.target.closest(itemSelector);
    if (!item || !listEl.contains(item)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    const rect = item.getBoundingClientRect();
    const after = event.clientY - rect.top > rect.height / 2;
    clearMarks();
    item.classList.add(after ? afterClass : beforeClass);
    const index = Number(item.dataset.dragIndex);
    dropSlot = after ? index + 1 : index;
  };

  const onDrop = (event) => {
    event.preventDefault();
    if (dragIndex === null || dropSlot === null) {
      finish();
      return;
    }
    let target = dropSlot;
    if (dragIndex < target) target -= 1;
    const from = dragIndex;
    finish();
    if (target !== from && target >= 0 && typeof onMove === "function") onMove(from, target);
  };

  const onDragEnd = () => finish();

  function finish() {
    clearMarks();
    const dragging = listEl.querySelector(`.${draggingClass}`);
    if (dragging) dragging.classList.remove(draggingClass);
    dragIndex = null;
    dropSlot = null;
  }

  listEl.addEventListener("dragstart", onDragStart);
  listEl.addEventListener("dragover", onDragOver);
  listEl.addEventListener("drop", onDrop);
  listEl.addEventListener("dragend", onDragEnd);
  listEl.addEventListener("dragleave", (event) => {
    if (!listEl.contains(event.relatedTarget)) clearMarks();
  });

  return () => {
    listEl.removeEventListener("dragstart", onDragStart);
    listEl.removeEventListener("dragover", onDragOver);
    listEl.removeEventListener("drop", onDrop);
    listEl.removeEventListener("dragend", onDragEnd);
  };
}
