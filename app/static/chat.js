// The conversation view: questions, streamed answers, citations and the source panel.

import * as api from "./api.js";
import { courseOf, kindOf, pathInCourse, placeOf, searchKey } from "./courses.js";
import { CITATION, renderMarkdown } from "./markdown.js";
import { conversations, savedAnswers } from "./store.js";
import {
  $,
  announce,
  copyText,
  esc,
  fileIcon,
  formatDate,
  formatNumber,
  icon,
  onAction,
  plural,
  toast,
  uid,
} from "./ui.js";

const HISTORY_MESSAGES = 6; // earlier messages sent back so follow-up questions work
const MIN_CHARS = 3; // the API's limits
const MAX_CHARS = 1000;
const CARET = "⁣"; // invisible marker for where the streaming caret goes
const SUGGESTIONS = [
  ["Classification", "Classification de Gharbi du kyste hydatique du foie"],
  ["Diagnostic", "Signes ECG de l'hyperkaliémie"],
  ["Conduite à tenir", "Conduite à tenir devant une hémorragie du post-partum"],
  ["Contre-indications", "Contre-indications du DIU"],
];
const ERRORS = {
  llm: "Le modèle ne répond pas. Vérifiez qu'Ollama est lancé, puis réessayez.",
  offline: "Serveur injoignable. Vérifiez que l'application est lancée, puis réessayez.",
  invalid: "La question doit contenir entre 3 et 1 000 caractères.",
  server: "Le serveur a rencontré une erreur. Réessayez dans un instant.",
};

let shell; // callbacks into main.js
let conversation; // the open conversation
let active = null; // { turn, controller } while an answer streams
let panelTurn = null; // the answer whose sources the panel shows
let followOutput = true; // keep the newest text in view while it streams
let textQueued = false; // a frame is already booked to draw streamed text
let quotaWarned = false;
let scopeOptions = []; // documents listed in the scope menu (null = all courses)
let highlighted = 0;

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const finePointer = matchMedia("(pointer: fine)");

export function initChat(callbacks) {
  shell = callbacks;
  const form = $("#composer");
  const input = $("#question");

  input.addEventListener("input", () => {
    autosize(input);
    updateComposer();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!active) form.requestSubmit();
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (active) return active.controller.abort(); // while streaming, the button stops
    const question = input.value.trim();
    if (question.length < MIN_CHARS) return;
    input.value = "";
    autosize(input);
    ask(question);
  });

  const scroller = $("#scroller");
  scroller.addEventListener(
    "scroll",
    () => {
      followOutput = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
      $("#jump").hidden = followOutput;
    },
    { passive: true },
  );

  onAction("jump", () => {
    followOutput = true;
    scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
  });
  onAction("suggest", (el) => active || ask(el.dataset.question));
  onAction("cite", (el) => openSources(turnFor(el), Number(el.dataset.n)));
  onAction("retry", (el) => {
    const turn = turnFor(el);
    if (turn && !active) ask(turn.question, turn);
  });
  onAction("copy", (el) => copyAnswer(turnFor(el)));
  onAction("save", (el) => toggleSaved(turnFor(el), el));
  onAction("clear-scope", () => setScope(null));
  initScopeMenu();
  updateComposer();
}

// --- Conversations ---------------------------------------------------------------

export function newConversation(scope = null) {
  stop();
  const now = Date.now();
  conversation = { id: uid(), title: "", createdAt: now, updatedAt: now, scope, turns: [] };
  shell.closePanel();
  renderThread();
  if (finePointer.matches) $("#question").focus(); // no surprise keyboard on phones
}

export function openConversation(id) {
  const found = conversations.get(id);
  if (!found) return newConversation();
  stop();
  conversation = found;
  shell.closePanel();
  renderThread();
  scrollToEnd(true);
}

/** "Interroger ce document": a fresh conversation limited to one document. */
export function askAbout(scope) {
  if (conversation.turns.length) newConversation(scope);
  else setScope(scope);
  $("#question").focus();
}

export const currentId = () => conversation?.id;

