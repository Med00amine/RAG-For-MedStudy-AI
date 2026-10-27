// Small DOM helpers shared by the views.

import { kindOf } from "./courses.js";
import { escapeHtml } from "./markdown.js";

export const esc = escapeHtml;
export const $ = (selector, root = document) => root.querySelector(selector);
export const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

export const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;

const FILE_ICONS = { pdf: "file", slides: "slides", image: "image", text: "file" };
export const fileIcon = (doc) => (doc.textbook ? "book" : FILE_ICONS[kindOf(doc.source)]);

const numbers = new Intl.NumberFormat("fr-FR");
export const formatNumber = (n) => numbers.format(n);
/** French plural: 0 and 1 are singular. */
export const plural = (n, one, many) => `${formatNumber(n)} ${n > 1 ? many : one}`;

const dates = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" });
export const formatDate = (timestamp) => dates.format(timestamp);

export function dayGroup(timestamp, now = Date.now()) {
  const today = new Date(now).setHours(0, 0, 0, 0);
  const day = 86_400_000;
  if (timestamp >= today) return "Aujourd'hui";
  if (timestamp >= today - day) return "Hier";
  if (timestamp >= today - 6 * day) return "7 derniers jours";
  if (timestamp >= today - 29 * day) return "30 derniers jours";
  return "Plus ancien";
}

// One click listener for the whole page: elements name their handler in data-action.
const actions = {};
export const onAction = (name, handler) => {
  actions[name] = handler;
};
document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  const handler = target && actions[target.dataset.action];
  if (handler && !target.disabled) handler(target, event);
});

export function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.innerHTML = `${icon(kind === "error" ? "alert" : "check")}<span>${esc(message)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => el.classList.add("is-leaving"), 3500);
  setTimeout(() => el.remove(), 3800);
}

/** Resolves to true when the user confirms. */
export function confirmDialog({ title, message, confirm }) {
  const dialog = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#confirm-ok").textContent = confirm;
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {
      once: true,
    });
  });
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // The Clipboard API needs a secure context (HTTPS or localhost).
    const area = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  }
}

/** Announces a status change to screen readers. */
export function announce(message) {
  const live = $("#live");
  live.textContent = "";
  requestAnimationFrame(() => {
    live.textContent = message;
  });
}
