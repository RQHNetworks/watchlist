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

# For the header's percent change. The sign already carries the meaning, so the
# colour is redundant encoding rather than the only signal. The palette's
# standard red (#d03b3b) measures 3.80:1 here, under the 4.5:1 text bar, so the
# dark-surface step is used instead.
STATUS_UP = "#0ca30c"    # 5.45:1
STATUS_DOWN = "#e66767"  # 5.66:1

# Plotted window. History is fetched well beyond this so the 200-day SMA has
# its warmup off-screen and still spans the whole chart.
DISPLAY_YEARS = 2


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


def build(ticker: str, hist: pd.DataFrame, out_path: Path, company: str | None = None,
          display_years: float = DISPLAY_YEARS) -> dict:
    # SMAs are computed over the FULL history, then everything is trimmed to the
    # display window. A rolling(200) has no value until its 200th session, so
    # computing and plotting over the same 2-year window left the 200-day line
    # starting ~39% across - it looked like missing data but was just warmup.
    # Fetching extra history that is never plotted lets all three lines span the
    # chart edge to edge.
    close_full = hist["Close"]
    sma50_full = close_full.rolling(50).mean()
    sma200_full = close_full.rolling(200).mean()

    plot_start = close_full.index[-1] - pd.DateOffset(years=display_years)
    close = close_full.loc[close_full.index >= plot_start]
    sma50 = sma50_full.loc[sma50_full.index >= plot_start]
    sma200 = sma200_full.loc[sma200_full.index >= plot_start]

    weekly = close.resample("W").last().dropna()
    # Search inside the displayed window so the marker can never land off-chart.
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
        # A freshly triggered cross sits at the right edge, where a rightward
        # box runs into the value labels. Flip it leftward there.
        span = close.index[-1] - close.index[0]
        near_right = (close.index[-1] - cross_date) < span * 0.25
        ax.annotate(
            label,
            xy=(cross_date, cross_price),
            xytext=(-12, 22) if near_right else (12, 22),
            ha="right" if near_right else "left",
            textcoords="offset points",
            color=TEXT_PRIMARY,
            fontsize=9.5,
            fontweight="bold",
            linespacing=1.4,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE,
                      edgecolor=TEXT_MUTED, linewidth=1),
            zorder=7,
        )

    # Direct labels at the right edge, each in its own line's colour so a value
    # can be traced to its curve at a glance. Colour normally stays out of text,
    # but each of these measures above 4.5:1 against the surface (blue 5.02,
    # gold 5.95, aqua 5.37), so they clear the contrast bar for text rather than
    # only the looser one for graphics.
    #
    # The two SMAs sit almost on top of each other right after a cross, which
    # rendered the labels as one illegible smudge. Push them apart when the gap
    # is smaller than the text, so the values stay readable at exactly the
    # moment the chart matters most.
    last_x = close.index[-1]
    ends = []
    for series, name, colour in ((sma50, "50d", COLOR_SMA50),
                                 (sma200, "200d", COLOR_SMA200)):
        value = series.dropna()
        if not value.empty:
            ends.append([name, float(value.iloc[-1]), 0.0, colour])

    if len(ends) == 2:
        y_px = [ax.transData.transform((0, e[1]))[1] for e in ends]
        gap = abs(y_px[0] - y_px[1])
        min_gap = 15.0
        if gap < min_gap:
            nudge = (min_gap - gap) / 2
            hi = 0 if ends[0][1] >= ends[1][1] else 1
            ends[hi][2] = nudge
            ends[1 - hi][2] = -nudge

    for name, value, dy, colour in ends:
        ax.annotate(f"  {name} {value:,.2f}",
                    xy=(last_x, value),
                    xytext=(6, dy), textcoords="offset points",
                    color=colour, fontsize=9, fontweight="bold",
                    va="center", zorder=5)

    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else latest
    change = (latest / prev - 1) if prev else 0.0

    # Header drawn in figure coords with explicit separation; anchoring the
    # subtitle to the axes put it on top of the title. The company name sits
    # beside the symbol so the chart identifies itself without the email.
    heading = f"{ticker} — {company}" if company and company != ticker else ticker
    fig.text(0.07, 0.945, heading,
             color=TEXT_PRIMARY, fontsize=15, fontweight="bold", va="top")
    fig.text(0.07, 0.888, "Technicals (50 / 200-day SMA)",
             color=TEXT_MUTED, fontsize=10, va="top")

    # Last close sits top-right, the corner the eye goes to for "what is it now".
    fig.text(0.955, 0.945, f"{latest:,.2f}",
             color=TEXT_PRIMARY, fontsize=17, fontweight="bold",
             va="top", ha="right")
    fig.text(0.955, 0.888,
             f"last close   {change:+.2%}",
             color=STATUS_UP if change >= 0 else STATUS_DOWN,
             fontsize=10, va="top", ha="right")

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
    p.add_argument("--period", default="3y",
                   help="History FETCHED. Must exceed the plotted window by more "
                        "than the 200-session warmup, or the 200-day SMA starts "
                        "partway across the chart instead of spanning it.")
    p.add_argument("--display-years", dest="display_years", type=float,
                   default=DISPLAY_YEARS,
                   help="History PLOTTED. The rest is warmup and stays off-chart.")
    p.add_argument("--company",
                   help="Company name shown beside the symbol. Defaults to a "
                        "yfinance lookup; pass it to keep the chart's name "
                        "identical to the email's.")
    p.add_argument("--as-of", dest="as_of",
                   help="Trigger date (YYYY-MM-DD). History is truncated here so "
                        "the chart reproduces exactly what the monitor saw. Without "
                        "it the chart computes as of now and silently disagrees "
                        "with the trigger it is illustrating.")
    args = p.parse_args()

    t = yf.Ticker(args.ticker)
    hist = t.history(period=args.period, auto_adjust=True)
    if hist.empty:
        raise SystemExit(f"No price history returned for {args.ticker}")

    if args.as_of:
        cutoff = pd.Timestamp(args.as_of).date()
        hist = hist[hist.index.date <= cutoff]
        if hist.empty:
            raise SystemExit(f"No {args.ticker} history on or before {args.as_of}")

    if args.company:
        company = args.company
    else:
        try:
            company = t.info.get("longName", args.ticker)
        except Exception:
            company = args.ticker

    result = build(args.ticker, hist, args.out, company, args.display_years)
    print(result)


if __name__ == "__main__":
    main()
