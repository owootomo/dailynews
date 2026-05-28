"""Shared email helper. Sends via Resend (if RESEND_API_KEY is set) or
Gmail SMTP (if GMAIL_APP_PASSWORD is set). Set whichever you prefer."""
import os
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM") or os.environ.get("GMAIL_ADDRESS", "")


def wrap_html(inner_html: str, title: str) -> str:
    """Wrap generated body HTML in a simple, email-safe container."""
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,'
        'sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;line-height:1.55;">'
        '<div style="border-bottom:3px solid #5b1a2e;padding-bottom:8px;'
        f'margin-bottom:16px;"><h2 style="margin:0;color:#5b1a2e;">{title}</h2></div>'
        f"{inner_html}</div>"
    )


def send_email(subject: str, html_body: str, text_body: str | None = None):
    if not EMAIL_TO:
        raise RuntimeError("EMAIL_TO is not set.")
    text_body = text_body or "Open this message in an HTML-capable client."
    if os.environ.get("RESEND_API_KEY"):
        return _send_resend(subject, html_body, text_body)
    if os.environ.get("GMAIL_APP_PASSWORD"):
        return _send_gmail(subject, html_body, text_body)
    raise RuntimeError(
        "No email method configured. Set RESEND_API_KEY (recommended) "
        "or GMAIL_ADDRESS + GMAIL_APP_PASSWORD."
    )


def _send_resend(subject, html_body, text_body):
    # Resend free tier = 100 emails/day. Until you verify your own domain,
    # use the sandbox sender "onboarding@resend.dev".
    sender = EMAIL_FROM or "Market Digest <onboarding@resend.dev>"
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": sender,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _send_gmail(subject, html_body, text_body):
    addr = os.environ["GMAIL_ADDRESS"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = addr
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(addr, os.environ["GMAIL_APP_PASSWORD"])
        s.sendmail(addr, [EMAIL_TO], msg.as_string())
    return {"status": "sent via gmail"}
