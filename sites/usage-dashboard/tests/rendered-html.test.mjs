import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the private aggregate dashboard shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="ja">/i);
  assert.match(html, /<title>ChatGPT 利用ダッシュボード<\/title>/i);
  assert.match(html, /会話本文を含まない集計データを読み込んでいます/);
  assert.match(html, /name="robots" content="noindex, nofollow, nocache"/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("keeps the public source surface minimal and local-only", async () => {
  const [page, layout, css, packageJson, publicFiles] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readdir(new URL("../public/", import.meta.url)),
  ]);

  assert.deepEqual(publicFiles.sort(), ["favicon.svg", "usage-data.json"]);
  assert.match(page, /fetch\("\/usage-data\.json"/);
  assert.match(page, /月ごとの送信回数/);
  assert.match(page, /日別送信回数/);
  assert.match(page, /選択月サマリー/);
  assert.match(page, /全期間サマリー/);
  assert.match(page, /音声を除く/);
  assert.match(page, /音声のみ/);
  assert.match(page, /1日平均/);
  assert.match(page, /最大/);
  assert.match(page, /最小/);
  assert.doesNotMatch(page, /3時間|gpt_3h/i);
  assert.doesNotMatch(page, /https?:\/\/|chatgpt-usage-dashboard-33/i);
  assert.doesNotMatch(layout, /next\/font|codex-preview|_sites-preview|chatgpt-usage-dashboard-33/i);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|drizzle/i);
  assert.match(css, /@media \(max-width: 820px\)/);
  assert.match(css, /@media \(max-width: 560px\)/);
  assert.match(css, /Noto Sans JP/);
  assert.match(page, /横スクロールせず月全体/);
  assert.match(css, /--daily-columns: 16/);
  assert.match(css, /--daily-columns: 8/);
  assert.match(css, /flex-wrap: wrap/);
  assert.match(css, /order: -1/);
  assert.match(css, /user-select: none/);
});
