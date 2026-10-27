// The library: every indexed document, with uploads and removal for administrators.

import * as api from "./api.js";
import { courseCounts, courseOf, pathInCourse, searchKey } from "./courses.js";
import { prefs } from "./store.js";
import { $, confirmDialog, esc, fileIcon, icon, onAction, plural, toast, uid } from "./ui.js";

const UPLOAD_ERRORS = {
  0: "Serveur injoignable",
  403: "Jeton administrateur refusé",
  413: "Fichier trop volumineux",
  415: "Format non pris en charge",
};

let shell;
let course = ""; // course filter, "" for all
const uploads = []; // this visit's uploads: { id, name, state, message }

const canEdit = () => Boolean(shell.catalog()?.uploads_enabled && prefs.get("adminToken", ""));
const hasFiles = (event) => [...(event.dataTransfer?.types ?? [])].includes("Files");

export function initLibrary(callbacks) {
  shell = callbacks;
  $("#library-search").addEventListener("input", renderList);
  $("#file-input").addEventListener("change", (event) => {
    upload([...event.target.files]);
    event.target.value = "";
  });
  onAction("library-course", (el) => showLibrary(el.dataset.course));
  onAction("clear-library-filters", () => {
    $("#library-search").value = "";
    showLibrary("");
  });
  onAction("upload", () => $("#file-input").click());
  onAction("delete-doc", (el) => remove(el.dataset.source, el.dataset.title));
  onAction("reload-library", () => shell.reloadCatalog());

  const view = $("#library-view");
  const overlay = $("#drop-overlay");
  let depth = 0; // dragenter and dragleave fire for every child element crossed
  view.addEventListener("dragenter", (event) => {
    if (!canEdit() || !hasFiles(event)) return;
    event.preventDefault();
    depth += 1;
    overlay.hidden = false;
  });
  view.addEventListener("dragover", (event) => {
    if (canEdit() && hasFiles(event)) event.preventDefault();
  });
  view.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) overlay.hidden = true;
  });
  view.addEventListener("drop", (event) => {
    if (!canEdit()) return;
    event.preventDefault();
    depth = 0;
    overlay.hidden = true;
    upload([...event.dataTransfer.files]);
  });
}

export function showLibrary(filter) {
  course = filter;
  renderLibrary();
}

export function renderLibrary() {
  const catalog = shell.catalog();
  const status = shell.status();
  $("#library-summary").textContent = catalog
    ? [
        plural(catalog.documents.length, "document indexé", "documents indexés"),
        status && plural(status.chunks, "passage", "passages"),
      ]
        .filter(Boolean)
        .join(" · ")
    : catalog === null
      ? "Bibliothèque indisponible"
      : "Chargement…";
  renderAdmin();
  renderCourses();
  renderList();
}

function renderAdmin() {
  const catalog = shell.catalog();
  const panel = $("#library-admin");
  $("#library-actions").innerHTML = canEdit()
    ? `<button type="button" class="btn btn-primary" data-action="upload">${icon("upload")}Ajouter des documents</button>`
    : "";
  if (!catalog?.uploads_enabled) {
    panel.innerHTML = "";
    return;
  }
  if (!canEdit()) {
    panel.innerHTML = `<div class="notice">${icon("info")}
        <span>L'ajout et le retrait de documents sont réservés aux administrateurs : saisissez le jeton dans les paramètres.</span>
        <button type="button" class="btn btn-ghost btn-sm" data-action="open-settings">Paramètres</button>
      </div>`;
    return;
  }
  $("#file-input").accept = catalog.upload_types.join(",");
  panel.innerHTML = uploads.length
    ? `<ul class="uploads" aria-label="Envois">${uploads.map(uploadHtml).join("")}</ul>`
    : `<p class="drop-hint">${icon("upload")}<span>Glissez-déposez des fichiers ici. Formats acceptés : ${catalog.upload_types.join(" ")}</span></p>`;
}

function uploadHtml(entry) {
  const marks = { error: icon("alert"), warn: icon("info"), done: icon("check") };
  const mark = marks[entry.state] ?? '<span class="spinner" aria-hidden="true"></span>';
  return `<li class="upload is-${entry.state}">${mark}
      <span class="upload-name">${esc(entry.name)}</span>
      <span class="upload-message">${esc(entry.message)}</span>
    </li>`;
}

function renderCourses() {
  const documents = shell.catalog()?.documents ?? [];
  const chips = [["", "Tous", documents.length], ...courseCounts(documents).map(([n, c]) => [n, n, c])];
  $("#library-courses").innerHTML = documents.length
    ? chips
        .map(
          ([value, label, count]) => `<button type="button" class="chip${course === value ? " is-on" : ""}" data-action="library-course" data-course="${esc(value)}" aria-pressed="${course === value}">${esc(label)}<span>${count}</span></button>`,
        )
        .join("")
    : "";
  shell.libraryFilterChanged(course);
}

const emptyState = (name, title, text, action = "") =>
  `<div class="empty-state"><span class="empty-icon">${icon(name)}</span><h3>${title}</h3><p>${text}</p>${action}</div>`;

