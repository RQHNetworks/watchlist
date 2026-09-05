"""
LULU price-swing dashboard -- 2026-09-04.

Four stacked panels (5y monthly price / quarterly revenue+FCF / weekly close
with 50-200d SMA / EPS estimate vs reported) rendered as one tall dark-mode PNG.

Price + SMA series come from yfinance daily closes (SMA values reconciled
exactly against wallstreetnumbers.com published readings). Fundamentals and
consensus EPS come from the sources listed in the accompanying .md file.

Built against the FINAL Sep 4, 2026 close of $100.61 (-17.38%).
"""

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parent / "LULU_price_swing_2026-09-04.png"
DAILY_CSV = "/tmp/lulu_daily.csv"

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG = "#131519"
PANEL_BG = "#181B21"
OFFWHITE = "#EAECEF"
MUTED = "#8B939C"
DIM = "#6A717A"
GRID = "#262A31"
BLUE = "#4E9BE8"
GREEN = "#35C75A"
RED = "#F0455A"
ORANGE = "#C2652A"          # revenue (deep muted dark orange)
ORANGE_EST = "#D69463"      # lighter / desaturated revenue (estimate)
FCF_GREEN = "#3DDC6B"       # free cash flow (bright green)
FCF_EST = "#86D7A4"         # lighter / desaturated FCF (estimate)
GOLD = "#E0B341"
PURPLE = "#A97BE0"
NEUTRAL = "#9AA2AB"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": OFFWHITE,
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.edgecolor": GRID,
})

# ---------------------------------------------------------------------------
# Header facts
# ---------------------------------------------------------------------------
COMPANY = "lululemon athletica inc."
TICKER = "LULU"
PRICE = 100.61
PREV_CLOSE = 121.77
CHG = PRICE - PREV_CLOSE
CHG_PCT = CHG / PREV_CLOSE * 100.0

WK52_HIGH, WK52_HIGH_DT = 225.98, "2025-12-18"   # intraday
WK52_LOW, WK52_LOW_DT = 97.99, "2026-09-04"      # intraday, set today


def yfrac(ts):
    """Calendar date -> fractional year, the shared numeric x-axis."""
    ts = pd.Timestamp(ts)
    start = pd.Timestamp(year=ts.year, month=1, day=1)
    end = pd.Timestamp(year=ts.year + 1, month=1, day=1)
    return ts.year + (ts - start).days / (end - start).days


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------
daily = pd.read_csv(DAILY_CSV, index_col=0, parse_dates=True)["Close"]
monthly = daily.loc["2021-01-01":].resample("ME").last().dropna()
weekly = daily.loc["2025-09-01":].resample("W-FRI").last().dropna()
sma50 = daily.rolling(50).mean()
sma200 = daily.rolling(200).mean()
sma50_w = sma50.reindex(weekly.index, method="ffill")
sma200_w = sma200.reindex(weekly.index, method="ffill")
SMA50_NOW = float(sma50.iloc[-1])
SMA200_NOW = float(sma200.iloc[-1])

X_MIN, X_MAX = 2021.0, yfrac("2027-10-15")
TODAY_X = yfrac("2026-09-04")

