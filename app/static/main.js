// App shell: sidebar, views, theme, settings and the server status.

import * as api from "./api.js";
import * as chat from "./chat.js";
import { courseCounts, searchKey } from "./courses.js";
import { initLibrary, renderLibrary, showLibrary } from "./library.js";
import { conversations, persistent, prefs, savedAnswers } from "./store.js";
import { $, confirmDialog, dayGroup, esc, formatNumber, icon, onAction, plural, toast } from "./ui.js";

const app = $("#app");
const desktop = matchMedia("(min-width: 900px)");
const wide = matchMedia("(min-width: 1280px)");
const prefersLight = matchMedia("(prefers-color-scheme: light)");

let status; // GET /health/ready, null when the server is unreachable
let catalog; // GET /documents: undefined while loading, null on failure
let documentsBySource = new Map();
let view = "chat";
let tab = "history";
let libraryCourse = "";
let savedOpen = null; // id of the saved answer on screen
let panelOpener = null; // element to refocus when the source panel closes

const shell = {
  status: () => status,
  catalog: () => catalog,
  documentFor: (source) => documentsBySource.get(source) ?? { source, textbook: false, openable: false },
  setTitle: (title, scope) => view === "chat" && setTitle(title, scope),
  conversationsChanged: renderSidebarList,
  openPanel,
  closePanel,
  reloadCatalog: refreshServer,
  libraryFilterChanged: (course) => {
    libraryCourse = course;
    markActive();
  },
};

// --- Views -----------------------------------------------------------------------

function showView(name) {
  view = name;
  for (const id of ["chat", "library", "saved"]) $(`#${id}-view`).hidden = id !== name;
  if (name === "chat") chat.activate();
  if (name === "library") {
    setTitle("Bibliothèque");
    closePanel();
  }
  if (name === "saved") setTitle("Réponse enregistrée");
  closeDrawer();
  markActive();
}

function setTitle(title, scope = null) {
  $("#view-title").textContent = title;
  $("#view-subtitle").hidden = !scope;
  $("#view-subtitle").textContent = scope ? `Limité à « ${scope.title} »` : "";
  document.title = title === "Nouvelle conversation" ? "MedStudy AI" : `${title} · MedStudy AI`;
}

// --- Sidebar ---------------------------------------------------------------------

function renderSidebarList() {
  const query = searchKey($("#history-search").value.trim());
  const matches = (text) => !query || searchKey(text).includes(query);
  const list = $("#history-list");
  if (tab === "history") {
    const items = conversations
      .list()
      .filter((c) => matches(`${c.title} ${c.turns.map((t) => t.question).join(" ")}`));
    list.innerHTML = items.length
      ? grouped(items, (c) => c.updatedAt, conversationItem)
      : emptyList(query ? "Aucune conversation trouvée." : "Vos conversations apparaîtront ici.");
  } else {
    const items = savedAnswers.list().filter((s) => matches(`${s.question} ${s.answer}`));
    list.innerHTML = items.length
      ? grouped(items, (s) => s.savedAt, savedItem)
      : emptyList(query ? "Aucune réponse trouvée." : "Enregistrez une réponse avec l'étoile pour la retrouver ici.");
  }
  markActive();
}

function grouped(items, time, render) {
  const groups = new Map();
  for (const item of items) {
    const label = dayGroup(time(item));
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups]
    .map(([label, entries]) => `<h3 class="list-label">${label}</h3><ul class="conv-list">${entries.map(render).join("")}</ul>`)
    .join("");
}

const emptyList = (text) => `<p class="list-empty">${text}</p>`;

const conversationItem = (c) => `<li class="conv" data-id="${c.id}">
    <button type="button" class="conv-open" data-action="open-conversation" data-id="${c.id}" title="${esc(c.title)}">
      ${c.scope ? icon("book") : ""}<span>${esc(c.title || "Sans titre")}</span>
    </button>
    <button type="button" class="icon-btn xs conv-delete" data-action="delete-conversation" data-id="${c.id}" title="Supprimer" aria-label="Supprimer « ${esc(c.title)} »">${icon("trash")}</button>
  </li>`;

const savedItem = (s) => `<li class="conv" data-id="${s.id}">
    <button type="button" class="conv-open" data-action="open-saved" data-id="${s.id}" title="${esc(s.question)}">
      ${icon("star")}<span>${esc(s.question)}</span>
    </button>
  </li>`;

