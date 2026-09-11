#!/usr/bin/env python3
"""Email one built dashboard (markdown analysis + PNG attachment).

Used by the Claude Routine dashboard path. The GitHub Actions path emails via
dawidd6/action-send-mail instead; this is the standalone equivalent for
environments that have no such action available.

Credentials come from the environment:
  SMTP_USERNAME  - the Gmail address that sends (same one GitHub Actions uses)
  SMTP_PASSWORD  - that account's Google app password
"""

import argparse
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
DEFAULT_RECIPIENT = "RQHNetworks@outlook.com"


def render_html(md_text: str) -> str:
    try:
        import markdown
    except ImportError:
        raise SystemExit(
            "The 'markdown' package is required to render the analysis as HTML.\n"
            "Install it first:  pip install markdown"
        )
    return markdown.markdown(md_text, extensions=["extra", "sane_lists"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--date", required=True, help="Trigger date, YYYY-MM-DD")
    p.add_argument("--triggers", required=True,
                   help="Comma-separated trigger types, e.g. sma_cross,price_swing")
    p.add_argument("--md", required=True, type=Path, help="Path to the markdown analysis")
    p.add_argument("--png", required=True, type=Path, help="Path to the dashboard PNG")
    p.add_argument("--to", default=os.environ.get("DASHBOARD_RECIPIENT", DEFAULT_RECIPIENT))
    args = p.parse_args()

    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    if not username or not password:
        raise SystemExit("SMTP_USERNAME and SMTP_PASSWORD must be set in the environment.")

    for path in (args.md, args.png):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")

    md_text = args.md.read_text()

    msg = EmailMessage()
    msg["Subject"] = f"[{args.date}] [{args.ticker}] [{args.triggers}]"
    msg["From"] = f"Watchlist Monitor <{username}>"
    msg["To"] = args.to
    msg.set_content(md_text)
    msg.add_alternative(render_html(md_text), subtype="html")

    msg.add_attachment(
        args.png.read_bytes(),
        maintype="image",
        subtype="png",
        filename=args.png.name,
    )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)

    print(f"Sent {args.ticker} dashboard to {args.to}")


if __name__ == "__main__":
    main()
