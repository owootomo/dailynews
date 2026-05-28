# Market Digest + Trump Alerts

A self-running, free-tier pipeline that emails you:

1. **A daily pre-market digest** (weekday mornings) — US futures, overnight headlines, a Trump/policy watch, the economic calendar, and stocks in focus. Built by Claude using live web search.
2. **Near-real-time Trump alerts** (optional) — checks Trump's Truth Social posts on an interval and emails you only the ones likely to move markets.

It runs on **GitHub Actions** (a free, persistent scheduler). No server to maintain.

---

## What you need (one-time)

| Thing | Why | Cost |
|---|---|---|
| GitHub account + a repo | Runs the scheduled jobs | Free |
| Anthropic API key | Research + summarization (`console.anthropic.com`) | ~pennies/day; pay-as-you-go |
| Email method | To receive the emails | Resend free 100/day, or Gmail free |
| Apify token (alerts only) | Scrapes Truth Social | Small per-run cost; you have Apify already |

**Important — enable web search:** in the Anthropic Console, turn on the Web Search tool for your organization (Settings). The daily digest depends on it.

---

## Setup

### 1. Create the repo
Create a new GitHub repo and add all these files (keep the folder structure). Easiest is to drag the unzipped folder into a fresh repo, or `git init` locally and push.

### 2. Add your keys to GitHub
In the repo: **Settings → Secrets and variables → Actions**.

Add these as **Secrets** (encrypted):
- `ANTHROPIC_API_KEY`
- `EMAIL_TO` — where the emails go
- **Email, pick one:**
  - `RESEND_API_KEY` (and optionally `EMAIL_FROM`), **or**
  - `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`
- For alerts only: `APIFY_TOKEN`

Add these as **Variables** (optional, not secret):
- `ANTHROPIC_MODEL` (default `claude-sonnet-4-6`)
- `APIFY_ACTOR_ID`, `APIFY_INPUT_JSON`, `LOOKBACK_MINUTES` (alerts tuning)

### 3. Test it before trusting the schedule
Go to the **Actions** tab → pick a workflow → **Run workflow**. Check your inbox and the run logs. The daily digest is the one to verify first.

### 4. Adjust the send time
`.github/workflows/daily-digest.yml` runs at `0 10 * * 1-5` = **10:00 UTC**, which is **6am ET in summer / 5am ET in winter** (GitHub cron is fixed UTC and does not follow daylight saving). Change the hour to taste.

---

## Email options

- **Resend (recommended):** sign up, grab an API key, done. Leave `EMAIL_FROM` blank to use the `onboarding@resend.dev` sandbox sender, or verify a domain later for a custom From.
- **Gmail:** turn on 2-step verification, create an **App Password** (Google Account → Security → App passwords), and set `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`. Don't use your normal password.

---

## The Trump-alerts job (optional, read this)

It's stateless: it asks the Apify actor for the latest posts, keeps only those newer than `LOOKBACK_MINUTES`, and emails the market-relevant ones. Keep `LOOKBACK_MINUTES` a bit larger than the cron interval (cron every 15 → lookback ~20) so nothing slips through a gap and nothing repeats.

**You will likely need to adjust two things** because Apify actors differ:
- `APIFY_INPUT_JSON` — the actor's input shape (check the actor's page on Apify).
- `TEXT_FIELDS` / `TIME_FIELDS` in `scripts/trump_alerts.py` — the field names the actor uses for post text and timestamp. Run it once via **Run workflow**, read the logs, and tweak if you see the "no timestamps parsed" warning.

If you'd rather skip this entirely, just delete `.github/workflows/trump-alerts.yml` — the daily digest already includes a Trump/policy section.

---

## Costs & limits (honest version)

- **Anthropic:** daily digest ≈ a handful of web searches + a few thousand tokens → roughly a few cents per day. Alerts are cheaper per run but run often.
- **GitHub Actions minutes:** public repos = unlimited free. Private repos = 2,000 free min/month. The 15-minute alert job is ~96 runs/day, which can blow past 2,000 min on a private repo. **Fix: make the repo public** (there are no secrets in the code — they live in GitHub Secrets), *or* widen the interval / restrict hours, *or* skip the alerts job.
- **Apify:** the Truth Social actor charges per run/result. Running every 15 min adds up — check the actor's pricing and your Apify credit.

## Reality check on "immediate"

GitHub's scheduled jobs are best-effort and can be delayed 5–15+ minutes under load, and web/scraper indexing isn't instant — so "real-time" here realistically means *within tens of minutes*. Markets and algorithms react in milliseconds, so treat this as **staying informed**, not as a tool to trade ahead of a move. None of the output is financial advice.

## Local testing
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
set -a; . ./.env; set +a
python scripts/daily_digest.py
python scripts/trump_alerts.py
```
