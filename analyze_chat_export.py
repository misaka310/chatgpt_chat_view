#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


CHUNK_SIZE = 1024 * 1024
CHAT_HTML_MARKER = "var jsonData ="
PARSED_REQUIRED_KEYS = (
    "meta",
    "monthly",
    "daily",
    "daily_hourly",
    "monthly_weekday_hour",
    "daily_top_conversations",
    "role_monthly",
)


def stream_json_array(path: Path, marker: Optional[str] = None) -> Iterator[dict]:
    decoder = json.JSONDecoder()
    marker_found = marker is None
    array_started = False
    eof = False
    buf = ""
    pos = 0
    with path.open("r", encoding="utf-8") as f:
        while True:
            if pos >= len(buf):
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    if not array_started:
                        raise ValueError(f"JSON array start not found in {path}")
                    return
                buf = chunk
                pos = 0
            if marker and not marker_found:
                while True:
                    idx = buf.find(marker, pos)
                    if idx >= 0:
                        pos = idx + len(marker)
                        marker_found = True
                        break
                    keep = buf[-(len(marker) - 1) :] if len(marker) > 1 else ""
                    chunk = f.read(CHUNK_SIZE)
                    if chunk == "":
                        raise ValueError(f"Marker '{marker}' not found in {path}")
                    buf = keep + chunk
                    pos = 0
            if not array_started:
                while True:
                    while pos < len(buf) and buf[pos] != "[":
                        pos += 1
                    if pos < len(buf):
                        pos += 1
                        array_started = True
                        break
                    chunk = f.read(CHUNK_SIZE)
                    if chunk == "":
                        raise ValueError(f"JSON array start '[' not found in {path}")
                    buf = chunk
                    pos = 0
            while True:
                while pos < len(buf) and (buf[pos].isspace() or buf[pos] == ","):
                    pos += 1
                if pos < len(buf):
                    break
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    eof = True
                    break
                buf = buf[pos:] + chunk
                pos = 0
            if eof:
                return
            if buf[pos] == "]":
                return
            try:
                item, end = decoder.raw_decode(buf, pos)
                pos = end
                if isinstance(item, dict):
                    yield item
            except json.JSONDecodeError:
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    raise
                buf = buf[pos:] + chunk
                pos = 0


def detect_inputs(base_dir: Path) -> tuple[list[Path], Optional[str]]:
    shards = sorted(base_dir.glob("conversations-*.json"))
    if shards:
        return shards, None
    single = base_dir / "conversations.json"
    if single.exists():
        return [single], None
    html = base_dir / "chat.html"
    if html.exists():
        return [html], CHAT_HTML_MARKER
    raise FileNotFoundError("No input file found.")


def ensure_timezone(tz_name: Optional[str]):
    if tz_name:
        if ZoneInfo is not None:
            try:
                return ZoneInfo(tz_name)
            except Exception:
                pass
        fallback = {"UTC": 0, "Etc/UTC": 0, "Asia/Tokyo": 9}
        if tz_name in fallback:
            return timezone(timedelta(hours=fallback[tz_name]), name=tz_name)
        raise RuntimeError(f"Timezone '{tz_name}' could not be resolved.")
    local_tz = datetime.now().astimezone().tzinfo
    return local_tz or timezone.utc


def pick_timestamp(message: dict) -> Optional[float]:
    for key in ("create_time", "update_time"):
        value = message.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def normalize_role(role: Optional[str]) -> str:
    if not role:
        return "other"
    value = role.strip().lower()
    if value in ("user", "assistant", "system", "tool"):
        return value
    return "other"


def has_required_parsed_shape(parsed: Any) -> bool:
    return isinstance(parsed, dict) and all(k in parsed for k in PARSED_REQUIRED_KEYS)


def should_reuse_parsed(parsed_path: Path, inputs: list[Path]) -> bool:
    if not parsed_path.exists():
        return False
    parsed_mtime = parsed_path.stat().st_mtime
    return all(p.stat().st_mtime <= parsed_mtime for p in inputs)


