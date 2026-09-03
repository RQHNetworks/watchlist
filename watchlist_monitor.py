"""
watchlist_monitor.py

Checks a watchlist of tickers daily for three trigger conditions:
  1. 50-day / 200-day SMA crossover (golden cross or death cross) happened today
  2. Next earnings date is exactly T-minus 3 business days away
  3. Most recent daily close moved +/- 15% or more vs. the prior close

When a trigger fires, it writes a ready-to-use dashboard prompt (with the
ticker/company name filled in) to an output folder, and appends a row to a
trigger log so you have a history of what fired and when.

Run this once per day (after market close is simplest) via cron / a
scheduled task / GitHub Actions. See the bottom of this file for scheduling
notes.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WATCHLIST = ["AAPL", "MSFT", "TSLA", "RDW", "PL", "LUNR", "LDOS", "APP", "UBER", "ORCL", "NVDA", "META", "IBM", "GOOGL", "AMZN", "QCOM", "PLTR", "PANW", "NET", "INTC", "DELL", "CRWD", "CRM", "AMD", "SPCX", "SNOW", "SMCI", "RKLB", "NBIS", "IONQ", "GTLB", "CRWV", "CART", "BSX", "UNH", "SPOT", "SBUX", "NKE", "NFLX", "LULU", "HOOD", "HIMS", "EXPE", "WMT", "TGT", "PEP", "MCD", "KO", "JNJ", "HD", "COST", "CAT", "V", "SOFI", "PYPL", "KLAR", "JPM", "GS", "COIN", "TMDX", "RBRK", "LMT", "IP", "ELF", "BA", "TTD", "NOW", "DUOL", "CHKP", "BBY", "ADBE"]

PRICE_SWING_THRESHOLD = 0.15       # +/- 15%
EARNINGS_LEAD_BUSINESS_DAYS = 3    # T-minus 3 business days

OUTPUT_DIR = Path("triggers")
LOG_PATH = Path("trigger_log.jsonl")

# The exact combined-dashboard prompt template we finalized in chat.
# {TICKER} and {COMPANY} get filled in per-ticker at trigger time.
DASHBOARD_PROMPT_TEMPLATE = """\
I want to analyze {TICKER} ({COMPANY}). Build a single combined PNG image with four stacked panels, in this exact order:

Panel 1: 5-year monthly stock price
Continuous monthly close line, calendar timeline (Jan of 5-years-ago -> today), in blue. Mark and annotate the 52-week high in green and 52-week low in red, each with a small dot marker directly on th[...]

Panel 2: Revenue & free cash flow by quarter, past 5 years
Grouped bars on the true calendar-month axis (same numeric x-axis as Panel 1) -- bars sit at the calendar month each quarter's results were actually released, not fiscal quarter-end. Thick/chunky bars[...]
Revenue: deep/muted dark orange. Free cash flow: bright green.
Actuals: solid fill. Estimates (next 4 quarters, from analyst consensus + company guidance): lighter/desaturated fill + hatching + dashed border.
Legend for all four categories.
Data-quality rules:
- Non-calendar fiscal year -> label by fiscal year, note the offset clearly.
- Spin-off/acquisition/divestiture breaking YoY comparability -> flag explicitly rather than computing a misleading growth rate.
- Check whether company-reported FCF is quarter-only or YTD/TTM cumulative -- some companies report FCF as trailing-twelve-months only, never discrete quarterly. When that happens, source discrete-qua[...]
- Re-search very recent quarters rather than relying on cached figures.
- Sanity-check every bar's release-month placement against the company's actual historical earnings cadence, including for the same fiscal quarter across different years.

