#!/usr/bin/env python3
"""Intraday market catalyst scanner.

Runs every 20 min during pre-market and market hours. Uses Claude with live
web search to find NEW market-moving catalysts from the last ~25 minutes.
Emails ONLY when something breaks — completely silent otherwise.

Required env: ANTHROPIC_API_KEY, EMAIL_TO, and one email method.
Optional env:  ANTHROPIC_MODEL, WATCHLIST (comma-separated tickers to prioritize).
"""
import os
import sys
import json
import datetime
import requests
from emailer import send_email, wrap_html

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"

now     = datetime.datetime.now()
NOW_STR = now.strftime("%I:%M %p ET, %A %B %d, %Y")

# Tickers to watch extra closely (optional — set via WATCHLIST repo variable)
WATCHLIST = os.environ.get("WATCHLIST", "").strip()
watchlist_line = (
    f"Pay extra attention to these tickers and alert on any news for them: "
    f"{WATCHLIST}.\n" if WATCHLIST else ""
)

SYSTEM = (
    "You are a real-time market catalyst scanner for an active US options trader. "
    "Your ONLY job is to identify genuinely NEW, market-moving events published in "
    "the LAST 25 MINUTES. Use web_search to verify recency — do NOT report anything "
    "older than 25 minutes. Be extremely selective: only flag events a serious options "
    "trader would act on quickly. Miss nothing truly important; ignore everything "
    "routine. Return ONLY a JSON object — no preamble, no markdown fences, nothing else."
)

PROMPT = f"""Current time: {NOW_STR}.
Scan for market-moving catalysts published in the LAST 25 MINUTES ONLY.

{watchlist_line}
Search for and report ONLY events that meet ALL three criteria:
1. Published or confirmed within the last 25 minutes (verify timestamps)
2. Likely to move a stock or its options by 2%+ on the day
3. Not already widely known or fully priced in before this 25-min window

Categories to scan (in priority order):
- Earnings releases and EPS/revenue vs consensus, guidance changes
- Analyst upgrades/downgrades with significant price-target moves
- FDA approvals, rejections, or clinical trial results
- M&A — merger announcements, acquisition news, buyout rumors
- Major contract wins/losses (government, enterprise, defense)
- Trump Truth Social posts naming specific companies, sectors, or tariffs
- Unusual options flow spikes on a single name (large block, unusual size)
- Major legal, regulatory, or congressional decisions affecting a sector

Return ONLY this exact JSON (no other text whatsoever):
{{
  "has_alerts": true or false,
  "window_checked": "{NOW_STR}",
  "alerts": [
    {{
      "ticker": "TICKER (or N/A if macro)",
      "type": "earnings|analyst|fda|ma|contract|trump|options_flow|regulatory|other",
      "headline": "one crisp sentence with real numbers where available",
      "options_angle": "one sentence: what this means for IV, premium, or directional options",
      "urgency": "high or medium"
    }}
  ],
  "summary": "one sentence covering all alerts combined, or empty string if no alerts"
}}

If nothing new and market-moving happened in the last 25 minutes, return exactly:
{{"has_alerts": false, "alerts": [], "summary": "", "window_checked": "{NOW_STR}"}}"""


URGENCY_COLOR = {"high": "#c0392b", "medium": "#e67e22"}
URGENCY_EMOJI = {"high": "🚨", "medium": "⚡"}
TYPE_LABEL = {
    "earnings":     "Earnings",
    "analyst":      "Analyst Move",
    "fda":          "FDA",
    "ma":           "M&A",
    "contract":     "Contract",
    "trump":        "Trump / Policy",
    "options_flow": "Options Flow",
    "regulatory":   "Regulatory",
    "other":        "Breaking News",
}


def scan() -> dict:
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
            "user_location": {
                "type": "approximate",
                "city": "Atlanta",
                "region": "Georgia",
                "country": "US",
                "timezone": "America/New_York",
            },
        }],
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"API error: {resp.status_code} {resp.text}")
    resp.raise_for_status()

    txt = "".join(
        b.get("text", "") for b in resp.json().get("content", [])
        if b.get("type") == "text"
    ).strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(txt)
    except Exception as e:
        print(f"JSON parse error: {e}\nRaw output: {txt[:600]}")
        return {"has_alerts": False, "alerts": [], "summary": ""}


def build_email(result: dict) -> tuple[str, str]:
    alerts  = result.get("alerts", [])
    summary = result.get("summary", "")
    tickers = [a["ticker"] for a in alerts if a.get("ticker") and a["ticker"] != "N/A"]

    blocks = []
    for a in alerts:
        ticker        = a.get("ticker", "")
        urgency       = a.get("urgency", "medium")
        atype         = a.get("type", "other")
        headline      = a.get("headline", "")
        options_angle = a.get("options_angle", "")
        color         = URGENCY_COLOR.get(urgency, "#e67e22")
        emoji         = URGENCY_EMOJI.get(urgency, "⚡")
        label         = TYPE_LABEL.get(atype, "News")
        ticker_tag    = f" · <strong>{ticker}</strong>" if ticker and ticker != "N/A" else ""

        blocks.append(
            f'<div style="margin-bottom:14px;padding:12px 14px;'
            f'border-left:4px solid {color};background:#fafafa;">'
            f'<p style="margin:0 0 4px;font-size:12px;color:#777;">'
            f'{emoji} <strong>{label}</strong>{ticker_tag}</p>'
            f'<p style="margin:0 0 6px;font-size:15px;line-height:1.4;">'
            f'<strong>{headline}</strong></p>'
            f'<p style="margin:0;font-size:13px;color:#444;">'
            f'<em>Options:</em> {options_angle}</p>'
            f'</div>'
        )

    inner = (
        f'<p><strong>{summary}</strong></p>'
        + "".join(blocks)
        + f'<p style="font-size:11px;color:#aaa;font-style:italic;margin-top:16px;">'
        f'Scanned at {result.get("window_checked", NOW_STR)} · '
        f'Automated alert, not financial advice.</p>'
    )
    ticker_str = ", ".join(tickers[:3]) if tickers else "Markets"
    subject    = f"⚡ {ticker_str} — Intraday Alert"
    return subject, inner


def main():
    result = scan()
    if not result.get("has_alerts"):
        print(f"[{NOW_STR}] No new catalysts in window. Silent.")
        return
    n = len(result.get("alerts", []))
    print(f"[{NOW_STR}] {n} alert(s) — sending email.")
    subject, inner = build_email(result)
    send_email(
        subject,
        wrap_html(inner, "Intraday Alert"),
        text_body="New market catalyst detected. Open in HTML for details.",
    )
    print("Alert sent.")


if __name__ == "__main__":
    main()
