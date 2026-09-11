# Claude Routine dashboard path (parallel to the GitHub Actions path)

A second, independent way to turn watchlist triggers into dashboards. It runs
**alongside** the existing GitHub Actions path, which is untouched, so both can
be exercised on the same triggers and compared before either is retired.

## How it differs from the existing path

|                | Existing path                                    | This path                                  |
| -------------- | ------------------------------------------------ | ------------------------------------------ |
| What selects   | You reply to a flag email with a trigger ID      | Every ticker that triggered that day       |
| Granularity    | One dashboard per trigger ID                     | One dashboard per **unique ticker**        |
| Glue           | Gmail Apps Script -> GitHub `workflow_dispatch`  | Claude Routine reads `triggers/` directly  |
| Build host     | GitHub Actions runner (`claude-code-action`)     | Claude Routine session                     |
| Billed as      | Anthropic API credits                            | Claude plan usage                          |
| Output         | `dashboards/<TICKER>_<TYPE>_<DATE>.png`          | `dashboards/routine/<TICKER>_<DATE>.png`   |

Output filenames deliberately differ so the two paths never overwrite each
other, and so a side-by-side comparison of the same trigger is possible.

## Why this path needs no email at all

`watchlist_monitor.py` already writes the complete, filled-in dashboard prompt
into `triggers/<TICKER>_<TYPE>_<DATE>.txt` on every run, and `run_once()` wipes
and recreates `triggers/` each time. That directory is therefore an accurate,
self-cleaning work queue for exactly the current run — strictly better as an
input than parsing it back out of an email.

## Prerequisites

**1. An environment with outbound access to financial data sources.**
This is the blocker as of this writing. In the default environment, price data
is refused at the proxy:

```
connect_rejected  gateway answered 403 to CONNECT  query2.finance.yahoo.com:443
connect_rejected  gateway answered 403 to CONNECT  fc.yahoo.com:443
```

A Routine firing in such an environment cannot build anything. The network
policy is chosen when a Claude Code environment is created, so this path needs
an environment provisioned with egress to the finance domains. Point the
Routine at that environment's `environment_id`.

**2. SMTP credentials as environment variables** on that environment, since a
Routine session has no Gmail connector:

- `SMTP_USERNAME` — the sending Gmail address (same one GitHub Actions uses)
- `SMTP_PASSWORD` — that account's Google app password
- `DASHBOARD_RECIPIENT` — optional; defaults to `RQHNetworks@outlook.com`

**3. Schedule.** The monitor runs at 20:30 UTC and takes about 7 minutes, so
fire this daily at **21:15 UTC** — after triggers are committed, not polling.
Re-fires are harmless because of the idempotency check below.

## The Routine prompt

Each firing starts a fresh session, so this is written to stand alone.

```text
Build dashboards for today's watchlist triggers.

Work in the RQHNetworks/watchlist repository. Start by pulling the latest main.

STEP 1 - VERIFY NETWORK, FAIL LOUDLY IF BLOCKED
Confirm you can actually reach financial data before doing anything else:
run a quick yfinance fetch for a single ticker (e.g. AAPL, 5 days of history).
If it fails with a proxy/403/connection error, STOP IMMEDIATELY. Do not attempt
any dashboard. Report that the environment lacks outbound access to financial
data and that this Routine cannot function until that is fixed. This is a real
and expected failure mode - report it clearly rather than working around it.

STEP 2 - BUILD THE WORK QUEUE
List triggers/*.txt, ignoring any file starting with no_triggers_. Each filename
is TICKER_TRIGGERTYPE_YYYY-MM-DD.txt, where TRIGGERTYPE is one of sma_cross,
price_swing, or earnings_countdown.

Group them BY TICKER. One dashboard per unique ticker, never one per trigger
file - if a ticker fired more than one trigger type on the same date, it still
gets exactly one dashboard, and you mention every one of its triggers in the
trigger-context section of that dashboard.

STEP 3 - IDEMPOTENCY GUARD, DO NOT SKIP
For each ticker, if dashboards/routine/<TICKER>_<DATE>.png already exists on
main, that ticker is already done - skip it silently. Without this check a
re-fire rebuilds everything and burns quota for no reason.

STEP 4 - BUILD
For each remaining ticker, read one of its triggers/*.txt files. That file
already contains the complete dashboard prompt with the ticker and company name
filled in - follow it as written. If the ticker had multiple trigger types,
adjust only the trigger-context line so it names all of them.

Save the results as:
  dashboards/routine/<TICKER>_<DATE>.png
  dashboards/routine/<TICKER>_<DATE>.md

STEP 5 - EMAIL EACH ONE
After each dashboard is built, email it:

  pip install markdown
  python3 routines/send_dashboard_email.py \
    --ticker <TICKER> --date <DATE> --triggers <comma-separated types> \
    --md dashboards/routine/<TICKER>_<DATE>.md \
    --png dashboards/routine/<TICKER>_<DATE>.png

SMTP_USERNAME and SMTP_PASSWORD come from the environment. If they are missing,
the script says so - report that rather than silently skipping delivery.

STEP 6 - COMMIT AND REPORT
Commit and push the new files in dashboards/routine/ to main. Finish with a
short summary: which tickers you built, which you skipped as already done, and
anything that failed and why.

CONSTRAINTS
- Do not modify .github/workflows/, watchlist_monitor.py, or
  tools/gmail-dashboard-trigger.gs. The existing GitHub Actions path must keep
  working untouched; this path runs alongside it during evaluation.
- Never write to dashboards/ at the top level - that belongs to the other path.
  This path owns dashboards/routine/ only.
- If a single ticker's build fails, continue with the remaining tickers and
  report the failure at the end. One bad ticker should not abort the run.
```

## Arming it

Once an open-egress environment exists, the Routine can be created directly —
it needs no connectors, so it does not have to be made from the claude.ai
Routines UI.

## Deprecating the old path later

Nothing here depends on the Apps Script or `build-dashboard-on-demand.yml`. When
this path has proven out, those can be retired independently: delete the Apps
Script trigger, then the workflow file. The daily monitor
(`watchlist-monitor.yml`) stays either way — it is what produces `triggers/`.
