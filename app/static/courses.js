// Course structure derived from the indexed file paths, which mirror the class drives:
// "DCEM2 2026_2027/S1/C1_ Gynéco_obstét/Obstétrique/HPP.pptx".

// Year and semester folders organise the drives but name no subject.
const CONTAINER = /^(S\d{1,2}|.*(?<!\d)(19|20)\d\d(?!\d).*)$/i;
const TEXTBOOKS = "Manuels";
const UPLOADS = "Documents ajoutés";

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** "C1_ Gynéco_obstét" -> "C1 · Gynéco obstét" */
export function tidy(folder) {
  const name = folder
    .replace(/[_\s]+/g, " ")
    .replace(/[\s+\-–]+$/, "")
    .trim();
  const code = name.match(/^([CM]\d+)\s+(.+)$/);
  return code ? `${code[1]} · ${capitalize(code[2])}` : capitalize(name);
}

const folders = (source) => source.split("/").slice(0, -1);
const courseIndex = (parts) => parts.findIndex((part) => !CONTAINER.test(part));

/** The course a document belongs to: its first folder that is not a year or semester. */
export function courseOf({ source, textbook = false }) {
  if (textbook) return TEXTBOOKS;
  const parts = folders(source);
  const start = courseIndex(parts);
  return start === -1 ? UPLOADS : tidy(parts[start]);
}

/** Folders below the course: "Néphro › ED". */
export function pathInCourse(source) {
  const parts = folders(source);
  const start = courseIndex(parts);
  return start === -1 ? "" : parts.slice(start + 1).map(tidy).join(" › ");
}

/** Courses with their document counts, textbooks last. */
export function courseCounts(documents) {
  const counts = new Map();
  for (const doc of documents) counts.set(courseOf(doc), (counts.get(courseOf(doc)) ?? 0) + 1);
  const rank = (name) => (name === TEXTBOOKS ? 1 : 0);
  return [...counts].sort(
    ([a], [b]) => rank(a) - rank(b) || a.localeCompare(b, "fr", { numeric: true }),
  );
}

/** "HTA — diapo 12" -> "diapo 12": the location the server computed, without the title. */
export function placeOf({ location, page }) {
  return page == null ? "" : location.slice(location.lastIndexOf(" — ") + 3);
}

/** pdf, slides, image or text: picks the file icon. */
export function kindOf(source) {
  const ext = source.slice(source.lastIndexOf(".") + 1).toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "ppt" || ext === "pptx") return "slides";
  if (["png", "jpg", "jpeg"].includes(ext)) return "image";
  return "text";
}

/** Case- and accent-insensitive search key. */
export const searchKey = (text) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
