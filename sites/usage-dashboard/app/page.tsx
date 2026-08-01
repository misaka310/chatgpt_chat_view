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
type DisplayDay = DailyRow & { display_messages: number };

const numberFormatter = new Intl.NumberFormat("ja-JP");
const decimalFormatter = new Intl.NumberFormat("ja-JP", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const countModes: Record<
  CountMode,
  {
    label: string;
    shortLabel: string;
    messageField: "sent_messages" | "non_voice_messages" | "voice_messages";
    activeDaysField: "active_days" | "non_voice_active_days" | "voice_active_days";
  }
> = {
  all: {
    label: "全件",
    shortLabel: "全件",
    messageField: "sent_messages",
    activeDaysField: "active_days",
  },
  nonVoice: {
    label: "音声を除く",
    shortLabel: "音声除外",
    messageField: "non_voice_messages",
    activeDaysField: "non_voice_active_days",
  },
  voice: {
    label: "音声のみ",
    shortLabel: "音声のみ",
    messageField: "voice_messages",
    activeDaysField: "voice_active_days",
  },
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
  return `${year}年${Number(value)}月`;
}

function formatMonthShort(month: string) {
  const [year, value] = month.split("-");
  return `${year.slice(2)}/${Number(value)}`;
}

function formatDate(date: string) {
  const [, month, day] = date.split("-");
  return `${Number(month)}/${Number(day)}`;
}

function formatDateLong(date: string) {
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

function RankRow({
  rank,
  label,
  value,
  tone,
  onClick,
  selected = false,
}: {
  rank: number;
  label: string;
  value: string;
  tone: number;
  onClick?: () => void;
  selected?: boolean;
}) {
  const content = (
    <>
      <span className="rank-number">{rank}</span>
      <span className="rank-main">
        <span className="rank-label">{label}</span>
        <span className="rank-track" aria-hidden="true">
          <span className="rank-fill" style={{ width: `${Math.max(3, tone)}%` }} />
        </span>
      </span>
      <strong className="rank-value">{value}</strong>
    </>
  );

  if (onClick) {
    return (
      <button type="button" className={`rank-row${selected ? " selected" : ""}`} onClick={onClick}>
        {content}
      </button>
    );
  }

  return <div className="rank-row static">{content}</div>;
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

  const dailyRanking = [...selectedDays]
    .filter((row) => row.display_messages > 0)
    .sort((left, right) => right.display_messages - left.display_messages || right.date.localeCompare(left.date))
    .slice(0, 5);
  const monthlyRanking = [...visibleMonthly]
    .sort(
      (left, right) =>
        messageCount(right, countMode) - messageCount(left, countMode) || right.month.localeCompare(left.month),
    );
  const recentActivity = [...(data?.daily ?? [])]
    .map((row) => ({ ...row, display_messages: messageCount(row, countMode) }))
    .filter((row) => row.display_messages > 0)
    .sort((left, right) => right.date.localeCompare(left.date))
    .slice(0, 5);

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
      <header className="topbar">
        <div className="title-group">
          <span className="eyebrow">SEND ANALYTICS</span>
          <h1>ChatGPT 利用ダッシュボード</h1>
          <p>匿名化した送信回数だけを月別・日別に確認</p>
        </div>
        <div className="topbar-meta">
          <div>
            <span>対象月</span>
            <strong>{selected ? formatMonth(selected.month) : "-"}</strong>
          </div>
          <div>
            <span>集計時刻</span>
            <strong>{new Date(data.generated_at).toLocaleString("ja-JP")}</strong>
          </div>
        </div>
      </header>

      <section className="control-bar" aria-label="表示設定">
        <div className="mode-switch" role="group" aria-label="集計対象">
          {(Object.keys(countModes) as CountMode[]).map((mode) => (
            <button
              type="button"
              key={mode}
              className={countMode === mode ? "active" : ""}
              aria-pressed={countMode === mode}
              onClick={() => setCountMode(mode)}
            >
              {countModes[mode].shortLabel}
            </button>
          ))}
        </div>
        <label className="month-select">
          <span>詳細月</span>
          <select value={selected?.month ?? ""} onChange={(event) => setSelectedMonth(event.target.value)}>
            {[...monthly].reverse().map((row) => (
              <option key={row.month} value={row.month}>
                {formatMonth(row.month)}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="grid-top">
        <section className="panel section monthly-panel">
          <div className="section-head">
            <div>
              <span className="section-kicker">MONTHLY</span>
              <h2 className="section-title">月ごとの送信回数</h2>
              <p className="section-subtitle">直近12か月・{countModes[countMode].label}</p>
            </div>
            <div className="trend-chip">
              前月差 <strong className={selectedDelta.className}>{selectedDelta.text}</strong>
            </div>
          </div>

          <div className="bar-chart monthly-chart" role="list" aria-label={`月別送信回数（${countModes[countMode].label}）`}>
            {visibleMonthly.map((row) => {
              const count = messageCount(row, countMode);
              const height = Math.max(4, (count / monthMaximum) * 100);
              const isSelected = row.month === selected?.month;
              return (
                <button
                  type="button"
                  className={`bar-item monthly${isSelected ? " selected" : ""}`}
                  key={row.month}
                  onClick={() => setSelectedMonth(row.month)}
                  aria-pressed={isSelected}
                  title={`${formatMonth(row.month)}: ${numberFormatter.format(count)}回`}
                >
                  <span className="bar-value">{numberFormatter.format(count)}</span>
                  <span className="bar-track">
                    <span className="bar-fill" style={{ height: `${height}%` }} />
                  </span>
                  <span className="bar-label">{formatMonthShort(row.month)}</span>
                </button>
              );
            })}
          </div>
          <p className="footnote">棒を選ぶと、右のサマリーと日別表示が同じ月へ切り替わります。</p>
        </section>

        <aside className="panel section summary-panel">
          <div className="section-head compact">
            <div>
              <span className="section-kicker">SUMMARY</span>
              <h2 className="section-title">選択月サマリー</h2>
              <p className="selected-month">{selected ? formatMonth(selected.month) : "-"}</p>
            </div>
          </div>
          <div className="summary-grid">
            <MetricCard label="全件" value={numberFormatter.format(messageCount(selected, "all"))} note="送信回数" selected={countMode === "all"} />
            <MetricCard label="音声を除く" value={numberFormatter.format(messageCount(selected, "nonVoice"))} note="音声会話を除外" selected={countMode === "nonVoice"} />
            <MetricCard label="音声のみ" value={numberFormatter.format(messageCount(selected, "voice"))} note="識別できた音声発話" selected={countMode === "voice"} />
            <MetricCard label="前月差" value={selectedDelta.text} note={countModes[countMode].label} />
            <MetricCard label="活動日数" value={`${numberFormatter.format(selectedActiveDays)}日`} note="送信があった日" />
            <MetricCard label="1日平均" value={decimalFormatter.format(selectedActiveAverage)} note="活動日あたり" />
          </div>
        </aside>
      </section>

      <section className="panel section daily-panel">
        <div className="section-head">
          <div>
            <span className="section-kicker">DAILY</span>
            <h2 className="section-title">{selected ? `${formatMonth(selected.month)}の日別送信回数` : "日別送信回数"}</h2>
            <p className="section-subtitle">31日すべてを横スクロールなしで表示・{countModes[countMode].label}</p>
          </div>
        </div>
        <div className="bar-chart daily-chart" role="list" aria-label={`${selected ? formatMonth(selected.month) : "選択月"}の日別送信回数`}>
          {selectedDays.map((row) => {
            const height = Math.max(3, (row.display_messages / dayMaximum) * 100);
            return (
              <div className="bar-item daily" key={row.date} title={`${formatDateLong(row.date)}: ${numberFormatter.format(row.display_messages)}回`}>
                <span className="bar-value">{numberFormatter.format(row.display_messages)}</span>
                <span className="bar-track">
                  <span className="bar-fill" style={{ height: `${height}%` }} />
                </span>
                <span className="bar-label">{row.day}日</span>
              </div>
            );
          })}
        </div>
        <div className="daily-footer">
          <div className="daily-stat"><span>合計</span><strong>{numberFormatter.format(dayTotal)}</strong></div>
          <div className="daily-stat"><span>暦日平均</span><strong>{decimalFormatter.format(dayAverage)}</strong></div>
          <div className="daily-stat"><span>最大</span><strong>{dayPeak ? `${numberFormatter.format(dayPeak.display_messages)}・${formatDate(dayPeak.date)}` : "-"}</strong></div>
          <div className="daily-stat"><span>最小</span><strong>{dayMinimum ? `${numberFormatter.format(dayMinimum.display_messages)}・${formatDate(dayMinimum.date)}` : "-"}</strong></div>
        </div>
      </section>

      <section className="insight-grid">
        <section className="panel section insight-panel">
          <div className="section-head compact">
            <div>
              <span className="section-kicker">TOP DAYS</span>
              <h2 className="section-title">送信回数ランキング</h2>
              <p className="section-subtitle">選択月の上位活動日</p>
            </div>
          </div>
          <div className="rank-list">
            {dailyRanking.length ? dailyRanking.map((row, index) => (
              <RankRow
                key={row.date}
                rank={index + 1}
                label={formatDateLong(row.date)}
                value={numberFormatter.format(row.display_messages)}
                tone={(row.display_messages / Math.max(1, dailyRanking[0].display_messages)) * 100}
              />
            )) : <p className="empty-state">この月には対象の送信がありません。</p>}
          </div>
        </section>

        <section className="panel section insight-panel monthly-ranking-panel">
          <div className="section-head compact">
            <div>
              <span className="section-kicker">MONTH RANK</span>
              <h2 className="section-title">月別ランキング</h2>
              <p className="section-subtitle">直近12か月をすべて比較</p>
            </div>
          </div>
          <div className="rank-list monthly-rank-list">
            {monthlyRanking.map((row, index) => (
              <RankRow
                key={row.month}
                rank={index + 1}
                label={formatMonth(row.month)}
                value={numberFormatter.format(messageCount(row, countMode))}
                tone={(messageCount(row, countMode) / monthMaximum) * 100}
                onClick={() => setSelectedMonth(row.month)}
                selected={row.month === selected?.month}
              />
            ))}
          </div>
        </section>

        <section className="panel section insight-panel">
          <div className="section-head compact">
            <div>
              <span className="section-kicker">RECENT DAYS</span>
              <h2 className="section-title">最近の活動日</h2>
              <p className="section-subtitle">送信があった直近の日付</p>
            </div>
          </div>
          <div className="recent-list">
            {recentActivity.length ? recentActivity.map((row) => (
              <div className="recent-row" key={row.date}>
                <span>{formatDateLong(row.date)}</span>
                <strong>{numberFormatter.format(row.display_messages)}回</strong>
              </div>
            )) : <p className="empty-state">対象の活動日はありません。</p>}
          </div>
        </section>
      </section>

      <section className="panel section overall-section" aria-label="全期間の数値集計">
        <div className="section-head compact">
          <div>
            <span className="section-kicker">ALL TIME</span>
            <h2 className="section-title">全期間サマリー</h2>
            <p className="section-subtitle">個人情報を含まない数値集計のみ</p>
          </div>
        </div>
        <div className="overall-grid">
          <MetricCard label="全件" value={numberFormatter.format(data.totals.sent_messages)} note="全ユーザー送信" />
          <MetricCard label="音声を除く" value={numberFormatter.format(data.totals.non_voice_messages)} note="音声会話を除外" />
          <MetricCard label="音声のみ" value={numberFormatter.format(data.totals.voice_messages)} note="識別できた音声発話" />
          <MetricCard label="活動日数" value={`${numberFormatter.format(data.totals.active_days)}日`} note="送信があった日" />
          <MetricCard label="会話数" value={numberFormatter.format(data.totals.conversation_count)} note="重複を除く会話単位" />
          <MetricCard label="推定トークン" value={numberFormatter.format(data.totals.estimated_tokens)} note="非公式の概算値" />
        </div>
      </section>

      <footer className="panel privacy-note" aria-label="集計方法">
        <strong>この画面に会話本文・会話タイトル・IDは含まれていません。</strong>
        <p>{data.method}</p>
        <p>数値はChatGPT公式の利用量ではなく、エクスポートデータからローカルで算出した非公式集計です。</p>
      </footer>
    </main>
  );
}
