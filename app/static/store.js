// Conversations, saved answers and preferences stay in this browser (localStorage): the
// server keeps no chat history. Storage may be unavailable (private browsing, blocked
// site data), in which case everything still works for the current visit.

const PREFIX = "medstudy.";
const MAX_CONVERSATIONS = 50;

export const persistent = (() => {
  try {
    localStorage.setItem(`${PREFIX}probe`, "1");
    localStorage.removeItem(`${PREFIX}probe`);
    return true;
  } catch {
    return false;
  }
})();

function read(key, fallback) {
  if (!persistent) return fallback;
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  if (!persistent) return false;
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
    return true;
  } catch {
    return false; // quota exceeded
  }
}

export const prefs = {
  get: (name, fallback) => read(name, fallback),
  set: (name, value) => write(name, value),
};

let allConversations = read("conversations", []);
let allSaved = read("saved", []);
// An answer still streaming when its conversation is deleted saves it once it stops:
// those saves are ignored, so deleted conversations never come back.
const removed = new Set();
let clearedAt = 0;

export const conversations = {
  list: () => allConversations,
  get: (id) => allConversations.find((c) => c.id === id),

  /** Returns false when older conversations had to be left out to fit the quota. */
  save(conversation) {
    if (removed.has(conversation.id) || conversation.createdAt < clearedAt) return true;
    allConversations = [conversation, ...allConversations.filter((c) => c.id !== conversation.id)]
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    let kept = allConversations;
    while (kept.length && !write("conversations", kept)) kept = kept.slice(0, -1);
    return !persistent || kept.length === allConversations.length;
  },

  remove(id) {
    removed.add(id);
    allConversations = allConversations.filter((c) => c.id !== id);
    write("conversations", allConversations);
  },

  clear() {
    clearedAt = Date.now();
    allConversations = [];
    write("conversations", allConversations);
  },
};

export const savedAnswers = {
  list: () => allSaved,
  get: (id) => allSaved.find((s) => s.id === id),
  has: (id) => allSaved.some((s) => s.id === id),

  /** Saves the answer, or removes it if it was saved. Returns whether it is now saved. */
  toggle(entry) {
    const saved = this.has(entry.id);
    allSaved = saved ? allSaved.filter((s) => s.id !== entry.id) : [entry, ...allSaved];
    write("saved", allSaved);
    return !saved;
  },

  clear() {
    allSaved = [];
    write("saved", allSaved);
  },
};
