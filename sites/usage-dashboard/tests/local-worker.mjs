import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = fileURLToPath(new URL("../", import.meta.url));
const WRANGLER = path.join(SITE, "node_modules", "wrangler", "bin", "wrangler.js");

function freePort() {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.unref();
    listener.on("error", reject);
    listener.listen(0, "127.0.0.1", () => {
      const address = listener.address();
      listener.close(() => resolve(address.port));
    });
  });
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function stopWorker(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null || !child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
    });
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
  }
  // Wait for the child to release its pipes and state directory on Windows.
  if (child.exitCode === null && child.signalCode === null) {
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, 5_000);
      child.once("exit", () => { clearTimeout(timer); resolve(); });
    });
  }
}

export async function startLocalWorker() {
  const port = await freePort();
  const statePath = mkdtempSync(path.join(os.tmpdir(), "usage-worker-test-"));
  const origin = `http://127.0.0.1:${port}`;
  let recentOutput = "";
  const child = spawn(process.execPath, [
    WRANGLER, "dev", "--config", "dist/server/wrangler.json",
    "--ip", "127.0.0.1", "--port", String(port),
    "--local", "--persist-to", statePath,
    "--show-interactive-dev-session=false",
  ], {
    cwd: SITE,
    detached: process.platform !== "win32",
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  for (const stream of [child.stdout, child.stderr]) {
    stream.on("data", (chunk) => {
      recentOutput = (recentOutput + chunk.toString()).slice(-4000);
    });
  }
  const close = async () => {
    await stopWorker(child);
    rmSync(statePath, { recursive: true, force: true, maxRetries: 8, retryDelay: 150 });
  };
  try {
    const until = Date.now() + 35_000;
    while (Date.now() < until) {
      if (child.exitCode !== null) break;
      try {
        const response = await fetch(origin + "/", { cache: "no-store" });
        if (response.status >= 100 && response.status <= 599) {
          return {
            fetch: (request) => {
              const target = new URL(request.url);
              return fetch(origin + target.pathname + target.search, {
                headers: request.headers,
                redirect: "manual",
                cache: "no-store",
              });
            },
            close,
          };
        }
      } catch {
        // Local Wrangler starts asynchronously.
      }
      await delay(200);
    }
    throw new Error(`Local Worker not ready: ${recentOutput.slice(-1800)}`);
  } catch (error) {
    await close();
    throw error;
  }
}