def safe_title(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def collect_stats_from_inputs(paths: Iterable[Path], marker: Optional[str], local_tz) -> dict:
    monthly_user: Counter[str] = Counter()
    monthly_conv_ids: Dict[str, set[str]] = defaultdict(set)
    monthly_active_days: Dict[str, set[str]] = defaultdict(set)
    daily_user: Counter[str] = Counter()
    daily_conv_ids: Dict[str, set[str]] = defaultdict(set)
    daily_hourly: Counter[tuple[str, int]] = Counter()
    monthly_weekday_hour: Counter[tuple[str, int, int]] = Counter()
    daily_conv_user_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    monthly_role_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    conv_titles: Dict[str, str] = {}
    total_conversation_objects = 0
    total_timestamped_messages = 0

    for path in paths:
        file_marker = marker if path.name.lower().endswith(".html") else None
        for conversation in stream_json_array(path, marker=file_marker):
            total_conversation_objects += 1
            conv_id = (
                conversation.get("conversation_id")
                or conversation.get("id")
                or f"conv-{total_conversation_objects}"
            )
            conv_titles[conv_id] = safe_title(conversation.get("title"), f"(untitled:{conv_id[:8]})")
            mapping = conversation.get("mapping")
            if not isinstance(mapping, dict):
                continue
            seen_ids: set[str] = set()
            for node in mapping.values():
                if not isinstance(node, dict):
                    continue
                message = node.get("message")
                if not isinstance(message, dict):
                    continue
                msg_id = message.get("id") or node.get("id")
                if isinstance(msg_id, str):
                    if msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                ts = pick_timestamp(message)
                if ts is None:
                    continue
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz)
                month = dt.strftime("%Y-%m")
                day = dt.strftime("%Y-%m-%d")
                hour = dt.hour
                weekday = dt.weekday()
                author = message.get("author") or {}
                role = normalize_role(author.get("role") if isinstance(author, dict) else None)
                monthly_role_counts[month][role] += 1
                total_timestamped_messages += 1
                if role != "user":
                    continue
                monthly_user[month] += 1
                monthly_conv_ids[month].add(conv_id)
                monthly_active_days[month].add(day)
                daily_user[day] += 1
                daily_conv_ids[day].add(conv_id)
                daily_hourly[(day, hour)] += 1
                monthly_weekday_hour[(month, weekday, hour)] += 1
                daily_conv_user_counts[day][conv_id] += 1

    months = sorted(
        set(monthly_user.keys())
        | set(monthly_conv_ids.keys())
        | set(monthly_active_days.keys())
        | set(monthly_role_counts.keys())
    )
    monthly_rows = []
    role_monthly_rows = []
    for month in months:
        role_counts = monthly_role_counts.get(month, Counter())
        monthly_rows.append(
            {
                "month": month,
                "year": month[:4],
                "user_messages": int(monthly_user.get(month, 0)),
                "conversations": int(len(monthly_conv_ids.get(month, set()))),
                "active_days": int(len(monthly_active_days.get(month, set()))),
            }
        )
        role_monthly_rows.append(
            {
                "month": month,
                "year": month[:4],
                "user": int(role_counts.get("user", 0)),
                "assistant": int(role_counts.get("assistant", 0)),
                "system": int(role_counts.get("system", 0)),
                "tool": int(role_counts.get("tool", 0)),
                "other": int(role_counts.get("other", 0)),
                "total": int(sum(role_counts.values())),
            }
        )

    days = sorted(daily_user.keys())
    daily_rows = [
        {
            "date": day,
            "year": day[:4],
            "month": day[:7],
            "day": int(day[8:10]),
            "weekday": datetime.strptime(day, "%Y-%m-%d").weekday(),
            "user_messages": int(daily_user[day]),
            "conversations": int(len(daily_conv_ids.get(day, set()))),
        }
        for day in days
    ]
    daily_hourly_rows = [
        {"date": day, "hour": hour, "user_messages": int(daily_hourly.get((day, hour), 0))}
        for day in days
        for hour in range(24)
    ]
    monthly_weekday_hour_rows = [
        {
            "month": month,
            "weekday": weekday,
            "hour": hour,
            "user_messages": int(monthly_weekday_hour.get((month, weekday, hour), 0)),
        }
        for month in months
        for weekday in range(7)
        for hour in range(24)
    ]
    daily_top_conversations_rows = []
    for day in days:
        ordered = sorted(daily_conv_user_counts.get(day, Counter()).items(), key=lambda kv: (-kv[1], kv[0]))
        for rank, (conv_id, count) in enumerate(ordered, start=1):
            daily_top_conversations_rows.append(
                {
                    "date": day,
                    "rank": rank,
                    "conversation_id": conv_id,
                    "title": conv_titles.get(conv_id, f"(untitled:{conv_id[:8]})"),
                    "user_messages": int(count),
                }
            )

    return {
        "meta": {
            "generated_at": datetime.now().astimezone().isoformat(),
            "timezone": getattr(local_tz, "key", str(local_tz)),
            "input_files": [str(p) for p in paths],
            "definitions": {
                "user_messages": "author.role == user",
                "conversation_count": "unique conversation_id with >=1 user message in period",
                "active_days": "unique local dates with >=1 user message in period",
                "timestamp_priority": "create_time first, then update_time",
            },
            "stats": {
                "total_conversation_objects": total_conversation_objects,
                "total_timestamped_messages": total_timestamped_messages,
            },
        },
        "monthly": monthly_rows,
        "daily": daily_rows,
        "daily_hourly": daily_hourly_rows,
        "monthly_weekday_hour": monthly_weekday_hour_rows,
        "daily_top_conversations": daily_top_conversations_rows,
        "role_monthly": role_monthly_rows,
    }


