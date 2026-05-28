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
import requests
from emailer import send_email, wrap_html

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

TODAY = datetime.datetime.now().strftime("%A, %B %d, %Y")

SYSTEM = (
    "You are a markets research assistant producing a concise pre-market email "
    "digest for a retail investor in the US (Eastern time). Be factual, specific, "
    "and current. Use the web_search tool to gather TODAY's actual information "
    "before writing; never rely on memory for time-sensitive figures. Do NOT give "
    "personalized buy/sell recommendations or position sizing — report the news and "
    "explain why it may matter to markets. Keep a neutral, un-hyped tone."
)

PROMPT = f"""Today is {TODAY}. Research and write my pre-market digest, with real figures and sources:

1. Market snapshot — US equity futures (S&P 500, Nasdaq, Dow) and overnight direction; major overseas markets; 10Y Treasury yield, crude oil, gold, and Bitcoin if notable.
2. Overnight & morning headlines — the few stories most likely to move US markets today.
3. Trump / policy watch — anything President Trump said or posted (Truth Social, statements, executive actions) or any administration policy news (tariffs, trade, the Fed, specific companies or sectors) in the last ~24h that markets may react to. If nothing notable, say so plainly.
4. Today's calendar — key economic data releases and notable earnings due today, with times in ET.
5. Stocks in focus — a handful of named tickers moving pre-market, each with a one-line reason.

Format the body as clean, simple HTML using only <h3>, <p>, <ul>/<li>, and <strong> — no <html>/<head>/<body> wrapper, no inline CSS, no images. Keep it scannable and under ~700 words. Make the very first line a one-sentence plain summary wrapped in <p><strong>...</strong></p>. End with a short <em>italic</em> line noting this is automated news, not financial advice."""


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
            "user_location": {
                "type": "approximate",
                "city": "Atlanta",
                "region": "Georgia",
                "country": "US",
                "timezone": "America/New_York",
            },
        }],
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    # Keep only final text blocks; skip server_tool_use / web_search_tool_result.
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def main():
    html = build_digest()
    if not html:
        print("ERROR: model returned no text.", file=sys.stderr)
        sys.exit(1)
    subject = f"\U0001F4C8 Pre-Market Digest \u2014 {datetime.datetime.now():%b %d}"
    send_email(
        subject,
        wrap_html(html, "Pre-Market Digest"),
        text_body="Your pre-market digest is ready. Open in an HTML email client.",
    )
    print("Digest sent.")


if __name__ == "__main__":
    main()
