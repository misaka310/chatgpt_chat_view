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

test("keeps the public source surface minimal, reference-aligned, responsive, and local-only", async () => {
  const [page, layout, css, packageJson, npmConfig, publicFiles] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../.npmrc", import.meta.url), "utf8"),
    readdir(new URL("../public/", import.meta.url)),
  ]);

  assert.deepEqual(publicFiles.sort(), ["favicon.svg", "usage-data.json"]);
  assert.match(page, /fetch\("\/usage-data\.json"/);
  assert.match(page, /送信分析ダッシュボード/);
  assert.match(page, /月ごとの送信回数/);
  assert.match(page, /日別送信回数/);
  assert.match(page, /のサマリー/);
  assert.match(page, /送信回数ランキング/);
  assert.match(page, /時間帯別の送信傾向/);
  assert.match(page, /最近の送信アクティビティ/);
  assert.match(page, /全期間サマリー/);
  assert.match(page, /音声を除く/);
  assert.match(page, /音声のみ/);
  assert.match(page, /前月差/);
  assert.match(page, /送信があった日数/);
  assert.match(page, /1日平均/);
  assert.match(page, /最大日/);
  assert.match(page, /エクスポート/);
  assert.match(page, /ダッシュボード/);
  assert.match(page, /キャンペーン/);
  assert.match(page, /送信履歴/);
  assert.match(page, /レポート/);
  assert.match(page, /設定/);
  assert.match(page, /hourly_weekday/);
  assert.match(page, /function HorizontalScroll/);
  assert.match(page, /data-initial-scroll/);
  assert.match(page, /横方向にスワイプ/);
  assert.doesNotMatch(page, /3時間|gpt_3h/i);
  assert.doesNotMatch(page, /https?:\/\/|chatgpt-usage-dashboard-33/i);
  assert.doesNotMatch(page, /conversation_id|message_id|node_id/i);
  assert.doesNotMatch(layout, /next\/font|codex-preview|_sites-preview|chatgpt-usage-dashboard-33/i);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|drizzle/i);
  assert.match(packageJson, /"test:ui": "node tests\/mobile-ui\.test\.mjs"/);
  assert.equal(npmConfig.trim(), "cache=.npm-cache");
  assert.match(css, /font-family:[^;]*Noto Sans JP/);
  assert.match(css, /overflow-x: clip/);
  assert.match(css, /grid-template-columns: 96px minmax\(0, 1fr\)/);
  assert.match(css, /grid-template-columns: minmax\(0, 1\.58fr\) minmax\(480px, 1fr\)/);
  assert.match(css, /grid-template-columns: repeat\(11, minmax\(0, 1fr\)\)/);
  assert.match(css, /grid-template-columns: repeat\(31, minmax\(0, 1fr\)\)/);
  assert.match(css, /grid-template-columns: minmax\(345px, 0\.95fr\)/);
  assert.match(css, /@media \(max-width: 1180px\)/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /@media \(max-width: 430px\)/);
  assert.match(css, /scrollbar-width: none/);
  assert.match(css, /scroll-frame\.can-scroll-left/);
  assert.match(css, /heatmap-row > strong[\s\S]*position: sticky/);
  assert.match(css, /user-select: none/);
  assert.doesNotMatch(css, /@import|url\(https?:/i);
});
