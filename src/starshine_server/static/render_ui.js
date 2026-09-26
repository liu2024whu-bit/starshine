export function setRequestStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

export function setReviewState(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("badge-error", isError);
  element.classList.toggle("badge-safe", !isError && message === "Reviewed");
}

function activatePanel(button) {
  const targetId = button.dataset.panelTarget;
  for (const candidate of document.querySelectorAll(".tab-button")) {
    const active = candidate === button;
    candidate.classList.toggle("is-active", active);
    candidate.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    panel.hidden = panel.id !== targetId;
  }
}

export function initializeTabs() {
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => activatePanel(button));
  }
}
