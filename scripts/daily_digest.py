#!/usr/bin/env python3
"""Daily pre-market digest.

Uses the Anthropic Messages API with the server-side web_search tool to
research the morning's market picture (futures, headlines, Trump/policy watch,
calendar, stocks in focus), then emails a formatted digest.

Required env: ANTHROPIC_API_KEY, EMAIL_TO, and one email method
(RESEND_API_KEY  OR  GMAIL_ADDRESS + GMAIL_APP_PASSWORD).
Optional env: ANTHROPIC_MODEL, EMAIL_FROM.
"""
import os
import sys
import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emailer import send_email, wrap_html

API_URL = "https://api.anthropic.com/v1/messages"
# Dated model IDs are most reliable on new API keys; override via ANTHROPIC_MODEL.
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"

TODAY = datetime.datetime.now().strftime("%A, %B %d, %Y")

SYSTEM = (
    "You are an equity and options markets research assistant producing a concise "
    "pre-market email digest for an active US retail trader (Eastern time) who "
    "focuses on individual stocks and options. Be factual, specific, and current. "
    "Use the web_search tool to gather TODAY's actual information before writing; "
    "never rely on memory for time-sensitive figures, prices, or moves. Prioritize "
    "concrete single-name catalysts over broad macro commentary. Do NOT give buy/sell "
    "recommendations, your own price targets, or position-sizing advice — report what "
    "happened and explain why it may matter to a stock or its options. Keep a neutral, "
    "un-hyped tone and cite sources."
)

PROMPT = f"""Today is {TODAY}. Research and write my pre-market trading digest, leading with single-stock and options catalysts. Use real, current figures and name specific tickers throughout.

1. Stocks in focus (lead with this) — the names moving most in pre-market and WHY: earnings beats/misses and guidance, analyst upgrades/downgrades and price-target changes, M&A, product or contract news, FDA/legal/regulatory events. For each: ticker, the pre-market move if known, and a one-line catalyst.

2. Options watch — names with notable options activity or setups today: unusual options volume or flow, elevated implied volatility, expected post-earnings moves, and any major events that could drive premium. Name tickers; explain the setup, not a trade to make.

3. Trump / policy watch — anything President Trump said or posted (Truth Social, statements, executive actions) or administration policy news (tariffs, trade, the Fed, named companies or sectors) in the last ~24h, mapped to the specific tickers or sectors that may react. If nothing notable, say so plainly.

4. Earnings & economic calendar — notable companies reporting today (before/after the bell) and key data releases, with times in ET.

5. Market snapshot (brief) — S&P 500, Nasdaq, Dow futures and overnight direction; 10Y Treasury yield, oil, gold, Bitcoin if notable. Keep this to a few lines.

Format the body as clean, simple HTML using only <h3>, <p>, <ul>/<li>, and <strong> — no <html>/<head>/<body> wrapper, no inline CSS, no images. Keep it scannable, under ~800 words. Make the very first line a one-sentence plain summary wrapped in <p><strong>...</strong></p>. End with a short <em>italic</em> line noting this is automated news, not financial advice."""


def _require_env(*names: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        msg = f"Missing required env var(s): {', '.join(missing)}"
        print(f"::error title=Config::{msg}", file=sys.stderr)
        raise RuntimeError(msg)


def build_digest() -> str:
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 8,
        }],
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=300)
    if resp.status_code != 200:
        print("API said:", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def main():
    _require_env("EMAIL_TO")
    if not os.environ.get("RESEND_API_KEY") and not os.environ.get("GMAIL_APP_PASSWORD"):
        msg = "No email method configured. Set RESEND_API_KEY or GMAIL_APP_PASSWORD."
        print(f"::error title=Config::{msg}", file=sys.stderr)
        raise RuntimeError(msg)

    html = build_digest()
    if not html:
        msg = "Model returned no text."
        print(f"::error title=Anthropic API::{msg}", file=sys.stderr)
        sys.exit(1)
    subject = f"\U0001F4C8 Pre-Market Digest \u2014 {datetime.datetime.now():%b %d}"
    try:
        send_email(
            subject,
            wrap_html(html, "Pre-Market Digest"),
            text_body="Your pre-market digest is ready. Open in an HTML email client.",
        )
    except Exception as exc:
        print(f"::error title=Email::{exc}", file=sys.stderr)
        raise
    print("Digest sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal: {exc}", file=sys.stderr)
        sys.exit(1)
