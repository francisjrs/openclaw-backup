#!/usr/bin/env python3
"""
Gmail Priority Monitor
Runs gog gmail list and filters for priority emails.
Called by cron job — returns alert text or exits silently (NO_REPLY).
"""

import subprocess
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

GOG_BIN = Path(os.environ.get("GOG_BIN", "/home/node/.openclaw/workspace/bin/gog"))
GOG_ACCOUNT = os.environ.get("GOG_ACCOUNT", "francisco.ramos.sanchez@gmail.com")
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "35"))  # slight overlap to avoid gaps

PRIORITY_SENDERS = [
    "herrington", "rrisd", "linda harrington", "round rock isd",
    "roundrockisd", "lisd",
]

PRIORITY_DOMAINS = [
    # Medical
    "ascension", "seton", "st.david", "stdavid", "bswhealth",
    "austinregionalclinic", "arc.org", "cedarssinai",
    # Banks / Finance
    "chase.com", "bankofamerica.com", "wellsfargo.com", "discover.com",
    "capitalone.com", "amex.com", "citibank.com", "paypal.com", "venmo.com",
    "sofi.com", "ally.com",
    # Utilities / Bills
    "austinenergy.com", "austinwater.org", "att.com", "tmobile.com",
    "spectrum.com", "xfinity.com",
]

PRIORITY_SUBJECTS = [
    "urgent", "action required", "payment", "past due", "overdue",
    "appointment", "confirmation", "reminder", "schedule", "alert",
    "account", "statement", "due", "invoice", "bill",
]

FAMILY_NAMES = [
    "ramos", "sanchez", "yolanda", "elisa", "alejandro", "sofia",
]

SPAM_SIGNALS = [
    "unsubscribe", "marketing", "newsletter", "promotion", "deal",
    "sale", "% off", "coupon", "offer", "promo",
]


def run_gog():
    env = os.environ.copy()
    env["GOG_ACCOUNT"] = GOG_ACCOUNT
    result = subprocess.run(
        [str(GOG_BIN), "gmail", "list", "--unread", "--max", "50", "-j"],
        capture_output=True, text=True, env=env, timeout=60
    )
    if result.returncode != 0:
        print(f"gog error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(0)
    return result.stdout.strip()


def parse_emails(raw):
    try:
        return json.loads(raw)
    except Exception:
        # Try to find JSON array in output
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end+1])
            except Exception:
                pass
    return []


def is_recent(email_obj, window_minutes):
    """Check if email was received within the last window_minutes."""
    date_str = email_obj.get("date") or email_obj.get("Date") or email_obj.get("receivedAt")
    if not date_str:
        return True  # If no date, include it (be conservative)
    try:
        # Try ISO format
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        now = datetime.now(timezone.utc)
        return (now - dt) <= timedelta(minutes=window_minutes)
    except Exception:
        return True


def is_priority(email_obj):
    """Return True if this email meets priority criteria."""
    from_field = (email_obj.get("from") or email_obj.get("From") or "").lower()
    subject = (email_obj.get("subject") or email_obj.get("Subject") or "").lower()
    snippet = (email_obj.get("snippet") or email_obj.get("body") or "").lower()

    combined_text = f"{from_field} {subject} {snippet}"

    # Skip obvious spam/marketing
    spam_count = sum(1 for sig in SPAM_SIGNALS if sig in combined_text)
    if spam_count >= 2:
        return False

    # Check priority sender name keywords
    for kw in PRIORITY_SENDERS:
        if kw in from_field:
            return True

    # Check priority domains
    for domain in PRIORITY_DOMAINS:
        if domain in from_field:
            return True

    # Check family names in sender
    for name in FAMILY_NAMES:
        if name in from_field:
            return True

    # Check subject keywords
    for kw in PRIORITY_SUBJECTS:
        if kw in subject:
            return True

    return False


def format_alert(email_obj):
    sender = email_obj.get("from") or email_obj.get("From") or "Unknown"
    subject = email_obj.get("subject") or email_obj.get("Subject") or "(no subject)"
    snippet = email_obj.get("snippet") or email_obj.get("body") or ""
    # Trim snippet
    if len(snippet) > 120:
        snippet = snippet[:120].rsplit(" ", 1)[0] + "…"
    return f"• **{sender}** — {subject}\n  {snippet}"


def main():
    raw = run_gog()
    if not raw:
        sys.exit(0)

    emails = parse_emails(raw)
    if not emails:
        sys.exit(0)

    # Handle both list and dict with messages key
    if isinstance(emails, dict):
        emails = emails.get("messages") or emails.get("emails") or list(emails.values())

    priority_emails = []
    for e in emails:
        if not isinstance(e, dict):
            continue
        if not is_recent(e, WINDOW_MINUTES):
            continue
        if is_priority(e):
            priority_emails.append(e)

    if not priority_emails:
        sys.exit(0)

    lines = ["📬 **Priority email alert:**"]
    for e in priority_emails[:5]:  # Cap at 5 alerts
        lines.append(format_alert(e))

    print("\n".join(lines))


if __name__ == "__main__":
    main()