# ---------------------------------------------------------------------------
# Panel 2 -- quarterly revenue & free cash flow, keyed to ACTUAL release dates
#   Fiscal-year labels follow lululemon's own convention (FY2025 ended
#   2026-02-01), one behind the "period-end year" label some vendors use.
#   Release dates cross-checked against SEC 8-K filing dates AND AlphaQuery.
#   FCF is derived by differencing lululemon's YTD cash-flow statements -- the
#   company never publishes a discrete quarterly cash-flow statement.
# ---------------------------------------------------------------------------
# (fiscal label, quarter end, release date, revenue $B, FCF $B)
QUARTERS = [
    ("FY21 Q2", "2021-08-01", "2021-09-08", 1.451, 0.2054),
    ("FY21 Q3", "2021-10-31", "2021-12-09", 1.450, 0.0359),
    ("FY21 Q4", "2022-01-30", "2022-03-29", 2.129, 0.6035),
    ("FY22 Q1", "2022-05-01", "2022-06-02", 1.613, -0.3546),
    ("FY22 Q2", "2022-07-31", "2022-09-01", 1.868, -0.0471),
    ("FY22 Q3", "2022-10-30", "2022-12-08", 1.857, -0.1098),
    ("FY22 Q4", "2023-01-29", "2023-03-28", 2.772, 0.8393),
    ("FY23 Q1", "2023-04-30", "2023-06-01", 2.001, -0.0914),
    ("FY23 Q2", "2023-07-30", "2023-08-31", 2.209, 0.3312),
    ("FY23 Q3", "2023-10-29", "2023-12-07", 2.204, 0.2270),
    ("FY23 Q4", "2024-01-28", "2024-03-21", 3.205, 1.1780),
    ("FY24 Q1", "2024-04-28", "2024-06-05", 2.209, -0.0032),
    ("FY24 Q2", "2024-07-28", "2024-08-29", 2.371, 0.2981),
    ("FY24 Q3", "2024-10-27", "2024-12-05", 2.397, 0.1222),
    ("FY24 Q4", "2025-02-02", "2025-03-27", 3.611, 1.1660),
    ("FY25 Q1", "2025-05-04", "2025-06-05", 2.371, -0.2712),
    ("FY25 Q2", "2025-08-03", "2025-09-04", 2.525, 0.1508),
    ("FY25 Q3", "2025-11-02", "2025-12-11", 2.566, 0.0824),
    ("FY25 Q4", "2026-02-01", "2026-03-17", 3.641, 0.9597),
    ("FY26 Q1", "2026-05-03", "2026-06-04", 2.472, 0.0870),
    ("FY26 Q2", "2026-08-02", "2026-09-03", 2.416, 0.2252),
]
# Next four quarters. Revenue: company guidance (Q3), FY-guidance-implied (Q4),
# street ~flat FY27 (Q1/Q2 FY27). FCF: model-derived (seasonal FCF margin
# applied to guided revenue, haircut for the guided earnings decline).
QUARTERS_EST = [
    ("FY26 Q3", "2026-11-01", "2026-12-04", 2.305, 0.030),
    ("FY26 Q4", "2027-01-31", "2027-03-19", 3.232, 0.700),
    ("FY27 Q1", "2027-05-02", "2027-06-03", 2.470, -0.050),
    ("FY27 Q2", "2027-08-01", "2027-09-02", 2.420, 0.120),
]

# ---------------------------------------------------------------------------
# Panel 4 -- EPS estimate vs reported (comparable / non-GAAP basis)
# ---------------------------------------------------------------------------
EPS_REPORTED = [
    ("FY25 Q3\nDec 11 '25", 2.22, 2.59),
    ("FY25 Q4\nMar 17 '26", 4.78, 5.01),
    ("FY26 Q1\nJun 4 '26", 1.68, 1.69),
    ("FY26 Q2\nSep 3 '26", 1.79, 2.06),
]
EPS_FORWARD = [
    ("FY26 Q3\nDec '26 (E)", 0.96),
    ("FY26 Q4\nMar '27 (E)", 4.04),
]

# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------
fig = plt.figure(figsize=(12.0, 26.0), dpi=100)
fig.patch.set_facecolor(BG)
gs = fig.add_gridspec(
    4, 1,
    left=0.078, right=0.972, top=0.928, bottom=0.100,
    hspace=0.86,
)

WRAP = 200


def style(ax, title, subtitle):
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color=GRID, lw=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(labelsize=9.5, length=0)
    ax.text(0, 1.115, title, transform=ax.transAxes, color=OFFWHITE,
            fontsize=15.5, fontweight="bold", va="bottom", ha="left")
    ax.text(0, 1.050, subtitle, transform=ax.transAxes, color=MUTED,
            fontsize=9.8, va="bottom", ha="left")


