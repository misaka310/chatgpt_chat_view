"use client";

import { useEffect, useMemo, useState } from "react";

type MonthlyRow = {
  month: string;
  sent_messages: number;
  non_voice_messages: number;
  voice_messages: number;
  active_days: number;
  non_voice_active_days: number;
  voice_active_days: number;
  conversation_count: number;
  estimated_tokens: number;
};

type DailyRow = {
  date: string;
  month: string;
  day: number;
  sent_messages: number;
  non_voice_messages: number;
  voice_messages: number;
  conversation_count: number;
  estimated_tokens: number;
};

type UsageData = {
  schema_version: 2;
  generated_at: string;
  timezone: string;
  method: string;
  totals: {
    sent_messages: number;
    non_voice_messages: number;
    voice_messages: number;
    active_days: number;
    non_voice_active_days: number;
    voice_active_days: number;
    conversation_count: number;
    estimated_tokens: number;
  };
  monthly: MonthlyRow[];
  daily: DailyRow[];
};

const numberFormatter = new Intl.NumberFormat("ja-JP");
const decimalFormatter = new Intl.NumberFormat("ja-JP", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatMonth(month: string) {
  const [year, value] = month.split("-");
  return `${year}年${value}月`;
}

function formatDate(date: string) {
  return date.replaceAll("-", "/");
}

function safeNumber(value: unknown) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

type CountMode = "all" | "nonVoice" | "voice";

const countModes: Record<CountMode, { label: string; messageField: "sent_messages" | "non_voice_messages" | "voice_messages"; activeDaysField: "active_days" | "non_voice_active_days" | "voice_active_days" }> = {
  all: { label: "すべて", messageField: "sent_messages", activeDaysField: "active_days" },
  nonVoice: { label: "音声を除く", messageField: "non_voice_messages", activeDaysField: "non_voice_active_days" },
  voice: { label: "音声のみ", messageField: "voice_messages", activeDaysField: "voice_active_days" },
};

function messageCount(row: MonthlyRow | DailyRow | UsageData["totals"], mode: CountMode) {
  return safeNumber(row[countModes[mode].messageField]);
}

function activeDays(row: MonthlyRow | UsageData["totals"], mode: CountMode) {
  return safeNumber(row[countModes[mode].activeDaysField]);
}

function StatCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <article className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <span className="stat-note">{note}</span>
    </article>
  );
}

