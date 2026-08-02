import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = fileURLToPath(new URL("../", import.meta.url));
const VINEXT = path.join(SITE, "node_modules", "vinext", "dist", "cli.js");
const ARTIFACT_DIR = path.join(SITE, ".npm-cache", "mobile-ui-test");

function findBrowser() {
  const candidates = [];
  if (process.env.CHROME_PATH) candidates.push(process.env.CHROME_PATH);

  if (process.platform === "win32") {
    candidates.push(
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
    );
  } else if (process.platform === "darwin") {
    candidates.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    );
  } else {
    for (const command of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
      const result = spawnSync("which", [command], { encoding: "utf8" });
      if (result.status === 0 && result.stdout.trim()) candidates.push(result.stdout.trim());
    }
  }

  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolvePort(port));
    });
  });
}

async function waitFor(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) return response;
    } catch {
      // Retry until the local process is ready.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

class CdpClient {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.socket = null;
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    await new Promise((resolveConnect, reject) => {
      this.socket.addEventListener("open", resolveConnect, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) return;
      const request = this.pending.get(message.id);
      if (!request) return;
      this.pending.delete(message.id);
      if (message.error) request.reject(new Error(message.error.message));
      else request.resolve(message.result ?? {});
    });
  }

  call(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolveCall, reject) => {
      this.pending.set(id, { resolve: resolveCall, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.call("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
    return result.result?.value;
  }

  close() {
    this.socket?.close();
  }
}

function stopProcess(child) {
  if (!child || child.exitCode !== null || !child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
    });
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
}

async function waitForDashboard(cdp) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const ready = await cdp.evaluate(
      "document.readyState === 'complete' && document.querySelectorAll('.daily-bars > div').length >= 28 && Boolean(document.querySelector('.activity-scroll'))",
    );
    if (ready) return;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
  }
  throw new Error("Dashboard did not finish rendering");
}

