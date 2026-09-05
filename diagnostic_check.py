"""
Read-only diagnostic: for every ticker in watchlist.json, print the raw
numbers behind the sma_cross and earnings_countdown triggers (regardless
of whether they'd actually fire), so we can see how close each one is
without writing any files or committing anything.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

EARNINGS_LEAD_BUSINESS_DAYS = 3


def load_watchlist(path: Path = Path("watchlist.json")) -> list:
    with open(path) as f:
        data = json.load(f)
    return [entry["symbol"] for entry in data["watchlist"]]


def business_days_between(d1: date, d2: date) -> int:
    days = pd.bdate_range(start=d1 + timedelta(days=1), end=d2)
    return len(days)


def main():
    today = date.today()
    print(f"Today: {today}\n")
    watchlist = load_watchlist()
    print(f"{len(watchlist)} tickers\n")

    sma_hits = []
    earnings_hits = []

    for ticker in watchlist:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y", auto_adjust=True)
            if hist.empty:
                print(f"[{ticker}] no price data, skipping")
                continue

            hist["sma50"] = hist["Close"].rolling(50).mean()
            hist["sma200"] = hist["Close"].rolling(200).mean()
            valid = hist.dropna(subset=["sma50", "sma200"])

            sma_line = "n/a (insufficient history)"
            if len(valid) >= 2:
                diff_today = valid["sma50"].iloc[-1] - valid["sma200"].iloc[-1]
                diff_yest = valid["sma50"].iloc[-2] - valid["sma200"].iloc[-2]
                crossed = (diff_today > 0) != (diff_yest > 0)
                sma_line = (
                    f"sma50={valid['sma50'].iloc[-1]:.2f} "
                    f"sma200={valid['sma200'].iloc[-1]:.2f} "
                    f"diff_today={diff_today:+.2f} diff_yesterday={diff_yest:+.2f} "
                    f"CROSSED={crossed}"
                )
                if crossed:
                    sma_hits.append(ticker)

            earnings_line = "n/a"
            try:
                edf = t.get_earnings_dates(limit=8)
                if edf is not None and not edf.empty:
                    upcoming = [d.date() for d in edf.index if d.date() >= today]
                    if upcoming:
                        next_earnings = min(upcoming)
                        bdays = business_days_between(today, next_earnings)
                        earnings_line = f"next={next_earnings} bdays_away={bdays}"
                        if bdays == EARNINGS_LEAD_BUSINESS_DAYS:
                            earnings_hits.append(ticker)
                    else:
                        earnings_line = "no upcoming dates in returned window"
                else:
                    earnings_line = "empty/None from yfinance"
            except Exception as e:
                earnings_line = f"ERROR: {type(e).__name__}: {e}"

            print(f"[{ticker}] {sma_line} | earnings: {earnings_line}")

        except Exception as e:
            print(f"[{ticker}] ERROR: {type(e).__name__}: {e}")

    print("\n--- SUMMARY ---")
    print(f"SMA crossovers today: {sma_hits}")
    print(f"Earnings T-minus-3 today: {earnings_hits}")


if __name__ == "__main__":
    main()
