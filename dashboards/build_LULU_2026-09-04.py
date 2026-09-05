"""
LULU price-swing dashboard -- 2026-09-04.

Four stacked panels rendered as one tall dark-mode portrait PNG:
  1. Five-year monthly close, 52-week high/low marked
  2. Revenue & free cash flow by fiscal quarter, plotted at RELEASE month
  3. Weekly close with 50-day / 200-day SMA
  4. Quarterly EPS -- estimate vs reported, plus four forward estimate bars

Price + SMA series come from yfinance daily closes; the computed SMA series
reconciles exactly to every dated reading wallstreetnumbers.com publishes.
Quarterly FCF is YTD-differenced straight from SEC XBRL company facts, and
every release month is the SEC 8-K Item 2.02 filing date.

No footnote / source-note text is drawn anywhere in the image -- all of that
lives in the companion markdown write-up.

Built against the FINAL Sep 4, 2026 close of $100.61 (-17.38%).
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parent / "LULU_price_swing_2026-09-04.png"
DAILY_CSV = "/tmp/lulu_daily_full.csv"

# ---------------------------------------------------------------------------
# Palette -- dark mode. Categorical sets cleared the dataviz validator on CVD
# separation, normal-vision separation and contrast-vs-surface.
# ---------------------------------------------------------------------------
BG = "#131519"
PANEL_BG = "#181B21"
OFFWHITE = "#EAECEF"
MUTED = "#8B939C"
DIM = "#6A717A"
GRID = "#262A31"
BLUE = "#5AA5EE"
GREEN = "#35C75A"
RED = "#F0455A"
ORANGE = "#C2652A"          # revenue (deep muted dark orange)
ORANGE_EST = "#D69463"      # lighter / desaturated revenue (estimate)
FCF_GREEN = "#33CE60"       # free cash flow (bright green)
FCF_EST = "#86D7A4"         # lighter / desaturated FCF (estimate)
GOLD = "#D8AC3E"
PURPLE = "#AE83E2"
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
#   Fiscal labels follow lululemon's own convention (FY2025 ended 2026-02-01),
#   one behind the "period-end year" label most data vendors use.
#   (fiscal label, quarter end, release date, revenue $B, FCF $B)
# ---------------------------------------------------------------------------
QUARTERS = [
    ("FY20 Q4", "2021-01-31", "2021-03-30", 1.7296, 0.6595),
    ("FY21 Q1", "2021-05-02", "2021-06-03", 1.2265, 0.1499),
    ("FY21 Q2", "2021-08-01", "2021-09-08", 1.4506, 0.2054),
    ("FY21 Q3", "2021-10-31", "2021-12-09", 1.4504, 0.0358),
    ("FY21 Q4", "2022-01-30", "2022-03-29", 2.1294, 0.6035),
    ("FY22 Q1", "2022-05-01", "2022-06-02", 1.6132, -0.3546),
    ("FY22 Q2", "2022-07-31", "2022-09-01", 1.8683, -0.0471),
    ("FY22 Q3", "2022-10-30", "2022-12-08", 1.8566, -0.1098),
    ("FY22 Q4", "2023-01-29", "2023-03-28", 2.7715, 0.8393),
    ("FY23 Q1", "2023-04-30", "2023-06-01", 2.0007, -0.0914),
    ("FY23 Q2", "2023-07-30", "2023-08-31", 2.2087, 0.3312),
    ("FY23 Q3", "2023-10-29", "2023-12-07", 2.2040, 0.2270),
    ("FY23 Q4", "2024-01-28", "2024-03-21", 3.2054, 1.1780),
    ("FY24 Q1", "2024-04-28", "2024-06-05", 2.2087, -0.0032),
    ("FY24 Q2", "2024-07-28", "2024-08-29", 2.3708, 0.2981),
    ("FY24 Q3", "2024-10-27", "2024-12-05", 2.3966, 0.1222),
    ("FY24 Q4", "2025-02-02", "2025-03-27", 3.6113, 1.1660),
    ("FY25 Q1", "2025-05-04", "2025-06-05", 2.3710, -0.2712),
    ("FY25 Q2", "2025-08-03", "2025-09-04", 2.5250, 0.1508),
    ("FY25 Q3", "2025-11-02", "2025-12-11", 2.5660, 0.0824),
    ("FY25 Q4", "2026-02-01", "2026-03-17", 3.6410, 0.9597),
    ("FY26 Q1", "2026-05-03", "2026-06-04", 2.4720, 0.0871),
    ("FY26 Q2", "2026-08-02", "2026-09-03", 2.4160, 0.2252),
]
# Next four quarters. Revenue: Q3 guidance midpoint, Q4 implied by the FY26
# guide, FY27 H1 model-derived. FCF: model-derived (no quarterly FCF consensus
# is published anywhere).
QUARTERS_EST = [
    ("FY26 Q3", "2026-11-01", "2026-12-09", 2.305, 0.028),
    ("FY26 Q4", "2027-01-31", "2027-03-18", 3.232, 0.700),
    ("FY27 Q1", "2027-05-02", "2027-06-03", 2.400, 0.078),
    ("FY27 Q2", "2027-08-01", "2027-09-02", 2.340, 0.077),
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
    ("FY27 Q1\nJun '27 (E)", 1.55),
    ("FY27 Q2\nSep '27 (E)", 1.90),
]

# ---------------------------------------------------------------------------
# Figure -- 1200 x 2550 px
# ---------------------------------------------------------------------------
fig = plt.figure(figsize=(12.0, 25.5), dpi=100)
fig.patch.set_facecolor(BG)

AX_L, AX_W, AX_H = 0.078, 0.894, 0.1680
AX_BOTTOMS = [0.752, 0.518, 0.284, 0.050]


def style(ax, title, subtitle):
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color=GRID, lw=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(labelsize=9.5, length=0)
    ax.text(0, 1.098, title, transform=ax.transAxes, color=OFFWHITE,
            fontsize=15.5, fontweight="bold", va="bottom", ha="left")
    ax.text(0, 1.042, subtitle, transform=ax.transAxes, color=MUTED,
            fontsize=9.8, va="bottom", ha="left")


# ===========================================================================
# Header
# ===========================================================================
fig.text(0.078, 0.9855, f"{COMPANY}  ({TICKER})", color=OFFWHITE,
         fontsize=21, fontweight="bold", va="center", ha="left")
fig.text(0.078, 0.9682,
         f"Price-swing trigger \u2014 Sep 4, 2026   \u00b7   prior close "
         f"\\${PREV_CLOSE:,.2f}   \u00b7   Q2 FY2026 revenue miss, "
         f"2nd straight guidance cut",
         color=MUTED, fontsize=9.8, va="center", ha="left")

fig.text(0.972, 0.9870, f"\\${PRICE:,.2f}", color=OFFWHITE,
         fontsize=22, fontweight="bold", va="center", ha="right")
fig.text(0.972, 0.9672, f"{CHG:+.2f}  ({CHG_PCT:+.2f}%)",
         color=RED, fontsize=13.0, fontweight="bold", va="center", ha="right")

# ===========================================================================
# Panel 1 -- 5-year monthly close
# ===========================================================================
ax1 = fig.add_axes([AX_L, AX_BOTTOMS[0], AX_W, AX_H])
style(ax1, "1.  Five-year stock chart \u2014 monthly close",
      "Continuous month-end closing price, Jan 2021 \u2013 Sep 2026   |   "
      "52-week high / low marked")

mx = [yfrac(d) for d in monthly.index]
ax1.plot(mx, monthly.values, color=BLUE, lw=2.0, zorder=3)
ax1.fill_between(mx, monthly.values, 0, color=BLUE, alpha=0.07, zorder=2)

hx, lx = yfrac(WK52_HIGH_DT), yfrac(WK52_LOW_DT)
ax1.plot([hx], [WK52_HIGH], "o", ms=8, color=GREEN, zorder=6,
         mec=PANEL_BG, mew=2)
ax1.plot([lx], [WK52_LOW], "o", ms=8, color=RED, zorder=6,
         mec=PANEL_BG, mew=2)
ax1.annotate(f"52W HIGH  \\${WK52_HIGH:,.2f}\nDec 18, 2025",
             xy=(hx, WK52_HIGH), xytext=(hx - 0.30, WK52_HIGH + 112),
             color=GREEN, fontsize=10.4, fontweight="bold", ha="center",
             va="bottom", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=GREEN, lw=1.1, alpha=0.8))
ax1.annotate(f"52W LOW  \\${WK52_LOW:,.2f}\nSep 4, 2026  (today)",
             xy=(lx, WK52_LOW), xytext=(lx - 1.85, 47),
             color=RED, fontsize=10.4, fontweight="bold", ha="left",
             va="center", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=RED, lw=1.1, alpha=0.8))

ax1.axhline(PRICE, color=MUTED, lw=0.9, ls=(0, (5, 4)), alpha=0.5, zorder=1)
ax1.text(X_MAX - 0.06, PRICE + 14, f"now  \\${PRICE:,.2f}", color=MUTED,
         fontsize=9.5, ha="right", va="bottom")

ath_x = yfrac("2023-12-29")
ax1.plot([ath_x], [511.29], "o", ms=6, color=NEUTRAL, zorder=5,
         mec=PANEL_BG, mew=1.6)
ax1.text(ath_x + 0.13, 511.29 + 6,
         "all-time closing high  \\$511.29  (Dec 29, 2023)  \u2014  today is "
         "\u201380.3% below it",
         color=NEUTRAL, fontsize=9.2, ha="left", va="bottom")

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

# ===========================================================================
# Panel 2 -- revenue & free cash flow by quarter, at release month
# ===========================================================================
ax2 = fig.add_axes([AX_L, AX_BOTTOMS[1], AX_W, AX_H])
style(ax2, "2.  Revenue & free cash flow (5 years)",
      "Plotted at the calendar month each quarter was actually REPORTED, not at "
      "fiscal quarter-end   |   same numeric axis as Panel 1")

BW = 0.104
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
ax2.annotate("FY26 Q2, reported Sep 3, 2026\nrevenue \\$2.42B, \u20134% YoY \u2014 "
             "first YoY decline\nin the 23 quarters charted; comps \u20139%",
             xy=(qx - BW / 2, 2.44), xytext=(qx - 0.42, 4.52),
             color=OFFWHITE, fontsize=9.3, ha="center", va="top",
             linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax2.annotate("53-week fiscal year:\nFY23 Q4 ran 14 weeks",
             xy=(yfrac("2024-03-21") - BW / 2, 3.24),
             xytext=(yfrac("2023-06-05"), 4.05),
             color=NEUTRAL, fontsize=8.8, ha="center", va="top", linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=DIM, lw=0.9))

ax2.axhline(0, color=MUTED, lw=1.0, alpha=0.6, zorder=4)
ax2.axvline(TODAY_X, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax2.axvspan(TODAY_X, X_MAX, color="#000000", alpha=0.20, zorder=0)
ax2.set_xlim(X_MIN, X_MAX)
ax2.set_ylim(-0.75, 4.95)
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

# ===========================================================================
# Panel 3 -- weekly close with 50d / 200d SMA
# ===========================================================================
ax3 = fig.add_axes([AX_L, AX_BOTTOMS[2], AX_W, AX_H])
style(ax3, "3.  Technicals \u2014 50-day & 200-day simple moving averages",
      "Past 53 weeks of Friday closes with dated 50D / 200D SMA readings "
      "overlaid")

wx = np.arange(len(weekly))
ax3.plot(wx, sma200_w.values, color=PURPLE, lw=2.0, marker="o", ms=3.0,
         label="200-day SMA", zorder=4)
ax3.plot(wx, sma50_w.values, color=GOLD, lw=2.0, marker="o", ms=3.0,
         label="50-day SMA", zorder=4)
ax3.plot(wx, weekly.values, color=BLUE, lw=2.0, marker="o", ms=3.6,
         label="Weekly close", zorder=5)

last = wx[-1]
# Current-value callouts sit in a reserved right-hand margin, level with each
# line end -- no arrows crossing other series, no label-on-line collisions.
for value, colour, text in (
    (SMA200_NOW, PURPLE, f"200D SMA  \\${SMA200_NOW:,.2f}"),
    (SMA50_NOW, GOLD, f"50D SMA  \\${SMA50_NOW:,.2f}"),
    (float(weekly.iloc[-1]), BLUE, f"close  \\${weekly.iloc[-1]:,.2f}"),
):
    ax3.plot([last, last + 1.0], [value, value], color=colour, lw=1.0,
             alpha=0.6, zorder=3)
    ax3.text(last + 1.5, value, text, color=colour, fontsize=10.4,
             fontweight="bold", ha="left", va="center")

ax3.text(3.2, 356,
         "NO CROSSOVER IN THIS WINDOW \u2014 the 50D has sat below the 200D in "
         "all 53 weeks shown; the last cross was a DEATH CROSS on\nApr 25, 2025 "
         "(50D \\$313.05 vs 200D \\$314.13), before this chart begins.\n"
         "1-year slope:  50D \\$212.97 \u2192 \\$118.40 (\u201344.4%)   |   "
         "200D \\$300.75 \u2192 \\$152.77 (\u201349.2%)  \u2014 both falling, "
         "both overhead as resistance.",
         color=NEUTRAL, fontsize=8.9, ha="left", va="top", linespacing=1.7)

ax3.set_xticks(wx[::4])
ax3.set_xticklabels([d.strftime("%b %-d\n%Y") for d in weekly.index[::4]],
                    fontsize=8.6)
ax3.set_xlim(-1.2, len(weekly) + 10.5)
ax3.set_ylim(70, 362)
ax3.set_ylabel("Share price (\\$)", fontsize=10)
ax3.legend(loc="lower left", frameon=False, fontsize=9.8, labelcolor=MUTED,
           handlelength=1.9)

# ===========================================================================
# Panel 4 -- EPS estimated vs reported
# ===========================================================================
ax4 = fig.add_axes([AX_L, AX_BOTTOMS[3], AX_W, AX_H])
style(ax4, "4.  Quarterly earnings \u2014 actuals & estimates",
      "Last four reported quarters, estimate vs actual on a comparable "
      "(non-GAAP) basis, then the next four quarters on estimates only")

labels = [l for l, _, _ in EPS_REPORTED] + [l for l, _ in EPS_FORWARD]
n_rep = len(EPS_REPORTED)
pos = np.arange(len(labels), dtype=float)
w = 0.30


def put_label(ax, x, v, color, weight="bold", size=9.3):
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
    put_label(ax4, pos[i] - w / 2 - 0.035, est, MUTED, weight="normal")
    put_label(ax4, pos[i] + w / 2 + 0.035, act, col)
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
ax4.set_ylim(-0.95, 6.6)
ax4.set_ylabel("Diluted EPS (\\$)", fontsize=10)
ax4.legend(handles=[
    Patch(facecolor=NEUTRAL, alpha=0.55, label="Consensus estimate"),
    Patch(facecolor=GREEN, label="Reported \u2014 beat"),
    Patch(facecolor=RED, label="Reported \u2014 miss"),
    Patch(facecolor="#474D55", edgecolor=NEUTRAL, hatch="////", ls="--",
          label="Forward estimate (not yet reported)"),
], loc="upper center", ncol=4, frameon=False, fontsize=9.4, labelcolor=MUTED,
    handlelength=1.6, columnspacing=1.5)

fig.savefig(OUT, facecolor=BG, dpi=100)
print("wrote", OUT)
