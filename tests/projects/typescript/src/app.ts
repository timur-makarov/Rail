import { Notes } from "./notes.ts";

const DONE = /^\/api\/notes\/(\d+)\/done$/;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function escape(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function page(notes: Notes): Response {
  const rows = notes.all().map((note) => `<li${note.done ? ' class="done"' : ""}>${escape(note.title)}</li>`);
  const html = `<!doctype html><title>Notes</title><h1>Notes</h1><ul>${rows.join("")}</ul>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function create(notes: Notes, request: Request): Promise<Response> {
  let title: unknown;
  try {
    title = ((await request.json()) as { title?: unknown }).title;
  } catch {
    return json(400, { error: "the body is not JSON" });
  }
  if (typeof title !== "string" || title === "") {
    return json(400, { error: "a note needs a title" });
  }
  return json(201, notes.add(title));
}

/** The app: GET / is the page; GET and POST /api/notes and POST /api/notes/ID/done are the API. */
export function app(notes: Notes = new Notes()): (request: Request) => Promise<Response> {
  return async (request) => {
    const path = new URL(request.url).pathname;
    const done = DONE.exec(path);
    if (request.method === "GET" && path === "/") {
      return page(notes);
    }
    if (request.method === "GET" && path === "/api/notes") {
      return json(200, notes.all());
    }
    if (request.method === "POST" && path === "/api/notes") {
      return create(notes, request);
    }
    if (request.method === "POST" && done !== null) {
      const found = notes.finish(Number(done[1]));
      return json(found ? 200 : 404, { done: found });
    }
    return json(404, { error: "not found" });
  };
}
