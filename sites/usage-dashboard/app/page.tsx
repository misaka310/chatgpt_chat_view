"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

type HourlyWeekdayRow = {
  month: string;
  weekday: number;
  hour: number;
  sent_messages: number;
  non_voice_messages: number;
  voice_messages: number;
};

type UsageData = {
  schema_version: 3;
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
  hourly_weekday: HourlyWeekdayRow[];
};

type CountMode = "all" | "nonVoice" | "voice";
type DisplayDay = DailyRow & { display_messages: number };
type IconName = "logo" | "dashboard" | "send" | "history" | "filter" | "report" | "settings" | "moon" | "download" | "calendar" | "chart";

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

const weekdays = ["月", "火", "水", "木", "金", "土", "日"];

function Icon({ name, size = 22 }: { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (name === "logo") {
    return (
      <svg {...common} viewBox="0 0 32 32">
        <path fill="currentColor" stroke="none" d="M15.9 2.2c3.5 0 5.4 2.9 4.7 5.7 2.8-1 6 .5 7 3.8 1 3.2-.8 6.1-3.7 6.8 2 2.2 1.7 5.8-.8 7.8-2.6 2-6 1.2-7.4-1.4-1.5 2.6-4.9 3.3-7.4 1.3-2.5-2-2.8-5.6-.8-7.8-2.9-.7-4.7-3.6-3.7-6.8 1-3.2 4.2-4.7 7-3.7-.6-2.8 1.4-5.7 5.1-5.7Z" opacity=".3"/>
        <path fill="currentColor" stroke="none" d="M13.5 4.7c2.7-2.2 6.8-.7 7.1 2.8.2 1.7-.7 3.3-2.2 4.2l-5.8 3.5c-1.9 1.1-4.4.3-5.3-1.7-.8-1.8-.1-3.9 1.6-4.9l4.6-3.9Z"/>
        <path fill="currentColor" stroke="none" d="M18.5 27.3c-2.7 2.2-6.8.7-7.1-2.8-.2-1.7.7-3.3 2.2-4.2l5.8-3.5c1.9-1.1 4.4-.3 5.3 1.7.8 1.8.1 3.9-1.6 4.9l-4.6 3.9Z"/>
      </svg>
    );
  }

  const paths: Record<Exclude<IconName, "logo">, React.ReactNode> = {
    dashboard: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 14h4"/></>,
    send: <><path d="m3 11 18-8-7 18-3-7-8-3Z"/><path d="m11 14 4-4"/></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6M12 7v5l3 2"/></>,
    filter: <><path d="M4 6h16M7 12h10M10 18h4"/><circle cx="8" cy="6" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="12" cy="18" r="1.5"/></>,
    report: <><path d="M5 20V10M10 20V4M15 20v-7M20 20V7"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
    moon: <path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>,
    download: <><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 20h14"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
    chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/></>,
  };

  return <svg {...common}>{paths[name as Exclude<IconName, "logo">]}</svg>;
}

function safeNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function messageCount(row: MonthlyRow | DailyRow | HourlyWeekdayRow | UsageData["totals"] | null, mode: CountMode) {
  if (!row) return 0;
  return safeNumber(row[countModes[mode].messageField]);
}

function activeDays(row: MonthlyRow | UsageData["totals"] | null, mode: CountMode) {
  if (!row) return 0;
  return safeNumber(row[countModes[mode].activeDaysField]);
}

function formatMonth(month: string) {
  const [year, value] = month.split("-");
  return `${year}年${String(Number(value)).padStart(2, "0")}月`;
}

function formatMonthAxis(month: string) {
  return month.replace("-", "-");
}

function formatDate(date: string) {
  const [, month, day] = date.split("-");
  return `${month}/${day}`;
}

function formatDateWithWeekday(date: string) {
  const value = new Date(`${date}T00:00:00+09:00`);
  const day = ["日", "月", "火", "水", "木", "金", "土"][value.getDay()];
  return `${formatDate(date)}（${day}）`;
}

function monthDayCount(month: string) {
  const [year, value] = month.split("-").map(Number);
  return new Date(year, value, 0).getDate();
}

function deltaInfo(current: number, previous: number | null) {
  if (previous === null) return { value: "-", percent: "", className: "neutral" };
  const delta = current - previous;
  const percent = previous > 0 ? (delta / previous) * 100 : 0;
  return {
    value: `${delta > 0 ? "+" : ""}${numberFormatter.format(delta)}`,
    percent: previous > 0 ? ` (${delta > 0 ? "+" : ""}${decimalFormatter.format(percent)}%)` : "",
    className: delta > 0 ? "positive" : delta < 0 ? "negative" : "neutral",
  };
}

function niceMaximum(value: number, targetStep: number) {
  return Math.max(targetStep, Math.ceil(value / targetStep) * targetStep);
}

function downloadCsv(rows: DisplayDay[], month: string, mode: CountMode) {
  const csv = [
    ["date", "messages"],
    ...rows.map((row) => [row.date, String(row.display_messages)]),
  ]
    .map((row) => row.join(","))
    .join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `chatgpt-usage-${month}-${mode}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Sidebar() {
  const links: Array<{ label: string; icon: IconName; href: string; active?: boolean }> = [
    { label: "ダッシュボード", icon: "dashboard", href: "#dashboard", active: true },
    { label: "キャンペーン", icon: "send", href: "#monthly" },
    { label: "送信履歴", icon: "history", href: "#daily" },
    { label: "除外リスト", icon: "filter", href: "#filters" },
    { label: "レポート", icon: "report", href: "#reports" },
    { label: "設定", icon: "settings", href: "#settings" },
  ];

  return (
    <aside className="sidebar" aria-label="ダッシュボードナビゲーション">
      <a className="brand" href="#dashboard" aria-label="先頭へ"><Icon name="logo" size={34} /></a>
      <nav className="side-nav">
        {links.map((link) => (
          <a key={link.label} className={link.active ? "active" : ""} href={link.href}>
            <Icon name={link.icon} size={23} />
            <span>{link.label}</span>
          </a>
        ))}
      </nav>
      <div className="theme-indicator" aria-label="ダークモード使用中">
        <Icon name="moon" size={22} />
        <span>ダーク<br />モード</span>
      </div>
    </aside>
  );
}

function MetricCard({ label, value, note, compact = false, accent = false }: { label: string; value: string; note: string; compact?: boolean; accent?: boolean }) {
  return (
    <article className={`summary-card${compact ? " compact" : ""}${accent ? " accent" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function HorizontalScroll({
  children,
  className = "",
  initialEnd = false,
  resetKey = "",
  label,
}: {
  children: React.ReactNode;
  className?: string;
  initialEnd?: boolean;
  resetKey?: string;
  label: string;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const updateEdges = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const maxScroll = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
    setEdges({
      left: viewport.scrollLeft > 2,
      right: viewport.scrollLeft < maxScroll - 2,
    });
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const resetPosition = () => {
      const mobile = window.matchMedia("(max-width: 760px)").matches;
      viewport.scrollLeft = initialEnd && mobile ? viewport.scrollWidth : 0;
      updateEdges();
    };

    const frame = window.requestAnimationFrame(resetPosition);
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateEdges);
    resizeObserver?.observe(viewport);
    if (viewport.firstElementChild instanceof HTMLElement) resizeObserver?.observe(viewport.firstElementChild);
    viewport.addEventListener("scroll", updateEdges, { passive: true });

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      viewport.removeEventListener("scroll", updateEdges);
    };
  }, [initialEnd, resetKey, updateEdges]);

  return (
    <div className={`scroll-frame${edges.left ? " can-scroll-left" : ""}${edges.right ? " can-scroll-right" : ""}`}>
      <div
        ref={viewportRef}
        className={`scroll-viewport${className ? ` ${className}` : ""}`}
        data-initial-scroll={initialEnd ? "end" : "start"}
        tabIndex={0}
        aria-label={label}
      >
        {children}
      </div>
    </div>
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
    return () => { active = false; };
  }, []);

  const monthly = useMemo(
    () => [...(data?.monthly ?? [])].sort((left, right) => left.month.localeCompare(right.month)),
    [data],
  );
  const visibleMonthly = monthly.slice(-11);
  const selected = monthly.find((row) => row.month === selectedMonth) ?? monthly.at(-1) ?? null;
  const selectedIndex = selected ? monthly.findIndex((row) => row.month === selected.month) : -1;
  const previous = selectedIndex > 0 ? monthly[selectedIndex - 1] : null;

  const selectedDays = useMemo<DisplayDay[]>(() => {
    if (!selected) return [];
    const source = new Map(
      (data?.daily ?? []).filter((row) => row.month === selected.month).map((row) => [row.date, row]),
    );
    return Array.from({ length: monthDayCount(selected.month) }, (_, index) => {
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

  const monthlyMaximum = niceMaximum(Math.max(1, ...visibleMonthly.map((row) => messageCount(row, countMode))), 3000);
  const dailyMaximum = niceMaximum(Math.max(1, ...selectedDays.map((row) => row.display_messages)), 250);
  const monthlyTicks = Array.from({ length: 5 }, (_, index) => Math.round((monthlyMaximum / 4) * index));
  const dailyTicks = Array.from({ length: 5 }, (_, index) => Math.round((dailyMaximum / 4) * index));

  const selectedTotal = messageCount(selected, countMode);
  const selectedActiveDays = activeDays(selected, countMode);
  const selectedAverage = selectedActiveDays ? selectedTotal / selectedActiveDays : 0;
  const selectedDelta = deltaInfo(selectedTotal, previous ? messageCount(previous, countMode) : null);
  const dayPeak = selectedDays.reduce<DisplayDay | null>((best, row) => (!best || row.display_messages > best.display_messages ? row : best), null);
  const dailyRanking = [...selectedDays]
    .filter((row) => row.display_messages > 0)
    .sort((left, right) => right.display_messages - left.display_messages || left.date.localeCompare(right.date))
    .slice(0, 5);
  const recentActivity = [...selectedDays]
    .filter((row) => row.display_messages > 0)
    .sort((left, right) => right.date.localeCompare(left.date))
    .slice(0, 5);

  const hourlyRows = (data?.hourly_weekday ?? []).filter((row) => row.month === selected?.month);
  const heatMap = new Map(hourlyRows.map((row) => [`${row.weekday}-${row.hour}`, messageCount(row, countMode)]));
  const heatMaximum = Math.max(1, ...heatMap.values());

  if (error) {
    return <main className="center-message"><h1>送信分析ダッシュボード</h1><p>{error}</p></main>;
  }

  if (!data) {
    return <main className="center-message" aria-busy="true"><div className="spinner"/><h1>送信分析ダッシュボード</h1><p>会話本文を含まない集計データを読み込んでいます。</p></main>;
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main id="dashboard" className="dashboard">
        <header className="dashboard-header">
          <h1>送信分析ダッシュボード</h1>
          <div className="header-actions">
            <label className="period-select">
              <span>期間選択</span>
              <Icon name="calendar" size={17} />
              <select value={selected?.month ?? ""} onChange={(event) => setSelectedMonth(event.target.value)}>
                {[...monthly].reverse().map((row) => <option key={row.month} value={row.month}>{formatMonth(row.month)}</option>)}
              </select>
            </label>
            <button className="export-button" type="button" onClick={() => selected && downloadCsv(selectedDays, selected.month, countMode)}>
              <Icon name="download" size={18} />
              エクスポート
            </button>
          </div>
        </header>

        <section className="top-grid">
          <section id="monthly" className="panel monthly-panel">
            <div className="panel-heading">
              <div>
                <h2>月ごとの送信回数 <span className="info-dot">i</span></h2>
                <p>月別の送信回数を比較して、増減の流れをつかめます</p>
              </div>
              <div className={`delta-pill ${selectedDelta.className}`}>前月比 <strong>{selectedDelta.value}{selectedDelta.percent}</strong></div>
            </div>
            <div className="axis-chart monthly-axis-chart" aria-label={`月別送信回数（${countModes[countMode].label}）`}>
              <div className="y-axis">
                {[...monthlyTicks].reverse().map((tick) => <span key={tick}>{numberFormatter.format(tick)}</span>)}
              </div>
              <div className="plot monthly-plot">
                {[...monthlyTicks].reverse().map((tick, index) => <i key={tick} style={{ top: `${index * 25}%` }} />)}
                <div className="monthly-bars">
                  {visibleMonthly.map((row) => {
                    const count = messageCount(row, countMode);
                    const selectedBar = row.month === selected?.month;
                    return (
                      <button type="button" key={row.month} className={selectedBar ? "selected" : ""} onClick={() => setSelectedMonth(row.month)} title={`${formatMonth(row.month)}: ${numberFormatter.format(count)}回`}>
                        <span className="chart-value">{numberFormatter.format(count)}</span>
                        <span className="bar-shell"><span className="bar-fill" style={{ height: `${Math.max(1.5, (count / monthlyMaximum) * 100)}%` }} /></span>
                        <span className="chart-label">{formatMonthAxis(row.month)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            <p className="chart-note">棒の高さは各月の送信回数です。棒を選ぶと日別表示へ切り替わります。</p>
          </section>

          <aside className="panel summary-panel">
            <div className="panel-heading summary-heading"><h2>{selected ? formatMonth(selected.month) : "選択月"}のサマリー</h2></div>
            <div className="summary-main-grid">
              <MetricCard label="送信回数（全体）" value={numberFormatter.format(messageCount(selected, "all"))} note="音声会話を含む送信回数" />
              <MetricCard label="音声を除く送信回数" value={numberFormatter.format(messageCount(selected, "nonVoice"))} note="音声会話と識別した発話を除外" />
              <MetricCard label="音声のみ送信回数" value={numberFormatter.format(messageCount(selected, "voice"))} note="音声会話として識別できた発話" />
              <MetricCard label={`前月差（${countModes[countMode].label}）`} value={selectedDelta.value} note="現在の集計対象で前月と比較" accent={selectedDelta.className === "positive"} />
            </div>
            <div className="summary-small-grid">
              <MetricCard compact label="送信があった日数" value={`${selectedActiveDays}`} note={`活動日数（${countModes[countMode].label}）`} />
              <MetricCard compact label="1日平均（すべて）" value={decimalFormatter.format(selectedAverage)} note="活動日数あたりの送信回数" />
              <MetricCard compact label="最大日" value={dayPeak ? formatDate(dayPeak.date) : "-"} note="1日の最大送信回数" />
            </div>
          </aside>
        </section>

        <section id="daily" className="panel daily-panel">
          <div className="panel-heading daily-heading">
            <div>
              <h2>{selected ? formatMonth(selected.month) : "選択月"}の日別送信回数 <span className="info-dot">i</span></h2>
              <p>日ごとの送信回数を確認できます（{countModes[countMode].label}）</p>
            </div>
            <div id="filters" className="mode-switch" role="group" aria-label="集計対象">
              {(Object.keys(countModes) as CountMode[]).map((mode) => (
                <button key={mode} type="button" className={countMode === mode ? "active" : ""} aria-pressed={countMode === mode} onClick={() => setCountMode(mode)}>{countModes[mode].label}</button>
              ))}
            </div>
            <span className="chart-icon"><Icon name="chart" size={20} /></span>
          </div>
          <HorizontalScroll
            className="daily-scroll"
            initialEnd
            resetKey={`${selectedMonth}-${countMode}`}
            label="日別送信回数。横方向にスワイプして日付を移動できます"
          >
            <div className="axis-chart daily-axis-chart" aria-label={`${selected ? formatMonth(selected.month) : "選択月"}の日別送信回数`}>
              <div className="y-axis">
                {[...dailyTicks].reverse().map((tick) => <span key={tick}>{numberFormatter.format(tick)}</span>)}
              </div>
              <div className="plot daily-plot">
                {[...dailyTicks].reverse().map((tick, index) => <i key={tick} style={{ top: `${index * 25}%` }} />)}
                <div className="daily-bars">
                  {selectedDays.map((row) => (
                    <div key={row.date} title={`${row.date}: ${numberFormatter.format(row.display_messages)}回`}>
                      <span className="chart-value">{numberFormatter.format(row.display_messages)}</span>
                      <span className="bar-shell"><span className="bar-fill" style={{ height: `${Math.max(1, (row.display_messages / dailyMaximum) * 100)}%` }} /></span>
                      <span className="chart-label">{String(row.day).padStart(2, "0")}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </HorizontalScroll>
        </section>

        <section id="reports" className="bottom-grid">
          <section className="panel ranking-panel">
            <div className="panel-heading compact"><h2>送信回数ランキング <span>（{selected ? formatMonth(selected.month) : "-"}）</span></h2></div>
            <div className="ranking-table">
              <div className="ranking-head"><span>ランク</span><span>日付</span><span>送信回数</span><span /></div>
              {dailyRanking.map((row, index) => (
                <div className="ranking-row" key={row.date}>
                  <span>{index + 1}</span>
                  <strong>{formatDateWithWeekday(row.date)}</strong>
                  <b>{numberFormatter.format(row.display_messages)}</b>
                  <i><span style={{ width: `${(row.display_messages / Math.max(1, dailyRanking[0]?.display_messages ?? 1)) * 100}%` }} /></i>
                </div>
              ))}
            </div>
          </section>

          <section className="panel heatmap-panel">
            <div className="panel-heading compact">
              <h2>時間帯別の送信傾向 <span>（{selected ? formatMonth(selected.month) : "-"}）</span> <span className="info-dot">i</span></h2>
              <p>時間帯ごとの平均送信回数（{countModes[countMode].label}）</p>
            </div>
            <HorizontalScroll
              className="heatmap-scroll"
              resetKey={`${selectedMonth}-${countMode}`}
              label="時間帯別の送信傾向。横方向にスワイプして時間を移動できます"
            >
              <div className="heatmap-wrap">
                <div className="heatmap-hours">{Array.from({ length: 12 }, (_, index) => <span key={index}>{index * 2}</span>)}</div>
                <div className="heatmap-grid">
                  {weekdays.map((weekday, weekdayIndex) => (
                    <div className="heatmap-row" key={weekday}>
                      <strong>{weekday}</strong>
                      <div>{Array.from({ length: 24 }, (_, hour) => {
                        const value = heatMap.get(`${weekdayIndex}-${hour}`) ?? 0;
                        const opacity = value ? 0.18 + (value / heatMaximum) * 0.82 : 0.08;
                        return <span key={hour} style={{ opacity }} title={`${weekday}曜 ${hour}時: ${numberFormatter.format(value)}回`} />;
                      })}</div>
                    </div>
                  ))}
                </div>
                <div className="heatmap-legend"><span>少ない</span>{Array.from({ length: 7 }, (_, index) => <i key={index} style={{ opacity: 0.12 + index * 0.14 }} />)}<span>多い</span></div>
              </div>
            </HorizontalScroll>
          </section>

          <section className="panel activity-panel">
            <div className="panel-heading compact"><h2>最近の送信アクティビティ</h2></div>
            <HorizontalScroll
              className="activity-scroll"
              resetKey={`${selectedMonth}-${countMode}`}
              label="最近の送信アクティビティ。横方向にスワイプして列を確認できます"
            >
              <div className="activity-table">
                <div className="activity-head"><span>日時</span><span>種別</span><span>送信回数</span><span>音声割合</span><span>ステータス</span></div>
                {recentActivity.map((row) => {
                  const voiceRatio = row.sent_messages ? (row.voice_messages / row.sent_messages) * 100 : 0;
                  return (
                    <div className="activity-row" key={row.date}>
                      <span>{row.date.replaceAll("-", "/")}</span>
                      <span>{countModes[countMode].label}</span>
                      <strong>{numberFormatter.format(row.display_messages)}</strong>
                      <span>{decimalFormatter.format(voiceRatio)}%</span>
                      <span className="status"><i />完了</span>
                    </div>
                  );
                })}
              </div>
            </HorizontalScroll>
            <a className="activity-link" href="#daily">送信履歴をすべて見る <span>→</span></a>
          </section>
        </section>

        <section className="panel all-time-panel" aria-label="全期間サマリー">
          <div className="panel-heading compact"><div><h2>全期間サマリー</h2><p>個人情報を含まない数値集計のみ</p></div></div>
          <div className="all-time-grid">
            <MetricCard compact label="全件" value={numberFormatter.format(data.totals.sent_messages)} note="全ユーザー送信" />
            <MetricCard compact label="音声を除く" value={numberFormatter.format(data.totals.non_voice_messages)} note="音声会話を除外" />
            <MetricCard compact label="音声のみ" value={numberFormatter.format(data.totals.voice_messages)} note="識別できた音声発話" />
            <MetricCard compact label="活動日数" value={`${numberFormatter.format(data.totals.active_days)}日`} note="送信があった日" />
            <MetricCard compact label="会話数" value={numberFormatter.format(data.totals.conversation_count)} note="重複を除く会話単位" />
            <MetricCard compact label="推定トークン" value={numberFormatter.format(data.totals.estimated_tokens)} note="非公式の概算値" />
          </div>
        </section>

        <footer id="settings" className="privacy-note">
          <strong>この画面に会話本文・会話タイトル・IDは含まれていません。</strong>
          <span>{data.method} 数値はChatGPT公式ではなく、エクスポートデータからローカルで算出した非公式集計です。</span>
        </footer>
      </main>
    </div>
  );
}
