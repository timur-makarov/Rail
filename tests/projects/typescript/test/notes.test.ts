import assert from "node:assert/strict";
import { test } from "node:test";

import { Notes } from "../src/notes.ts";

test("notes are kept in the order they were added", () => {
  const notes = new Notes();
  notes.add("write the report");
  notes.add("send it");
  assert.deepEqual(notes.all().map((note) => note.title), ["write the report", "send it"]);
});

test("a note with no title is refused", () => {
  assert.throws(() => new Notes().add(""), /a note needs a title/);
});

test("finishing marks one note", () => {
  const notes = new Notes();
  const first = notes.add("write the report");
  notes.add("send it");
  assert.equal(notes.finish(first.id), true);
  assert.deepEqual(notes.all().map((note) => note.done), [true, false]);
  assert.equal(notes.finish(99), false);
});
