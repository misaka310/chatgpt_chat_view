#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def judge(row: dict) -> str:
    if row.get("exceeded_threshold"):
        return '<span class="bad">160超過</span>'
    if row.get("reached_threshold"):
        return '<span class="warn">160到達</span>'
    return '<span class="ok">未到達</span>'


def build_table(rows: list[dict], key: str) -> str:
    body = "".join(
        f"<tr><td>{esc(r.get(key))}</td><td class='num'>{esc(r.get('max_3h_user_messages'))}</td><td>{judge(r)}</td><td>{esc(r.get('peak_window_start_jst'))}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='4'>データなし</td></tr>"
    return "<table><thead><tr><th>期間</th><th>最大3時間送信数</th><th>判定</th><th>ピーク開始</th></tr></thead><tbody>" + body + "</tbody></table>"


def build_windows(rows: list[dict]) -> str:
    body = "".join(
        f"<tr><td>{esc(r.get('window_start_jst'))}</td><td>{esc(r.get('window_end_jst'))}</td><td class='num'>{esc(r.get('user_messages_in_3h'))}</td><td>{judge(r)}</td><td>{esc(r.get('conversation_title_at_start'))}</td></tr>"
        for r in rows[:50]
    ) or "<tr><td colspan='5'>160到達ウィンドウなし</td></tr>"
    return "<table><thead><tr><th>開始</th><th>終了</th><th>送信数</th><th>判定</th><th>開始時の会話</th></tr></thead><tbody>" + body + "</tbody></table>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, default=Path("output"))
    args = ap.parse_args()
    out = args.output_dir.resolve()
    data = json.loads((out / "gpt_3h_limit_summary.json").read_text(encoding="utf-8"))
    s = data["summary"]
    verdict = "160超過" if s["exceeded_threshold"] else ("160到達" if s["reached_threshold"] else "160未到達")
    cls = "bad" if s["exceeded_threshold"] else ("warn" if s["reached_threshold"] else "ok")
    html_text = f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><link rel='icon' href='favicon.svg' type='image/svg+xml'><title>GPT 3時間160送信チェック</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:radial-gradient(circle at 10% 0%,#1d3f8a55,transparent 35%),linear-gradient(135deg,#050816,#091428 55%,#030611);color:#edf4ff;font-family:Segoe UI,Yu Gothic UI,Meiryo,sans-serif}}.wrap{{max-width:1240px;margin:0 auto;padding:24px 16px 48px;display:grid;gap:16px}}.hero,.panel,.card{{background:rgba(11,22,43,.82);border:1px solid rgba(126,164,255,.22);border-radius:22px;box-shadow:0 24px 70px #0008}}.hero{{padding:22px}}.panel{{padding:16px}}h1,h2{{margin:0 0 10px}}.sub,.label,.unit,th{{color:#91a6c8}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}.card{{padding:14px;border-radius:18px}}.value{{font-size:1.45rem;font-weight:850}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid rgba(126,164,255,.14);padding:8px;text-align:left}}.num{{text-align:right}}.ok,.warn,.bad{{display:inline-block;border-radius:999px;padding:4px 10px;font-weight:850}}.ok{{background:#42d98e29;color:#8effc5}}.warn{{background:#ffbd6b29;color:#ffd08e}}.bad{{background:#ff6b7a29;color:#ff9aa4}}a{{color:#65a7ff}}
</style></head><body><main class='wrap'><section class='hero'><h1>GPT 3時間160送信チェック</h1><div class='sub'>任意の連続3時間で160送信に到達・超過した候補を確認します。</div></section><section class='cards'><div class='card'><div class='label'>連続3時間の最大送信数</div><div class='value'>{esc(s['max_3h_user_messages'])}</div><div class='unit'>user messages</div></div><div class='card'><div class='label'>閾値</div><div class='value'>{esc(s['threshold_user_messages'])}</div><div class='unit'>/ {esc(s['window_hours'])}h</div></div><div class='card'><div class='label'>判定</div><div class='value'><span class='{cls}'>{verdict}</span></div><div class='unit'>booleanは表示しません</div></div><div class='card'><div class='label'>ピーク窓</div><div class='value'>{esc(s['peak_window_start_jst'])}</div><div class='unit'>〜 {esc(s['peak_window_end_jst'])}</div></div></section><section class='panel'><h2>月別ピーク</h2>{build_table(data.get('monthly', []), 'month')}</section><section class='panel'><h2>日別ピーク 上位30件</h2>{build_table(sorted(data.get('daily', []), key=lambda r: -int(r.get('max_3h_user_messages',0)))[:30], 'date')}</section><section class='panel'><h2>160到達ウィンドウ</h2>{build_windows(data.get('threshold_windows', []))}</section><section class='panel'><a href='dashboard.html'>ダッシュボードに戻る</a></section></main></body></html>"""
    (out / "gpt_3h_limit.html").write_text(html_text, encoding="utf-8")
    print(f"patched {out / 'gpt_3h_limit.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