/** Called when the chat view comes back on screen. */
export function activate() {
  shell.setTitle(conversation.title || "Nouvelle conversation", conversation.scope);
  for (const button of document.querySelectorAll('#thread [data-action="save"]')) {
    const saved = savedAnswers.has(button.closest("[data-turn]").dataset.turn);
    setSaveButton(button, saved);
  }
}

/** Redraws the thread once the server status or the library has loaded. */
export function refresh() {
  if (active) return;
  const scroller = $("#scroller");
  const top = scroller.scrollTop;
  renderThread();
  scroller.scrollTop = top;
}

function stop() {
  active?.controller.abort();
}

// --- Asking ----------------------------------------------------------------------

async function ask(question, retried = null) {
  const owner = conversation;
  const turn = retried ?? { id: uid(), question, at: Date.now() };
  Object.assign(turn, { answer: "", sources: [], status: "searching", error: "" });
  if (!retried) owner.turns.push(turn);
  owner.title ||= question.length > 80 ? `${question.slice(0, 79)}…` : question;

  const controller = new AbortController();
  active = { turn, controller };
  updateComposer();
  shell.setTitle(owner.title, owner.scope);
  if (retried) renderTurn(turn);
  else if (owner.turns.length === 1) renderThread();
  else $("#thread").insertAdjacentHTML("beforeend", turnHtml(turn, true));
  scrollToEnd(true);

  const history = owner.turns
    .slice(0, owner.turns.indexOf(turn))
    .filter((t) => t.status === "done")
    .flatMap((t) => [
      { role: "user", content: t.question },
      { role: "assistant", content: t.answer },
    ])
    .slice(-HISTORY_MESSAGES);
  const visible = () => owner === conversation;

  try {
    const body = { question, history, source: owner.scope?.source ?? null };
    for await (const event of api.chat(body, controller.signal)) {
      if (event.type === "sources") {
        turn.sources = event.sources;
        turn.status = "writing";
        if (visible()) renderTurn(turn);
      } else if (event.type === "token") {
        turn.answer += event.text;
        if (visible()) queueText(turn);
      } else if (event.type === "error") {
        turn.status = "error";
        turn.error = "llm";
      }
    }
    if (turn.status !== "error") turn.status = "done";
  } catch (error) {
    if (error.name === "AbortError") {
      turn.status = "stopped";
    } else {
      turn.status = "error";
      turn.error = { 0: "offline", 422: "invalid" }[error.status] ?? "server";
    }
  }

  active = null;
  owner.updatedAt = Date.now();
  if (!conversations.save(owner) && !quotaWarned) {
    quotaWarned = true;
    toast("Mémoire du navigateur pleine : les plus anciennes conversations ne sont plus conservées.", "error");
  }
  shell.conversationsChanged();
  updateComposer();
  if (visible()) {
    renderTurn(turn);
    const outcome = { done: "Réponse prête.", stopped: "Réponse interrompue." };
    announce(outcome[turn.status] ?? "La réponse a échoué.");
  }
}

function updateComposer() {
  const input = $("#question");
  const send = $("#send");
  const length = input.value.trim().length;
  send.disabled = !active && length < MIN_CHARS;
  send.classList.toggle("is-stop", Boolean(active));
  send.setAttribute("aria-label", active ? "Arrêter la réponse" : "Envoyer la question");
  send.title = active ? "Arrêter la réponse" : "Envoyer (Entrée)";
  send.innerHTML = icon(active ? "stop" : "arrow-up");
  const count = $("#char-count");
  count.hidden = input.value.length < MAX_CHARS - 150;
  count.textContent = `${formatNumber(input.value.length)} / ${formatNumber(MAX_CHARS)}`;
}

function autosize(input) {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
}

function scrollToEnd(force = false) {
  if (force) followOutput = true;
  if (!followOutput) return;
  const scroller = $("#scroller");
  scroller.scrollTop = scroller.scrollHeight;
}

// --- Rendering -------------------------------------------------------------------

