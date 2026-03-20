"""
notifier.py – extend this to send real notifications.

Current implementation just logs; replace / extend with email, Slack, Telegram, etc.
"""

import logging

logger = logging.getLogger(__name__)


def notify_new(entries: list[dict]):
    """Called whenever new internships are detected.

    Replace the body of this function to add real notifications, e.g.:
        - send_email(entries)
        - post_to_slack(entries)
        - send_telegram_message(entries)
    """
    for entry in entries:
        logger.info(
            "NOTIFY: New internship – %s | %s | %s | %s",
            entry["company"],
            entry["role"],
            entry["location"],
            entry["apply_link"],
        )


# ── Optional: email example (uncomment + fill in credentials) ─────────────────
#
# import smtplib
# from email.mime.text import MIMEText
#
# SMTP_HOST = "smtp.gmail.com"
# SMTP_PORT = 587
# FROM_ADDR = "you@gmail.com"
# TO_ADDR   = "you@gmail.com"
# PASSWORD  = "app-password-here"
#
# def send_email(entries):
#     body = "\n".join(
#         f"• {e['company']} – {e['role']} ({e['location']})\n  {e['apply_link']}"
#         for e in entries
#     )
#     msg = MIMEText(body)
#     msg["Subject"] = f"[Internship Tracker] {len(entries)} new listing(s)"
#     msg["From"] = FROM_ADDR
#     msg["To"]   = TO_ADDR
#     with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
#         s.starttls()
#         s.login(FROM_ADDR, PASSWORD)
#         s.send_message(msg)
#     logger.info("Email sent with %d entries.", len(entries))