def write_csv(path: Path, header: list[str], rows: Iterable[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_monthly_summary_md(path: Path, parsed: dict) -> None:
    monthly = parsed["monthly"]
    by_month = {row["month"]: row for row in monthly}
    lines = ["# Monthly Usage Summary", "", "## 結論"]
    for month in ("2026-03", "2026-02"):
        row = by_month.get(month)
        if row:
            lines.append(
                f"- `{month}`: userメッセージ {row['user_messages']} 件 / 会話数 {row['conversations']} 件 / 活動日数 {row['active_days']} 日"
            )
        else:
            lines.append(f"- `{month}`: データなし")
    lines += [
        "",
        "## 定義",
        "- userメッセージ数: `author.role == user` の件数",
        "- 会話数(月別): その月に user メッセージが1件以上ある会話のユニーク数",
        "- 活動日数(月別): その月に user メッセージがあったローカル日付のユニーク数",
        "- タイムスタンプ: `create_time` 優先、なければ `update_time`",
        f"- タイムゾーン: `{parsed['meta']['timezone']}`",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _json_for_html(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_dashboard_html(parsed: dict) -> str:
    payload = _json_for_html(parsed)
    template = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChatGPT Usage Dashboard</title>
  <style>
    :root{{--bg:#0a0f1a;--card:#121a2a;--line:#23314d;--ink:#e8eefc;--muted:#9caecc;--a:#52a8ff;--b:#f59f6a;--r:14px}}
    *{{box-sizing:border-box}} body{{margin:0;color:var(--ink);font-family:"Segoe UI","Yu Gothic UI","Meiryo",sans-serif;background:radial-gradient(900px 500px at -10% -10%,#1d3158 0%,transparent 60%),radial-gradient(700px 400px at 110% -20%,#31204c 0%,transparent 58%),linear-gradient(180deg,#0a0f1a 0%,#070b12 100%)}}
    .wrap{{max-width:1400px;margin:0 auto;padding:18px 22px 28px;display:grid;gap:14px}}
    .card{{border:1px solid var(--line);border-radius:var(--r);background:linear-gradient(180deg,var(--card) 0%,#101625 100%);box-shadow:0 18px 45px rgba(2,5,11,.34);padding:14px}}
    .header{{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}} h1{{margin:0;font-size:1.45rem}} p{{margin:6px 0 0;color:var(--muted);font-size:.92rem}}
    select{{background:#0d1320;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:.95rem}}
    .kpis{{display:grid;grid-template-columns:repeat(6,minmax(140px,1fr));gap:10px}} .kpi{{border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:linear-gradient(170deg,rgba(255,255,255,.03),rgba(255,255,255,.01))}}
    .kpi .label{{color:var(--muted);font-size:.82rem}} .kpi .value{{margin-top:6px;font-size:1.25rem;font-weight:700}}
    .t{{margin:0 0 10px;font-size:1.02rem;font-weight:700}} .ga{{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:10px}} .gm{{display:grid;grid-template-columns:1.2fr 1fr;gap:10px}} .gd{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
    .meta{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:.9rem;margin-bottom:8px}} .area{{border:1px solid var(--line);border-radius:12px;padding:10px;min-height:235px;background:rgba(8,14,24,.5)}}
    .bar-chart{{height:210px;display:grid;align-items:end;gap:6px}} .bar-item{{display:grid;grid-template-rows:1fr auto auto;gap:4px;border:none;background:transparent;color:inherit;cursor:pointer;padding:0}}
    .bar{{border-radius:8px 8px 4px 4px;border:1px solid rgba(255,255,255,.1);background:linear-gradient(180deg,rgba(82,168,255,.95),rgba(82,168,255,.45));min-height:4px;transition:transform .15s ease,box-shadow .15s ease}}
    .bar-item:hover .bar{{transform:translateY(-2px);box-shadow:0 0 0 2px rgba(82,168,255,.15) inset}} .bar-item.active .bar{{outline:2px solid rgba(245,159,106,.65);background:linear-gradient(180deg,rgba(245,159,106,.95),rgba(245,159,106,.45))}}
    .bar-label{{font-size:.73rem;color:var(--muted);text-align:center;white-space:nowrap}} .bar-value{{font-size:.7rem;text-align:center;color:#becdf0}}
    .c-head{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin-bottom:4px}} .c-head div{{color:var(--muted);font-size:.72rem;text-align:center}}
    .c-grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}} .day{{border:1px solid rgba(255,255,255,.08);border-radius:8px;min-height:44px;font-size:.75rem;padding:4px;color:#d9e6ff;background:rgba(255,255,255,.03);display:flex;flex-direction:column;justify-content:space-between;cursor:pointer}}
    .day.m{{visibility:hidden;pointer-events:none}} .day.a{{outline:2px solid rgba(245,159,106,.8)}} .n{{font-weight:600}} .cnt{{color:#b7caef;font-size:.68rem}}
    .hmw{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;padding:8px;background:rgba(6,12,22,.65)}} .hmt{border-collapse:collapse;min-width:860px;width:100%}
    .hmt th,.hmt td{{border:1px solid rgba(255,255,255,.06);text-align:center;font-size:.67rem;padding:4px}} .hmt th{{color:var(--muted);background:rgba(255,255,255,.03);position:sticky;left:0;z-index:1}}
    .tw{{border:1px solid var(--line);border-radius:10px;overflow:auto;max-height:310px}table{width:100%;border-collapse:collapse;min-width:420px}th,td{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.07);font-size:.84rem;text-align:left;vertical-align:top}th{color:var(--muted);position:sticky;top:0;background:#0d1422;z-index:1}
    .e{color:var(--muted);font-size:.9rem}
    @media (max-width:1200px){.ga,.gm,.gd{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,minmax(140px,1fr))}}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card header"><div><h1>ChatGPT 利用履歴ダッシュボード</h1><p>file:// 直開き対応 / 時刻基準: <span id="tz"></span></p></div><div><label for="year" style="color:var(--muted);font-size:.85rem">表示年</label><br/><select id="year"></select></div></section>
    <section class="card"><h2 class="t">上段 KPI</h2><div class="kpis" id="kpis"></div></section>
    <section class="card"><h2 class="t">年間ビュー</h2><div class="ga"><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">月別 user メッセージ数（クリックで月詳細）</div><div id="mUser"></div></div><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">月別 平均/経過日</div><div id="mAvgElapsed"></div></div><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">月別 平均/アクティブ日</div><div id="mAvgActive"></div></div><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">月別 中央値/日次</div><div id="mMedianDaily"></div></div></div></section>
    <section class="card"><h2 class="t">月間ビュー <span id="mTitle"></span></h2><div class="meta" id="mMeta"></div><div class="gm"><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">日別 user メッセージ数（クリックで日詳細）</div><div id="dInM"></div></div><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">月内日別カレンダーヒートマップ</div><div id="cal"></div></div></div><div class="area" style="margin-top:10px"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">曜日 × 時間帯 user メッセージ数 ヒートマップ</div><div id="wHm"></div></div></section>
    <section class="card"><h2 class="t">日別ビュー <span id="dTitle"></span></h2><div class="meta" id="dMeta"></div><div class="gd"><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">時間帯別 user メッセージ数</div><div id="hInD"></div></div><div class="area"><div style="margin-bottom:8px;color:var(--muted);font-size:.84rem">会話ごとの件数ランキング</div><div id="dTbl"></div></div></div></section>
  </div>
  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA=JSON.parse(document.getElementById("data").textContent),WD=["月","火","水","木","金","土","日"],WDS=["日","月","火","水","木","金","土"];
    const M=DATA.monthly||[],D=DATA.daily||[],DH=DATA.daily_hourly||[],MWH=DATA.monthly_weekday_hour||[],DTC=DATA.daily_top_conversations||[];
    const MM=new Map(M.map(r=>[r.month,r])),DBM=new Map(),DHM=new Map(),MWHM=new Map(),DTCM=new Map(),DMM=new Map(),LAST_DAY_BY_MONTH=new Map();
    for(const r of D){if(!DBM.has(r.month))DBM.set(r.month,[]);DBM.get(r.month).push(r);if(!DMM.has(r.month))DMM.set(r.month,new Map());DMM.get(r.month).set(r.day,r.user_messages);LAST_DAY_BY_MONTH.set(r.month,Math.max(LAST_DAY_BY_MONTH.get(r.month)||0,r.day))} for(const a of DBM.values())a.sort((x,y)=>x.date.localeCompare(y.date));
    for(const r of DH){if(!DHM.has(r.date))DHM.set(r.date,Array(24).fill(0));DHM.get(r.date)[r.hour]=r.user_messages}
    for(const r of MWH){if(!MWHM.has(r.month))MWHM.set(r.month,Array.from({length:7},()=>Array(24).fill(0)));MWHM.get(r.month)[r.weekday][r.hour]=r.user_messages}
    for(const r of DTC){if(!DTCM.has(r.date))DTCM.set(r.date,[]);DTCM.get(r.date).push(r)}
    const years=Array.from(new Set(M.map(r=>r.year))).sort(),S={year:years.length?years[years.length-1]:null,month:null,day:null};
    const f=v=>Number(v||0).toLocaleString(),f1=v=>Number(v||0).toLocaleString(undefined,{minimumFractionDigits:1,maximumFractionDigits:1}),maxBy=(arr,fn)=>arr.length?arr.reduce((a,b)=>fn(b)>fn(a)?b:a):null;
    const monthsInYear=y=>M.filter(r=>r.year===y).map(r=>r.month).sort(),daysInMonth=m=>(DBM.get(m)||[]).slice().sort((a,b)=>a.date.localeCompare(b.date));
    const calendarDaysInMonth=m=>{const y=Number(m.slice(0,4)),mm=Number(m.slice(5,7));return new Date(y,mm,0).getDate()};
    const latestDaily=maxBy(D,r=>r.date),latestMonth=latestDaily?latestDaily.month:null;
    const isInProgressMonth=month=>{if(!latestMonth||month!==latestMonth)return false;const last=LAST_DAY_BY_MONTH.get(month)||0;return last>0&&last<calendarDaysInMonth(month)};
    const elapsedDaysInMonth=month=>{if(isInProgressMonth(month)){return LAST_DAY_BY_MONTH.get(month)||calendarDaysInMonth(month)}return calendarDaysInMonth(month)};
    const median=arr=>{if(!arr.length)return 0;const s=arr.slice().sort((a,b)=>a-b),mid=Math.floor(s.length/2);return s.length%2?s[mid]:(s[mid-1]+s[mid])/2};
    const dailySeriesForMonth=(month,useElapsedDays=true)=>{const maxDay=useElapsedDays?elapsedDaysInMonth(month):calendarDaysInMonth(month),dayMap=DMM.get(month)||new Map(),vals=[];for(let day=1;day<=maxDay;day++)vals.push(dayMap.get(day)||0);return vals};
    const avgPerElapsedDay=row=>row?row.user_messages/elapsedDaysInMonth(row.month):0;
    const avgPerCalendarDay=row=>row?row.user_messages/calendarDaysInMonth(row.month):0;
    const avgPerActiveDay=row=>row&&row.active_days>0?row.user_messages/row.active_days:0;
    const medianPerDaily=row=>row?median(dailySeriesForMonth(row.month,true)):0;
    const c=(v,m,w)=>{const r=m>0?Math.min(1,v/m):0;return w===1?`rgba(245,${Math.round(120+60*r)},${Math.round(80+40*r)},${0.15+r*0.8})`:`rgba(${Math.round(82+10*r)},${Math.round(168+20*r)},255,${0.15+r*0.8})`};
    function bar(id,labels,vals,opt={}){const root=document.getElementById(id);root.innerHTML="";const g=document.createElement("div");g.className="bar-chart";g.style.gridTemplateColumns=`repeat(${Math.max(labels.length,1)},minmax(0,1fr))`;const mv=Math.max(...vals,0),vf=opt.valueFormatter||f;labels.forEach((lab,i)=>{const v=vals[i]||0,b=document.createElement("button");b.className="bar-item";if(opt.activeLabel&&opt.activeLabel===lab)b.classList.add("active");const h=document.createElement("span");h.className="bar";h.style.height=`${Math.max(4,Math.round((mv>0?v/mv:0)*160))}px`;const l=document.createElement("span");l.className="bar-label";l.textContent=lab;const n=document.createElement("span");n.className="bar-value";n.textContent=vf(v);b.append(h,l,n);if(typeof opt.onClick==="function"){b.addEventListener("click",()=>opt.onClick(lab,v,i))}else{b.style.cursor="default"}g.appendChild(b)});root.appendChild(g)}
    function yearSelect(){const e=document.getElementById("year");e.innerHTML="";for(const y of years){const o=document.createElement("option");o.value=y;o.textContent=y;if(y===S.year)o.selected=true;e.appendChild(o)}e.onchange=()=>{S.year=e.value;const ms=monthsInYear(S.year);S.month=ms.length?ms[ms.length-1]:null;const ds=S.month?daysInMonth(S.month):[];S.day=ds.length?ds[0].date:null;render()}}
    function kpis(){const ms=M.filter(r=>r.year===S.year),mids=ms.map(m=>m.month),tu=M.reduce((a,r)=>a+r.user_messages,0),ta=M.reduce((a,r)=>a+r.active_days,0),ted=M.reduce((a,r)=>a+elapsedDaysInMonth(r.month),0),allSeries=M.flatMap(m=>dailySeriesForMonth(m.month,true)),td=maxBy(D,r=>r.user_messages);
      const items=[["総 user メッセージ数",f(tu)],["総活動日数",f(ta)],["総平均/経過日",f1(ted?tu/ted:0)],["総平均/アクティブ日",f1(ta?tu/ta:0)],["総中央値/日次",f1(median(allSeries))],["最多日",td?`${td.date} (${f(td.user_messages)})`:"-"]];
      const g=document.getElementById("kpis");g.innerHTML="";for(const it of items){const el=document.createElement("div");el.className="kpi";el.innerHTML=`<div class="label">${it[0]}</div><div class="value">${it[1]}</div>`;g.appendChild(el)}
      if((!S.month||!mids.includes(S.month))&&mids.length)S.month=mids[mids.length-1];const cds=S.month?daysInMonth(S.month):[];if((!S.day||!cds.some(d=>d.date===S.day))&&cds.length){const t=maxBy(cds,d=>d.user_messages);S.day=t?t.date:cds[0].date}}
    function annual(){const ms=M.filter(r=>r.year===S.year).slice().sort((a,b)=>a.month.localeCompare(b.month)),labels=ms.map(m=>m.month.slice(5));
      bar("mUser",labels,ms.map(m=>m.user_messages),{activeLabel:S.month?S.month.slice(5):null,onClick:(lab)=>{S.month=`${S.year}-${lab}`;const ds=daysInMonth(S.month),t=maxBy(ds,d=>d.user_messages);S.day=t?t.date:(ds[0]?ds[0].date:null);render()}});
      bar("mAvgElapsed",labels,ms.map(m=>avgPerElapsedDay(m)),{activeLabel:S.month?S.month.slice(5):null,valueFormatter:f1});bar("mAvgActive",labels,ms.map(m=>avgPerActiveDay(m)),{activeLabel:S.month?S.month.slice(5):null,valueFormatter:f1});bar("mMedianDaily",labels,ms.map(m=>medianPerDaily(m)),{activeLabel:S.month?S.month.slice(5):null,valueFormatter:f1})}
    function dayBar(rows){bar("dInM",rows.map(r=>String(r.day).padStart(2,"0")),rows.map(r=>r.user_messages),{activeLabel:S.day?S.day.slice(8):null,onClick:(lab)=>{S.day=`${S.month}-${lab}`;day();cal(rows)}})}
    function cal(rows){const root=document.getElementById("cal");root.innerHTML="";if(!S.month){root.innerHTML='<div class="e">月データがありません</div>';return}const h=document.createElement("div");h.className="c-head";for(const x of WDS){const d=document.createElement("div");d.textContent=x;h.appendChild(d)}root.appendChild(h);const g=document.createElement("div");g.className="c-grid";root.appendChild(g);
      const map=new Map(rows.map(r=>[r.day,r])),y=Number(S.month.slice(0,4)),m=Number(S.month.slice(5,7)),fd=new Date(y,m-1,1).getDay(),dim=new Date(y,m,0).getDate(),mx=Math.max(...rows.map(r=>r.user_messages),0);
      for(let i=0;i<fd;i++){const b=document.createElement("div");b.className="day m";g.appendChild(b)} for(let d=1;d<=dim;d++){const row=map.get(d),cnt=row?row.user_messages:0,cell=document.createElement("button");cell.className="day";if(`${S.month}-${String(d).padStart(2,"0")}`===S.day)cell.classList.add("a");cell.style.background=c(cnt,mx,1);cell.innerHTML=`<span class="n">${d}</span><span class="cnt">${f(cnt)}</span>`;cell.addEventListener("click",()=>{S.day=`${S.month}-${String(d).padStart(2,"0")}`;day();cal(rows);dayBar(rows)});g.appendChild(cell)}}
    function wh(){const root=document.getElementById("wHm");root.innerHTML="";const matrix=MWHM.get(S.month);if(!matrix){root.innerHTML='<div class="e">ヒートマップデータがありません</div>';return}let mx=0;for(const r of matrix)for(const v of r)mx=Math.max(mx,v);
      const wrap=document.createElement("div");wrap.className="hmw";const t=document.createElement("table");t.className="hmt";const th=document.createElement("thead"),trh=document.createElement("tr"),c0=document.createElement("th");c0.textContent="曜/時";trh.appendChild(c0);for(let h=0;h<24;h++){const x=document.createElement("th");x.textContent=String(h);trh.appendChild(x)}th.appendChild(trh);t.appendChild(th);
      const tb=document.createElement("tbody");for(let w=0;w<7;w++){const tr=document.createElement("tr"),x=document.createElement("th");x.textContent=WD[w];tr.appendChild(x);for(let h=0;h<24;h++){const td=document.createElement("td"),v=matrix[w][h]||0;td.textContent=v?String(v):"";td.title=`${WD[w]}曜 ${h}時: ${v}`;td.style.background=c(v,mx,0);tr.appendChild(td)}tb.appendChild(tr)}t.appendChild(tb);wrap.appendChild(t);root.appendChild(wrap)}
    function month(){document.getElementById("mTitle").textContent=S.month?`(${S.month})`:"";if(!S.month){document.getElementById("mMeta").innerHTML='<span class="e">月が選択されていません</span>';return}
      const m=MM.get(S.month),ds=daysInMonth(S.month),td=maxBy(ds,d=>d.user_messages),meta=[`月内 user メッセージ: ${f(m?m.user_messages:0)}`,`月内 活動日数: ${f(m?m.active_days:0)}`,`月平均/経過日: ${f1(m?avgPerElapsedDay(m):0)}`,`月平均/全日数: ${f1(m?avgPerCalendarDay(m):0)}`,`月平均/アクティブ日: ${f1(m?avgPerActiveDay(m):0)}`,`月中央値/日次: ${f1(m?medianPerDaily(m):0)}`,`最多日: ${td?`${td.date} (${f(td.user_messages)})`:"-"}`];
      if(isInProgressMonth(S.month)){meta.push(`経過日数基準: 最新観測日 ${f(elapsedDaysInMonth(S.month))} 日`)}
      document.getElementById("mMeta").innerHTML=meta.map(s=>`<span>${s}</span>`).join("");dayBar(ds);cal(ds);wh()}
    function convTable(){const root=document.getElementById("dTbl");root.innerHTML="";if(!S.day){root.innerHTML='<div class="e">日付が選択されていません</div>';return}const rows=DTCM.get(S.day)||[];if(!rows.length){root.innerHTML='<div class="e">この日の会話データはありません</div>';return}
      const w=document.createElement("div");w.className="tw";const t=document.createElement("table");t.innerHTML="<thead><tr><th>#</th><th>title</th><th>user messages</th></tr></thead>";const b=document.createElement("tbody");for(const r of rows){const tr=document.createElement("tr"),title=r.title||r.conversation_id;tr.innerHTML=`<td>${r.rank}</td><td>${title}</td><td>${f(r.user_messages)}</td>`;b.appendChild(tr)}t.appendChild(b);w.appendChild(t);root.appendChild(w)}
    function day(){document.getElementById("dTitle").textContent=S.day?`(${S.day})`:"";if(!S.day){document.getElementById("dMeta").innerHTML='<span class="e">日付が選択されていません</span>';return}const d=D.find(x=>x.date===S.day),hourly=DHM.get(S.day)||Array(24).fill(0);
      bar("hInD",Array.from({length:24},(_,i)=>String(i).padStart(2,"0")),hourly);let bh=0,bv=0;for(let i=0;i<hourly.length;i++){if(hourly[i]>bv){bv=hourly[i];bh=i}}
      const m=[`user メッセージ: ${f(d?d.user_messages:0)}`,`会話数: ${f(d?d.conversations:0)}`,`最多時間帯: ${String(bh).padStart(2,"0")}時 (${f(bv)})`];document.getElementById("dMeta").innerHTML=m.map(s=>`<span>${s}</span>`).join("");convTable()}
    function render(){document.getElementById("tz").textContent=DATA.meta?.timezone||"unknown";yearSelect();kpis();annual();month();day()} render();
  </script>
</body>
</html>"""
    return template.replace("__PAYLOAD__", payload)


def write_dashboard_html(path: Path, parsed: dict) -> None:
    path.write_text(build_dashboard_html(parsed), encoding="utf-8")


def load_parsed(path: Path) -> dict:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not has_required_parsed_shape(parsed):
        raise ValueError("parsed_summary.json exists but schema is incompatible.")
    return parsed


def write_outputs(output_dir: Path, parsed: dict) -> None:
    monthly = sorted(parsed["monthly"], key=lambda r: r["month"])
    daily = sorted(parsed["daily"], key=lambda r: r["date"])
    daily_hourly = sorted(parsed["daily_hourly"], key=lambda r: (r["date"], r["hour"]))
    write_csv(output_dir / "monthly_user_messages.csv", ["month", "user_messages"], [[r["month"], r["user_messages"]] for r in monthly])
    write_csv(output_dir / "monthly_conversations.csv", ["month", "conversations"], [[r["month"], r["conversations"]] for r in monthly])
    write_csv(output_dir / "monthly_active_days.csv", ["month", "active_days"], [[r["month"], r["active_days"]] for r in monthly])
    write_csv(output_dir / "daily_user_messages.csv", ["date", "user_messages"], [[r["date"], r["user_messages"]] for r in daily])
    write_csv(output_dir / "daily_hourly_user_messages.csv", ["date", "hour", "user_messages"], [[r["date"], r["hour"], r["user_messages"]] for r in daily_hourly])
    write_csv(output_dir / "daily_conversations.csv", ["date", "conversations"], [[r["date"], r["conversations"]] for r in daily])
    (output_dir / "parsed_summary.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    write_monthly_summary_md(output_dir / "monthly_summary.md", parsed)
    write_dashboard_html(output_dir / "dashboard.html", parsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze ChatGPT export and generate static dashboard outputs.")
    parser.add_argument("--input-dir", default=".", help="Directory containing export files")
    parser.add_argument("--output-dir", default=".", help="Directory for generated outputs")
    parser.add_argument("--timezone", default="Asia/Tokyo", help="IANA timezone (default: Asia/Tokyo)")
    parser.add_argument("--rebuild", action="store_true", help="Force reparsing raw export even if parsed_summary.json is reusable")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files, marker = detect_inputs(input_dir)
    parsed_path = output_dir / "parsed_summary.json"

    if not args.rebuild and should_reuse_parsed(parsed_path, input_files):
        parsed = load_parsed(parsed_path)
        parse_mode = "reused parsed_summary.json"
    else:
        local_tz = ensure_timezone(args.timezone)
        parsed = collect_stats_from_inputs(input_files, marker, local_tz)
        parse_mode = "parsed raw export"

    parsed["meta"]["timezone"] = args.timezone
    parsed["meta"]["input_files"] = [str(p) for p in input_files]
    parsed["meta"]["generated_at"] = datetime.now().astimezone().isoformat()
    write_outputs(output_dir, parsed)

    print(f"Mode: {parse_mode}")
    print("Input files:")
    for path in input_files:
        print(f"  - {path}")
    print("Output files:")
    for name in (
        "dashboard.html",
        "monthly_user_messages.csv",
        "monthly_conversations.csv",
        "monthly_active_days.csv",
        "daily_user_messages.csv",
        "daily_hourly_user_messages.csv",
        "daily_conversations.csv",
        "parsed_summary.json",
        "monthly_summary.md",
    ):
        print(f"  - {output_dir / name}")


if __name__ == "__main__":
    main()
