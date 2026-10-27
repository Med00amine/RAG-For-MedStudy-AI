import assert from "node:assert/strict";
import { test } from "node:test";

import { renderMarkdown } from "../../app/static/markdown.js";

const cite = (n) => (n <= 3 ? `<cite ${n}>` : null);

test("model output cannot inject HTML", () => {
  const html = renderMarkdown('<img src=x onerror="alert(1)"> **gras**');

  assert.equal(
    html,
    "<p>&lt;img src=x onerror=&quot;alert(1)&quot;&gt; <strong>gras</strong></p>",
  );
});

test("nested lists keep their structure and numbering", () => {
  const md = "1. **Réponse** :\n   - Onde T [1]\n   - PR\n\n2. **Exemple** : cas";

  assert.equal(
    renderMarkdown(md),
    "<ol><li><strong>Réponse</strong> :<ul><li>Onde T [1]</li><li>PR</li></ul></li>" +
      "<li><strong>Exemple</strong> : cas</li></ol>",
  );
});

test("numbering resumes after unindented bullets", () => {
  const html = renderMarkdown("1. Réponse\n- a\n- b\n2. Exemple");

  assert.equal(html, '<ol><li>Réponse</li></ol><ul><li>a</li><li>b</li></ul><ol start="2"><li>Exemple</li></ol>');
});

test("headings open named sections", () => {
  const html = renderMarkdown("### Réponse\nTexte.\n\n**Exemple clinique**\nCas.");

  assert.equal(
    html,
    '<section class="md-section" data-section="reponse"><h3>Réponse</h3><p>Texte.</p></section>' +
      '<section class="md-section" data-section="exemple-clinique"><h3>Exemple clinique</h3>' +
      "<p>Cas.</p></section>",
  );
});

test("only citations of retrieved passages become badges", () => {
  const html = renderMarkdown("Onde T [1, 2], QRS [3] et PR [9].", { cite });

  assert.equal(html, "<p>Onde T <cite 1><cite 2>, QRS <cite 3> et PR [9].</p>");
});

test("code spans are left untouched", () => {
  assert.equal(renderMarkdown("`**x** [1]`", { cite }), "<p><code>**x** [1]</code></p>");
});

test("tables are wrapped so they scroll on small screens", () => {
  const html = renderMarkdown("| Type | Gharbi |\n|---|:---:|\n| CE1 | I [1] |", { cite });

  assert.equal(
    html,
    '<div class="table-wrap"><table><thead><tr><th>Type</th><th style="text-align:center">Gharbi</th></tr></thead>' +
      '<tbody><tr><td>CE1</td><td style="text-align:center">I <cite 1></td></tr></tbody></table></div>',
  );
});

test("paragraph lines are joined, quotes and rules are kept", () => {
  assert.equal(
    renderMarkdown("Une\nphrase.\n\n> Note\n\n---"),
    "<p>Une phrase.</p><blockquote><p>Note</p></blockquote><hr>",
  );
});
