import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("fuzz", `${process.pid}-${Date.now()}`);
  return (await import(workerUrl.href)).default;
}

test("property: arbitrary request paths never crash the dashboard worker", async () => {
  const worker = await loadWorker();
  await fc.assert(
    fc.asyncProperty(
      fc.array(fc.constantFrom(..."abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"), { maxLength: 80 })
        .map((parts) => parts.join("")),
      async (segment) => {
        const response = await worker.fetch(
          new Request(`http://localhost/${segment}`, { headers: { accept: "text/html" } }),
          { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
          { waitUntil() {}, passThroughOnException() {} },
        );
        assert.ok(response instanceof Response);
        assert.ok(response.status >= 100 && response.status <= 599);
      },
    ),
    { numRuns: 100 },
  );
});