def footer(ax, paragraphs, y=-0.165):
    lines = []
    for p in paragraphs:
        lines.extend(textwrap.wrap(p, WRAP))
    ax.text(0, y, "\n".join(lines), transform=ax.transAxes, color=DIM,
            fontsize=7.0, va="top", ha="left", linespacing=1.60)


# ===========================================================================
# Header
# ===========================================================================
fig.text(0.078, 0.9855, f"{COMPANY}  ({TICKER})", color=OFFWHITE,
         fontsize=21, fontweight="bold", va="center", ha="left")
fig.text(0.078, 0.9670,
         f"\\${PRICE:,.2f}   {CHG:+.2f} ({CHG_PCT:+.2f}%)   "
         f"prior close \\${PREV_CLOSE:,.2f}",
         color=RED, fontsize=13.5, fontweight="bold", va="center", ha="left")
fig.text(0.972, 0.9865, "PRICE-SWING TRIGGER  \u2014  Sep 4, 2026",
         color=OFFWHITE, fontsize=13, fontweight="bold", va="center", ha="right")
fig.text(0.972, 0.9700, "Q2 FY2026 miss, 2nd straight guidance cut",
         color=MUTED, fontsize=9.6, va="center", ha="right")
fig.text(0.972, 0.9575, "first sub-\\$100 trade since May 2018",
         color=MUTED, fontsize=9.6, va="center", ha="right")

# ===========================================================================
# Panel 1 -- 5-year monthly close
# ===========================================================================
ax1 = fig.add_subplot(gs[0])
style(ax1, "1.  Five-year monthly close",
      "Month-end closing price, Jan 2021 \u2013 Sep 2026   |   52-week high / low "
      "marked on an intraday basis")

mx = [yfrac(d) for d in monthly.index]
ax1.plot(mx, monthly.values, color=BLUE, lw=2.1, zorder=3)
ax1.fill_between(mx, monthly.values, 0, color=BLUE, alpha=0.07, zorder=2)

hx, lx = yfrac(WK52_HIGH_DT), yfrac(WK52_LOW_DT)
ax1.plot([hx], [WK52_HIGH], "o", ms=7, color=GREEN, zorder=6)
ax1.plot([lx], [WK52_LOW], "o", ms=7, color=RED, zorder=6)
ax1.annotate(f"52W HIGH  \\${WK52_HIGH:,.2f}\nDec 18, 2025",
             xy=(hx, WK52_HIGH), xytext=(hx - 0.26, WK52_HIGH + 118),
             color=GREEN, fontsize=10.2, fontweight="bold", ha="center",
             va="bottom", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=GREEN, lw=1.1, alpha=0.8))
ax1.annotate(f"52W LOW  \\${WK52_LOW:,.2f}\nSep 4, 2026  (today)",
             xy=(lx, WK52_LOW), xytext=(lx - 2.95, 46),
             color=RED, fontsize=10.2, fontweight="bold", ha="left",
             va="center", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=RED, lw=1.1, alpha=0.8))

ax1.axhline(PRICE, color=MUTED, lw=0.9, ls=(0, (5, 4)), alpha=0.5, zorder=1)
ax1.text(X_MAX - 0.06, PRICE + 14, f"now  \\${PRICE:,.2f}", color=MUTED,
         fontsize=9.5, ha="right", va="bottom")
ax1.plot([yfrac("2023-12-29")], [511.29], "o", ms=5, color=NEUTRAL, zorder=5)
ax1.text(yfrac("2023-12-29") + 0.12, 511.29 + 8,
         "all-time closing high  \\$511.29  (Dec 29, 2023)",
         color=NEUTRAL, fontsize=9, ha="left", va="bottom")