function markActive() {
  for (const item of document.querySelectorAll(".conv")) {
    const current =
      (view === "chat" && tab === "history" && item.dataset.id === chat.currentId()) ||
      (view === "saved" && tab === "saved" && item.dataset.id === savedOpen);
    item.classList.toggle("is-active", current);
    item.querySelector(".conv-open").toggleAttribute("aria-current", current);
  }
  const library = $("#nav-library");
  library.classList.toggle("is-active", view === "library" && !libraryCourse);
  for (const item of document.querySelectorAll("#course-list [data-course]")) {
    item.classList.toggle("is-active", view === "library" && item.dataset.course === libraryCourse);
  }
}

function renderCourses() {
  const list = $("#course-list");
  $("#doc-count").textContent = catalog ? formatNumber(catalog.documents.length) : "";
  if (!catalog?.documents.length) {
    const note = catalog === null ? "Bibliothèque indisponible" : catalog ? "Aucun document indexé" : "Chargement…";
    list.innerHTML = `<li class="list-empty">${note}</li>`;
    return;
  }
  list.innerHTML = courseCounts(catalog.documents)
    .map(
      ([name, count]) => `<li><button type="button" class="nav-item sub" data-action="open-course" data-course="${esc(name)}" title="${esc(name)}">
          <span class="label">${esc(name)}</span><span class="count">${count}</span>
        </button></li>`,
    )
    .join("");
  markActive();
}

function setCollapsed(collapsed) {
  app.dataset.sidebar = collapsed ? "collapsed" : "open";
  prefs.set("sidebarCollapsed", collapsed);
}

function closeDrawer() {
  delete app.dataset.drawer;
  updateScrim();
}

// --- Source panel ----------------------------------------------------------------

function openPanel() {
  if ($("#source-panel").hidden) panelOpener = document.activeElement;
  $("#source-panel").hidden = false;
  app.dataset.panel = "open";
  updateScrim();
  if (!wide.matches) $("#source-list .is-current")?.focus({ preventScroll: true });
}

function closePanel() {
  if ($("#source-panel").hidden) return;
  $("#source-panel").hidden = true;
  delete app.dataset.panel;
  updateScrim();
  if (!wide.matches && panelOpener?.isConnected) panelOpener.focus();
  panelOpener = null;
}

function updateScrim() {
  const drawer = app.dataset.drawer === "open" && !desktop.matches;
  const panel = app.dataset.panel === "open" && !wide.matches;
  $("#scrim").hidden = !(drawer || panel);
}

// --- Theme and settings ----------------------------------------------------------

function applyTheme(choice) {
  const light = choice === "light" || (choice === "system" && prefersLight.matches);
  document.documentElement.dataset.theme = light ? "light" : "dark";
  $('meta[name="theme-color"]').content = light ? "#ffffff" : "#101418";
  const button = $("#theme-btn");
  const label = light ? "Passer au thème sombre" : "Passer au thème clair";
  button.innerHTML = icon(light ? "moon" : "sun");
  button.setAttribute("aria-label", label);
  button.title = label;
}

function syncSettings() {
  const theme = prefs.get("theme", "dark");
  for (const radio of document.querySelectorAll('input[name="theme"]')) radio.checked = radio.value === theme;

  const disabled = catalog?.uploads_enabled === false;
  const token = $("#admin-token");
  token.value = prefs.get("adminToken", "");
  token.disabled = disabled;
  $("#admin-help").textContent = disabled
    ? "L'ajout de documents est désactivé sur ce serveur (variable ADMIN_TOKEN non définie)."
    : "Permet d'ajouter et de retirer des documents. Conservé uniquement dans ce navigateur.";

  $("#local-data").textContent = persistent
    ? `${plural(conversations.list().length, "conversation", "conversations")} et ${plural(savedAnswers.list().length, "réponse enregistrée", "réponses enregistrées")}, conservées uniquement dans ce navigateur.`
    : "Le stockage local est bloqué (navigation privée ?) : l'historique disparaîtra à la fermeture de la page.";
  $("#about-index").textContent = status
    ? `${plural(status.chunks, "passage indexé", "passages indexés")}${catalog ? ` dans ${plural(catalog.documents.length, "document", "documents")}` : ""}.`
    : "Serveur injoignable.";
}

// --- Server ----------------------------------------------------------------------

async function checkStatus() {
  try {
    status = await api.getStatus();
  } catch {
    status = null;
  }
  $("#banner").hidden = status !== null;
}

