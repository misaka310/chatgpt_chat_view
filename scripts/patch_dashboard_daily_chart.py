#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

START = "<!-- dashboard-layout-fit:start -->"
END = "<!-- dashboard-layout-fit:end -->"

PATCH = f"""
{START}
<style>
  .shell {{ gap: 10px !important; padding-top: 16px !important; }}
  .grid-top, .grid-bottom {{ gap: 10px !important; align-items: start !important; }}
  .grid-top > .panel, .grid-bottom > .panel {{ align-self: start !important; }}
  .section {{ padding: 16px !important; }}
  .section-head {{ margin-bottom: 10px !important; }}
  .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 8px !important; }}
  .metric {{ min-height: 82px !important; padding: 10px !important; gap: 5px !important; }}
  .metric.emphasis {{ grid-column: auto !important; }}
  .metric .big {{ font-size: clamp(1.18rem, 1.36vw, 1.62rem) !important; line-height: 1.04 !important; white-space: nowrap !important; letter-spacing: -0.035em !important; }}
  .summary-grid .metric:nth-child(2) .big {{ font-size: clamp(1.05rem, 1.16vw, 1.42rem) !important; }}
  .metric .small {{ font-size: 0.76rem !important; }}
  .chart-frame {{ gap: 7px !important; }}
  .bar-chart {{ gap: clamp(4px, 0.5vw, 9px) !important; }}
  .bar-item {{ grid-template-rows: auto 118px auto !important; gap: 6px !important; }}
  .bar-item.daily {{ grid-template-rows: auto 124px auto !important; }}
  .bar-track, .bar-item.daily .bar-track {{ min-height: 0 !important; height: 100% !important; padding: 6px 4px !important; }}
  .bar-value {{ font-size: clamp(0.62rem, 0.7vw, 0.78rem) !important; line-height: 1 !important; }}
  .footnote {{ margin-top: 6px !important; }}
  .chart-scroll {{ overflow-x: visible !important; padding-bottom: 0 !important; }}
  .daily-chart {{ width: 100% !important; min-width: 0 !important; grid-template-columns: repeat(var(--day-count, 31), minmax(0, 1fr)) !important; gap: clamp(2px, 0.34vw, 6px) !important; }}
  .daily-chart .bar-item {{ min-width: 0 !important; overflow: visible !important; }}
  .daily-chart .bar-value {{ min-width: 0 !important; max-width: 100% !important; white-space: nowrap !important; overflow: visible !important; font-size: clamp(0.52rem, 0.58vw, 0.68rem) !important; letter-spacing: -0.055em !important; }}
  .daily-chart .bar-label {{ font-size: clamp(0.54rem, 0.62vw, 0.7rem) !important; }}
  .daily-footer {{ margin-top: 8px !important; }}
  .daily-footer .stat {{ padding: 10px 10px !important; gap: 4px !important; }}
  @media (max-width: 1200px) {{ .daily-chart {{ min-width: 0 !important; }} }}
</style>
{END}
"""


def inject(text: str) -> str:
    legacy_starts = ["<!-- daily-chart-fit:start -->", START]
    legacy_ends = ["<!-- daily-chart-fit:end -->", END]
    changed = True
    while changed:
        changed = False
        for start, end in zip(legacy_starts, legacy_ends):
            if start in text and end in text:
                before = text.split(start, 1)[0]
                after = text.split(end, 1)[1]
                text = before + after
                changed = True
    marker = "</head>"
    if marker not in text:
        raise RuntimeError("</head> not found")
    return text.replace(marker, PATCH + "\n" + marker, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch generated dashboard layout CSS.")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    dashboard = args.output_dir.resolve() / "dashboard.html"
    if not dashboard.exists():
        raise SystemExit(f"missing {dashboard}")
    dashboard.write_text(inject(dashboard.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Patched dashboard layout: {dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