function renderThread() {
  shell.setTitle(conversation.title || "Nouvelle conversation", conversation.scope);
  renderScope();
  $("#thread").innerHTML = conversation.turns.length
    ? conversation.turns.map((turn) => turnHtml(turn)).join("")
    : welcomeHtml();
  $("#jump").hidden = true;
}

function renderTurn(turn) {
  const answer = $("#thread").querySelector(`[data-turn="${turn.id}"] .answer`);
  if (!answer) return;
  answer.dataset.status = turn.status;
  answer.innerHTML = answerHtml(turn);
  scrollToEnd();
}

/** Streamed text is drawn at most once per frame, however fast tokens arrive. */
function queueText(turn) {
  if (textQueued) return;
  textQueued = true;
  requestAnimationFrame(() => {
    textQueued = false;
    const el = $("#thread").querySelector(`[data-turn="${turn.id}"] .markdown`);
    if (!el || turn.status !== "writing") return;
    el.innerHTML = markdownHtml(turn);
    scrollToEnd();
  });
}

const turnHtml = (turn, fresh = false) => `
  <article class="turn${fresh ? " is-new" : ""}" data-turn="${turn.id}">
    <div class="question"><p>${esc(turn.question)}</p></div>
    <div class="answer" data-status="${turn.status}">${answerHtml(turn)}</div>
  </article>`;

function answerHtml(turn) {
  const working = { searching: "Recherche dans vos cours…", writing: "Rédaction de la réponse…" };
  const label = working[turn.status];
  const head = `<div class="answer-head">
      <span class="avatar">${icon("activity")}</span><span class="who">MedStudy AI</span>
      ${label ? `<span class="working"><span class="pulse"></span>${label}</span>` : ""}
    </div>`;
  if (turn.status === "searching") {
    return `${head}<div class="skeleton" aria-hidden="true"><span></span><span></span><span></span></div>`;
  }
  const text = turn.answer || turn.status === "writing";
  return (
    head +
    (text ? `<div class="markdown">${markdownHtml(turn)}</div>` : "") +
    noticeHtml(turn) +
    sourcesHtml(turn) +
    actionsHtml(turn)
  );
}

function markdownHtml(turn) {
  const writing = turn.status === "writing";
  let markdown = turn.answer;
  if (writing) {
    // Close a bold span the model is still writing, so "**" never flashes on screen.
    const unclosed = (markdown.match(/\*\*/g) ?? []).length % 2 === 1;
    markdown = markdown.trimEnd() + CARET + (unclosed ? "**" : "");
  }
  const html = renderMarkdown(markdown, { cite: (n) => citeHtml(turn, n) });
  return writing ? html.replace(CARET, '<span class="caret" aria-hidden="true"></span>') : html;
}

function citeHtml(turn, n) {
  const source = turn.sources[n - 1];
  if (!source) return null; // the model cited a passage it was not given
  const where = esc(source.location);
  return `<button type="button" class="cite" data-action="cite" data-n="${n}" title="${where}" aria-label="Source ${n} : ${where}">${n}</button>`;
}

function noticeHtml(turn) {
  if (turn.status !== "error" && turn.status !== "stopped") return "";
  const failed = turn.status === "error";
  const canRetry = conversation.turns.at(-1) === turn && turn.error !== "invalid";
  const retry = canRetry
    ? `<button type="button" class="btn btn-secondary btn-sm" data-action="retry">${icon("refresh")}Réessayer</button>`
    : "";
  const message = failed ? ERRORS[turn.error] : "Réponse interrompue.";
  return `<div class="notice${failed ? " notice-error" : ""}" role="${failed ? "alert" : "status"}">
      ${icon(failed ? "alert" : "info")}<span>${message}</span>${retry}
    </div>`;
}

const citedNumbers = (answer) =>
  new Set([...answer.matchAll(CITATION)].flatMap((match) => match[1].split(",").map(Number)));

const documentPath = (source) =>
  [courseOf(shell.documentFor(source)), pathInCourse(source)].filter(Boolean).join(" › ");

