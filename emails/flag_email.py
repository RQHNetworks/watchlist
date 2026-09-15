#!/usr/bin/env python3
"""Build the daily Market Movers Report as HTML.

Reads the triggers/ directory and trigger_log.jsonl and emits an HTML email.
Plain text cannot carry the green/red that distinguishes a gain from a loss at a
glance, which is the whole point of the layout, so this replaces the old
plain-text body.

Prints a JSON summary (date, tickers, count) so the workflow can build the
subject line without re-deriving any of it.
"""

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

TRIGGERS_DIR = Path("triggers")
LOG_PATH = Path("trigger_log.jsonl")

# Verified against the #2b2b2b surface: white 14.16:1, green 5.09:1, red 4.74:1,
# muted 5.36:1 - all clear of the 4.5:1 an email client needs for text. The
# chart's red (#e66767) measures only 4.38:1 here and is deliberately not reused.
BG = "#2b2b2b"
INK = "#ffffff"
GREEN = "#4caf50"
RED = "#e57373"
MUTED = "#9aa0a6"

FONT = ("-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif")

TRIGGER_RE = re.compile(
    r"^([A-Za-z0-9.]+)_(sma_cross|price_swing|earnings_countdown)_"
    r"(\d{4}-\d{2}-\d{2})$"
)
PCT_RE = re.compile(r"([+-]\d+(?:\.\d+)?)%")
DAYS_RE = re.compile(r"\((\d+) business day")
EARNINGS_DATE_RE = re.compile(r"Earnings on (\d{4}-\d{2}-\d{2})")


def load_log() -> list:
    if not LOG_PATH.exists():
        return []
    rows = []
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def collect() -> dict:
    """Group today's fired triggers into the report's sections."""
    rows = load_log()
    buckets = {"earnings": [], "golden": [], "death": [], "winners": [], "losers": []}
    tickers = []

    if not TRIGGERS_DIR.is_dir():
        return buckets, tickers

    for path in sorted(TRIGGERS_DIR.iterdir()):
        if not path.name.endswith(".txt") or path.name.startswith("no_triggers_"):
            continue
        m = TRIGGER_RE.match(path.stem)
        if not m:
            continue
        ticker, kind, day = m.groups()

        match = None
        for row in rows:
            if (row.get("ticker") == ticker
                    and row.get("trigger_type") == kind
                    and row.get("date") == day):
                match = row
        if match is None:
            continue

        detail = match.get("detail", "")
        company = match.get("company") or ""
        tickers.append(ticker)
        entry = {"ticker": ticker, "company": company, "id": path.stem}

        if kind == "earnings_countdown":
            days = DAYS_RE.search(detail)
            when = EARNINGS_DATE_RE.search(detail)
            entry["sort"] = int(days.group(1)) if days else 999
            entry["note"] = (f"{when.group(1)} ({entry['sort']} business "
                             f"day{'s' if entry['sort'] != 1 else ''} away)"
                             if when else detail)
            buckets["earnings"].append(entry)

        elif kind == "sma_cross":
            # Older log rows spell out "(50-day crossed above 200-day)"; newer
            # ones do not. Both start with the direction, so match on that.
            buckets["golden" if detail.startswith("golden") else "death"].append(entry)

        elif kind == "price_swing":
            pct = PCT_RE.search(detail)
            value = float(pct.group(1)) if pct else 0.0
            entry["sort"] = value
            entry["note"] = f"{value:+.1f}%"
            buckets["winners" if value >= 0 else "losers"].append(entry)

    buckets["earnings"].sort(key=lambda e: e["sort"])
    buckets["golden"].sort(key=lambda e: e["ticker"])
    buckets["death"].sort(key=lambda e: e["ticker"])
    buckets["winners"].sort(key=lambda e: e["sort"], reverse=True)   # biggest gain first
    buckets["losers"].sort(key=lambda e: e["sort"])                  # biggest loss first
    return buckets, tickers


def label(entry: dict) -> str:
    # get_company_name() falls back to the ticker when a longName lookup fails,
    # so an unresolved name arrives equal to the symbol - rendering it would
    # give "RBRK (RBRK)".
    company = entry["company"]
    show_company = company and company != entry["ticker"]
    name = f"{entry['ticker']} ({company})" if show_company else entry["ticker"]
    return f"{name}: {entry['note']}" if entry.get("note") else name


def bullets(entries: list, colour: str) -> str:
    if not entries:
        return (f'<div style="color:{INK};font:14px {FONT};margin:2px 0 0 0;">'
                f'None</div>')
    items = "".join(
        f'<li style="color:{colour};font:14px {FONT};margin:0 0 4px 0;">{label(e)}</li>'
        for e in entries
    )
    return f'<ul style="margin:4px 0 0 0;padding-left:22px;">{items}</ul>'


def section(title: str) -> str:
    return (f'<div style="color:{INK};font:bold 15px {FONT};'
            f'text-decoration:underline;margin:22px 0 6px 0;">{title}</div>')


def subhead(text: str, colour: str) -> str:
    return (f'<div style="color:{colour};font:bold 14px {FONT};'
            f'margin:14px 0 0 0;">{text}</div>')


def render(buckets: dict, report_date: date, ids: list) -> str:
    body = [
        f'<div style="color:{INK};font:bold 13px {FONT};margin:0 0 4px 0;">'
        f'Market Movers Report: {report_date.strftime("%m/%d/%Y")}</div>',

        section("EARNINGS COUNTDOWN:"),
        bullets(buckets["earnings"], INK),

        section("SMA CROSS (50 vs. 200 day)"),
        subhead("Golden Cross:", GREEN),
        bullets(buckets["golden"], GREEN),
        subhead("Death Cross:", RED),
        bullets(buckets["death"], RED),

        section("PRICE MOVEMENT (+/- 10%)"),
        subhead("Winners:", GREEN),
        bullets(buckets["winners"], GREEN),
        subhead("Losers:", RED),
        bullets(buckets["losers"], RED),
    ]

    if ids:
        listed = "<br>".join(ids)
        body.append(
            f'<div style="color:{MUTED};font:12px {FONT};margin:26px 0 0 0;'
            f'border-top:1px solid #3d3d3d;padding-top:12px;">'
            f'Reply quoting one of these IDs for a full AI-built dashboard:<br>'
            f'{listed}</div>'
        )

    inner = "".join(body)
    # bgcolor as well as the inline style: Outlook honours the attribute more
    # reliably, and without a background the white text would be invisible.
    return (
        f'<html><body style="margin:0;padding:0;background-color:{BG};">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'bgcolor="{BG}" style="background-color:{BG};">'
        f'<tr><td style="padding:22px 24px;">{inner}</td></tr>'
        f'</table></body></html>'
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--date", help="Report date YYYY-MM-DD; defaults to today.")
    args = p.parse_args()

    report_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                   if args.date else date.today())

    buckets, tickers = collect()
    ids = [e["id"] for group in buckets.values() for e in group]
    ids.sort()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(buckets, report_date, ids))

    print(json.dumps({
        "date": report_date.strftime("%Y-%m-%d"),
        "tickers": ",".join(sorted(set(tickers))),
        "count": len(tickers),
    }))


if __name__ == "__main__":
    main()
