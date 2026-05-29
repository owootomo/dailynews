#!/usr/bin/env python3
"""Near-real-time Trump Truth Social market alerts.

Pulls the latest Truth Social posts via an Apify actor, keeps only those inside
the lookback window, asks Claude whether each is likely to move markets, and
emails the relevant ones.

This is STATELESS: it dedupes by time window, so LOOKBACK_MINUTES should be a
little LARGER than your cron interval (e.g. cron every 15 min -> lookback ~20).

Required env: ANTHROPIC_API_KEY, APIFY_TOKEN, EMAIL_TO + an email method.
Optional env: ANTHROPIC_MODEL, APIFY_ACTOR_ID, APIFY_INPUT_JSON, LOOKBACK_MINUTES.

NOTE: Apify actors differ in their input and output shapes. Confirm your chosen
actor's schema on its Apify page and adjust APIFY_INPUT_JSON and the field-name
lists below (TEXT_FIELDS / TIME_FIELDS) if your actor uses different keys.
"""
import os
import sys
import json
import html
import datetime
import requests
from emailer import send_email, wrap_html

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
APIFY_TOKEN = os.environ["APIFY_TOKEN"]
# Default actor scrapes Truth Social. Verify input/output on its Apify page.
ACTOR_ID = os.environ.get("APIFY_ACTOR_ID", "muhammetakkurtt~truth-social-scraper")
LOOKBACK_MIN = int(os.environ.get("LOOKBACK_MINUTES") or "20")

TEXT_FIELDS = ["text", "content", "post", "body", "caption", "title"]
TIME_FIELDS = ["created_at", "createdAt", "timestamp", "published",
               "publishedAt", "date", "time"]


def fetch_posts():
    """Run the Apify actor synchronously and return its dataset items (a list)."""
    default_input = {"profiles": ["realDonaldTrump"], "maxItems": 5}
    actor_input = json.loads(
        os.environ.get("APIFY_INPUT_JSON", json.dumps(default_input))
    )
    url = (f"https://api.apify.com/v2/acts/{ACTOR_ID}"
           f"/run-sync-get-dataset-items?token={APIFY_TOKEN}")
    r = requests.post(url, json=actor_input, timeout=240)
    r.raise_for_status()
    return r.json()


def get_field(item, names):
    for n in names:
        if isinstance(item, dict) and item.get(n):
            return item[n]
    return None


def parse_time(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        ts = val / 1000 if val > 1e12 else val  # ms vs s
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    s = str(val).strip().replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z", "%a %b %d %H:%M:%S %z %Y"):
            try:
                return datetime.datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def recent_posts(items):
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(minutes=LOOKBACK_MIN)
    out, parsed_any = [], False
    for it in items if isinstance(items, list) else []:
        text = get_field(it, TEXT_FIELDS)
        t = parse_time(get_field(it, TIME_FIELDS))
        if t is not None:
            parsed_any = True
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            if t >= cutoff and text:
                out.append((t, str(text)))
    if items and not parsed_any:
        print("WARNING: no timestamps parsed. Check TIME_FIELDS for your actor.",
              file=sys.stderr)
    return out


def assess(text):
    """Ask Claude if a post is likely to move markets. Returns a dict."""
    prompt = (
        "A new Truth Social post from Donald Trump is below. Judge whether it is "
        "likely to move US financial markets (stocks, bonds, FX, crypto, "
        "commodities) in the near term. Respond with ONLY a JSON object and no "
        'other text: {"relevant": true or false, "why": "one sentence", '
        '"areas": "tickers/sectors/asset classes likely affected, or empty"}\n\n'
        f'POST:\n"""\n{text}\n"""'
    )
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {"model": MODEL, "max_tokens": 400,
               "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    txt = "".join(b.get("text", "") for b in r.json().get("content", [])
                  if b.get("type") == "text").strip()
    txt = txt.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(txt)
    except Exception:
        return {"relevant": True, "why": "(could not parse model output)", "areas": ""}


def main():
    posts = recent_posts(fetch_posts())
    if not posts:
        print("No new posts in lookback window.")
        return
    flagged = []
    for t, text in posts:
        v = assess(text)
        if v.get("relevant"):
            flagged.append((t, text, v))
    if not flagged:
        print(f"{len(posts)} new post(s); none judged market-relevant.")
        return

    blocks = []
    for t, text, v in flagged:
        blocks.append(
            f'<p style="color:#888;font-size:12px;margin:0;">'
            f'{t:%b %d, %I:%M %p UTC}</p>'
            f'<blockquote style="border-left:3px solid #5b1a2e;margin:4px 0 8px;'
            f'padding-left:10px;">{html.escape(text)}</blockquote>'
            f'<p><strong>Why it may matter:</strong> {html.escape(v.get("why",""))}'
            f'<br><strong>Watch:</strong> {html.escape(v.get("areas","") or "—")}'
            f'</p><hr>'
        )
    inner = "".join(blocks) + (
        '<p style="font-size:12px;font-style:italic;color:#888;">Automated alert, '
        'not financial advice. Verify before acting — by the time you read this, '
        'markets may already have moved.</p>'
    )
    subject = f"\U0001F6A8 Trump post may move markets ({len(flagged)})"
    send_email(subject, wrap_html(inner, "Trump Market Alert"),
               text_body="New market-relevant Trump post(s). Open in HTML.")
    print(f"Sent alert covering {len(flagged)} post(s).")


if __name__ == "__main__":
    main()
