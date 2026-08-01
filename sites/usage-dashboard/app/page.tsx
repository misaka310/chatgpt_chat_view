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

type CountMode = "all" | "nonVoice" | "voice";

type DisplayDay = DailyRow & {
  display_messages: number;
};

const numberFormatter = new Intl.NumberFormat("ja-JP");
const decimalFormatter = new Intl.NumberFormat("ja-JP", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const countModes: Record<
  CountMode,
  {
    label: string;
    messageField: "sent_messages" | "non_voice_messages" | "voice_messages";
    activeDaysField: "active_days" | "non_voice_active_days" | "voice_active_days";
  }
> = {
  all: { label: "すべて", messageField: "sent_messages", activeDaysField: "active_days" },
  nonVoice: { label: "音声を除く", messageField: "non_voice_messages", activeDaysField: "non_voice_active_days" },
  voice: { label: "音声のみ", messageField: "voice_messages", activeDaysField: "voice_active_days" },
};

function safeNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function messageCount(row: MonthlyRow | DailyRow | UsageData["totals"] | null, mode: CountMode) {
  if (!row) return 0;
  return safeNumber(row[countModes[mode].messageField]);
}

function activeDays(row: MonthlyRow | UsageData["totals"] | null, mode: CountMode) {
  if (!row) return 0;
  return safeNumber(row[countModes[mode].activeDaysField]);
}

function formatMonth(month: string) {
  const [year, value] = month.split("-");
  return `${year}年${value}月`;
}

function formatDate(date: string) {
  return date.replaceAll("-", "/");
}

function monthDayCount(month: string) {
  const [year, value] = month.split("-").map(Number);
  return new Date(year, value, 0).getDate();
}

function deltaInfo(current: number, previous: number | null) {
  if (previous === null) return { text: "-", className: "zero" };
  const delta = current - previous;
  if (delta > 0) return { text: `+${numberFormatter.format(delta)}`, className: "pos" };
  if (delta < 0) return { text: numberFormatter.format(delta), className: "neg" };
  return { text: "±0", className: "zero" };
}

function MetricCard({
  label,
  value,
  note,
  selected = false,
}: {
  label: string;
  value: string;
  note: string;
  selected?: boolean;
}) {
  return (
    <article className={`metric${selected ? " selected-mode" : ""}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-note">{note}</span>
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
        setSelectedMonth(payload.monthly.at(-1)?.month ?? "");
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
    () => [...(data?.monthly ?? [])].sort((left, right) => left.month.localeCompare(right.month)),
    [data],
  );
  const visibleMonthly = monthly.slice(-12);
  const selected = monthly.find((row) => row.month === selectedMonth) ?? monthly.at(-1) ?? null;
  const selectedIndex = selected ? monthly.findIndex((row) => row.month === selected.month) : -1;
  const previous = selectedIndex > 0 ? monthly[selectedIndex - 1] : null;

  const selectedDays = useMemo<DisplayDay[]>(() => {
    if (!selected) return [];
    const source = new Map(
      (data?.daily ?? [])
        .filter((row) => row.month === selected.month)
        .map((row) => [row.date, row]),
    );
    const count = monthDayCount(selected.month);
    return Array.from({ length: count }, (_, index) => {
      const day = index + 1;
      const date = `${selected.month}-${String(day).padStart(2, "0")}`;
      const row = source.get(date) ?? {
        date,
        month: selected.month,
        day,
        sent_messages: 0,
        non_voice_messages: 0,
        voice_messages: 0,
        conversation_count: 0,
        estimated_tokens: 0,
      };
      return { ...row, display_messages: messageCount(row, countMode) };
    });
  }, [countMode, data?.daily, selected]);

  const monthMaximum = Math.max(1, ...visibleMonthly.map((row) => messageCount(row, countMode)));
  const dayMaximum = Math.max(1, ...selectedDays.map((row) => row.display_messages));
  const dayTotal = selectedDays.reduce((sum, row) => sum + row.display_messages, 0);
  const dayAverage = selectedDays.length ? dayTotal / selectedDays.length : 0;
  const dayPeak = selectedDays.reduce<DisplayDay | null>(
    (best, row) => (!best || row.display_messages > best.display_messages ? row : best),
    null,
  );
  const dayMinimum = selectedDays.reduce<DisplayDay | null>(
    (best, row) => (!best || row.display_messages < best.display_messages ? row : best),
    null,
  );

  if (error) {
    return (
      <main className="shell">
        <section className="panel notice-card">
          <h1>ChatGPT 利用ダッシュボード</h1>
          <p>{error}</p>
          <p className="muted">ローカルでSites用データを生成してから、もう一度開いてください。</p>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="shell" aria-busy="true">
        <section className="panel notice-card loading-card">
          <div className="loading-mark" aria-hidden="true" />
          <h1>ChatGPT 利用ダッシュボード</h1>
          <p>会話本文を含まない集計データを読み込んでいます。</p>
        </section>
      </main>
    );
  }

  const selectedDelta = deltaInfo(
    messageCount(selected, countMode),
    previous ? messageCount(previous, countMode) : null,
  );
  const selectedActiveDays = activeDays(selected, countMode);
  const selectedActiveAverage = selectedActiveDays
    ? messageCount(selected, countMode) / selectedActiveDays
    : 0;

  return (
    <main className="shell">
      <header className="panel hero">
        <div className="brand">
          <div className="app-mark" aria-hidden="true">G</div>
          <div>
            <h1>ChatGPT 利用ダッシュボード</h1>
            <p className="subtitle">送信回数の推移を中心に確認</p>
          </div>
        </div>
        <div className="hero-meta">
          <div className="meta-chip">データ更新: {new Date(data.generated_at).toLocaleString("ja-JP")}</div>
          <div className="meta-chip">最新月: {monthly.at(-1) ? formatMonth(monthly.at(-1)!.month) : "-"}</div>
        </div>
      </header>

      <section className="panel section filter-panel" aria-label="表示設定">
        <div className="filters">
          <label className="field">
            <span>期間</span>
            <select disabled aria-label="期間"><option>直近12か月</option></select>
          </label>
          <label className="field">
            <span>表示単位</span>
            <select disabled aria-label="表示単位"><option>月別</option></select>
          </label>
          <label className="field">
            <span>集計対象</span>
            <select value={countMode} onChange={(event) => setCountMode(event.target.value as CountMode)}>
              <option value="all">すべて</option>
              <option value="nonVoice">音声を除く</option>
              <option value="voice">音声のみ</option>
            </select>
          </label>
          <label className="field field-wide">
            <span>詳細月</span>
            <select value={selected?.month ?? ""} onChange={(event) => setSelectedMonth(event.target.value)}>
              {[...monthly].reverse().map((row) => (
                <option key={row.month} value={row.month}>{formatMonth(row.month)}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="grid-top">
        <section className="panel section">
          <div className="section-head">
            <div>
              <h2 className="section-title">月ごとの送信回数</h2>
              <p className="section-subtitle">月別の送信回数を比較して、増減の流れをつかめます</p>
            </div>
            <div className="trend-chip">前月比 <strong className={selectedDelta.className}>{selectedDelta.text}</strong></div>
          </div>

          <div className="chart-scroll monthly-scroll">
            <div className="bar-chart monthly-chart" role="list" aria-label={`月別送信回数（${countModes[countMode].label}）`}>
              {visibleMonthly.map((row) => {
                const count = messageCount(row, countMode);
                const height = Math.max(5, (count / monthMaximum) * 100);
                const isSelected = row.month === selected?.month;
                return (
                  <button
                    type="button"
                    className={`bar-item${isSelected ? " selected" : ""}`}
                    key={row.month}
                    onClick={() => setSelectedMonth(row.month)}
                    aria-pressed={isSelected}
                    title={`${formatMonth(row.month)}: ${numberFormatter.format(count)}回`}
                  >
                    <span className="bar-value">{numberFormatter.format(count)}</span>
                    <span className="bar-track"><span className="bar-fill" style={{ height: `${height}%` }} /></span>
                    <span className="bar-label">{row.month}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <p className="footnote">棒の高さは各月の送信回数です。棒を選ぶと日別表示も切り替わります。</p>
        </section>

        <aside className="panel section">
          <div className="section-head summary-head">
            <div>
              <h2 className="section-title">選択月サマリー</h2>
              <p className="selected-month">{selected ? `${formatMonth(selected.month)}・${countModes[countMode].label}` : "-"}</p>
            </div>
          </div>
          <div className="summary-grid">
            <MetricCard label="全件" value={numberFormatter.format(messageCount(selected, "all"))} note="音声発話を含む送信回数" selected={countMode === "all"} />
            <MetricCard label="音声を除く" value={numberFormatter.format(messageCount(selected, "nonVoice"))} note="音声会話として識別した発話を除外" selected={countMode === "nonVoice"} />
            <MetricCard label="音声のみ" value={numberFormatter.format(messageCount(selected, "voice"))} note="音声会話として識別できた発話" selected={countMode === "voice"} />
            <MetricCard label={`前月差（${countModes[countMode].label}）`} value={selectedDelta.text} note="現在の集計対象で前月と比較" />
            <MetricCard label={`活動日数（${countModes[countMode].label}）`} value={numberFormatter.format(selectedActiveDays)} note="送信があった日数" />
            <MetricCard label={`1日平均（${countModes[countMode].label}）`} value={decimalFormatter.format(selectedActiveAverage)} note="活動日数あたりの送信回数" />
          </div>
        </aside>
      </section>

      <section className="grid-bottom">
        <section className="panel section">
          <div className="section-head">
            <div>
              <h2 className="section-title">月別一覧</h2>
              <p className="section-subtitle">月を選ぶと上の日別推移も連動します</p>
            </div>
          </div>
          <div className="monthly-list" role="table" aria-label="月別集計一覧">
            <div className="monthly-list-head" role="row">
              <span>月</span><span>送信回数</span><span>前月差</span><span>活動日数</span><span>1日平均</span>
            </div>
            {[...visibleMonthly].reverse().map((row) => {
              const index = monthly.findIndex((item) => item.month === row.month);
              const prior = index > 0 ? monthly[index - 1] : null;
              const delta = deltaInfo(messageCount(row, countMode), prior ? messageCount(prior, countMode) : null);
              const days = activeDays(row, countMode);
              const average = days ? messageCount(row, countMode) / days : 0;
              return (
                <button
                  type="button"
                  className={`monthly-list-row${row.month === selected?.month ? " selected" : ""}`}
                  key={row.month}
                  onClick={() => setSelectedMonth(row.month)}
                  role="row"
                >
                  <span data-label="月">{formatMonth(row.month)}</span>
                  <span data-label="送信回数" className="num">{numberFormatter.format(messageCount(row, countMode))}</span>
                  <span data-label="前月差" className={`num delta ${delta.className}`}>{delta.text}</span>
                  <span data-label="活動日数" className="num">{numberFormatter.format(days)}日</span>
                  <span data-label="1日平均" className="num">{decimalFormatter.format(average)}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="panel section">
          <div className="section-head">
            <div>
              <h2 className="section-title">{selected ? `${formatMonth(selected.month)}の日別送信回数` : "選択月の日別送信回数"}</h2>
              <p className="section-subtitle">日ごとの送信回数を、横スクロールせず月全体で確認できます（{countModes[countMode].label}）</p>
            </div>
          </div>
          <div className="chart-scroll daily-scroll">
            <div className="bar-chart daily-chart" role="list" aria-label={`${selected ? formatMonth(selected.month) : "選択月"}の日別送信回数`}>
              {selectedDays.map((row) => {
                const height = Math.max(4, (row.display_messages / dayMaximum) * 100);
                return (
                  <div className="bar-item daily" key={row.date} title={`${formatDate(row.date)}: ${numberFormatter.format(row.display_messages)}回`}>
                    <span className="bar-value">{numberFormatter.format(row.display_messages)}</span>
                    <span className="bar-track"><span className="bar-fill" style={{ height: `${height}%` }} /></span>
                    <span className="bar-label">{String(row.day).padStart(2, "0")}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="daily-footer">
            <div className="daily-stat"><span>合計</span><strong>{numberFormatter.format(dayTotal)}</strong></div>
            <div className="daily-stat"><span>暦日平均</span><strong>{decimalFormatter.format(dayAverage)}</strong></div>
            <div className="daily-stat"><span>最大</span><strong>{dayPeak ? `${numberFormatter.format(dayPeak.display_messages)}（${formatDate(dayPeak.date)}）` : "-"}</strong></div>
            <div className="daily-stat"><span>最小</span><strong>{dayMinimum ? `${numberFormatter.format(dayMinimum.display_messages)}（${formatDate(dayMinimum.date)}）` : "-"}</strong></div>
          </div>
        </section>
      </section>

      <section className="panel section overall-section" aria-label="全期間の数値集計">
        <div className="section-head">
          <div>
            <h2 className="section-title">全期間サマリー</h2>
            <p className="section-subtitle">個人情報を含まない数値集計だけを表示しています</p>
          </div>
        </div>
        <div className="overall-grid">
          <MetricCard label="全件" value={numberFormatter.format(data.totals.sent_messages)} note="音声発話を含む全ユーザー送信" />
          <MetricCard label="音声を除く" value={numberFormatter.format(data.totals.non_voice_messages)} note="音声発話を除外した送信" />
          <MetricCard label="音声のみ" value={numberFormatter.format(data.totals.voice_messages)} note="識別できた音声発話" />
          <MetricCard label="活動日数" value={numberFormatter.format(data.totals.active_days)} note="全期間で送信があった日数" />
          <MetricCard label="会話数" value={numberFormatter.format(data.totals.conversation_count)} note="重複を除いた会話単位" />
          <MetricCard label="推定総トークン" value={numberFormatter.format(data.totals.estimated_tokens)} note="非公式の概算値" />
        </div>
      </section>

      <section className="panel privacy-note" aria-label="集計方法">
        <strong>この画面に会話本文・タイトル・IDは含まれていません。</strong>
        <p>{data.method}</p>
        <p>数値はChatGPT公式の利用量ではなく、エクスポートデータからローカルで算出した非公式集計です。</p>
      </section>
    </main>
  );
}
