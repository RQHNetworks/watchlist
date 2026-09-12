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
| Commits to     | `main`                                           | `claude/routine-dashboards` branch only    |

Output filenames deliberately differ so the two paths never overwrite each
other, and so a side-by-side comparison of the same trigger is possible. They
also land on different branches: this path commits only to
`claude/routine-dashboards` and never to `main`, so nothing it does can disturb
the existing pipeline while both are running.

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

Work in the RQHNetworks/watchlist repository.

STEP 0 - SET UP THE WORKING BRANCH
This path never commits to main. It owns the branch claude/routine-dashboards.
Run exactly this, which resumes that branch if it exists and creates it from
main on the first run, then brings in today's triggers either way:

  git fetch origin
  git checkout -B claude/routine-dashboards origin/claude/routine-dashboards \
    || git checkout -B claude/routine-dashboards origin/main
  git merge origin/main --no-edit

The merge matters: triggers/ is committed to main by the GitHub Actions monitor,
so without it you would be working against a stale queue. Branches prefixed with
claude/ are always accepted on push, whereas a push to main is rejected when the
branch carries commits authored by someone else - and main carries commits from
the GitHub Actions bot, so pushing there would fail.

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
For each ticker, if dashboards/routine/<TICKER>_<DATE>.png already exists on the
claude/routine-dashboards branch you checked out in STEP 0, that ticker is
already done - skip it silently. Without this check a re-fire rebuilds
everything and burns quota for no reason.

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
Commit the new files in dashboards/routine/ and push them to the working branch:

  git push -u origin claude/routine-dashboards

Never push to main. If the push fails, say so explicitly in your summary - the
emails will already have gone out, but a failed push breaks the STEP 3 guard and
the next run would rebuild the same dashboards.

Finish with a short summary: which tickers you built, which you skipped as
already done, and anything that failed and why.

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

Create the Routine from the web form at
[claude.ai/code/routines](https://claude.ai/code/routines) -> **New routine**:

| Field        | Value                                                        |
| ------------ | ------------------------------------------------------------ |
| Name         | Daily watchlist dashboards                                   |
| Instructions | the prompt block above                                       |
| Repositories | `RQHNetworks/watchlist`                                      |
| Environment  | the open-egress environment from Prerequisites                |
| Trigger      | Schedule -> daily, 5:15 PM local (the form converts to UTC)  |
| Connectors   | remove all; this design needs none                            |

**Selecting the repository is not optional and is easy to miss.** A routine
clones the repositories listed on it at the start of every run. A routine
created without one produces a session with no clone, so it cannot read
`triggers/` or write `dashboards/routine/` — it will appear to run fine and
silently accomplish nothing. Two probe runs were lost this way: the run status
showed SUCCEEDED both times, because that status only means the session started
and exited without an infrastructure error, not that the task succeeded.

Note that Claude pushes to `claude/`-prefixed branches without restriction, so
committing to the project's working branch needs no extra permission.

Creating routines programmatically (for example via an MCP `create_trigger`
tool) is not equivalent: that path has no repositories parameter, and produces
exactly the repo-less sessions described above.

## Deprecating the old path later

Nothing here depends on the Apps Script or `build-dashboard-on-demand.yml`. When
this path has proven out, those can be retired independently: delete the Apps
Script trigger, then the workflow file. The daily monitor
(`watchlist-monitor.yml`) stays either way — it is what produces `triggers/`.
