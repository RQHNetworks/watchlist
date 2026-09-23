#!/usr/bin/env python3
"""Render the report's three trigger tables as a single PNG.

Why this exists: an HTML table is laid out by the mail client, and mobile
clients draw small type larger than the stated px. That reflows columns and
splits words mid-word - "months" arriving as "month" + "s". Sizing the HTML
with headroom makes that unlikely; rendering a picture makes it impossible,
because nothing downstream gets a say.

Designed phone-first and scaled up, never down. The layout is 340 CSS px wide
and rasterised at 3x (1020px). A phone displays it at roughly its design size,
and a desktop stretches it to the cap in report.py - upward, into pixels that
already exist, so it stays sharp and the text gets bigger.

The tempting alternative is to design wide and let width:100% shrink it on a
phone. That inverts the problem: a 600px table squeezed into 358px renders
its text at 0.6x, smaller than the HTML it was meant to improve on.

Colours, the company-name shortening and the percent formatting come from
flag_email, so the picture and the HTML can never disagree about a number.
The type scale and column proportions are this module's own, because the two
now serve different screens.

Fonts are matplotlib's bundled DejaVu Sans rather than the HTML's system
stack, so the two will not look glyph-for-glyph identical - that is the point
of the comparison, not a defect.
"""

import html
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle
from matplotlib.textpath import TextPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "emails"))
import flag_email as fe  # noqa: E402  (path set above)

# The coordinate space is CSS px: 1 unit = 0.01 inch, so at dpi=300 one unit
# rasterises to exactly 3 device px. Font sizes convert with PT = css * 0.72
# (1 pt = 1/72 inch, 1 css px = 1/100 inch).
CSS_W = 340
DPI = 300
UNIT_IN = 0.01
PT_PER_CSS = 0.72

GAP = 1              # the grid: background showing between cells
PAD_X = 5            # cell padding, matching the HTML
HEADER_H = 24
ROW_H = 36
TITLE_H = 26
SECTION_GAP = 12

FAMILY = "DejaVu Sans"
MIN_SIZE = 5         # below this, truncate rather than shrink further

# The image keeps its own type scale and column proportions, separate from the
# HTML's. The two now serve different screens - the HTML table is sized to
# read on a desktop, this is sized to read on a phone - so tying them together
# would mean one of them is always wrong. Colours, the company shortening and
# the percent formatting are still shared, so the numbers can never disagree.
WIDTHS = ("26%", "23%", "17%", "17%", "17%")
HEADER_SIZE = 9
DATA_SIZE = 10
TICKER_SIZE = 12
COMPANY_SIZE = 6


_TAG_RE = re.compile(r"<[^>]+>")


def plain(s: str) -> str:
    """Strip the markup the HTML cells carry.

    col2 for an earnings row is pretty_date(), which returns
    "September 29<sup>th</sup>". A browser renders the superscript;
    matplotlib drew the tags literally, so the cell read
    "September 29<sup>th<...".
    """
    return html.unescape(_TAG_RE.sub("", s)).strip()


def text_width(s: str, css_size: float, bold: bool = False) -> float:
    """Width of `s` in CSS px at `css_size`."""
    if not s:
        return 0.0
    prop = FontProperties(family=FAMILY, weight="bold" if bold else "normal")
    tp = TextPath((0, 0), s, size=css_size * PT_PER_CSS, prop=prop)
    return tp.get_extents().width / PT_PER_CSS


def fit(s: str, avail: float, css_size: float, bold: bool = False):
    """Largest size <= css_size at which `s` fits `avail`, truncating if it can't.

    The whole reason for the image: rather than letting a client reflow text
    that does not fit, decide here and guarantee one line. "% Change Today"
    fits on a single line at a point smaller instead of wrapping.
    """
    size = css_size
    while size > MIN_SIZE and text_width(s, size, bold) > avail:
        size -= 0.25
    if text_width(s, size, bold) <= avail:
        return s, size
    # Still too wide at the floor: drop characters for an ellipsis.
    out = s
    while out and text_width(out + "…", size, bold) > avail:
        out = out[:-1]
    return (out.rstrip() + "…") if out else "", size


def col_widths() -> list:
    """WIDTHS as CSS px, absorbing rounding into the last column."""
    fracs = [int(w.rstrip("%")) / 100 for w in WIDTHS]
    inner = CSS_W - GAP * (len(fracs) + 1)
    px = [round(inner * f) for f in fracs]
    px[-1] += inner - sum(px)
    return px