ax1.axvline(TODAY_X, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax1.axvspan(TODAY_X, X_MAX, color="#000000", alpha=0.20, zorder=0)
ax1.text(TODAY_X + 0.07, 26, "forward\nperiod", color=DIM, fontsize=8.6,
         ha="left", va="bottom", linespacing=1.4)
ax1.set_xlim(X_MIN, X_MAX)
ax1.set_ylim(0, 600)
ax1.set_ylabel("Share price (\\$)", fontsize=10)
ax1.set_xticks(np.arange(2021, 2028, 1))
ax1.set_xticklabels([str(y) for y in range(2021, 2028)])
ax1.yaxis.set_major_formatter(lambda v, p: f"{v:,.0f}")
footer(ax1, [
    "Source: daily closes via Yahoo Finance, resampled to month-end. The 52-week range shown is the "
    "INTRADAY range (\\$97.99 \u2013 \\$225.98), matching the range published by stockanalysis.com; on a "
    "closing basis the 52-week extremes are \\$215.88 (Jan 6, 2026) and \\$100.61 (Sep 4, 2026), so the "
    "two dots sit slightly off the month-end line by design.",
    "This is NOT an all-time-high setup: the all-time closing high of \\$511.29 was set on Dec 29, 2023, "
    "and today's close is a fresh 52-week low \u2014 the lowest LULU has traded since May 2018.",
    "The axis runs to Oct 2027 so Panels 1 and 2 share one numeric calendar axis; everything right of "
    "the dotted line is forward-looking and carries no price history.",
])

# ===========================================================================
# Panel 2 -- revenue & free cash flow by quarter, at release month
# ===========================================================================
ax2 = fig.add_subplot(gs[1])
style(ax2, "2.  Revenue & free cash flow by fiscal quarter",
      "Plotted at the calendar month each quarter was actually REPORTED, not at "
      "fiscal quarter-end   |   same numeric axis as Panel 1")

BW = 0.090
for label, qend, rel, rev, fcf in QUARTERS:
    x = yfrac(rel)
    ax2.bar(x - BW / 2, rev, width=BW, color=ORANGE, zorder=3)
    ax2.bar(x + BW / 2, fcf, width=BW, color=FCF_GREEN, zorder=3)
for label, qend, rel, rev, fcf in QUARTERS_EST:
    x = yfrac(rel)
    ax2.bar(x - BW / 2, rev, width=BW, color=ORANGE_EST, hatch="////",
            edgecolor=ORANGE, lw=1.1, ls="--", zorder=3)
    ax2.bar(x + BW / 2, fcf, width=BW, color=FCF_EST, hatch="////",
            edgecolor="#1E7A44", lw=1.1, ls="--", zorder=3)

qx = yfrac("2026-09-03")
ax2.annotate("FY26 Q2, reported Sep 3, 2026\nrevenue \\$2.42B (\u20134% YoY), comps \u20139%",
             xy=(qx - BW / 2, 2.44), xytext=(qx - 0.32, 4.36),
             color=OFFWHITE, fontsize=9.3, ha="center", va="top",
             linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax2.annotate("53-week fiscal year:\nFY23 Q4 ran 14 weeks",
             xy=(yfrac("2024-03-21") - BW / 2, 3.24),
             xytext=(yfrac("2023-07-01"), 3.96),
             color=NEUTRAL, fontsize=8.8, ha="center", va="top", linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=DIM, lw=0.9))

ax2.axhline(0, color=MUTED, lw=1.0, alpha=0.6, zorder=4)
ax2.axvline(TODAY_X, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax2.axvspan(TODAY_X, X_MAX, color="#000000", alpha=0.20, zorder=0)
ax2.set_xlim(X_MIN, X_MAX)
ax2.set_ylim(-0.75, 4.80)
ax2.set_ylabel("\\$ billions", fontsize=10)
ax2.set_xticks(np.arange(2021, 2028, 1))
ax2.set_xticklabels([str(y) for y in range(2021, 2028)])
ax2.legend(handles=[
    Patch(facecolor=ORANGE, label="Revenue \u2014 actual"),
    Patch(facecolor=ORANGE_EST, edgecolor=ORANGE, hatch="////", ls="--",
          label="Revenue \u2014 estimate"),
    Patch(facecolor=FCF_GREEN, label="Free cash flow \u2014 actual"),
    Patch(facecolor=FCF_EST, edgecolor="#1E7A44", hatch="////", ls="--",
          label="Free cash flow \u2014 estimate"),
], loc="upper left", ncol=2, frameon=False, fontsize=9.4,
    labelcolor=MUTED, handlelength=1.6, columnspacing=1.4)
footer(ax2, [
    "FISCAL-YEAR OFFSET \u2014 lululemon's fiscal year ends the Sunday nearest Jan 31: FY2025 ran "
    "Feb 2025 \u2013 Feb 1, 2026 and FY2026 ends Jan 31, 2027. Labels use the COMPANY's convention; "
    "several vendors label the same quarters one year higher (their \"Q2 2027\" is FY26 Q2 here). "
    "Fiscal Q4 runs 14 weeks in 53-week years \u2014 FY23 Q4 (Mar 2024) did, inflating it against its "
    "neighbours.",
    "FCF BASIS \u2014 lululemon publishes only year-to-date cash-flow statements, never a discrete "
    "quarterly one, so every bar is YTD-differenced (operating cash flow less purchases of property and "
    "equipment). FY26 Q2: \\$589.3M H1 OCF less \\$214.4M Q1 OCF = \\$374.9M, less (\\$277.1M less "
    "\\$127.4M) = \\$149.7M capex, giving \\$225.2M. No acquisition, divestiture or spin-off breaks YoY "
    "comparability in this window (the MIRROR / lululemon Studio wind-down was immaterial to revenue), "
    "so the YoY reads are clean.",
    "RELEASE MONTHS \u2014 each verified twice, against SEC 8-K filing dates and AlphaQuery. Cadence is "
    "NOT fixed for a given fiscal quarter across years: Q4 moved from Mar 29, 2022 / Mar 28, 2023 to "
    "Mar 21, 2024, Mar 27, 2025 and Mar 17, 2026; Q2 from Sep 8, 2021 to Aug 29, 2024 and back to "
    "Sep 3, 2026.",
    "ESTIMATES \u2014 FY26 Q3 revenue is the guidance midpoint (\\$2.29\u20132.32B, issued Sep 3, 2026); "
    "FY26 Q4 is implied by the FY26 guide midpoint (\\$10.35\u201310.50B) less H1 actual less the Q3 "
    "guide; FY27 Q1/Q2 use the street's roughly flat-YoY FY27. Quarterly FCF estimates are MODEL-DERIVED "
    "(no broker publishes a quarterly FCF consensus) from the prior-year seasonal FCF margin on guided "
    "revenue, haircut for the guided earnings decline; FY26 capex is guided to \\$700\u2013720M. Treat "
    "the hatched FCF bars as directional only.",
])

# ===========================================================================
# Panel 3 -- weekly close with 50d / 200d SMA
# ===========================================================================
ax3 = fig.add_subplot(gs[2])
style(ax3, "3.  Weekly close with 50-day & 200-day simple moving averages",
      "Past 53 weeks   |   Friday closes, with SMA readings sampled weekly from "
      "the daily series")

wx = np.arange(len(weekly))
ax3.plot(wx, sma200_w.values, color=PURPLE, lw=1.8, marker="o", ms=2.8,
         label="200-day SMA", zorder=4)
ax3.plot(wx, sma50_w.values, color=GOLD, lw=1.8, marker="o", ms=2.8,
         label="50-day SMA", zorder=4)
ax3.plot(wx, weekly.values, color=BLUE, lw=2.0, marker="o", ms=3.4,
         label="Weekly close", zorder=5)

last = wx[-1]
ax3.annotate(f"200D SMA\n\\${SMA200_NOW:,.2f}", xy=(last, SMA200_NOW),
             xytext=(last - 7.5, SMA200_NOW + 30), color=PURPLE, fontsize=10.2,
             fontweight="bold", ha="center", va="bottom", linespacing=1.4,
             arrowprops=dict(arrowstyle="->", color=PURPLE, lw=1.0, alpha=0.85))
ax3.annotate(f"50D SMA\n\\${SMA50_NOW:,.2f}", xy=(last, SMA50_NOW),
             xytext=(last - 12.5, 141), color=GOLD, fontsize=10.2,
             fontweight="bold", ha="center", va="bottom", linespacing=1.4,
             arrowprops=dict(arrowstyle="->", color=GOLD, lw=1.0, alpha=0.85))
ax3.annotate(f"close  \\${weekly.iloc[-1]:,.2f}", xy=(last, weekly.iloc[-1]),
             xytext=(last - 8.0, 88), color=BLUE, fontsize=10.2,
             fontweight="bold", ha="center", va="center",
             arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0, alpha=0.85))

ax3.text(6.5, 319, "The 50D has sat below the 200D in every week shown \u2014\n"
                   "the death cross itself dates to Apr 25, 2025",
         color=NEUTRAL, fontsize=8.9, ha="left", va="top", linespacing=1.5)

ax3.set_xticks(wx[::4])
ax3.set_xticklabels([d.strftime("%b %-d\n%Y") for d in weekly.index[::4]],
                    fontsize=8.6)
ax3.set_xlim(-1.2, len(weekly) + 0.5)
ax3.set_ylim(72, 324)
ax3.set_ylabel("Share price (\\$)", fontsize=10)
ax3.legend(loc="lower left", frameon=False, fontsize=9.8, labelcolor=MUTED,
           handlelength=1.9)
footer(ax3, [
    "Weekly closes are every Friday close taken from the full daily series (Yahoo Finance) \u2014 all 53 "
    "points are confirmed data; none are interpolated or estimated between anchors. Had any week needed "
    "filling in between confirmed anchors it would be flagged here; none did.",
    "The 50D and 200D series are computed from those same daily closes and reconcile EXACTLY to every "
    "dated reading wallstreetnumbers.com publishes for LULU: current \u2014 50D \\$118.40, 200D "
    "\\$152.77; Sep 3, 2026 \u2014 50D \\$118.63, 200D \\$153.09; Dec 31, 2025 \u2014 50D \\$183.78, "
    "200D \\$223.62; the 50D 1-year low of \\$117.57 on Aug 17, 2026; and the 1-year highs of 50D "
    "\\$214.25 / 200D \\$301.56 set Sep 4, 2025. Today's 200D reading is itself a fresh 1-year low.",
    "Price has closed below the 200-day average on every session since Jun 6, 2025. It had, however, "
    "spent 23 of the 28 sessions from Jul 28 through Sep 3, 2026 back above the 50-day \u2014 longest "
    "unbroken run 14 sessions (Jul 28 \u2013 Aug 14), slipping below on Aug 17, 20, 26, 27 and Sep 1 "
    "\u2014 so this gap-down destroyed a short-term recovery that was still in progress. Today's close "
    "sits 15.0% under the 50D and 34.1% under the 200D.",
])

# ===========================================================================
# Panel 4 -- EPS estimated vs reported
# ===========================================================================
ax4 = fig.add_subplot(gs[3])
style(ax4, "4.  Earnings per share \u2014 estimated vs. reported",
      "Last four reported quarters on a comparable (non-GAAP) basis, then the "
      "next two quarters on estimates only")

labels = [l for l, _, _ in EPS_REPORTED] + [l for l, _ in EPS_FORWARD]
n_rep = len(EPS_REPORTED)
pos = np.arange(len(labels), dtype=float)
w = 0.30


def put_label(ax, x, v, color, weight="bold", size=10.4):
    """Label always beyond the bar tip, never over the bar."""
    if v >= 0:
        ax.text(x, v + 0.11, f"\\${v:,.2f}", color=color, fontsize=size,
                fontweight=weight, ha="center", va="bottom")
    else:
        ax.text(x, v - 0.11, f"\\${v:,.2f}", color=color, fontsize=size,
                fontweight=weight, ha="center", va="top")


for i, (lab, est, act) in enumerate(EPS_REPORTED):
    ax4.bar(pos[i] - w / 2, est, width=w, color=NEUTRAL, alpha=0.55, zorder=3)
    met = abs(act - est) < 0.005
    beat = act > est
    col = NEUTRAL if met else (GREEN if beat else RED)
    ax4.bar(pos[i] + w / 2, act, width=w, color=col, zorder=3)
    put_label(ax4, pos[i] - w / 2, est, MUTED, weight="normal")
    put_label(ax4, pos[i] + w / 2, act, col)
    tag = "MET" if met else ("BEAT" if beat else "MISS")
    ax4.text(pos[i], -0.30, f"{tag}  {act - est:+.2f}", color=col,
             fontsize=10.4, fontweight="bold", ha="center", va="top")

for j, (lab, est) in enumerate(EPS_FORWARD):
    i = n_rep + j
    ax4.bar(pos[i], est, width=w, color="#474D55", hatch="////",
            edgecolor=NEUTRAL, lw=1.1, ls="--", zorder=3)
    put_label(ax4, pos[i], est, MUTED, weight="normal")
    ax4.text(pos[i], -0.30, "ESTIMATE", color=DIM, fontsize=10.4,
             fontweight="bold", ha="center", va="top")

ax4.axvline(n_rep - 0.5, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax4.axhline(0, color=MUTED, lw=1.0, alpha=0.6, zorder=4)
ax4.set_xticks(pos)
ax4.set_xticklabels(labels, fontsize=9.6, color=MUTED)
ax4.tick_params(axis="x", pad=24)
ax4.set_xlim(-0.7, len(labels) - 0.3)
ax4.set_ylim(-0.95, 6.4)
ax4.set_ylabel("Diluted EPS (\\$)", fontsize=10)
ax4.legend(handles=[
    Patch(facecolor=NEUTRAL, alpha=0.55, label="Consensus estimate"),
    Patch(facecolor=GREEN, label="Reported \u2014 beat"),
    Patch(facecolor=RED, label="Reported \u2014 miss"),
    Patch(facecolor="#474D55", edgecolor=NEUTRAL, hatch="////", ls="--",
          label="Forward estimate (not yet reported)"),
], loc="upper center", ncol=4, frameon=False, fontsize=9.4, labelcolor=MUTED,
    handlelength=1.6, columnspacing=1.5)
footer(ax4, [
    "NON-GAAP SUBSTITUTION \u2014 FY26 Q2 headline diluted EPS was \\$2.92, but it carries \\$0.86/sh "
    "(net of tax) from one-time IEEPA tariff refunds of \\$134.5M plus related interest. The comparable "
    "\\$2.06 is charted instead, so the quarter reads as a +\\$0.27 beat rather than a meaningless "
    "+\\$1.13. FY25 Q3's actual is likewise the comparable \\$2.59.",
    "Each pair was confirmed twice \u2014 AlphaQuery's dated earnings history plus contemporaneous "
    "coverage of the release itself (Zacks/AP for the FY25 Q3 \\$2.22 consensus and the FY25 Q4 "
    "\\$4.78; CNBC/LSEG and TradingView for the FY26 Q1 \\$1.68; CNBC and Newsquawk for the FY26 Q2 "
    "\\$1.79). Vendors disagree slightly on the FY25 Q4 consensus, quoted at \\$4.76\u2013\\$4.79; the "
    "\\$4.78 cited in coverage at the time is charted and the BEAT verdict holds across the range. FY26 Q1's +\\$0.01 is a beat so narrow "
    "it is effectively an in-line print.",
    "FORWARD BARS \u2014 FY26 Q3 \\$0.96 is the midpoint of company guidance of \\$0.93\u2013\\$0.98 "
    "issued Sep 3, 2026, against a pre-print sell-side consensus of \\$2.41 that is now stale and being "
    "cut toward that guide. FY26 Q4 \\$4.04 is the FY26 EPS guidance midpoint of \\$9.605 "
    "(\\$9.48\u2013\\$9.73) less H1 actual of \\$4.61 less the Q3 guide. Both forward bars sit on a "
    "guidance (as-reported) basis rather than the comparable basis used for the actuals. Next report "
    "expected early-to-mid Dec 2026.",
], y=-0.255)

fig.savefig(OUT, facecolor=BG, dpi=100)
print("wrote", OUT)