async function captureFailure(cdp) {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  const result = await cdp.call("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  const target = path.join(ARTIFACT_DIR, "mobile-ui-failure.png");
  writeFileSync(target, Buffer.from(result.data, "base64"));
  return target;
}

async function main() {
  const browserPath = findBrowser();
  if (!browserPath) throw new Error("Chrome, Chromium, or Brave was not found. Set CHROME_PATH to run the mobile UI test.");

  const [sitePort, debugPort] = await Promise.all([freePort(), freePort()]);
  const profile = mkdtempSync(path.join(os.tmpdir(), "chatgpt-usage-mobile-ui-"));
  let server = null;
  let browser = null;
  let cdp = null;

  try {
    server = spawn(process.execPath, [VINEXT, "start", "--hostname", "127.0.0.1", "--port", String(sitePort)], {
      cwd: SITE,
      detached: process.platform !== "win32",
      stdio: "ignore",
      windowsHide: true,
    });
    await waitFor(`http://127.0.0.1:${sitePort}/`);

    const browserArgs = [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--remote-allow-origins=*",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profile}`,
      "--window-size=390,844",
      `http://127.0.0.1:${sitePort}/`,
    ];
    if (process.platform === "linux") browserArgs.unshift("--no-sandbox");

    browser = spawn(browserPath, browserArgs, {
      detached: process.platform !== "win32",
      stdio: "ignore",
      windowsHide: true,
    });

    await waitFor(`http://127.0.0.1:${debugPort}/json/version`);
    const pages = await (await waitFor(`http://127.0.0.1:${debugPort}/json/list`)).json();
    const page = pages.find((entry) => entry.type === "page");
    if (!page?.webSocketDebuggerUrl) throw new Error("No browser page target was available");

    cdp = new CdpClient(page.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.call("Page.enable");
    await cdp.call("Runtime.enable");
    await cdp.call("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await cdp.call("Page.reload", { ignoreCache: true });
    await waitForDashboard(cdp);
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));

    const initial = await cdp.evaluate(`(() => {
      const describe = (selector) => {
        const element = document.querySelector(selector);
        if (!element) return null;
        const style = getComputedStyle(element);
        const maxScroll = Math.max(0, element.scrollWidth - element.clientWidth);
        return {
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          scrollLeft: element.scrollLeft,
          maxScroll,
          hasInternalOverflow: maxScroll > 10,
          atEnd: Math.abs(element.scrollLeft - maxScroll) <= 3,
          scrollbarWidth: style.scrollbarWidth,
          overflowX: style.overflowX,
          frameClass: element.parentElement?.className ?? "",
        };
      };
      const root = document.documentElement;
      const weekday = document.querySelector('.heatmap-row > strong');
      return {
        viewport: [innerWidth, innerHeight],
        pageHasHorizontalScroll: root.scrollWidth > root.clientWidth + 1,
        daily: describe('.daily-scroll'),
        heatmap: describe('.heatmap-scroll'),
        activity: describe('.activity-scroll'),
        weekdayPosition: weekday ? getComputedStyle(weekday).position : null,
        dailyCount: document.querySelectorAll('.daily-bars > div').length,
        heatmapCount: document.querySelectorAll('.heatmap-row > div > span').length,
      };
    })()`);

    await cdp.evaluate(`(() => {
      const element = document.querySelector('.daily-scroll');
      element.scrollLeft = 0;
      element.dispatchEvent(new Event('scroll'));
      return true;
    })()`);
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 120));

    const afterSwipe = await cdp.evaluate(`(() => {
      const element = document.querySelector('.daily-scroll');
      return {
        scrollLeft: element.scrollLeft,
        frameClass: element.parentElement?.className ?? "",
      };
    })()`);

    await cdp.evaluate("document.querySelectorAll('.mode-switch button')[2].click()");
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 120));
    const activeMode = await cdp.evaluate("document.querySelector('.mode-switch button[aria-pressed=\"true\"]')?.textContent?.trim() ?? ''");

    await cdp.evaluate(`(() => {
      const select = document.querySelector('.period-select select');
      select.value = '2025-12';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()`);
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
    const afterMonthChange = await cdp.evaluate(`(() => {
      const select = document.querySelector('.period-select select');
      const daily = document.querySelector('.daily-scroll');
      const maxScroll = Math.max(0, daily.scrollWidth - daily.clientWidth);
      return {
        selectedMonth: select.value,
        summaryTitle: document.querySelector('.summary-panel h2')?.textContent?.trim() ?? '',
        dailyAtEnd: Math.abs(daily.scrollLeft - maxScroll) <= 3,
      };
    })()`);

    const checks = {
      viewport: initial.viewport[0] === 390 && initial.viewport[1] === 844,
      page_no_horizontal_scroll: !initial.pageHasHorizontalScroll,
      daily_is_internal_scroll: initial.daily?.hasInternalOverflow && initial.daily?.overflowX === "auto",
      daily_starts_at_latest: initial.daily?.atEnd,
      daily_left_hint_at_latest: initial.daily?.frameClass.includes("can-scroll-left") && !initial.daily?.frameClass.includes("can-scroll-right"),
      daily_hint_updates_after_swipe: afterSwipe.scrollLeft <= 1 && afterSwipe.frameClass.includes("can-scroll-right") && !afterSwipe.frameClass.includes("can-scroll-left"),
      heatmap_is_internal_scroll: initial.heatmap?.hasInternalOverflow && initial.heatmap?.overflowX === "auto",
      activity_is_internal_scroll: initial.activity?.hasInternalOverflow && initial.activity?.overflowX === "auto",
      native_scrollbars_hidden: [initial.daily, initial.heatmap, initial.activity].every((entry) => entry?.scrollbarWidth === "none"),
      weekday_labels_sticky: initial.weekdayPosition === "sticky",
      complete_daily_data: [28, 29, 30, 31].includes(initial.dailyCount),
      complete_heatmap_data: initial.heatmapCount === 168,
      mode_switch_works: activeMode === "音声のみ",
      month_switch_works: afterMonthChange.selectedMonth === "2025-12" && afterMonthChange.summaryTitle.includes("2025年12月"),
      month_switch_resets_daily_to_latest: afterMonthChange.dailyAtEnd,
    };

    const failures = Object.entries(checks).filter(([, passed]) => !passed);
    if (failures.length === 0) {
      console.log("PASS mobile dashboard: contained swipes, latest-day start, hidden scrollbars, sticky labels, working controls");
      return;
    }

    const artifact = await captureFailure(cdp);
    for (const [name] of failures) console.error(`FAIL ${name}`);
    console.error(`Artifact: ${artifact}`);
    process.exitCode = 1;
  } finally {
    cdp?.close();
    stopProcess(browser);
    stopProcess(server);
    rmSync(profile, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(`FAIL mobile dashboard: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
