import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import { startLocalWorker } from "./local-worker.mjs";

let worker;
test.before(async () => { worker = await startLocalWorker(); });
test.after(async () => { await worker?.close(); });

test("property: arbitrary request paths never crash the dashboard worker", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.array(fc.constantFrom(..."abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"), { maxLength: 80 })
        .map((parts) => parts.join("")),
      async (segment) => {
        const response = await worker.fetch(
          new Request(`http://localhost/${segment}`, { headers: { accept: "text/html" } }),
        );
        assert.ok(response instanceof Response);
        assert.ok(response.status >= 100 && response.status <= 599);
      },
    ),
    { numRuns: 100 },
  );
});
