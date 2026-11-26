// The app driven over a real socket, as a browser or a client would use it.
import assert from "node:assert/strict";
import { after, before, test } from "node:test";

import { serve } from "../bin/serve.mjs";
import { app } from "../src/app.ts";

let server: { address(): { port: number }; close(): void };
let url = "";

before(async () => {
  server = await serve(app());
  url = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

async function post(path: string, body?: unknown): Promise<[number, unknown]> {
  const answer = await fetch(url + path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  return [answer.status, await answer.json()];
}

test("a created note is listed by the API and shown on the page", async () => {
  assert.deepEqual(await post("/api/notes", { title: "write <the> report" }), [
    201,
    { id: 1, title: "write <the> report", done: false },
  ]);
  const listed = await (await fetch(url + "/api/notes")).json();
  assert.deepEqual(listed, [{ id: 1, title: "write <the> report", done: false }]);
  const page = await (await fetch(url + "/")).text();
  assert.match(page, /<li>write &lt;the&gt; report<\/li>/);
});

test("a note with no title is a 400", async () => {
  assert.deepEqual(await post("/api/notes", {}), [400, { error: "a note needs a title" }]);
  assert.deepEqual(await post("/api/notes"), [400, { error: "the body is not JSON" }]);
});

test("a note is finished once, and an unknown one is a 404", async () => {
  assert.deepEqual(await post("/api/notes/1/done"), [200, { done: true }]);
  assert.deepEqual(await post("/api/notes/7/done"), [404, { done: false }]);
  assert.equal((await fetch(url + "/nowhere")).status, 404);
  const page = await (await fetch(url + "/")).text();
  assert.match(page, /<li class="done">/);
});