export default function Home() {
  const [data, setData] = useState<UsageData | null>(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [countMode, setCountMode] = useState<CountMode>("all");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/usage-data.json", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("集計データを読み込めませんでした");
        return response.json() as Promise<UsageData>;
      })
      .then((payload) => {
        if (!active) return;
        setData(payload);
        const latest = payload.monthly.at(-1)?.month ?? "";
        setSelectedMonth(latest);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "集計データを読み込めませんでした");
      });
    return () => {
      active = false;
    };
  }, []);

  const monthly = useMemo(
    () => [...(data?.monthly ?? [])].sort((a, b) => a.month.localeCompare(b.month)),
    [data],
  );
  const selected = monthly.find((row) => row.month === selectedMonth) ?? monthly.at(-1) ?? null;
  const selectedDays = useMemo(
    () => (data?.daily ?? []).filter((row) => row.month === selected?.month).sort((a, b) => a.date.localeCompare(b.date)),
    [data, selected?.month],
  );

  const monthMax = Math.max(1, ...monthly.map((row) => messageCount(row, countMode)));
  const dayMax = Math.max(1, ...selectedDays.map((row) => messageCount(row, countMode)));
  const dayTotal = selectedDays.reduce((sum, row) => sum + messageCount(row, countMode), 0);
  const dayAverage = selectedDays.length ? dayTotal / selectedDays.length : 0;
  const dayPeak = selectedDays.reduce<DailyRow | null>(
    (best, row) => (!best || messageCount(row, countMode) > messageCount(best, countMode) ? row : best),
    null,
  );
  const dayMinimum = selectedDays.reduce<DailyRow | null>(
    (best, row) => (!best || messageCount(row, countMode) < messageCount(best, countMode) ? row : best),
    null,
  );

  if (error) {
    return (
      <main className="page-shell">
        <section className="notice-card error-card">
          <h1>ChatGPT 利用集計</h1>
          <p>{error}</p>
          <p className="muted">ローカルで公開用データを生成してから、もう一度開いてください。</p>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="page-shell" aria-busy="true">
        <section className="notice-card loading-card">
          <div className="loading-mark" aria-hidden="true" />
          <h1>ChatGPT 利用集計</h1>
          <p>会話本文を含まない集計データを読み込んでいます。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <header className="hero panel">
        <div>
          <span className="eyebrow">PERSONAL USAGE SUMMARY</span>
          <h1>ChatGPT 利用集計</h1>
          <p className="hero-copy">全件・音声除外・音声のみの送信回数を月別・日別に確認する、会話本文を含まない個人用集計画面です。</p>
        </div>
        <div className="hero-meta">
          <span>更新 {new Date(data.generated_at).toLocaleString("ja-JP")}</span>
          <span>{data.timezone}</span>
        </div>
      </header>

      <section className="privacy-note panel" aria-label="集計について">
        <div className="privacy-icon" aria-hidden="true">✓</div>
        <div>
          <strong>会話本文・タイトル・IDは含まれていません</strong>
          <p>{data.method}</p>
        </div>
      </section>

      <section className="totals-grid" aria-label="全期間の集計">
        <StatCard label="全期間・全件" value={numberFormatter.format(data.totals.sent_messages)} note="音声発話を含むユーザー送信" />
        <StatCard label="全期間・音声を除く" value={numberFormatter.format(data.totals.non_voice_messages)} note="GPT Liveなどの音声発話を除外" />
        <StatCard label="全期間・音声のみ" value={numberFormatter.format(data.totals.voice_messages)} note="音声会話として識別できた発話" />
        <StatCard label={`活動日数・${countModes[countMode].label}`} value={numberFormatter.format(activeDays(data.totals, countMode))} note="現在の集計対象で送信があった日数" />
        <StatCard label="会話数" value={numberFormatter.format(data.totals.conversation_count)} note="重複を除いた会話単位" />
        <StatCard label="推定総トークン" value={numberFormatter.format(data.totals.estimated_tokens)} note="非公式の概算値" />
      </section>

      <section className="panel section-block">
        <div className="section-heading">
          <div>
            <span className="eyebrow">MONTHLY</span>
            <h2>月別の送信回数（{countModes[countMode].label}）</h2>
            <p>棒または一覧の月を選ぶと、日別表示が切り替わります。</p>
          </div>
          <div className="section-controls">
            <label className="month-select">
              <span>集計対象</span>
              <select value={countMode} onChange={(event) => setCountMode(event.target.value as CountMode)}>
                <option value="all">すべて</option>
                <option value="nonVoice">音声を除く</option>
                <option value="voice">音声のみ</option>
              </select>
            </label>
            <label className="month-select">
              <span>表示する月</span>
              <select value={selected?.month ?? ""} onChange={(event) => setSelectedMonth(event.target.value)}>
                {[...monthly].reverse().map((row) => (
                  <option key={row.month} value={row.month}>{formatMonth(row.month)}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="monthly-chart" role="list" aria-label="月別送信回数グラフ">
          {monthly.map((row) => {
            const height = Math.max(7, (messageCount(row, countMode) / monthMax) * 100);
            const isSelected = row.month === selected?.month;
            return (
              <button
                type="button"
                className={`month-bar${isSelected ? " selected" : ""}`}
                key={row.month}
                onClick={() => setSelectedMonth(row.month)}
                aria-pressed={isSelected}
                title={`${formatMonth(row.month)}: ${numberFormatter.format(messageCount(row, countMode))}回`}
              >
                <span className="bar-number">{numberFormatter.format(messageCount(row, countMode))}</span>
                <span className="bar-track"><span className="bar-fill" style={{ height: `${height}%` }} /></span>
                <span className="bar-caption">{row.month}</span>
              </button>
            );
          })}
        </div>

        <div className="monthly-table-wrap">
          <table className="monthly-table">
            <thead>
              <tr><th>月</th><th>送信回数（{countModes[countMode].label}）</th><th>活動日（{countModes[countMode].label}）</th><th>会話数</th><th>推定トークン</th></tr>
            </thead>
            <tbody>
              {[...monthly].reverse().map((row) => (
                <tr key={row.month} className={row.month === selected?.month ? "selected" : ""} onClick={() => setSelectedMonth(row.month)}>
                  <th scope="row">{formatMonth(row.month)}</th>
                  <td>{numberFormatter.format(messageCount(row, countMode))}</td>
                  <td>{numberFormatter.format(activeDays(row, countMode))}</td>
                  <td>{numberFormatter.format(row.conversation_count)}</td>
                  <td>{numberFormatter.format(row.estimated_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="panel section-block" aria-label={`${formatMonth(selected.month)}の日別集計`}>
          <div className="section-heading compact-heading">
            <div>
              <span className="eyebrow">DAILY</span>
              <h2>{formatMonth(selected.month)}の日別送信回数（{countModes[countMode].label}）</h2>
              <p>横にスクロールすると月内のすべての日を確認できます。</p>
            </div>
          </div>

          <div className="daily-chart-scroll">
            <div className="daily-chart" style={{ gridTemplateColumns: `repeat(${Math.max(1, selectedDays.length)}, minmax(34px, 1fr))` }}>
              {selectedDays.map((row) => {
                const height = Math.max(5, (messageCount(row, countMode) / dayMax) * 100);
                return (
                  <div className="day-bar" key={row.date} title={`${formatDate(row.date)}: ${numberFormatter.format(messageCount(row, countMode))}回`}>
                    <span className="day-number">{numberFormatter.format(messageCount(row, countMode))}</span>
                    <span className="day-track"><span className="day-fill" style={{ height: `${height}%` }} /></span>
                    <span className="day-caption">{String(row.day).padStart(2, "0")}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="daily-summary">
            <div><span>合計</span><strong>{numberFormatter.format(dayTotal)}</strong></div>
            <div><span>暦日平均</span><strong>{decimalFormatter.format(dayAverage)}</strong></div>
            <div><span>最大</span><strong>{dayPeak ? `${numberFormatter.format(messageCount(dayPeak, countMode))} / ${formatDate(dayPeak.date)}` : "-"}</strong></div>
            <div><span>最小</span><strong>{dayMinimum ? `${numberFormatter.format(messageCount(dayMinimum, countMode))} / ${formatDate(dayMinimum.date)}` : "-"}</strong></div>
          </div>
        </section>
      )}

      <footer className="footer-note">
        <p>この画面の数値はChatGPTの公式利用量ではなく、エクスポートデータからローカルで算出した非公式集計です。</p>
      </footer>
    </main>
  );
}
