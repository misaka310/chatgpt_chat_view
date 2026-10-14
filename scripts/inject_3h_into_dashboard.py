#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

START = "<!-- gpt-3h-summary:start -->"
END = "<!-- gpt-3h-summary:end -->"


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def verdict(summary: dict) -> tuple[str, str, str]:
    if summary.get("exceeded_threshold"):
        return "160超過", "neg", "160を超えた候補があります"
    if summary.get("reached_threshold"):
        return "160到達", "zero", "160ちょうどに到達した候補があります"
    return "160未到達", "pos", "160には届いていません"


def build_panel(report: dict) -> str:
    summary = report.get("summary", {})
    text, cls, note = verdict(summary)
    return f"""
    {START}
    <section class="panel section" id="gpt3hSummary">
      <div class="section-head">
        <div>
          <h2 class="section-title">3時間160チェック</h2>
          <div class="section-subtitle">任意の連続3時間で160送信に到達・超過した候補です</div>
        </div>
        <a class="trend-chip" href="gpt_3h_limit.html" style="text-decoration:none;">詳細を開く</a>
      </div>
      <div class="summary-grid">
        <article class="metric emphasis">
          <div class="kicker">最大3時間送信数 <span class="small">user messages</span></div>
          <div class="big value-strong">{fmt_int(summary.get('max_3h_user_messages'))}</div>
          <div class="small">閾値 {fmt_int(summary.get('threshold_user_messages', 160))} / {esc(summary.get('window_hours', 3))}h</div>
        </article>
        <article class="metric">
          <div class="kicker">判定</div>
          <div class="big {cls}">{esc(text)}</div>
          <div class="small">{esc(note)}</div>
        </article>
        <article class="metric">
          <div class="kicker">ピーク開始</div>
          <div class="big" style="font-size:1.05rem;line-height:1.3;">{esc(summary.get('peak_window_start_jst', '-'))}</div>
          <div class="small">終了: {esc(summary.get('peak_window_end_jst', '-'))}</div>
        </article>
        <article class="metric">
          <div class="kicker">160到達ウィンドウ数</div>
          <div class="big">{fmt_int(summary.get('threshold_window_count'))}</div>
          <div class="small">超過幅: {fmt_int(summary.get('over_threshold_by'))}</div>
        </article>
      </div>
      <div class="footnote">これは公式のモデル別利用量ではなく、ChatGPTエクスポート内のユーザー送信数から作る候補値です。</div>
    </section>
    {END}
"""


def inject(html_text: str, panel: str) -> str:
    if START in html_text and END in html_text:
        before = html_text.split(START, 1)[0]
        after = html_text.split(END, 1)[1]
        return before + panel + after
    marker = "\n  </div>\n\n  <script>"
    if marker not in html_text:
        raise RuntimeError("dashboard shell marker not found")
    return html_text.replace(marker, "\n" + panel + marker, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject 3h summary into dashboard.html.")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    out = args.output_dir.resolve()
    dashboard_path = out / "dashboard.html"
    report_path = out / "gpt_3h_limit_summary.json"
    if not dashboard_path.exists():
        raise SystemExit(f"missing {dashboard_path}")
    if not report_path.exists():
        raise SystemExit(f"missing {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    panel = build_panel(report)
    dashboard_path.write_text(inject(dashboard_path.read_text(encoding="utf-8"), panel), encoding="utf-8")
    print(f"Injected 3h summary into {dashboard_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