Panel 3: Weekly close with 50-day & 200-day SMA, past year
Weekly closing prices sourced from confirmed weekly/near-weekly data points across multiple sources. Weeks between confirmed anchors may be estimated -- say so in the footer.
Overlay 50-day and 200-day SMA using actual dated historical readings from a source that publishes SMA history (e.g. wallstreetnumbers.com's /stocks/[ticker]/moving-average page) -- current value, 1-y[...]
Blue = weekly close, gold = 50-day SMA, purple = 200-day SMA, small markers on each line. Annotate each SMA's current value directly on the chart.

Panel 4: Earnings per share -- estimated vs. reported (Nasdaq.com style)
Grouped bars for the last 4 reported quarters (estimated + actual side by side, with a BEAT/MISS/MET label in green/red/neutral beneath each pair), followed by single estimate-only bars for the next 4[...]
Value labels must never overlap or be covered by their own bar. For a positive bar, place the label beyond the bar's tip (further from zero) with vertical alignment "bottom". For a negative bar (a los[...]
Use comparable/non-GAAP EPS, not headline GAAP EPS, if a one-time item would otherwise make the beat/miss comparison meaningless -- note this substitution in the footer.
Source actual reported EPS and the consensus estimate it beat/missed from financial news at the time of each release -- confirm both numbers per quarter.

Style (whole image): Dark mode throughout (#131519-ish background), off-white header text, muted gray subtext/axis labels/legend text, subtle gridlines. Header row: company name (left) with current st[...]

Technical notes: Python/matplotlib, one tall portrait PNG (~1200x2500-2600px). Escape literal dollar signs in any text string containing two or more of them (\\$ instead of $). Panels use their own ap[...]

Trigger context for this run: {TRIGGER_REASON}

After building the dashboard, follow it with this written analysis:
1. Distance from 52-week high (or ATH label).
2. One-word Positive/Negative verdict for Sections 2, 3, and 4, each with a rationale grounded in that panel's actual data.
3. Next 3 average-down price levels using real technical reference points (support/resistance, moving-average 1-year lows, the 52-week low), nearest-to-current first, with the final level flagged as a[...]
Close with a plain not-investment-advice reminder.
"""


@dataclass
class TriggerEvent:
    ticker: str
    date: str
    trigger_type: str
    detail: str


def business_days_between(d1: date, d2: date) -> int:
    """Count business days between two dates (exclusive of d1, inclusive of d2)."""
    days = pd.bdate_range(start=d1 + timedelta(days=1), end=d2)
    return len(days)


def check_sma_cross(hist: pd.DataFrame) -> TriggerEvent | None:
    """Detect a 50/200-day SMA crossover on the most recent trading day."""
    hist = hist.copy()
    hist["sma50"] = hist["Close"].rolling(50).mean()
    hist["sma200"] = hist["Close"].rolling(200).mean()
    hist = hist.dropna(subset=["sma50", "sma200"])
    if len(hist) < 2:
        return None

    diff_today = hist["sma50"].iloc[-1] - hist["sma200"].iloc[-1]
    diff_yesterday = hist["sma50"].iloc[-2] - hist["sma200"].iloc[-2]

    crossed = (diff_today > 0) != (diff_yesterday > 0)
    if not crossed:
        return None

    cross_type = "golden cross (50-day crossed above 200-day)" if diff_today > 0 else "death cross (50-day crossed below 200-day)"
    return TriggerEvent(
        ticker="",  # filled by caller
        date=str(hist.index[-1].date()),
        trigger_type="sma_cross",
        detail=f"{cross_type}: 50-day={hist['sma50'].iloc[-1]:.2f}, 200-day={hist['sma200'].iloc[-1]:.2f}",
    )


def check_price_swing(hist: pd.DataFrame, threshold: float = PRICE_SWING_THRESHOLD) -> TriggerEvent | None:
    """Detect a daily close-to-close move of at least +/- threshold."""
    if len(hist) < 2:
        return None
    pct_change = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2]) - 1
    if abs(pct_change) < threshold:
        return None
    direction = "up" if pct_change > 0 else "down"
    return TriggerEvent(
        ticker="",
        date=str(hist.index[-1].date()),
        trigger_type="price_swing",
        detail=f"Daily move {direction} {pct_change:+.1%} (close {hist['Close'].iloc[-2]:.2f} -> {hist['Close'].iloc[-1]:.2f})",
    )


def check_earnings_countdown(ticker_obj: yf.Ticker, today: date) -> TriggerEvent | None:
    """Detect whether the next earnings date is exactly T-minus 3 business days away."""
    try:
        edf = ticker_obj.get_earnings_dates(limit=8)
    except Exception:
        return None
    if edf is None or edf.empty:
        return None

    upcoming = [d.date() for d in edf.index if d.date() >= today]
    if not upcoming:
        return None
    next_earnings = min(upcoming)

    bdays_away = business_days_between(today, next_earnings)
    if bdays_away != EARNINGS_LEAD_BUSINESS_DAYS:
        return None
    return TriggerEvent(
        ticker="",
        date=str(today),
        trigger_type="earnings_countdown",
        detail=f"Earnings on {next_earnings} ({EARNINGS_LEAD_BUSINESS_DAYS} business days away)",
    )


def get_company_name(ticker_obj: yf.Ticker, ticker: str) -> str:
    try:
        return ticker_obj.info.get("longName", ticker)
    except Exception:
        return ticker


def run_once(watchlist: list = WATCHLIST) -> list:
    today = date.today()
    fired = []

    OUTPUT_DIR.mkdir(exist_ok=True)

    for ticker in watchlist:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")  # enough for 200-day SMA plus buffer
        if hist.empty:
            print(f"[{ticker}] no price data returned, skipping")
            continue

        events = []
        for check in (check_sma_cross, check_price_swing):
            ev = check(hist)
            if ev:
                ev.ticker = ticker
                events.append(ev)

        ev = check_earnings_countdown(t, today)
        if ev:
            ev.ticker = ticker
            events.append(ev)

        for ev in events:
            print(f"TRIGGER FIRED: {ev.ticker} / {ev.trigger_type} / {ev.detail}")
            fired.append(ev)
            _write_prompt_file(ev, get_company_name(t, ticker))
            _append_log(ev)

    if not fired:
        print(f"[{today}] No triggers fired for any ticker in the watchlist.")
    return fired


def _write_prompt_file(ev: TriggerEvent, company_name: str) -> None:
    reason_map = {
        "sma_cross": f"50/200-day SMA crossover detected today ({ev.detail}).",
        "price_swing": f"Large daily price move detected today ({ev.detail}).",
        "earnings_countdown": f"Earnings report is coming up ({ev.detail}).",
    }
    prompt = DASHBOARD_PROMPT_TEMPLATE.format(
        TICKER=ev.ticker,
        COMPANY=company_name,
        TRIGGER_REASON=reason_map[ev.trigger_type],
    )
    filename = OUTPUT_DIR / f"{ev.ticker}_{ev.trigger_type}_{ev.date}.txt"
    filename.write_text(prompt)
    print(f"  -> prompt written to {filename}")


def _append_log(ev: TriggerEvent) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(asdict(ev)) + "\n")


if __name__ == "__main__":
    events = run_once()
    if events:
        print(f"\n{len(events)} trigger(s) fired. Prompt files are in ./{OUTPUT_DIR}/")
        print("Wire up notify.py (see notify_example.py) to auto-send these, or paste")
        print("them into claude.ai / Claude Code manually.")
