// node bin/serve.mjs [PORT]: serve the app. serve(handle, port) is also what the tests start.
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

export function serve(handle, port = 0) {
  const server = createServer(async (incoming, outgoing) => {
    const chunks = [];
    for await (const chunk of incoming) {
      chunks.push(chunk);
    }
    const body = incoming.method === "GET" || incoming.method === "HEAD" ? undefined : Buffer.concat(chunks);
    const request = new Request(`http://${incoming.headers.host}${incoming.url}`, {
      method: incoming.method,
      headers: incoming.headers,
      body,
    });
    const response = await handle(request);
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { app } = await import("../src/app.ts");
  const handle = app();
  // A fault to switch on from outside, for a check that drives the running app: the list comes back empty.
  const faulty = (request) =>
    request.method === "GET" && new URL(request.url).pathname === "/api/notes" ? Response.json([]) : handle(request);
  const server = await serve(process.env.NOTES_FAULT ? faulty : handle, Number(process.argv[2] ?? 8000));
  console.log(`notes on http://127.0.0.1:${server.address().port}`);
}
