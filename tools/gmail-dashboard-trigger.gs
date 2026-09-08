/**
 * Gmail Apps Script bridge: reply to a "Watchlist Triggers" flag email with
 * one of its trigger IDs (e.g. LULU_price_swing_2026-09-04) to have this
 * script call GitHub's API and kick off build-dashboard-on-demand.yml for
 * that trigger.
 *
 * This file lives in the repo for reference/version control only - it is
 * NOT executed by GitHub Actions. Copy it into a Google Apps Script project
 * bound to the Gmail account that SENDS the watchlist emails (the
 * SMTP_USERNAME address), then set it up on a time-driven trigger.
 *
 * Required script properties (Project Settings -> Script Properties):
 *   GITHUB_TOKEN  - a fine-grained PAT scoped to this repo only,
 *                   with "Actions: Read and write" permission
 *   GITHUB_OWNER  - e.g. "RQHNetworks"
 *   GITHUB_REPO   - e.g. "watchlist"
 *   BOT_EMAIL     - the Gmail address this script runs as (the same
 *                   address as the SMTP_USERNAME secret) - used to tell
 *                   the bot's own sent mail apart from a real reply
 */

function checkForDashboardRequests() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');
  const owner = props.getProperty('GITHUB_OWNER');
  const repo = props.getProperty('GITHUB_REPO');
  const botEmail = props.getProperty('BOT_EMAIL');
  if (!token || !owner || !repo || !botEmail) {
    throw new Error('Missing one of GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO / BOT_EMAIL script properties.');
  }

  const lastCheckStr = props.getProperty('LAST_CHECK_TS');
  const lastCheckTs = lastCheckStr ? parseInt(lastCheckStr, 10) : (Date.now() - 24 * 60 * 60 * 1000);
  const runStartTs = Date.now();

  Logger.log('Run start: ' + new Date(runStartTs) + ' | lastCheckTs: ' + new Date(lastCheckTs));

  const idPattern = /\b([A-Za-z0-9.]+_(?:sma_cross|price_swing|earnings_countdown)_\d{4}-\d{2}-\d{2})\b/g;

  // Limit the search window so this stays fast on every poll.
  const searchQuery = 'subject:"Watchlist Triggers" newer_than:7d';
  const threads = GmailApp.search(searchQuery, 0, 50);
  Logger.log('Search "' + searchQuery + '" found ' + threads.length + ' thread(s).');

  const seenIds = new Set();

  threads.forEach(function (thread) {
    const messages = thread.getMessages();
    Logger.log('Thread "' + thread.getFirstMessageSubject() + '" has ' + messages.length + ' message(s).');

    messages.forEach(function (message) {
      const msgTs = message.getDate().getTime();
      const from = message.getFrom();

      if (msgTs <= lastCheckTs) {
        Logger.log('  SKIP (already handled): from=' + from + ' date=' + message.getDate());
        return;
      }
      if (from.indexOf(botEmail) !== -1) {
        Logger.log('  SKIP (bot\'s own mail): from=' + from + ' date=' + message.getDate());
        return;
      }

      const body = message.getPlainBody();
      Logger.log('  CONSIDERING reply: from=' + from + ' date=' + message.getDate() +
        ' bodyLength=' + body.length + ' bodySnippet=' + body.substring(0, 200).replace(/\n/g, ' \\n '));

      let match;
      let foundAny = false;
      while ((match = idPattern.exec(body)) !== null) {
        seenIds.add(match[1]);
        foundAny = true;
      }
      if (!foundAny) {
        Logger.log('  No trigger ID found in this message body.');
      }
    });
  });

  Logger.log('Trigger IDs found this run: ' + (seenIds.size ? Array.from(seenIds).join(', ') : '(none)'));

  seenIds.forEach(function (id) {
    dispatchDashboardBuild(owner, repo, token, id);
  });

  props.setProperty('LAST_CHECK_TS', String(runStartTs));
}

function dispatchDashboardBuild(owner, repo, token, triggerFile) {
  const url = 'https://api.github.com/repos/' + owner + '/' + repo +
    '/actions/workflows/build-dashboard-on-demand.yml/dispatches';
  const payload = {
    ref: 'main',
    inputs: { trigger_file: triggerFile }
  };
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  const code = response.getResponseCode();
  if (code !== 204) {
    Logger.log('Failed to dispatch for ' + triggerFile + ': ' + code + ' ' + response.getContentText());
  } else {
    Logger.log('Dispatched dashboard build for ' + triggerFile);
  }
}