class Canvas:
    """Draws cells into a CSS-px coordinate space, top-down."""

    def __init__(self, height: float):
        self.h = height
        self.fig = plt.figure(figsize=(CSS_W * UNIT_IN, height * UNIT_IN), dpi=DPI)
        self.fig.patch.set_facecolor(fe.BG)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, CSS_W)
        self.ax.set_ylim(height, 0)          # inverted: y grows downward
        self.ax.axis("off")

    def rect(self, x, y, w, h, colour):
        self.ax.add_patch(Rectangle((x, y), w, h, facecolor=colour,
                                    edgecolor="none", zorder=1))

    def label(self, x, y, s, css_size, colour, bold=False, ha="center"):
        self.ax.text(x, y, s, color=colour, ha=ha, va="center", zorder=3,
                     fontsize=css_size * PT_PER_CSS,
                     fontfamily=FAMILY, fontweight="bold" if bold else "normal")

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=DPI, facecolor=fe.BG,
                         pad_inches=0, bbox_inches=None)
        plt.close(self.fig)


def table_height(entries: list) -> float:
    return GAP + HEADER_H + GAP + (ROW_H + GAP) * max(len(entries), 1)


def draw_table(c: Canvas, y: float, col2_header: str, entries: list,
               returns: dict, widths: list) -> float:
    """Draw one table starting at `y`; returns the y below it."""
    headers = ("Stock", col2_header, "3 months", "6 months", "1 year")

    # The grid is a filled block behind the cells, with the cells inset by
    # GAP - exactly how the HTML draws it with bgcolor and cellspacing.
    total_h = table_height(entries)
    c.rect(0, y, CSS_W, total_h, fe.BORDER)

    # Every internal y is relative to `y`, the table's own top. Taking these
    # from the canvas origin instead drew all three tables on top of one
    # another, with only their backgrounds in the right place.
    def row(y0, h, cells):
        x = GAP
        for (content, colour, size, bold), w in zip(cells, widths):
            c.rect(x, y0, w, h, fe.BG)
            avail = w - PAD_X * 2
            if isinstance(content, tuple):        # ticker + company
                ticker_company = content
                ticker, company = plain(ticker_company[0]), plain(ticker_company[1])
                t, ts = fit(ticker, avail, TICKER_SIZE, True)
                c.label(x + w / 2, y0 + h / 2 - 6, t, ts, fe.INK, True)
                if company:
                    n, ns = fit(company, avail, COMPANY_SIZE)
                    c.label(x + w / 2, y0 + h / 2 + 7, n, ns, fe.MUTED)
            else:
                s, sz = fit(plain(content), avail, size, bold)
                c.label(x + w / 2, y0 + h / 2, s, sz, colour, bold)
            x += w + GAP

    row(y + GAP, HEADER_H,
        [(h, fe.INK, HEADER_SIZE, True) for h in headers])

    y0 = y + GAP + HEADER_H + GAP
    if not entries:
        # One cell across the full width, as the HTML's colspan=5 does.
        c.rect(GAP, y0, CSS_W - GAP * 2, ROW_H, fe.BG)
        c.label(CSS_W / 2, y0 + ROW_H / 2, "None", DATA_SIZE, fe.INK)
    else:
        for e in entries:
            r = returns.get(e["ticker"], {})
            company = fe.short_company(e["company"]) if e.get("company") else ""
            if company == e["ticker"]:
                company = ""
            cells = [((e["ticker"], company), fe.INK, TICKER_SIZE, True),
                     (e["col2"], e.get("col2_colour", fe.INK), DATA_SIZE, False)]
            for h in fe.HORIZONS:
                v = r.get(h)
                if not fe._usable(v):
                    cells.append(("n/a", fe.MUTED, HEADER_SIZE, False))
                else:
                    cells.append((fe.whole_pct(v),
                                  fe.GREEN if v >= 0 else fe.RED,
                                  HEADER_SIZE, False))
            row(y0, ROW_H, cells)
            y0 += ROW_H + GAP

    return y + total_h


def render(buckets: dict, returns: dict, out: Path) -> Path:
    """Write the three tables to `out` as one PNG."""
    sections = [("EARNINGS COUNTDOWN", "Earnings Date", buckets["earnings"]),
                ("SMA CROSS  (50 day vs. 200 day)", "Cross", buckets["sma"]),
                ("PRICE MOVEMENT  (+/- 10%)", "% Change Today", buckets["price"])]

    # No gap below the last table, or the image carries a dead strip.
    height = (sum(TITLE_H + table_height(e) for _, _, e in sections)
              + SECTION_GAP * (len(sections) - 1))
    c = Canvas(height)
    widths = col_widths()

    y = 0.0
    for title, col2, entries in sections:
        c.label(0, y + TITLE_H / 2, title, 12, fe.BLUE, bold=True, ha="left")
        y = draw_table(c, y + TITLE_H, col2, entries, returns, widths)
        y += SECTION_GAP

    c.save(out)
    return out


def main() -> None:
    import argparse
    import datetime

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()

    # Standalone: read the committed triggers, skip the network.
    buckets, tickers, as_of = fe.collect()
    returns = fe.fetch_returns(as_of, offline=True)
    render(buckets, returns, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