function renderList() {
  const catalog = shell.catalog();
  const list = $("#library-list");
  if (catalog === undefined) {
    list.innerHTML = `<div class="list-skeleton" aria-label="Chargement">${"<span></span>".repeat(6)}</div>`;
    return;
  }
  if (catalog === null) {
    const retry = `<button type="button" class="btn btn-secondary btn-sm" data-action="reload-library">${icon("refresh")}Réessayer</button>`;
    list.innerHTML = emptyState("alert", "Impossible de charger la bibliothèque", "Le serveur ne répond pas. Vérifiez qu'il est lancé.", retry);
    return;
  }
  if (!catalog.documents.length) {
    const hint = catalog.uploads_enabled
      ? "Ajoutez vos cours avec « Ajouter des documents »."
      : "Indexez un dossier avec <code>python scripts/ingest.py data/raw/drive</code>.";
    list.innerHTML = emptyState("library", "Aucun document indexé", hint);
    return;
  }

  const query = searchKey($("#library-search").value.trim());
  const shown = catalog.documents
    .filter((doc) => !course || courseOf(doc) === course)
    .filter((doc) => !query || searchKey(`${doc.title} ${doc.source}`).includes(query))
    .sort((a, b) => a.source.localeCompare(b.source, "fr", { numeric: true }));
  if (!shown.length) {
    const clear = `<button type="button" class="btn btn-secondary btn-sm" data-action="clear-library-filters">Effacer les filtres</button>`;
    list.innerHTML = emptyState("search", "Aucun document ne correspond", "Essayez un autre mot-clé ou retirez le filtre de cours.", clear);
    return;
  }

  const groups = new Map(courseCounts(shown).map(([name]) => [name, []]));
  for (const doc of shown) groups.get(courseOf(doc)).push(doc);
  list.innerHTML = [...groups]
    .map(
      ([name, docs]) => `<section class="doc-group" aria-label="${esc(name)}">
        <h3 class="group-title">${esc(name)}<span>${docs.length}</span></h3>
        <ul class="lib-list">${docs.map(rowHtml).join("")}</ul>
      </section>`,
    )
    .join("");
}

function rowHtml(doc) {
  const title = esc(doc.title);
  const where = pathInCourse(doc.source) || (doc.textbook ? "Manuel de référence" : courseOf(doc));
  const open = doc.openable
    ? `<a class="icon-btn sm" href="${esc(api.fileUrl(doc.source))}" target="_blank" rel="noopener" title="Ouvrir le fichier original" aria-label="Ouvrir « ${title} »">${icon(doc.type === "pdf" ? "external" : "download")}</a>`
    : "";
  const remove = canEdit()
    ? `<button type="button" class="icon-btn sm danger" data-action="delete-doc" data-source="${esc(doc.source)}" data-title="${title}" title="Retirer de la bibliothèque" aria-label="Retirer « ${title} »">${icon("trash")}</button>`
    : "";
  return `<li class="lib-row">
      <span class="doc-icon">${icon(fileIcon(doc))}</span>
      <span class="lib-main"><span class="lib-title" title="${title}">${title}</span><span class="lib-path">${esc(where)}</span></span>
      <span class="lib-meta"><span class="tag">${esc(doc.type || "?")}</span><span class="lib-count">${plural(doc.chunks, "passage", "passages")}</span></span>
      <span class="lib-actions">
        <button type="button" class="icon-btn sm" data-action="ask-doc" data-source="${esc(doc.source)}" data-title="${title}" title="Poser une question sur ce document" aria-label="Interroger « ${title} »">${icon("message")}</button>
        ${open}${remove}
      </span>
    </li>`;
}

async function upload(files) {
  const catalog = shell.catalog();
  if (!files.length || !catalog || !canEdit()) return;
  const token = prefs.get("adminToken", "");
  const queue = files.map((file) => ({ id: uid(), file, name: file.name, state: "pending", message: "En attente…" }));
  uploads.unshift(...queue);
  for (const entry of queue) {
    const dot = entry.name.lastIndexOf(".");
    const extension = dot > 0 ? entry.name.slice(dot).toLowerCase() : "";
    if (!catalog.upload_types.includes(extension)) {
      Object.assign(entry, { state: "error", message: `Format non pris en charge${extension ? ` (${extension})` : ""}` });
    } else {
      entry.message = "Indexation en cours…";
      renderAdmin();
      try {
        const { chunks } = await api.uploadDocument(entry.file, token);
        Object.assign(
          entry,
          chunks
            ? { state: "done", message: plural(chunks, "passage indexé", "passages indexés") }
            : { state: "warn", message: "Aucun texte lisible (document scanné ?)" },
        );
      } catch (error) {
        const message = error.status === 400 ? `Fichier illisible : ${error.message}` : UPLOAD_ERRORS[error.status];
        Object.assign(entry, { state: "error", message: message ?? "Échec de l'indexation" });
      }
    }
    delete entry.file;
    renderAdmin();
  }
  await shell.reloadCatalog();
}

async function remove(source, title) {
  const confirmed = await confirmDialog({
    title: "Retirer ce document ?",
    message: `« ${title} » ne sera plus utilisé pour répondre. Le fichier reste sur le serveur et pourra être réindexé.`,
    confirm: "Retirer",
  });
  if (!confirmed) return;
  try {
    await api.deleteDocument(source, prefs.get("adminToken", ""));
    toast(`« ${title} » retiré de la bibliothèque`, "success");
  } catch (error) {
    toast(error.status === 403 ? "Jeton administrateur refusé" : "Impossible de retirer ce document", "error");
  }
  await shell.reloadCatalog();
}
