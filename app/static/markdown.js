// A small, safe Markdown renderer for model answers.
// The whole answer is HTML-escaped first, so it can never inject markup: only the tags
// below are produced. Citations such as [2] or [1, 3] are drawn by the caller's `cite`
// callback, which returns null for a number that matches no retrieved passage.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const slug = (text) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const FENCE = /^\s*```/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const BOLD_HEADING = /^\*\*([^*]{1,60})\*\*\s*:?\s*$/; // "**Réponse**" alone on its line
const RULE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const ITEM = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
const QUOTE = /^\s{0,3}&gt;\s?(.*)$/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$/;
export const CITATION = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

function inline(text, cite) {
  return text
    .split(/(`[^`]+`)/)
    .map((part, i) =>
      i % 2
        ? `<code>${part.slice(1, -1)}</code>`
        : part
            .replace(/\*\*(?=\S)(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/(^|[\s(«])[*_](?=\S)(.+?)[*_](?=$|[\s.,;:!?)»])/g, "$1<em>$2</em>")
            .replace(CITATION, (match, list) => {
              const badges = list.split(",").map((n) => cite(Number(n)));
              return badges.every(Boolean) ? badges.join("") : match;
            }),
    )
    .join("");
}

const cells = (row) =>
  row
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());

export function renderMarkdown(markdown, { cite = () => null } = {}) {
  const lines = escapeHtml(markdown).replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  const lists = []; // open lists, innermost last: { tag, indent }
  let paragraph = [];
  let inSection = false;
  let blank = false; // the previous line was empty
  const format = (text) => inline(text, cite);

  const endParagraph = () => {
    if (paragraph.length) html.push(`<p>${format(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const closeLists = (indent = -1) => {
    while (lists.length && lists.at(-1).indent > indent) html.push(`</li></${lists.pop().tag}>`);
  };
  const endBlocks = () => {
    endParagraph();
    closeLists();
  };
  // Level 1-3 headings start a section, so the UI can style "Astuce" or "Exemple clinique".
  const heading = (level, text) => {
    endBlocks();
    if (level <= 3) {
      if (inSection) html.push("</section>");
      html.push(`<section class="md-section" data-section="${slug(text)}">`);
      inSection = true;
    }
    const tag = level <= 3 ? "h3" : "h4";
    html.push(`<${tag}>${format(text)}</${tag}>`);
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (FENCE.test(line)) {
      endBlocks();
      const code = [];
      while (++i < lines.length && !FENCE.test(lines[i])) code.push(lines[i]);
      html.push(`<pre><code>${code.join("\n")}</code></pre>`);
      blank = false;
      continue;
    }
    if (!line.trim()) {
      endParagraph();
      blank = true;
      continue;
    }

    const title = line.match(HEADING) ?? line.match(BOLD_HEADING);
    if (title) {
      title.length > 2 ? heading(title[1].length, title[2]) : heading(3, title[1]);
      blank = false;
      continue;
    }
    if (RULE.test(line)) {
      endBlocks();
      html.push("<hr>");
      blank = false;
      continue;
    }

    const item = line.match(ITEM);
    if (item) {
      endParagraph();
      const indent = item[1].replace(/\t/g, "    ").length;
      const tag = /\d/.test(item[2]) ? "ol" : "ul";
      closeLists(indent);
      if (lists.at(-1)?.indent === indent && lists.at(-1).tag !== tag) {
        html.push(`</li></${lists.pop().tag}>`);
      }
      if (lists.at(-1)?.indent === indent) {
        html.push(`</li><li>${format(item[3])}`);
      } else {
        // Keep "2. Exemple" numbered 2 when bullets in between closed the first list.
        const start = tag === "ol" ? parseInt(item[2], 10) : 1;
        html.push(`<${tag}${start > 1 ? ` start="${start}"` : ""}><li>${format(item[3])}`);
        lists.push({ tag, indent });
      }
      blank = false;
      continue;
    }

    const quote = line.match(QUOTE);
    if (quote) {
      endBlocks();
      const body = [quote[1]];
      while (i + 1 < lines.length && QUOTE.test(lines[i + 1])) body.push(lines[++i].match(QUOTE)[1]);
      html.push(`<blockquote><p>${format(body.join(" "))}</p></blockquote>`);
      blank = false;
      continue;
    }

    if (line.includes("|") && TABLE_DIVIDER.test(lines[i + 1] ?? "")) {
      endBlocks();
      const align = cells(lines[i + 1]).map((c) =>
        c.endsWith(":") ? (c.startsWith(":") ? "center" : "right") : "",
      );
      const row = (text, tag) =>
        `<tr>${cells(text)
          .map((c, k) => `<${tag}${align[k] ? ` style="text-align:${align[k]}"` : ""}>${format(c)}</${tag}>`)
          .join("")}</tr>`;
      const head = row(line, "th");
      const body = [];
      i += 1;
      while (i + 1 < lines.length && lines[i + 1].includes("|")) body.push(row(lines[++i], "td"));
      html.push(
        `<div class="table-wrap"><table><thead>${head}</thead><tbody>${body.join("")}</tbody></table></div>`,
      );
      blank = false;
      continue;
    }

    // Text right under a list item, or indented below it, belongs to that item.
    if (lists.length && (!blank || /^\s{2,}/.test(line))) {
      html.push(`${blank ? "<br>" : " "}${format(line.trim())}`);
      blank = false;
      continue;
    }

    closeLists();
    paragraph.push(line.trim());
    blank = false;
  }
  endBlocks();
  if (inSection) html.push("</section>");
  return html.join("");
}
