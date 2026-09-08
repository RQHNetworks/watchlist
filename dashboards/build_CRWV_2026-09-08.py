"""
CRWV price-swing dashboard -- 2026-09-08.

Four stacked panels rendered as one tall dark-mode portrait PNG:
  1. Five-year monthly close (CoreWeave IPO'd 2025-03-28, so the series
     starts there), 52-week high/low and the all-time high marked
  2. Revenue & free cash flow by quarter, plotted at RELEASE month
  3. Weekly close with 50-day / 200-day SMA
  4. Quarterly EPS -- consensus vs reported, plus four forward estimate bars

Price + SMA series come from yfinance daily closes; the computed SMA series
reconciles exactly to every dated reading wallstreetnumbers.com publishes
(50D $85.68 / 200D $91.60 today; 50D 1y low $80.59 Jan 23 '26; 200D 1y high
$110.07 Mar 4 '26; 200D 1y low $91.35 Sep 1 '26; YE25 50D $91.49 / 200D
$103.41).

Quarterly FCF is YTD-differenced straight from SEC XBRL company facts
(NetCashProvidedByUsedInOperatingActivities less
PaymentsToAcquirePropertyPlantAndEquipment) -- CoreWeave publishes only
cumulative year-to-date cash-flow statements, never a discrete quarterly one.
Every release month is the SEC 8-K Item 2.02 filing date.

No footnote / source-note text is drawn anywhere in the image -- all of that
lives in the companion markdown write-up.

Built against the FINAL Sep 8, 2026 close of $99.83 (+11.72%).
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parent / "CRWV_price_swing_2026-09-08.png"
DAILY_CSV = "/tmp/crwv_daily_clean.csv"

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
COMPANY = "CoreWeave, Inc."
TICKER = "CRWV"
PRICE = 99.83
PREV_CLOSE = 89.36
CHG = PRICE - PREV_CLOSE
CHG_PCT = CHG / PREV_CLOSE * 100.0

WK52_HIGH, WK52_HIGH_DT = 153.20, "2025-10-10"   # intraday
WK52_LOW, WK52_LOW_DT = 60.55, "2026-07-29"      # intraday
ATH, ATH_DT = 187.00, "2025-06-20"               # intraday, all-time
IPO_DT, IPO_PRICE = "2025-03-28", 40.00


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
monthly = daily.resample("ME").last().dropna()
weekly = daily.loc["2025-09-05":].resample("W-FRI").last().dropna()
# min_periods=1 matches how wallstreetnumbers computes the 200D over the
# post-IPO window before a full 200 sessions exist (verified to the cent).
sma50 = daily.rolling(50, min_periods=1).mean()
sma200 = daily.rolling(200, min_periods=1).mean()
sma50_w = sma50.reindex(weekly.index, method="ffill")
sma200_w = sma200.reindex(weekly.index, method="ffill")
SMA50_NOW = float(sma50.iloc[-1])
SMA200_NOW = float(sma200.iloc[-1])

X_MIN, X_MAX = 2021.0, yfrac("2027-10-15")
TODAY_X = yfrac("2026-09-08")

# ---------------------------------------------------------------------------
# Panel 2 -- quarterly revenue & free cash flow, keyed to ACTUAL release dates.
#   CoreWeave's fiscal year IS the calendar year, so no fiscal-label offset.
#   Release dates are SEC 8-K Item 2.02 filing dates; the cadence drifts
#   (Q1: May 14 '25 -> May 7 '26; Q2: Aug 12 '25 -> Aug 11 '26).
#   FCF = operating cash flow less purchases of property & equipment, both
#   YTD-differenced from SEC XBRL facts.
#   (label, quarter end, release date, revenue $B, FCF $B)
# ---------------------------------------------------------------------------
QUARTERS = [
    ("Q1 2025", "2025-03-31", "2025-05-14", 0.9820, -1.3460),
    ("Q2 2025", "2025-06-30", "2025-08-12", 1.2120, -2.7040),
    ("Q3 2025", "2025-09-30", "2025-11-10", 1.3647, -0.7001),
    ("Q4 2025", "2025-12-31", "2026-02-26", 1.5719, -2.5009),
    ("Q1 2026", "2026-03-31", "2026-05-07", 2.0780, -4.7110),
    ("Q2 2026", "2026-06-30", "2026-08-11", 2.5750, -5.7430),
]
# Next four quarters. Revenue: Q3'26 is the company guidance midpoint, Q4'26 is
# implied by the raised FY26 guide, FY27 quarters are split from the $26.47B
# FY27 consensus. FCF: model-derived from guided capex (Q3'26 $11.5-13.5B mid;
# Q4'26 the residual of the $35-39B FY26 guide) -- no broker publishes a
# quarterly FCF consensus.
QUARTERS_EST = [
    ("Q3 2026", "2026-09-30", "2026-11-10", 3.525, -10.209),
    ("Q4 2026", "2026-12-31", "2027-02-25", 4.700, -7.328),
    ("Q1 2027", "2027-03-31", "2027-05-06", 5.450, -5.457),
    ("Q2 2027", "2027-06-30", "2027-08-10", 6.200, -5.270),
]

# ---------------------------------------------------------------------------
# Panel 4 -- EPS consensus vs reported.
#   Reported = CoreWeave's own diluted net loss per share from each 8-K press
#   release. No one-time item distorts any of these four comparisons (the
#   adjustments CoreWeave makes are recurring SBC / financing items), so the
#   headline figure is the comparable figure and no non-GAAP swap is needed.
# ---------------------------------------------------------------------------
EPS_REPORTED = [
    ("Q3 2025\nNov 10 '25", -0.36, -0.22),
    ("Q4 2025\nFeb 26 '26", -0.61, -0.89),
    ("Q1 2026\nMay 7 '26", -1.17, -1.40),
    ("Q2 2026\nAug 11 '26", -1.52, -1.14),
]
EPS_FORWARD = [
    ("Q3 2026\nNov '26 (E)", -1.62),
    ("Q4 2026\nFeb '27 (E)", -1.14),
    ("Q1 2027\nMay '27 (E)", -1.25),
    ("Q2 2027\nAug '27 (E)", -1.02),
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
         f"Price-swing trigger \u2014 Sep 8, 2026   \u00b7   prior close "
         f"\\${PREV_CLOSE:,.2f}   \u00b7   AI-infrastructure bid after "
         f"OpenAI's Astra launch",
         color=MUTED, fontsize=9.8, va="center", ha="left")

fig.text(0.972, 0.9870, f"\\${PRICE:,.2f}", color=OFFWHITE,
         fontsize=22, fontweight="bold", va="center", ha="right")
fig.text(0.972, 0.9672, f"{CHG:+.2f}  ({CHG_PCT:+.2f}%)",
         color=GREEN, fontsize=13.0, fontweight="bold", va="center", ha="right")

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
ax1.annotate(f"52W HIGH  \\${WK52_HIGH:,.2f}\nOct 10, 2025",
             xy=(hx, WK52_HIGH), xytext=(hx + 0.34, WK52_HIGH + 22),
             color=GREEN, fontsize=10.4, fontweight="bold", ha="left",
             va="bottom", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=GREEN, lw=1.1, alpha=0.8))
ax1.annotate(f"52W LOW  \\${WK52_LOW:,.2f}\nJul 29, 2026",
             xy=(lx, WK52_LOW), xytext=(lx + 0.36, 43),
             color=RED, fontsize=10.4, fontweight="bold", ha="left",
             va="center", linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=RED, lw=1.1, alpha=0.8))

ax1.axhline(PRICE, color=MUTED, lw=0.9, ls=(0, (5, 4)), alpha=0.5, zorder=1)
ax1.text(X_MAX - 0.06, PRICE + 5, f"now  \\${PRICE:,.2f}", color=MUTED,
         fontsize=9.5, ha="right", va="bottom")

ath_x = yfrac(ATH_DT)
ax1.plot([ath_x], [ATH], "o", ms=6, color=NEUTRAL, zorder=5,
         mec=PANEL_BG, mew=1.6)
ax1.text(ath_x - 0.10, ATH + 4,
         "all-time high  \\$187.00  (Jun 20, 2025)  \u2014  today is "
         "\u201346.6% below it",
         color=NEUTRAL, fontsize=9.2, ha="right", va="bottom")

ipo_x = yfrac(IPO_DT)
ax1.plot([ipo_x], [IPO_PRICE], "o", ms=6, color=BLUE, zorder=5,
         mec=PANEL_BG, mew=1.6)
ax1.annotate("IPO Mar 28, 2025 @ \\$40.00\nno public price history before this date",
             xy=(ipo_x, IPO_PRICE), xytext=(2021.35, 72),
             color=NEUTRAL, fontsize=9.6, ha="left", va="center",
             linespacing=1.6,
             arrowprops=dict(arrowstyle="->", color=DIM, lw=1.0))

ax1.axvline(TODAY_X, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax1.axvspan(TODAY_X, X_MAX, color="#000000", alpha=0.20, zorder=0)
ax1.text(X_MAX - 0.06, 10, "forward period", color=DIM, fontsize=8.6,
         ha="right", va="bottom")
ax1.set_xlim(X_MIN, X_MAX)
ax1.set_ylim(0, 215)
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

BW = 0.105
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

qx = yfrac("2026-08-11")
ax2.annotate("Q2 2026, reported Aug 11, 2026\nrevenue \\$2.58B, +112% YoY \u2014 sixth\n"
             "straight quarter of triple-digit growth",
             xy=(qx - BW / 2, 2.60), xytext=(qx - 1.60, 6.8),
             color=OFFWHITE, fontsize=9.3, ha="center", va="top",
             linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax2.annotate("free cash flow has been negative in every\nreported quarter \u2014 capex "
             "guided to \\$35\u201339B for 2026",
             xy=(yfrac("2026-08-11") + BW / 2, -5.80),
             xytext=(2022.35, -8.6),
             color=NEUTRAL, fontsize=9.3, ha="left", va="center",
             linespacing=1.6,
             arrowprops=dict(arrowstyle="->", color=DIM, lw=0.9))
ax2.annotate("first quarter reported as a public company\n(IPO Mar 28, 2025)",
             xy=(yfrac("2025-05-14") - BW / 2, 1.06),
             xytext=(2022.05, 3.5),
             color=NEUTRAL, fontsize=9.3, ha="left", va="center",
             linespacing=1.6,
             arrowprops=dict(arrowstyle="->", color=DIM, lw=0.9))

ax2.axhline(0, color=MUTED, lw=1.0, alpha=0.6, zorder=4)
ax2.axvline(TODAY_X, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax2.axvspan(TODAY_X, X_MAX, color="#000000", alpha=0.20, zorder=0)
ax2.set_xlim(X_MIN, X_MAX)
ax2.set_ylim(-11.6, 7.9)
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
      "Past 54 weeks of Friday closes with dated 50D / 200D SMA readings "
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
    (float(weekly.iloc[-1]), BLUE, f"close  \\${weekly.iloc[-1]:,.2f}"),
    (SMA200_NOW, PURPLE, f"200D SMA  \\${SMA200_NOW:,.2f}"),
    (SMA50_NOW, GOLD, f"50D SMA  \\${SMA50_NOW:,.2f}"),
):
    ax3.plot([last, last + 1.0], [value, value], color=colour, lw=1.0,
             alpha=0.6, zorder=3)
    ax3.text(last + 1.5, value, text, color=colour, fontsize=10.4,
             fontweight="bold", ha="left", va="center")

# Most recent crossover: death cross on Jul 28, 2026 (50D 95.84 / 200D 95.91).
cross_x = float(np.interp(
    pd.Timestamp("2026-07-28").value,
    [weekly.index[46].value, weekly.index[47].value], [46.0, 47.0]))
ax3.axvline(cross_x, color=RED, lw=1.1, ls=(0, (4, 3)), alpha=0.75, zorder=2)
ax3.annotate("DEATH CROSS  Jul 28, 2026\n50D \\$95.84  \u00d7  200D \\$95.91",
             xy=(cross_x, 95.9), xytext=(cross_x - 8.0, 148),
             color=RED, fontsize=9.6, fontweight="bold", ha="center",
             va="center", linespacing=1.5,
             arrowprops=dict(arrowstyle="->", color=RED, lw=1.0, alpha=0.85))

ax3.text(0.4, 70.0,
         "Three crossovers in this window \u2014 death cross Dec 15, 2025; golden "
         "cross May 19, 2026; death cross Jul 28, 2026 (most recent).\n"
         "1-year slope:  50D \\$118.85 \u2192 \\$85.68 (\u201327.9%)   |   "
         "200D \\$101.90 \u2192 \\$91.60 (\u201310.1%)  \u2014 both still falling.\n"
         "Today's close sits +16.5% above the 50D and +9.0% above the 200D, with "
         "the 50D\u2013200D gap narrowed to \\$5.92.",
         color=NEUTRAL, fontsize=8.9, ha="left", va="top", linespacing=1.7)

ax3.set_xticks(wx[::4])
ax3.set_xticklabels([d.strftime("%b %-d\n%Y") for d in weekly.index[::4]],
                    fontsize=8.6)
ax3.set_xlim(-1.2, len(weekly) + 10.5)
ax3.set_ylim(46, 166)
ax3.set_ylabel("Share price (\\$)", fontsize=10)
ax3.legend(loc="upper left", frameon=False, fontsize=9.8, labelcolor=MUTED,
           handlelength=1.9)

# ===========================================================================
# Panel 4 -- EPS estimated vs reported
# ===========================================================================
ax4 = fig.add_axes([AX_L, AX_BOTTOMS[3], AX_W, AX_H])
style(ax4, "4.  Quarterly earnings \u2014 actuals & estimates",
      "Last four reported quarters, consensus vs actual diluted EPS, then the "
      "next four quarters on estimates only")

labels = [l for l, _, _ in EPS_REPORTED] + [l for l, _ in EPS_FORWARD]
n_rep = len(EPS_REPORTED)
pos = np.arange(len(labels), dtype=float)
w = 0.30
TAG_Y = -2.16


def put_label(ax, x, v, color, weight="bold", size=9.3):
    """Label always beyond the bar tip, never over the bar."""
    if v >= 0:
        ax.text(x, v + 0.075, f"\\${v:,.2f}", color=color, fontsize=size,
                fontweight=weight, ha="center", va="bottom")
    else:
        ax.text(x, v - 0.075, f"\u2013\\${abs(v):,.2f}", color=color,
                fontsize=size, fontweight=weight, ha="center", va="top")


for i, (lab, est, act) in enumerate(EPS_REPORTED):
    ax4.bar(pos[i] - w / 2, est, width=w, color=NEUTRAL, alpha=0.55, zorder=3)
    met = abs(act - est) < 0.005
    beat = act > est
    col = NEUTRAL if met else (GREEN if beat else RED)
    ax4.bar(pos[i] + w / 2, act, width=w, color=col, zorder=3)
    put_label(ax4, pos[i] - w / 2 - 0.035, est, MUTED, weight="normal")
    put_label(ax4, pos[i] + w / 2 + 0.035, act, col)
    tag = "MET" if met else ("BEAT" if beat else "MISS")
    ax4.text(pos[i], TAG_Y, f"{tag}  {act - est:+.2f}", color=col,
             fontsize=10.4, fontweight="bold", ha="center", va="top")

for j, (lab, est) in enumerate(EPS_FORWARD):
    i = n_rep + j
    ax4.bar(pos[i], est, width=w, color="#474D55", hatch="////",
            edgecolor=NEUTRAL, lw=1.1, ls="--", zorder=3)
    put_label(ax4, pos[i], est, MUTED, weight="normal")
    ax4.text(pos[i], TAG_Y, "ESTIMATE", color=DIM, fontsize=10.4,
             fontweight="bold", ha="center", va="top")

ax4.axvline(n_rep - 0.5, color=DIM, lw=0.9, ls=":", alpha=0.9)
ax4.axhline(0, color=MUTED, lw=1.0, alpha=0.6, zorder=4)
ax4.set_xticks(pos)
ax4.set_xticklabels(labels, fontsize=9.6, color=MUTED)
ax4.tick_params(axis="x", pad=26)
ax4.set_xlim(-0.7, len(labels) - 0.3)
ax4.set_ylim(-2.55, 0.92)
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
