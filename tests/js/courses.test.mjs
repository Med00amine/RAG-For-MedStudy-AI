import assert from "node:assert/strict";
import { test } from "node:test";

import { courseCounts, courseOf, pathInCourse, placeOf } from "../../app/static/courses.js";

const HPP = "DCEM2 2026_2027/S1/C1_ Gynéco_obstét/Obstétrique/HPP.pptx";
const HTA = "C2_ Médecine d'urgence + Médecine interne +/M1_ Médecine d'urgence/1-HTA.pptx";

test("courses are named after the first folder that is not a year or semester", () => {
  assert.equal(courseOf({ source: HPP }), "C1 · Gynéco obstét");
  assert.equal(courseOf({ source: HTA }), "C2 · Médecine d'urgence + Médecine interne");
  assert.equal(courseOf({ source: "DCEM2 2026_2027/stage/Gastro/Chir/x.pdf" }), "Stage");
  assert.equal(courseOf({ source: "DCEM2 2026_2027/Books/Uro.pdf", textbook: true }), "Manuels");
  assert.equal(courseOf({ source: "notes.pdf" }), "Documents ajoutés");
});

test("the path inside a course skips the course itself", () => {
  assert.equal(pathInCourse(HTA), "M1 · Médecine d'urgence");
  assert.equal(pathInCourse(HPP), "Obstétrique");
  assert.equal(pathInCourse("notes.pdf"), "");
});

test("course counts put textbooks last", () => {
  const docs = [
    { source: "DCEM2 2026_2027/Books/a.pdf", textbook: true },
    { source: HTA },
    { source: HPP },
    { source: HPP.replace("HPP", "DIU") },
  ];

  assert.deepEqual(courseCounts(docs), [
    ["C1 · Gynéco obstét", 2],
    ["C2 · Médecine d'urgence + Médecine interne", 1],
    ["Manuels", 1],
  ]);
});

test("the place is the server's location without the title", () => {
  assert.equal(placeOf({ location: "HTA — diapo 12", page: 12 }), "diapo 12");
  assert.equal(placeOf({ location: "Notes — A — page 3", page: 3 }), "page 3");
  assert.equal(placeOf({ location: "Notes", page: null }), "");
});