/** "Où réviser": the retrieved passages grouped by document, with their exact location. */
function sourcesHtml(turn) {
  if (!turn.sources.length) return "";
  const done = turn.status !== "writing";
  const cited = citedNumbers(turn.answer);
  const anyCited = done && turn.sources.some((_, i) => cited.has(i + 1));
  const byDocument = new Map();
  turn.sources.forEach((source, i) => {
    const refs = byDocument.get(source.source) ?? [];
    byDocument.set(source.source, [...refs, { n: i + 1, source }]);
  });

  const rows = [...byDocument.values()].map((refs) => {
    const { source, title } = refs[0].source;
    const chips = refs
      .map(({ n, source: passage }) => {
        const uncited = anyCited && !cited.has(n);
        const hint = uncited ? " (consulté, non cité dans la réponse)" : "";
        return `<button type="button" class="ref${uncited ? " is-uncited" : ""}" data-action="cite" data-n="${n}" title="${esc(passage.location + hint)}"><b>${n}</b>${esc(placeOf(passage) || "extrait")}</button>`;
      })
      .join("");
    return `<li class="doc-row">
        <span class="doc-icon">${icon(fileIcon(shell.documentFor(source)))}</span>
        <span class="doc-main">
          <span class="doc-title">${esc(title)}</span>
          <span class="doc-path">${esc(documentPath(source))}</span>
        </span>
        <span class="doc-refs">${chips}</span>
      </li>`;
  });

  const label = !done || anyCited ? "Où réviser" : "Passages consultés";
  const count = `${plural(byDocument.size, "document", "documents")} · ${plural(turn.sources.length, "passage", "passages")}`;
  return `<section class="revise" aria-label="${label}">
      <div class="revise-head">
        <h3>${label}</h3><span>${count}</span>
        <button type="button" class="link-btn" data-action="cite" data-n="1">Voir les extraits</button>
      </div>
      <ul class="doc-list">${rows.join("")}</ul>
    </section>`;
}

function actionsHtml(turn) {
  if (turn.status === "writing" || !turn.answer) return "";
  const saved = savedAnswers.has(turn.id);
  return `<div class="answer-actions">
      <button type="button" class="icon-btn sm" data-action="copy" title="Copier la réponse" aria-label="Copier la réponse">${icon("copy")}</button>
      <button type="button" class="icon-btn sm${saved ? " is-on" : ""}" data-action="save" aria-pressed="${saved}" title="${saved ? "Retirer des réponses enregistrées" : "Enregistrer la réponse"}" aria-label="Enregistrer la réponse">${icon("star")}</button>
    </div>`;
}

function welcomeHtml() {
  const status = shell.status();
  const catalog = shell.catalog();
  const scope = conversation.scope;
  if (status?.chunks === 0) {
    return `<div class="welcome">
        <div class="welcome-mark is-muted">${icon("library")}</div>
        <h2>Aucun cours indexé pour l'instant</h2>
        <p>Ajoutez des documents depuis la bibliothèque, ou indexez un dossier avec
          <code>python scripts/ingest.py data/raw/drive</code>.</p>
        <button type="button" class="btn btn-primary" data-action="open-library">${icon("library")}Ouvrir la bibliothèque</button>
      </div>`;
  }
  const stats = [
    catalog && plural(catalog.documents.length, "document", "documents"),
    status && plural(status.chunks, "passage indexé", "passages indexés"),
  ].filter(Boolean);
  const suggestions = SUGGESTIONS.map(
    ([kind, question]) => `<button type="button" class="suggestion" data-action="suggest" data-question="${esc(question)}">
        <span class="suggestion-kind">${kind}</span><span>${esc(question)}</span>
      </button>`,
  ).join("");
  return `<div class="welcome">
      <div class="welcome-mark">${icon("activity")}</div>
      <h2>${scope ? "Que voulez-vous savoir sur ce cours ?" : "Que voulez-vous réviser aujourd'hui ?"}</h2>
      <p>${
        scope
          ? `Les réponses viendront uniquement de « ${esc(scope.title)} ».`
          : "Des réponses tirées de vos cours, avec la diapo ou la page exacte à revoir."
      }</p>
      ${scope ? "" : `<div class="suggestions">${suggestions}</div>`}
      ${stats.length ? `<p class="welcome-stats">${icon("library")}${stats.join(" · ")}</p>` : ""}
    </div>`;
}

