#!/usr/bin/env python3
"""Build the 50/200-day SMA technicals panel for one ticker.

Deterministic: every number is computed from daily closes, so no AI and no API
cost. The SMAs use the same rolling windows as check_sma_cross() in
watchlist_monitor.py, which means the chart provably agrees with the trigger
that fired - a third-party SMA series could not guarantee that.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

SURFACE = "#131519"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#c3c2b7"
TEXT_MUTED = "#8a8a82"
GRID = "#2a2d33"

# Validated against the dark surface with the dataviz palette validator:
# all-pairs normal-vision floor 19.8, CVD 8.4. The house style's purple SMA200
# was replaced with aqua because purple/blue scored 12.1 normal-vision - under
# the floor of 15, i.e. hard to tell apart even with full colour vision, which
# is disqualifying on a chart whose whole point is which line is on top.
COLOR_CLOSE = "#3987e5"
COLOR_SMA50 = "#c98500"
COLOR_SMA200 = "#199e70"


def find_last_crossover(sma50: pd.Series, sma200: pd.Series):
    """Date and direction of the most recent 50/200 crossover, or (None, None)."""
    diff = (sma50 - sma200).dropna()
    if len(diff) < 2:
        return None, None
    sign = diff > 0
    changes = sign.ne(sign.shift())
    changes.iloc[0] = False
    dates = diff.index[changes]
    if len(dates) == 0:
        return None, None
    date = dates[-1]
    return date, "golden" if bool(sign.loc[date]) else "death"


def build(ticker: str, hist: pd.DataFrame, out_path: Path, company: str | None = None) -> dict:
    close = hist["Close"]
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    weekly = close.resample("W").last().dropna()
    cross_date, cross_type = find_last_crossover(sma50, sma200)

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=110)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(weekly.index, weekly.values, color=COLOR_CLOSE, linewidth=2,
            marker="o", markersize=2.5, label="Weekly close", zorder=3)
    ax.plot(sma50.index, sma50.values, color=COLOR_SMA50, linewidth=2,
            label="50-day SMA", zorder=4)
    ax.plot(sma200.index, sma200.values, color=COLOR_SMA200, linewidth=2,
            label="200-day SMA", zorder=4)

    if cross_date is not None:
        cross_price = float(sma50.loc[cross_date])
        ax.axvline(cross_date, color=TEXT_MUTED, linewidth=1,
                   linestyle="--", zorder=2)
        # Surface-coloured ring so the marker reads on top of the crossing lines.
        ax.plot([cross_date], [cross_price], marker="o", markersize=9,
                markerfacecolor=TEXT_PRIMARY, markeredgecolor=SURFACE,
                markeredgewidth=2, zorder=6)
        label = f"{'Golden' if cross_type == 'golden' else 'Death'} cross\n{cross_date.date()}"
        ax.annotate(
            label,
            xy=(cross_date, cross_price),
            xytext=(12, 22),
            textcoords="offset points",
            color=TEXT_PRIMARY,
            fontsize=9.5,
            fontweight="bold",
            linespacing=1.4,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE,
                      edgecolor=TEXT_MUTED, linewidth=1),
            zorder=7,
        )

    # Direct labels at the right edge. Text wears ink tokens, never the series
    # colour - the adjacent line carries identity.
    last_x = close.index[-1]
    for series, name in ((sma50, "50d"), (sma200, "200d")):
        value = series.dropna()
        if value.empty:
            continue
        ax.annotate(f"  {name} {value.iloc[-1]:,.2f}",
                    xy=(last_x, value.iloc[-1]),
                    xytext=(6, 0), textcoords="offset points",
                    color=TEXT_SECONDARY, fontsize=9,
                    va="center", zorder=5)

    latest = float(close.iloc[-1])
    # Header drawn in figure coords with explicit separation; anchoring the
    # subtitle to the axes put it on top of the title.
    fig.text(0.07, 0.945, f"{ticker} — Technicals (50 / 200-day SMA)",
             color=TEXT_PRIMARY, fontsize=15, fontweight="bold", va="top")
    fig.text(0.07, 0.888, f"{company or ticker}   ·   last close {latest:,.2f}",
             color=TEXT_MUTED, fontsize=10, va="top")

    # Headroom so the legend never sits on the data.
    low = float(min(weekly.min(), sma200.min(skipna=True), sma50.min(skipna=True)))
    high = float(max(weekly.max(), sma200.max(skipna=True), sma50.max(skipna=True)))
    span = high - low
    ax.set_ylim(low - span * 0.06, high + span * 0.18)

    ax.grid(True, color=GRID, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9.5, ncol=3)
    for text in legend.get_texts():
        text.set_color(TEXT_SECONDARY)

    fig.subplots_adjust(left=0.07, right=0.90, top=0.84, bottom=0.10)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)

    return {
        "ticker": ticker,
        "cross_date": None if cross_date is None else str(cross_date.date()),
        "cross_type": cross_type,
        "sma50": float(sma50.dropna().iloc[-1]),
        "sma200": float(sma200.dropna().iloc[-1]),
        "last_close": latest,
        "path": str(out_path),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--period", default="2y",
                   help="History window. 2y keeps a full year of 200-day SMA "
                        "after the 200-session warmup; 1y leaves only ~50 points.")
    args = p.parse_args()

    t = yf.Ticker(args.ticker)
    hist = t.history(period=args.period, auto_adjust=True)
    if hist.empty:
        raise SystemExit(f"No price history returned for {args.ticker}")

    try:
        company = t.info.get("longName", args.ticker)
    except Exception:
        company = args.ticker

    result = build(args.ticker, hist, args.out, company)
    print(result)


if __name__ == "__main__":
    main()
