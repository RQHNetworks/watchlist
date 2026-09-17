#!/usr/bin/env python3
"""Build the "Watchlist Triggers Notes" newsletter as HTML.

A second email that reproduces the Market Movers Report's tables and adds a
short write-up per ticker beneath them. It is generated AFTER the report is
sent, so nothing here can delay or break that email.

Everything is computed or quoted - there is no model in this path and no API
cost. That constrains the prose: every sentence states arithmetic or names a
source. It deliberately does not say what a number means, because inferring
"this news will move the stock" is exactly the judgement a deterministic
script cannot make, and a template that pretends to would be worse than
silence. Headlines are listed with their dates and left to the reader.

Tables, colours, return maths and name shortening are imported from
flag_email rather than copied, so the two emails cannot drift apart.
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flag_email as fe  # noqa: E402  (path set above)

SLOT = "#9aa0a6"
MAX_HEADLINES = 3
# A five-month-old headline is not "recent news" for a company about to
# report. Without a window the provider's ordering is the only filter,
# and stale items surface on quiet symbols.
EARNINGS_NEWS_DAYS = 30

SMA_RE = re.compile(r"50-day=([\d.]+), 200-day=([\d.]+)")
SWING_RE = re.compile(r"close ([\d.]+) -> ([\d.]+)")


def money(v) -> str:
    """Scale a raw statement figure to B/M, or n/a."""
    if v is None:
        return "n/a"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.0f}M"
    return f"{sign}${a:,.0f}"


def yoy(cur, prior) -> str:
    if cur is None or prior is None:
        return ""
    try:
        cur, prior = float(cur), float(prior)
    except (TypeError, ValueError):
        return ""
    if prior == 0:
        return ""
    pct = cur / prior - 1
    # A sign flip makes a percentage change meaningless - the blueprint's
    # comparability rule. Say so rather than printing a number.
    if (cur < 0) != (prior < 0):
        return " (sign change YoY, so no meaningful growth rate)"
    colour = fe.GREEN if pct >= 0 else fe.RED
    return f' (<span style="color:{colour};">{pct:+.1%}</span> YoY)'


def _row(df, *names):
    """First matching row label in a yfinance statement frame."""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def fundamentals(t) -> dict:
    """TTM revenue and free cash flow, against the prior four quarters.

    FCF is operating cash flow minus capital expenditure. That is not always
    a company's own headline definition - some also deduct finance-lease
    principal - so the footer names the basis rather than implying it is the
    company's figure.
    """
    out = {"ok": False}
    try:
        qi = t.quarterly_income_stmt
        qc = t.quarterly_cashflow
        rev = _row(qi, "Total Revenue", "TotalRevenue", "Operating Revenue")
        ocf = _row(qc, "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = _row(qc, "Capital Expenditure", "Capital Expenditures")
        if rev is None or ocf is None:
            return out

        def window(series, lo, hi):
            vals = [v for v in series.iloc[lo:hi].tolist() if v == v]  # drop NaN
            return sum(vals) if len(vals) == (hi - lo) else None

        out["rev_ttm"] = window(rev, 0, 4)
        out["rev_prior"] = window(rev, 4, 8)
        o_ttm, o_prior = window(ocf, 0, 4), window(ocf, 4, 8)
        if capex is not None:
            c_ttm, c_prior = window(capex, 0, 4), window(capex, 4, 8)
        else:
            c_ttm = c_prior = 0.0
        # yfinance reports capex as a negative number already; adding it is
        # the subtraction. Guard against a provider that flips the sign.
        out["fcf_ttm"] = None if o_ttm is None or c_ttm is None else o_ttm - abs(c_ttm)
        out["fcf_prior"] = (None if o_prior is None or c_prior is None
                            else o_prior - abs(c_prior))
        out["ok"] = out["rev_ttm"] is not None
    except Exception as e:
        fe.log(f"WARNING: fundamentals failed: {type(e).__name__}: {e}")
    return out


def earnings_record(t, as_of: date) -> dict:
    """Beat/miss over the last four reported quarters, plus the next estimate."""
    out = {"past": [], "next_est": None}
    try:
        df = t.get_earnings_dates(limit=16)
        if df is None or df.empty:
            return out
        est = next((c for c in df.columns if "Estimate" in c), None)
        rep = next((c for c in df.columns if "Reported" in c), None)
        if est is None or rep is None:
            return out
        import pandas as pd
        cutoff = pd.Timestamp(as_of)
        idx = df.index
        naive = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx

        for when, e, r in sorted(zip(naive, df[est], df[rep])):
            if when > cutoff:
                if out["next_est"] is None and e == e:
                    out["next_est"] = (when.date(), float(e))
                continue
            if e == e and r == r:
                out["past"].append((when.date(), float(e), float(r)))
        out["past"] = out["past"][-4:]
    except Exception as e:
        fe.log(f"WARNING: earnings record failed: {type(e).__name__}: {e}")
    return out


def headlines(t, limit: int = MAX_HEADLINES, since: date | None = None) -> list:
    """(date, title, url) triples. Schema-tolerant: yfinance has moved these
    keys between releases, and a headline block is not worth crashing over."""
    out = []
    try:
        items = t.news or []
    except Exception as e:
        fe.log(f"WARNING: news fetch failed: {type(e).__name__}: {e}")
        return out

    for it in items:
        c = it.get("content", it) if isinstance(it, dict) else {}
        title = c.get("title") or it.get("title")
        if not title:
            continue
        url = ""
        for key in ("canonicalUrl", "clickThroughUrl"):
            v = c.get(key)
            if isinstance(v, dict) and v.get("url"):
                url = v["url"]
                break
        url = url or c.get("link") or it.get("link") or ""

        when = None
        raw = c.get("pubDate") or c.get("displayTime")
        if raw:
            try:
                when = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
            except ValueError:
                when = None
        if when is None:
            ts = it.get("providerPublishTime") or c.get("providerPublishTime")
            if ts:
                try:
                    when = datetime.utcfromtimestamp(int(ts)).date()
                except (ValueError, OSError):
                    when = None
        if since and when and when < since:
            continue
        out.append((when, title, url))
        if len(out) >= limit:
            break
    return out


def news_bullet(items: list, label: str) -> str:
    if not items:
        return (f'<b>{label}:</b> <span style="color:{SLOT};">no recent '
                f'headlines returned for this symbol.</span>')
    parts = []
    for when, title, url in items:
        d = f"{when:%b %d} — " if when else ""
        parts.append(f'<a href="{url}" style="color:{fe.BLUE};">{title}</a>'
                     if url else title)
        parts[-1] = d + parts[-1]
    return f"<b>{label}:</b><br>" + "<br>".join(parts)


def trend_clause(r3, r6, r12, lead: str = "the stock ") -> str:
    """Full clause including its leading space, or empty.

    Returning a bare adjective left "the stock ." dangling whenever the
    returns were unavailable, so the caller cannot be trusted to guard it.
    """
    body = trend_phrase(r3, r6, r12)
    return f" — {lead}{body}" if body else ""


def trend_phrase(r3, r6, r12) -> str:
    if r3 is None or r12 is None:
        return ""
    if r12 >= 0 and r3 < 0:
        return "has given back part of the year's gain over the last quarter"
    if r12 >= 0 and r3 >= 0:
        return "is up across both the quarter and the year"
    if r12 < 0 and r3 < 0:
        return "is down over every window shown"
    return "is up over the quarter despite a negative year"


def pct(v) -> str:
    """fetch_returns yields decimals, so format with % - not :+.2f plus a
    literal sign. Getting that wrong prints -0.11% where the table above says
    -11.05%, i.e. two numbers for the same thing in the same email."""
    return "n/a" if v is None else f"{v:+.2%}"


def earnings_bullets(e, ret, fund, earn) -> list:
    r3, r6, r12 = (ret.get(3), ret.get(6), ret.get(12))
    b = []

    b.append(f"<b>Price:</b> {pct(r12)} over 12 months, {pct(r6)} over 6 and "
             f"{pct(r3)} over 3{trend_clause(r3, r6, r12)}.")

    if fund.get("ok"):
        b.append(f"<b>Revenue &amp; FCF:</b> trailing-four-quarter revenue "
                 f"{money(fund.get('rev_ttm'))}{yoy(fund.get('rev_ttm'), fund.get('rev_prior'))}; "
                 f"free cash flow {money(fund.get('fcf_ttm'))}"
                 f"{yoy(fund.get('fcf_ttm'), fund.get('fcf_prior'))}.")
    else:
        b.append('<b>Revenue &amp; FCF:</b> <span style="color:%s;">quarterly '
                 'statements not available for this symbol.</span>' % SLOT)

    past, nxt = earn.get("past"), earn.get("next_est")
    if past:
        beats = sum(1 for _, est, rep in past if rep >= est)
        seq = ", ".join(
            f'{w:%b %Y} <span style="color:{fe.GREEN if rep >= est else fe.RED};">'
            f'{"beat" if rep >= est else "miss"}</span> ({rep:.2f} vs {est:.2f} est)'
            for w, est, rep in past)
        tail = (f' Next report: consensus {nxt[1]:.2f} for {nxt[0]:%b %d}.'
                if nxt else "")
        b.append(f"<b>Earnings:</b> {beats} of {len(past)} recent quarters beat — "
                 f"{seq}.{tail}")
    elif nxt:
        b.append(f"<b>Earnings:</b> no reported history returned; consensus for "
                 f"{nxt[0]:%b %d} is {nxt[1]:.2f}.")
    else:
        b.append('<b>Earnings:</b> <span style="color:%s;">no estimate or actual '
                 'history returned.</span>' % SLOT)

    return b


def sma_bullets(e, ret) -> list:
    r3, r6, r12 = (ret.get(3), ret.get(6), ret.get(12))
    b = []
    m = SMA_RE.search(e.get("detail", ""))
    golden = e.get("detail", "").startswith("golden")
    word = "Golden" if golden else "Death"

    if m:
        s50, s200 = float(m.group(1)), float(m.group(2))
        gap = abs(s50 - s200) / s200 if s200 else 0.0
        b.append(f"<b>{word} cross:</b> the 50-day sits at <b>{s50:,.2f}</b> against "
                 f"a 200-day of <b>{s200:,.2f}</b> — <b>{gap:.2%}</b> apart"
                 + (", inside half a percent." if gap < 0.005 else "."))
    else:
        b.append(f"<b>{word} cross</b> confirmed on the trigger date.")

    windows = [(abs(v), n) for v, n in ((r3, "3-month"), (r6, "6-month"),
                                        (r12, "12-month")) if v is not None]
    if not windows:
        b.append('<b>Trend into it:</b> <span style="color:%s;">trailing returns '
                 'unavailable for this symbol.</span>' % SLOT)
    elif windows:
        _, biggest = max(windows)
        b.append(f"<b>Trend into it:</b> {pct(r3)} over 3 months, {pct(r6)} over 6 "
                 f"and {pct(r12)} over 12. The {biggest} window holds the largest "
                 f"move of the three, so that is the leg doing most of the work on "
                 f"the averages.")
    return b


def price_bullets(e, ret) -> list:
    r3, r6, r12 = (ret.get(3), ret.get(6), ret.get(12))
    b = []
    m = SWING_RE.search(e.get("detail", ""))
    move = e.get("col2", "")
    if m:
        b.append(f"<b>Move:</b> {move} in one session, {float(m.group(1)):,.2f} → "
                 f"{float(m.group(2)):,.2f}. Against {pct(r3)} over 3 months and "
                 f"{pct(r12)} over 12{trend_clause(r3, r6, r12)}.")
    else:
        b.append(f"<b>Move:</b> {move} in one session; {pct(r12)} over 12 months.")
    return b


def writeup(title: str, bullets: list) -> str:
    lis = "".join(f'<li style="color:{fe.INK};font:13px {fe.FONT};'
                  f'margin:0 0 6px 0;line-height:1.5;">{x}</li>' for x in bullets)
    return (f'<div style="color:{fe.INK};font:bold 13px {fe.FONT};'
            f'margin:18px 0 2px 0;">{title}</div>'
            f'<ul style="margin:4px 0 0 0;padding-left:20px;">{lis}</ul>')


def render(buckets, returns, funds, earns, news, report_date: date) -> str:
    body = [
        f'<div style="color:{fe.INK};font:bold 13px {fe.FONT};margin:0 0 10px 0;">'
        f'Watchlist Triggers Notes: {report_date.strftime("%m/%d/%Y")}</div>',

        fe.section("EARNINGS COUNTDOWN"),
        fe.table("Earnings Date", buckets["earnings"], returns),
        fe.section("SMA CROSS", "(50 day vs. 200 day)"),
        fe.table("Cross", buckets["sma"], returns),
        fe.section("PRICE MOVEMENT", "(+/- 10%)"),
        fe.table("% Change Today", buckets["price"], returns),

        f'<div style="border-top:1px solid #3d3d3d;margin:30px 0 0 0;'
        f'padding-top:6px;"></div>',
    ]

    blocks = (
        ("NOTES — EARNINGS COUNTDOWN", "earnings"),
        ("NOTES — SMA CROSS", "sma"),
        ("NOTES — PRICE MOVEMENT", "price"),
    )
    for heading, key in blocks:
        entries = buckets[key]
        if not entries:
            continue
        body.append(fe.section(heading))
        for e in entries:
            t = e["ticker"]
            ret = returns.get(t, {})
            title = fe.stock_label(e).replace(f"{t} (", f"{t} — ").rstrip(")")
            if key == "earnings":
                bl = earnings_bullets(e, ret, funds.get(t, {}), earns.get(t, {}))
                bl.append(news_bullet(news.get(t, []), "News"))
            elif key == "sma":
                bl = sma_bullets(e, ret)
            else:
                bl = price_bullets(e, ret)
                bl.append(news_bullet(news.get(t, []), "Around the move"))
            body.append(writeup(title, bl))

    body.append(
        f'<div style="color:{fe.MUTED};font:12px {fe.FONT};margin:28px 0 0 0;'
        f'border-top:1px solid #3d3d3d;padding-top:12px;">'
        f'Every figure above is computed from daily closes and the company\'s own '
        f'quarterly statements, or quoted from a dated headline. Free cash flow is '
        f'operating cash flow minus capital expenditure, which is not always a '
        f'company\'s own headline definition. Headlines are listed with their dates '
        f'and are not interpreted. Not investment advice.</div>')

    return (
        f'<html><body style="margin:0;padding:0;background-color:{fe.BG};">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'bgcolor="{fe.BG}" style="background-color:{fe.BG};">'
        f'<tr><td style="padding:22px 24px;">{"".join(body)}</td></tr>'
        f'</table></body></html>'
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--date", help="Report date YYYY-MM-DD; defaults to today.")
    p.add_argument("--offline", action="store_true",
                   help="Skip every network fetch. For testing without egress.")
    args = p.parse_args()

    report_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                   if args.date else date.today())

    buckets, tickers, as_of = fe.collect()
    returns = fe.fetch_returns(as_of, offline=args.offline)

    funds, earns, news = {}, {}, {}
    if not args.offline:
        try:
            import yfinance as yf
        except ImportError as e:
            fe.log(f"WARNING: {e}; notes will degrade to price-only")
            yf = None

        if yf is not None:
            earn_tickers = {e["ticker"] for e in buckets["earnings"]}
            px_tickers = {e["ticker"] for e in buckets["price"]}
            # Fundamentals are fetched only for earnings tickers, and headlines
            # only where a write-up quotes them - never for the whole watchlist.
            for t in sorted(earn_tickers | px_tickers):
                try:
                    obj = yf.Ticker(t)
                except Exception as e:
                    fe.log(f"WARNING: {t}: {type(e).__name__}: {e}")
                    continue
                if t in earn_tickers:
                    trig = datetime.strptime(as_of[t], "%Y-%m-%d").date()
                    funds[t] = fundamentals(obj)
                    earns[t] = earnings_record(obj, trig)
                    news[t] = headlines(
                        obj, since=trig - timedelta(days=EARNINGS_NEWS_DAYS))
                else:
                    trig = datetime.strptime(as_of[t], "%Y-%m-%d").date()
                    # A swing is explained by what was published around it, so
                    # the window opens the day before the trigger.
                    news[t] = headlines(obj, since=trig - timedelta(days=1))
                fe.log(f"  notes {t:<6s} fundamentals="
                       f"{'ok' if funds.get(t, {}).get('ok') else '-'} "
                       f"earnings={len(earns.get(t, {}).get('past', []))}q "
                       f"headlines={len(news.get(t, []))}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(buckets, returns, funds, earns, news, report_date))

    print(json.dumps({
        "date": report_date.strftime("%Y-%m-%d"),
        "tickers": ",".join(sorted(set(tickers))),
        "count": len(tickers),
    }))


if __name__ == "__main__":
    main()