// --- Source panel ----------------------------------------------------------------

function turnFor(el) {
  if (el.closest("#source-panel")) return panelTurn;
  const id = el.closest("[data-turn]")?.dataset.turn;
  if (el.closest("#saved-view")) {
    const saved = savedAnswers.get(id);
    return saved && { ...saved, status: "done" };
  }
  return conversation.turns.find((turn) => turn.id === id);
}

function openSources(turn, n) {
  if (!turn?.sources.length) return;
  panelTurn = turn;
  $("#source-subtitle").textContent = turn.question;
  $("#source-list").innerHTML = turn.sources
    .map((source, i) => passageHtml(source, i + 1, i + 1 === n))
    .join("");
  shell.openPanel();
  $("#source-list .is-current")?.scrollIntoView({ block: "nearest" });
}

function openLink(source, doc) {
  if (!doc.openable) return "";
  const kind = kindOf(source.source);
  const page = kind === "pdf" ? source.page : null;
  const labels = {
    pdf: page ? `Ouvrir à la page ${page}` : "Ouvrir le PDF",
    slides: "Télécharger la présentation",
    image: "Ouvrir l'image",
    text: "Ouvrir le fichier",
  };
  const external = kind === "pdf" || kind === "image";
  return `<a class="btn btn-secondary btn-sm" href="${esc(api.fileUrl(source.source, page))}" target="_blank" rel="noopener">${icon(external ? "external" : "download")}${labels[kind]}</a>`;
}

function passageHtml(source, n, current) {
  const doc = shell.documentFor(source.source);
  const place = placeOf(source);
  const meta = [place && capitalize(place), documentPath(source.source)].filter(Boolean).join(" · ");
  const actions = `<footer class="passage-actions">
      ${openLink(source, doc)}
      <button type="button" class="btn btn-ghost btn-sm" data-action="ask-doc" data-source="${esc(source.source)}" data-title="${esc(source.title)}">${icon("message")}Interroger ce document</button>
      <span class="score" title="Similarité entre la question et ce passage">similarité ${source.score.toFixed(2).replace(".", ",")}</span>
    </footer>`;
  return `<article class="passage${current ? " is-current" : ""}" ${
    current ? 'aria-current="true" tabindex="-1"' : `data-action="cite" data-n="${n}"`
  }>
      <header class="passage-head">
        <span class="num">${n}</span>
        <div class="passage-title"><h3>${esc(source.title)}</h3><p>${esc(meta)}</p></div>
      </header>
      <p class="excerpt">${esc(source.text)}</p>
      ${current ? actions : ""}
    </article>`;
}

// --- Answer actions --------------------------------------------------------------

async function copyAnswer(turn) {
  if (!turn) return;
  const refs = turn.sources.map((source, i) => `[${i + 1}] ${source.location}`).join("\n");
  const text = refs ? `${turn.answer.trim()}\n\nSources :\n${refs}` : turn.answer.trim();
  const copied = await copyText(text);
  toast(copied ? "Réponse copiée" : "Impossible de copier la réponse", copied ? "success" : "error");
}

function setSaveButton(button, saved) {
  button.classList.toggle("is-on", saved);
  button.setAttribute("aria-pressed", saved);
  button.title = saved ? "Retirer des réponses enregistrées" : "Enregistrer la réponse";
}

function toggleSaved(turn, button) {
  if (!turn) return;
  const saved = savedAnswers.toggle({
    id: turn.id,
    conversationId: turn.conversationId ?? conversation.id,
    question: turn.question,
    answer: turn.answer,
    sources: turn.sources,
    savedAt: Date.now(),
  });
  setSaveButton(button, saved);
  toast(saved ? "Réponse enregistrée" : "Réponse retirée des enregistrées", "success");
  shell.conversationsChanged();
}

