import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dataUrl = new URL("../public/usage-data.json", import.meta.url);
const dataPath = fileURLToPath(dataUrl);
const original = existsSync(dataPath) ? readFileSync(dataPath) : null;
const npmCachePath = fileURLToPath(new URL("../.npm-cache", import.meta.url));
mkdirSync(npmCachePath, { recursive: true });
const safeEnv = { ...process.env };
for (const key of Object.keys(safeEnv)) {
  if (key.toLowerCase() === "npm_config_cache") delete safeEnv[key];
}
safeEnv.npm_config_cache = npmCachePath;

const synthetic = {
  schema_version: 3,
  generated_at: "2026-01-03T12:00:00+09:00",
  timezone: "Asia/Tokyo",
  method: "ChatGPTエクスポートをPC内で解析し、全体・音声除外・音声のみの送信回数など、本文を含まない数値データだけを公開用に抽出しています。",
  totals: {
    sent_messages: 42,
    non_voice_messages: 35,
    voice_messages: 7,
    active_days: 3,
    non_voice_active_days: 3,
    voice_active_days: 3,
    conversation_count: 7,
    estimated_tokens: 6300,
  },
  monthly: [
    { month: "2025-12", sent_messages: 12, non_voice_messages: 10, voice_messages: 2, active_days: 1, non_voice_active_days: 1, voice_active_days: 1, conversation_count: 2, estimated_tokens: 1800 },
    { month: "2026-01", sent_messages: 30, non_voice_messages: 25, voice_messages: 5, active_days: 2, non_voice_active_days: 2, voice_active_days: 2, conversation_count: 5, estimated_tokens: 4500 },
  ],
  daily: [
    { date: "2025-12-28", month: "2025-12", day: 28, sent_messages: 12, non_voice_messages: 10, voice_messages: 2, conversation_count: 2, estimated_tokens: 1800 },
    { date: "2026-01-02", month: "2026-01", day: 2, sent_messages: 18, non_voice_messages: 15, voice_messages: 3, conversation_count: 3, estimated_tokens: 2700 },
    { date: "2026-01-03", month: "2026-01", day: 3, sent_messages: 12, non_voice_messages: 10, voice_messages: 2, conversation_count: 2, estimated_tokens: 1800 },
  ],
  hourly_weekday: Array.from({ length: 7 * 24 }, (_, index) => ({
    month: "2026-01",
    weekday: Math.floor(index / 24),
    hour: index % 24,
    sent_messages: (index % 9) + 1,
    non_voice_messages: (index % 7) + 1,
    voice_messages: index % 3,
  })),
};

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    env: safeEnv,
    stdio: "inherit",
  });
  if (result.error) console.error(`Failed to start ${command}: ${result.error.message}`);
  if (result.signal) console.error(`${command} stopped with signal ${result.signal}`);
  if (result.status !== 0) process.exitCode = result.status ?? 1;
  return result.status === 0;
}

try {
  writeFileSync(dataPath, `${JSON.stringify(synthetic)}\n`, "utf8");
  const built = run(process.execPath, ["./node_modules/vinext/dist/cli.js", "build"]);
  if (built) {
    run(process.execPath, ["--test", "tests/rendered-html.test.mjs"]);
    run(process.execPath, ["tests/mobile-ui.test.mjs"]);
  }
} finally {
  if (original === null) {
    rmSync(dataPath, { force: true });
  } else {
    writeFileSync(dataPath, original);
    run(process.execPath, ["./node_modules/vinext/dist/cli.js", "build"]);
  }
}