async function loadCatalog() {
  try {
    catalog = await api.getDocuments();
  } catch {
    catalog = null;
  }
  documentsBySource = new Map((catalog?.documents ?? []).map((doc) => [doc.source, doc]));
}

async function refreshServer() {
  await Promise.all([checkStatus(), loadCatalog()]);
  renderCourses();
  renderLibrary();
  syncSettings();
  chat.refresh();
}

// --- Actions ---------------------------------------------------------------------

onAction("new-chat", () => {
  chat.newConversation();
  showView("chat");
});
onAction("open-library", () => {
  showLibrary("");
  showView("library");
});
onAction("open-course", (el) => {
  showLibrary(el.dataset.course);
  showView("library");
});
onAction("open-conversation", (el) => {
  chat.openConversation(el.dataset.id);
  showView("chat");
});
onAction("delete-conversation", async (el) => {
  const conversation = conversations.get(el.dataset.id);
  const confirmed = await confirmDialog({
    title: "Supprimer la conversation ?",
    message: `« ${conversation.title} » sera supprimée de ce navigateur. Les réponses enregistrées sont conservées.`,
    confirm: "Supprimer",
  });
  if (!confirmed) return;
  conversations.remove(conversation.id);
  if (conversation.id === chat.currentId()) chat.newConversation();
  renderSidebarList();
});
onAction("open-saved", (el) => {
  const entry = savedAnswers.get(el.dataset.id);
  if (!entry) return;
  savedOpen = entry.id;
  chat.renderSaved(entry);
  showView("saved");
});
onAction("ask-doc", (el) => {
  showView("chat");
  closePanel();
  chat.askAbout({ source: el.dataset.source, title: el.dataset.title });
});
onAction("tab", (el) => {
  tab = el.dataset.tab;
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.setAttribute("aria-selected", button.dataset.tab === tab);
  }
  renderSidebarList();
});
onAction("collapse-sidebar", () => (desktop.matches ? setCollapsed(true) : closeDrawer()));
onAction("expand-sidebar", () => setCollapsed(false));
onAction("search-history", () => {
  setCollapsed(false);
  $("#history-search").focus();
});
onAction("open-drawer", () => {
  app.dataset.drawer = "open";
  updateScrim();
  $("#sidebar .new-chat").focus();
});
onAction("close-overlays", () => {
  closeDrawer();
  closePanel();
});
onAction("close-sources", closePanel);
onAction("toggle-theme", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  prefs.set("theme", next);
  applyTheme(next);
});
onAction("open-settings", () => {
  syncSettings();
  closeDrawer();
  $("#settings-dialog").showModal();
});
onAction("close-dialog", (el) => el.closest("dialog").close());
onAction("clear-history", async () => {
  const confirmed = await confirmDialog({
    title: "Effacer l'historique ?",
    message: "Toutes les conversations et réponses enregistrées dans ce navigateur seront supprimées.",
    confirm: "Effacer",
  });
  if (!confirmed) return;
  conversations.clear();
  savedAnswers.clear();
  chat.newConversation();
  showView("chat");
  renderSidebarList();
  syncSettings();
  toast("Historique effacé", "success");
});
onAction("retry-status", async () => {
  await refreshServer();
  if (!status) toast("Le serveur ne répond toujours pas.", "error");
});

// --- Start -----------------------------------------------------------------------

applyTheme(prefs.get("theme", "dark"));
prefersLight.addEventListener("change", () => {
  if (prefs.get("theme", "dark") === "system") applyTheme("system");
});
for (const radio of document.querySelectorAll('input[name="theme"]')) {
  radio.addEventListener("change", () => {
    prefs.set("theme", radio.value);
    applyTheme(radio.value);
  });
}
$("#admin-token").addEventListener("input", (event) => {
  prefs.set("adminToken", event.target.value.trim());
  renderLibrary();
});
$("#history-search").addEventListener("input", renderSidebarList);
const courses = $("#courses-group");
courses.open = prefs.get("coursesOpen", true);
courses.addEventListener("toggle", () => prefs.set("coursesOpen", courses.open));
desktop.addEventListener("change", closeDrawer);
wide.addEventListener("change", updateScrim);
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || event.defaultPrevented || $("dialog[open]")) return;
  if (app.dataset.panel) closePanel();
  else closeDrawer();
});

app.dataset.sidebar = prefs.get("sidebarCollapsed", false) ? "collapsed" : "open";
chat.initChat(shell);
initLibrary(shell);
chat.newConversation();
showView("chat");
renderSidebarList();
renderCourses();
renderLibrary();
refreshServer();