export function renderSaved(entry) {
  const link = conversations.get(entry.conversationId)
    ? `<button type="button" class="btn btn-ghost btn-sm" data-action="open-conversation" data-id="${entry.conversationId}">${icon("message")}Ouvrir la conversation</button>`
    : "";
  $("#saved-view").innerHTML = `<div class="scroller"><div class="thread">
      <div class="saved-head">
        <span class="saved-badge">${icon("star")}Enregistrée le ${formatDate(entry.savedAt)}</span>${link}
      </div>
      ${turnHtml({ ...entry, status: "done" })}
    </div></div>`;
}

// --- Document scope --------------------------------------------------------------

export function setScope(scope) {
  conversation.scope = scope;
  if (conversation.turns.length) {
    conversations.save(conversation);
    shell.conversationsChanged();
  }
  shell.setTitle(conversation.title || "Nouvelle conversation", scope);
  renderScope();
  if (!conversation.turns.length) renderThread();
}

function renderScope() {
  const scope = conversation.scope;
  $("#scope-btn").classList.toggle("is-scoped", Boolean(scope));
  $("#scope-btn").title = scope ? `Questions limitées à « ${scope.title} »` : "Limiter la recherche à un document";
  $("#scope-label").textContent = scope ? scope.title : "Tous les cours";
  $("#scope-clear").hidden = !scope;
}

function initScopeMenu() {
  const menu = $("#scope-menu");
  const search = $("#scope-search");
  onAction("pick-scope", () => (menu.hidden ? openScopeMenu() : closeScopeMenu()));
  search.addEventListener("input", () => {
    highlighted = 0;
    renderScopeOptions();
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      highlighted = (highlighted + step + scopeOptions.length) % scopeOptions.length;
      renderScopeOptions(false);
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseScope(scopeOptions[highlighted]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeScopeMenu();
      $("#scope-btn").focus();
    }
  });
  $("#scope-options").addEventListener("click", (event) => {
    const option = event.target.closest("[data-index]");
    if (option) chooseScope(scopeOptions[Number(option.dataset.index)]);
  });
  document.addEventListener("pointerdown", (event) => {
    if (menu.hidden || menu.contains(event.target) || $("#scope-btn").contains(event.target)) return;
    closeScopeMenu();
  });
}

function openScopeMenu() {
  $("#scope-menu").hidden = false;
  $("#scope-btn").setAttribute("aria-expanded", "true");
  $("#scope-search").value = "";
  highlighted = 0;
  renderScopeOptions();
  $("#scope-search").focus();
}

function closeScopeMenu() {
  $("#scope-menu").hidden = true;
  $("#scope-btn").setAttribute("aria-expanded", "false");
}

function renderScopeOptions(filter = true) {
  const catalog = shell.catalog();
  if (filter) {
    const query = searchKey($("#scope-search").value.trim());
    const documents = (catalog?.documents ?? []).filter(
      (doc) => !query || searchKey(`${doc.title} ${doc.source}`).includes(query),
    );
    scopeOptions = [null, ...documents.slice(0, 80)];
  }
  const current = conversation.scope?.source ?? null;
  const options = scopeOptions.map((doc, i) => {
    const selected = (doc?.source ?? null) === current;
    return `<li role="option" id="scope-option-${i}" data-index="${i}" aria-selected="${i === highlighted}" class="${selected ? "is-current" : ""}">
        <span>${doc ? esc(doc.title) : "Tous les cours"}</span>
        <small>${doc ? esc(courseOf(doc)) : "Chercher dans tous les documents"}</small>
      </li>`;
  });
  if (!catalog) {
    const note = catalog === null ? "Bibliothèque indisponible" : "Chargement des documents…";
    options.push(`<li class="menu-note">${note}</li>`);
  } else if (scopeOptions.length === 1) {
    options.push('<li class="menu-note">Aucun document ne correspond.</li>');
  }
  $("#scope-options").innerHTML = options.join("");
  $("#scope-search").setAttribute("aria-activedescendant", `scope-option-${highlighted}`);
  $(`#scope-option-${highlighted}`)?.scrollIntoView({ block: "nearest" });
}

function chooseScope(doc) {
  setScope(doc ? { source: doc.source, title: doc.title } : null);
  closeScopeMenu();
  $("#question").focus();
}
