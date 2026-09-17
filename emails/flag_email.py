#!/usr/bin/env python3
"""Build the daily Market Movers Report as HTML.

Reads the triggers/ directory and trigger_log.jsonl and emits an HTML email
laid out as one table per section.

Also fetches price history for the handful of tickers that actually fired, to
fill the 3 / 6 / 12-month trailing-return columns. That fetch lives here rather
than in watchlist_monitor.py on purpose: the monitor fetches period="1y", which
has no headroom for a 12-month return - it would be anchored on whatever the
window's first row happened to be. Widening the monitor's fetch would mean
15 months x 536 tickers on every run; doing it here is 15 months x however many
fired, typically under a dozen.

Prints a JSON summary (date, tickers, count) so the workflow can build the
subject line without re-deriving any of it.
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

TRIGGERS_DIR = Path("triggers")
LOG_PATH = Path("trigger_log.jsonl")

# Verified against the #2b2b2b surface: white 14.16:1, green 5.09:1, red 4.74:1,
# blue 5.76:1, muted 5.36:1 - all clear of the 4.5:1 an email client needs for
# text. The mockup's heading blue (#4a90e2) measured 4.30:1, just under, so it
# is lightened here. The chart's red (#e66767) measures 4.38:1 and is not reused.
BG = "#2b2b2b"
INK = "#ffffff"
GREEN = "#4caf50"
RED = "#e57373"
BLUE = "#6aa9f0"
MUTED = "#9aa0a6"
# Borders are graphics, not text, so the bar is 3:1. This measures 4.10:1.
BORDER = "#8a8a8a"

FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Fixed column widths, so a long company name wraps inside its own column
# instead of stretching it. Every table is the same shape regardless of what
# fired. Sums to 100%.
WIDTHS = ("26%", "20%", "18%", "18%", "18%")

HORIZONS = (3, 6, 12)
# Fetched history. Must exceed the longest horizon by enough that the 12-month
# lookup lands on a real prior session rather than the first row of the window.
FETCH_PERIOD = "15mo"

TRIGGER_RE = re.compile(
    r"^([A-Za-z0-9.]+)_(sma_cross|price_swing|earnings_countdown)_"
    r"(\d{4}-\d{2}-\d{2})$"
)
PCT_RE = re.compile(r"([+-]\d+(?:\.\d+)?)%")
DAYS_RE = re.compile(r"\((\d+) business day")
EARNINGS_DATE_RE = re.compile(r"Earnings on (\d{4}-\d{2}-\d{2})")

# Only unambiguous legal-entity forms. "Holdings" and "Group" are left alone -
# they read as part of the name ("CrowdStrike Holdings", "Coinbase Global").
_SUFFIX_RE = re.compile(
    r"[,\s]+(?:incorporated|inc|corporation|corp|company|co|plc|p\.l\.c\.|"
    r"ltd|limited|n\.v\.|nv|s\.a\.|sa|a\.g\.|ag|se|llc|l\.l\.c\.|lp|l\.p\.)"
    r"\.?\s*$",
    re.IGNORECASE,
)


def short_company(name: str) -> str:
    """'Skyworks Solutions, Inc.' -> 'Skyworks Solutions'.

    Applied repeatedly because names stack forms ('Coherent Corp.' leaves
    nothing to strip on the second pass, but 'Foo Holdings Ltd.' would).
    """
    out = prev = name.strip()
    while True:
        out = _SUFFIX_RE.sub("", out).strip().rstrip(" &,").strip()
        if out == prev:
            break
        prev = out
    return out or name.strip()


def ordinal(n: int) -> str:
    # 11/12/13 take "th" despite ending in 1/2/3.
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def pretty_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}<sup>{ordinal(d.day)}</sup>"


def log(msg: str) -> None:
    """Diagnostics go to stderr.

    Only the JSON summary may touch stdout: the workflow captures it and
    pipes it into jq to build the subject line, so a stray line there empties
    the subject instead of failing loudly.
    """
    print(msg, file=sys.stderr)


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


def fetch_returns(tickers: dict, offline: bool = False) -> dict:
    """{ticker: {3: pct, 6: pct, 12: pct}} as decimals, or None per horizon.

    `tickers` maps ticker -> as-of date. Anchoring to the trigger's own date
    rather than "now" is what keeps a re-run from producing an email that
    disagrees with the one sent earlier.
    """
    out = {t: {h: None for h in HORIZONS} for t in tickers}
    if offline or not tickers:
        return out

    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as e:
        log(f"WARNING: {e}; returns will render as n/a")
        return out

    for ticker, as_of in tickers.items():
        # One bad symbol degrades its own row to n/a rather than taking down
        # the whole report - the tickers and crosses come from the committed
        # log and are still correct without this.
        try:
            hist = yf.Ticker(ticker).history(period=FETCH_PERIOD, auto_adjust=True)
            if hist.empty:
                log(f"WARNING: no history for {ticker}; returns n/a")
                continue

            close = hist["Close"].copy()
            # Drop tz so comparisons against a plain date work, and collapse
            # any duplicate sessions before the asof lookups below.
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            close = close[~close.index.duplicated(keep="last")].sort_index()
            close = close[close.index <= pd.Timestamp(as_of)]
            if close.empty:
                log(f"WARNING: no {ticker} history at or before {as_of}; n/a")
                continue

            anchor_date = close.index[-1]
            anchor = float(close.iloc[-1])

            for months in HORIZONS:
                target = anchor_date - pd.DateOffset(months=months)
                # asof, not an exact match: the date N months back is often a
                # weekend or holiday, and this walks back to the last real
                # session. Returns NaN when the window starts after `target`,
                # which is the recent-IPO case.
                past = close.asof(target)
                if past is None or pd.isna(past) or float(past) == 0.0:
                    continue
                out[ticker][months] = anchor / float(past) - 1
        except Exception as e:
            log(f"WARNING: returns for {ticker} failed: {type(e).__name__}: {e}")

    return out


def collect() -> tuple:
    """Group today's fired triggers into the report's three sections."""
    rows = load_log()
    buckets = {"earnings": [], "sma": [], "price": []}
    tickers = []
    as_of = {}

    if not TRIGGERS_DIR.is_dir():
        return buckets, tickers, as_of

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
        as_of[ticker] = day
        # detail is carried for newsletter.py, which parses the SMA values
        # and swing closes back out of it. The report itself ignores it.
        entry = {"ticker": ticker, "company": company, "id": path.stem,
                 "detail": detail}

        if kind == "earnings_countdown":
            days = DAYS_RE.search(detail)
            when = EARNINGS_DATE_RE.search(detail)
            # Days-away is no longer displayed but is still the sort key.
            entry["sort"] = int(days.group(1)) if days else 999
            entry["col2"] = (pretty_date(datetime.strptime(when.group(1), "%Y-%m-%d").date())
                             if when else detail)
            buckets["earnings"].append(entry)

        elif kind == "sma_cross":
            # Older log rows spell out "(50-day crossed above 200-day)"; newer
            # ones do not. Both start with the direction, so match on that.
            golden = detail.startswith("golden")
            entry["col2"] = "Golden Cross" if golden else "Death Cross"
            entry["sort"] = (0 if golden else 1, ticker)
            buckets["sma"].append(entry)

        elif kind == "price_swing":
            pct = PCT_RE.search(detail)
            value = float(pct.group(1)) if pct else 0.0
            entry["sort"] = value
            # One decimal here, matching the monitor; the return columns use
            # two. The mockup distinguishes them, so it is kept.
            entry["col2"] = f"{value:+.1f}%"
            entry["col2_colour"] = GREEN if value >= 0 else RED
            buckets["price"].append(entry)

    buckets["earnings"].sort(key=lambda e: e["sort"])          # soonest first
    buckets["sma"].sort(key=lambda e: e["sort"])               # golden, then death
    buckets["price"].sort(key=lambda e: e["sort"], reverse=True)  # straight descending
    return buckets, tickers, as_of


def stock_label(entry: dict) -> str:
    # get_company_name() falls back to the ticker when a longName lookup fails,
    # so an unresolved name arrives equal to the symbol - rendering it would
    # give "RBRK (RBRK)".
    company = short_company(entry["company"]) if entry["company"] else ""
    if company and company != entry["ticker"]:
        return f"{entry['ticker']} ({company})"
    return entry["ticker"]


def cell(content: str, colour: str = INK, bold: bool = False,
         width: str | None = None, colspan: int = 1) -> str:
    attrs = f' width="{width}"' if width else ""
    if colspan > 1:
        attrs += f' colspan="{colspan}"'
    weight = "bold " if bold else ""
    style = (f"padding:7px 8px;border:1px solid {BORDER};"
             f"color:{colour};font:{weight}13px {FONT};text-align:center;"
             f"word-wrap:break-word;")
    if width:
        style += f"width:{width};"
    return f'<td{attrs} style="{style}">{content}</td>'


def pct_cell(value) -> str:
    if value is None:
        return cell("n/a", MUTED)
    return cell(f"{value:+.2%}", GREEN if value >= 0 else RED)


def table(col2_header: str, entries: list, returns: dict) -> str:
    headers = ("Stock", col2_header, "3 months", "6 months", "1 year")
    head = "".join(cell(h, INK, bold=True, width=w)
                   for h, w in zip(headers, WIDTHS))
    rows = [f"<tr>{head}</tr>"]

    if not entries:
        rows.append(f"<tr>{cell('None', INK, colspan=5)}</tr>")
    else:
        for e in entries:
            r = returns.get(e["ticker"], {})
            body = (cell(stock_label(e))
                    + cell(e["col2"], e.get("col2_colour", INK))
                    + "".join(pct_cell(r.get(h)) for h in HORIZONS))
            rows.append(f"<tr>{body}</tr>")

    # table-layout:fixed is what makes the widths authoritative - without it
    # the browser reflows columns to fit the content.
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="width:100%;table-layout:fixed;border-collapse:collapse;'
        f'margin:4px 0 0 0;">{"".join(rows)}</table>'
    )


def section(title: str, note: str = "") -> str:
    tail = (f'<span style="font:bold 12px {FONT};"> {note}</span>') if note else ""
    return (f'<div style="color:{BLUE};font:bold 14px {FONT};'
            f'margin:22px 0 0 0;">{title}{tail}</div>')


def render(buckets: dict, returns: dict, report_date: date, ids: list) -> str:
    body = [
        f'<div style="color:{INK};font:bold 13px {FONT};margin:0 0 10px 0;">'
        f'Market Movers Report: {report_date.strftime("%m/%d/%Y")}</div>',

        section("EARNINGS COUNTDOWN"),
        table("Earnings Date", buckets["earnings"], returns),

        section("SMA CROSS", "(50 day vs. 200 day)"),
        table("Cross", buckets["sma"], returns),

        section("PRICE MOVEMENT", "(+/- 10%)"),
        table("% Change Today", buckets["price"], returns),
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
    p.add_argument("--offline", action="store_true",
                   help="Skip the price fetch and render every return as n/a. "
                        "For testing where there is no network egress.")
    args = p.parse_args()

    report_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                   if args.date else date.today())

    buckets, tickers, as_of = collect()
    returns = fetch_returns(as_of, offline=args.offline)

    # Log what was actually computed. A failed fetch already warns, but a
    # horizon that lands on n/a does not - that is the legitimate short-history
    # case. Without this line an email where every return silently rendered
    # n/a would look identical in the log to a healthy one.
    for t in sorted(returns):
        cells = " ".join(
            f"{h}m=" + ("n/a" if returns[t][h] is None else f"{returns[t][h]:+.2%}")
            for h in HORIZONS)
        log(f"  returns {t:<6s} {cells}")
    missing = sum(1 for t in returns for h in HORIZONS if returns[t][h] is None)
    total = len(returns) * len(HORIZONS)
    if total and missing == total:
        log(f"WARNING: all {total} return values are n/a - the fetch is "
            f"producing nothing, even though no individual ticker errored.")
    elif missing:
        log(f"NOTE: {missing}/{total} return values are n/a.")
    ids = sorted(e["id"] for group in buckets.values() for e in group)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(buckets, returns, report_date, ids))

    print(json.dumps({
        "date": report_date.strftime("%Y-%m-%d"),
        "tickers": ",".join(sorted(set(tickers))),
        "count": len(tickers),
    }))


if __name__ == "__main__":
    main()
