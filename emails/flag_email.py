#!/usr/bin/env python3
"""Collect the day's triggers and render them as the report's tables.

Imported by report.py, which assembles the email around these tables and adds
the per-ticker write-ups. This module owns reading triggers/ and
trigger_log.jsonl, computing the trailing returns, and the table markup.

Keeps a CLI so the tables can be rendered on their own while working on them;
the workflow runs report.py, not this.

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
import math
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
#
# Solved from the measured width of the widest unbreakable token in each
# column, not guessed. A cell only breaks mid-word when a single word is
# wider than its column, so the longest WORD is what sets the minimum:
# "months" for the return headers, "+1712%" for their values, "September"
# for the earnings date, and the company name for the Stock column.
#
# Every column is sized to hold its longest word with at least ~30% spare,
# because mobile mail clients render small type larger than the stated px -
# Outlook on a phone was drawing 11px text wide enough to split "months"
# into "month" + "s" even though it measured as fitting at 390px. Sizing to
# "just fits" is what put those breaks back; the headroom is the fix.
WIDTHS = ("26%", "23%", "17%", "17%", "17%")

# Type scale. Headers are the smallest because their words are the longest
# relative to their columns; the company name is a reference under the
# ticker, not a label to read at a glance.
HEADER_SIZE = 9
DATA_SIZE = 10
TICKER_SIZE = 12
# Half the ticker, deliberately: the name is a reference for the symbol above
# it, not something to read at a glance. Being this small is also what lets
# the longest real name ("DuPont de Nemours") sit on one line with room to
# spare if a client enlarges it.
COMPANY_SIZE = TICKER_SIZE // 2
# Characters of company name that fit on one line in the Stock column at
# COMPANY_SIZE, with the same allowance for a client enlarging the type.
COMPANY_BUDGET = 19
# Measured headroom at 390px, i.e. how much larger a client may draw the type
# before a cell breaks. The binding cases:
#   "+1712%"            17% column,  9px  1.44x
#   "September"         23% column, 10px  1.36x
#   "months"            17% column,  9px  1.48x
#   "DuPont de Nemours" 26% column,  6px  1.97x
# The earnings column went 21% -> 23% so the full month name keeps its
# headroom; "September" at 21% had 1.23x and split into "Septembe" + "r".
# That width came from the Stock column, which the 6px name no longer needs.
# The return columns went 15% -> 17% because "+1712%" - a real 12-month
# return, from SNDK - had only 1.16x and was splitting into "+1712" + "%".
# The width came from the Stock column, which the 7px company name freed up.

HORIZONS = (3, 6, 12)
# Fetched history. Must exceed the longest horizon by enough that the 12-month
# lookup lands on a real prior session rather than the first row of the window.
FETCH_PERIOD = "15mo"

TRIGGER_RE = re.compile(
    r"^([A-Za-z0-9.]+)_(sma_cross|price_swing|earnings_countdown)_"
    r"(\d{4}-\d{2}-\d{2})$"
)
PCT_RE = re.compile(r"([+-]\d+(?:\.\d+)?)%")
# "Daily move down +nan% (close 336.13 -> nan)". A detail that cannot state a
# number is a broken fetch wearing a trigger's clothes.
NONFINITE_RE = re.compile(r"\b(?:nan|[+-]?inf(?:inity)?)\b", re.IGNORECASE)
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
            # Drop sessions with no close before anchoring. Yahoo pads the
            # frame with a placeholder row when the fetch reaches into a day
            # that has not traded, and anchoring on it made every horizon NaN
            # - which then rendered as "+nan%" in the table, because NaN is
            # not None and so slipped past the n/a branch.
            close = close[close.notna()]
            close = close[close.index <= pd.Timestamp(as_of)]
            if close.empty:
                log(f"WARNING: no {ticker} history at or before {as_of}; n/a")
                continue

            anchor_date = close.index[-1]
            anchor = float(close.iloc[-1])
            if not math.isfinite(anchor) or anchor == 0.0:
                log(f"WARNING: {ticker} anchor close is {anchor}; returns n/a")
                continue

            for months in HORIZONS:
                target = anchor_date - pd.DateOffset(months=months)
                # asof, not an exact match: the date N months back is often a
                # weekend or holiday, and this walks back to the last real
                # session. Returns NaN when the window starts after `target`,
                # which is the recent-IPO case.
                past = close.asof(target)
                if past is None or pd.isna(past) or float(past) == 0.0:
                    continue
                value = anchor / float(past) - 1
                if not math.isfinite(value):
                    log(f"WARNING: {ticker} {months}m return is {value}; n/a")
                    continue
                out[ticker][months] = value
        except Exception as e:
            log(f"WARNING: returns for {ticker} failed: {type(e).__name__}: {e}")

    return out


def collect() -> tuple:
    """Group today's fired triggers into the report's three sections."""
    rows = load_log()
    buckets = {"earnings": [], "sma": [], "price": []}
    tickers = []
    as_of = {}
    skipped = []

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
        if NONFINITE_RE.search(detail):
            log(f"  SKIP {ticker} {kind}: detail carries a non-finite figure "
                f"({detail!r}) - treating as a data fault, not a trigger")
            skipped.append(f"{ticker}/{kind}")
            continue
        company = match.get("company") or ""
        tickers.append(ticker)
        as_of[ticker] = day
        # detail is carried for the write-ups, which parse the SMA values and
        # swing closes back out of it. The tables themselves ignore it.
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
            # Whole number, like the return columns beside it: this is a
            # table cell, and the decimals cost width the column does not
            # have on a phone. Display only - the trigger still fires on the
            # unrounded value, so a 10.04% move shows as +10%. The write-ups
            # below the tables keep full precision; they have the room.
            entry["col2"] = f"{value:+.0f}%"
            entry["col2_colour"] = GREEN if value >= 0 else RED
            buckets["price"].append(entry)

    buckets["earnings"].sort(key=lambda e: e["sort"])          # soonest first
    buckets["sma"].sort(key=lambda e: e["sort"])               # golden, then death
    buckets["price"].sort(key=lambda e: e["sort"], reverse=True)  # straight descending
    if skipped:
        log(f"WARNING: skipped {len(skipped)} trigger(s) with non-finite "
            f"details: {', '.join(skipped[:12])}"
            + (" ..." if len(skipped) > 12 else ""))
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
         width: str | None = None, colspan: int = 1, size: int = DATA_SIZE,
         nowrap: bool = False) -> str:
    """One cell. Its own background, and no border of its own.

    The grid is drawn by the table's bgcolor showing through 1px cellspacing
    (see table()), not by a CSS border here. Gmail re-serialises HTML when you
    forward a message and drops per-cell border styles, which is why forwarded
    copies arrived with no table lines at all. bgcolor is an HTML attribute and
    survives that round trip.
    """
    attrs = f' width="{width}"' if width else ""
    if colspan > 1:
        attrs += f' colspan="{colspan}"'
    weight = "bold " if bold else ""
    # word-wrap:break-word used to be here. It is what split "months" into
    # "month" + "s" and "+1712%" into "+1712" + "%": when a word does not
    # fit, it breaks it mid-word rather than letting it hang. Removing it
    # means a too-long word overflows instead, which is visible and fixable,
    # rather than silently mangling the header of every table.
    style = (f"padding:6px 5px;color:{colour};font:{weight}{size}px {FONT};"
             f"text-align:center;")
    if nowrap:
        style += "white-space:nowrap;"
    if width:
        style += f"width:{width};"
    return f'<td{attrs} bgcolor="{BG}" style="{style}">{content}</td>'


def _usable(v) -> bool:
    """A return value that can be displayed and counted as present.

    None is the honest "no data" case. A NaN is not None, so counting only
    None reported "7/1605 n/a" for a run whose table was almost entirely
    "+nan%" - the alarm that should have caught it stayed quiet.
    """
    return v is not None and math.isfinite(v)


def whole_pct(value: float) -> str:
    """A decimal fraction as whole percent, with no signed zero.

    For table cells only. The columns are too narrow on a phone to hold
    "-11.05%" without wrapping, so the tables round; the write-ups beneath
    them quote the same figures at full precision.

    ":+.0%" renders -0.0034 as "-0%", which reads as a formatting bug rather
    than a small decline. Anything that rounds to zero prints a plain "0%";
    the cell colour still carries the direction.
    """
    text = f"{value:+.0%}"
    return "0%" if text in ("+0%", "-0%") else text


def pct_cell(value) -> str:
    # A point smaller than the rest, and rounded to whole percent: "-11%" in
    # an 11px face clears a ~57px column with room to spare, where "-11.05%"
    # at 12px did not and wrapped onto a second line.
    # `is None` alone was not enough: a NaN is not None, so it reached
    # whole_pct() and rendered a red "+nan%" cell.
    # HEADER_SIZE, not DATA_SIZE: "+1712%" is a real 12-month return and at
    # 10px it had only 1.30x headroom, splitting into "+1712" + "%" once a
    # client enlarged the type. A point smaller buys 1.44x.
    if value is None or not math.isfinite(value):
        return cell("n/a", MUTED, size=HEADER_SIZE, nowrap=True)
    return cell(whole_pct(value), GREEN if value >= 0 else RED,
                size=HEADER_SIZE, nowrap=True)


def fit_company(name: str) -> str:
    """Shorten a company name to one line in the Stock column.

    "Cadence Design Systems" was wrapping onto three lines, which made every
    row a different height. Cutting it here rather than in CSS keeps the
    result identical in every client: text-overflow needs overflow:hidden and
    a definite width, and mail clients honour that unevenly.

    Prefers a word boundary, so "Cadence Design Systems" reads "Cadence
    Design" rather than "Cadence Desig...". Falls back to a hard cut when the
    first word is most of the budget, so "NXP Semiconductors" keeps enough to
    be recognisable instead of collapsing to "NXP".
    """
    name = name.strip()
    if len(name) <= COMPANY_BUDGET:
        return name
    cut = name.rfind(" ", 0, COMPANY_BUDGET + 1)
    # A word boundary that throws away most of the budget is worse than an
    # ellipsis: "NXP" tells you less than "NXP Semiconduct...".
    if cut >= COMPANY_BUDGET - 6:
        return name[:cut]
    return name[:COMPANY_BUDGET - 1].rstrip() + "\u2026"


def stock_cell(entry: dict) -> str:
    """Ticker on its own line, company beneath it, smaller and muted.

    One line of "SWKS (Skyworks Solutions)" in a 100px column wraps wherever
    the words happen to fall, so every row ends up a different height. Splitting
    it puts the break where it belongs and keeps the ticker scannable.
    """
    company = fit_company(short_company(entry["company"])) if entry["company"] else ""
    name = (f'<div style="color:{MUTED};font:{COMPANY_SIZE}px {FONT};'
            f'margin:2px 0 0 0;white-space:nowrap;">'
            f'{company}</div>') if company and company != entry["ticker"] else ""
    return (f'<div style="color:{INK};font:bold {TICKER_SIZE}px {FONT};'
            f'white-space:nowrap;">'
            f'{entry["ticker"]}</div>{name}')


def table(col2_header: str, entries: list, returns: dict) -> str:
    headers = ("Stock", col2_header, "3 months", "6 months", "1 year")
    # The smallest type in the table, because "months" and "Change" are the
    # longest words relative to the space they get. They still break at the
    # space onto two lines, which is uniform across all three return columns;
    # what must never happen is a break inside the word itself.
    head = "".join(cell(h, INK, bold=True, width=w, size=HEADER_SIZE)
                   for h, w in zip(headers, WIDTHS))
    rows = [f"<tr>{head}</tr>"]

    if not entries:
        rows.append(f"<tr>{cell('None', INK, colspan=5)}</tr>")
    else:
        for e in entries:
            r = returns.get(e["ticker"], {})
            body = (cell(stock_cell(e))
                    + cell(e["col2"], e.get("col2_colour", INK))
                    + "".join(pct_cell(r.get(h)) for h in HORIZONS))
            rows.append(f"<tr>{body}</tr>")

    # The grid lines ARE this table's background, showing through the 1px
    # cellspacing between opaque cells. No CSS borders anywhere, so nothing is
    # left to strip when the message is forwarded. border-collapse must stay
    # off or the spacing that draws the lines collapses with it.
    #
    # table-layout:fixed is what makes the widths authoritative - without it
    # the browser reflows columns to fit the content.
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="1" '
        f'border="0" bgcolor="{BORDER}" style="width:100%;table-layout:fixed;'
        f'margin:4px 0 0 0;">{"".join(rows)}</table>'
    )


def section(title: str, note: str = "") -> str:
    tail = (f'<span style="font:bold 11px {FONT};"> {note}</span>') if note else ""
    return (f'<div style="color:{BLUE};font:bold 13px {FONT};'
            f'margin:22px 0 0 0;">{title}{tail}</div>')


def render(buckets: dict, returns: dict, report_date: date, ids: list) -> str:
    body = [
        f'<div style="color:{INK};font:bold 12px {FONT};margin:0 0 10px 0;">'
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
            f'<div style="color:{MUTED};font:11px {FONT};margin:26px 0 0 0;'
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
            f"{h}m=" + ("n/a" if not _usable(returns[t][h]) else f"{returns[t][h]:+.2%}")
            for h in HORIZONS)
        log(f"  returns {t:<6s} {cells}")
    missing = sum(1 for t in returns for h in HORIZONS if not _usable(returns[t][h]))
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
