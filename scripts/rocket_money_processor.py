#!/usr/bin/env python3
"""
Rocket Money Transaction Processor
- Receives transaction JSON via stdin
- Categorizes using known merchant rules + state file
- Detects anomalies (price spikes, new merchants, duplicates)
- Writes weekly file to Obsidian vault
- Outputs formatted report to stdout for Discord
"""

import json
import sys
import os
import re
from datetime import datetime, timedelta

STATE_FILE = "/home/node/.openclaw/workspace/state/rocket_money_state.json"
VAULT_BASE = "/home/node/obsidian-vault/Finance/Spending"
RECURRING_DIR = "/home/node/obsidian-vault/Finance/Recurring"
BUDGET_FILE = "/home/node/obsidian-vault/Finance/Budget.md"

ANOMALY_THRESHOLD = 0.30  # flag if >30% above average


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_scrape_date": None, "known_merchants": {}, "approved_categories": {}, "merchant_averages": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def normalize_merchant(name):
    return name.lower().strip()


def find_category(merchant_raw, state):
    """Look up category for a merchant. Returns (category, confidence)."""
    norm = normalize_merchant(merchant_raw)
    # Exact match
    if norm in state["known_merchants"]:
        return state["known_merchants"][norm], "HIGH"
    # Approved overrides
    if norm in state["approved_categories"]:
        return state["approved_categories"][norm], "HIGH"
    # Partial match
    for key, cat in state["known_merchants"].items():
        if key in norm or norm in key:
            return cat, "MEDIUM"
    # Heuristic fallbacks
    heuristics = [
        (["payroll", "paycheck", "direct deposit", "income"], "Income"),
        (["savings transfer", "savings booster", "transfer to savings", "transfer from savings"], "Savings Transfer"),
        (["credit card payment", "card payment"], "Credit Card Payment"),
        (["venmo", "zelle", "cashapp", "paypal"], "Transfer"),
        (["amazon", "amzn", "walmart", "target", "costco"], "Shopping"),
        (["uber", "lyft", "parking", "gas station", "shell", "chevron", "exxon", "sunoco"], "Auto & Transport"),
        (["netflix", "spotify", "apple", "google play", "hulu", "disney"], "Entertainment"),
        (["restaurant", "cafe", "coffee", "chipotle", "mcdonald", "starbucks", "doordash", "grubhub", "uber eats"], "Food & Dining"),
        (["gym", "fitness", "planet fitness", "anytime fitness"], "Health & Fitness"),
        (["cvs", "walgreens", "pharmacy", "rite aid"], "Health & Fitness"),
        (["electric", "energy", "utility", "water", "sewer", "gas company", "atmos", "txu", "oncor"], "Bills & Utilities"),
        (["insurance", "geico", "allstate", "state farm"], "Insurance"),
        (["mud", "municipal utility"], "Bills & Utilities"),
    ]
    norm_lower = norm.lower()
    for keywords, cat in heuristics:
        if any(k in norm_lower for k in keywords):
            return cat, "MEDIUM"
    return "Uncategorized", "LOW"


def detect_anomaly(merchant_raw, amount, state):
    """Returns anomaly description or None."""
    norm = normalize_merchant(merchant_raw)
    avg = state["merchant_averages"].get(norm)
    if avg and amount > 0:
        pct = (amount - avg) / avg
        if pct > ANOMALY_THRESHOLD:
            return f"+{pct*100:.0f}% above average (avg ${avg:.2f})"
    return None


def update_merchant_average(merchant_raw, amount, state):
    """Update rolling average for a merchant."""
    norm = normalize_merchant(merchant_raw)
    if amount > 0:
        current = state["merchant_averages"].get(norm)
        if current is None:
            state["merchant_averages"][norm] = amount
        else:
            # Simple exponential moving average
            state["merchant_averages"][norm] = round(current * 0.7 + amount * 0.3, 2)


def get_week_label(date_str=None):
    """Returns YYYY-WNN label for a given date string or today."""
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            d = datetime.now()
    else:
        d = datetime.now()
    week_num = d.isocalendar()[1]
    return f"{d.year}-W{week_num:02d}"


def write_vault_file(week_label, transactions, categorized, needs_review, anomalies):
    """Write the weekly transaction markdown file to Obsidian vault."""
    os.makedirs(VAULT_BASE, exist_ok=True)
    filepath = os.path.join(VAULT_BASE, f"{week_label}-transactions.md")

    total_spending = sum(
        t["amount"] for t in transactions
        if t.get("amount", 0) > 0 and t.get("category") not in ("Income", "Savings Transfer", "Internal Transfers")
    )

    lines = [
        f"---",
        f"week: {week_label}",
        f"source: rocket-money",
        f"status: pending-review",
        f"total_spending: {total_spending:.2f}",
        f"scraped_at: {datetime.now().isoformat()}",
        f"---",
        f"",
        f"# Transactions: {week_label}",
        f"",
        f"## Summary",
        f"- Total spending: ${total_spending:.2f}",
        f"- Auto-categorized: {len(categorized)}",
        f"- Needs review: {len(needs_review)}",
        f"- Anomalies: {len(anomalies)}",
        f"",
    ]

    if categorized:
        lines += [
            f"## Categorized (auto)",
            f"| Date | Merchant | Amount | Category | Account |",
            f"|------|----------|--------|----------|---------|",
        ]
        for t in categorized:
            lines.append(f"| {t.get('date','')} | {t.get('merchant','')} | ${t.get('amount',0):.2f} | {t.get('category','')} | {t.get('account','')} |")
        lines.append("")

    if needs_review:
        lines += [
            f"## Needs Review",
            f"| Date | Merchant | Amount | Suggested | Confidence |",
            f"|------|----------|--------|-----------|------------|",
        ]
        for t in needs_review:
            lines.append(f"| {t.get('date','')} | {t.get('merchant','')} | ${t.get('amount',0):.2f} | {t.get('suggested_category','')} | {t.get('confidence','')} |")
        lines.append("")

    if anomalies:
        lines += [f"## Anomalies", ""]
        for a in anomalies:
            lines.append(f"- **{a['merchant']}** ${a['amount']:.2f}: {a['reason']}")
        lines.append("")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    return filepath


def format_discord_report(week_label, categorized, needs_review, anomalies, vault_path):
    """Format the report for Discord."""
    lines = [
        f"## 💰 Weekly Transaction Review — {week_label}",
        f"",
    ]

    if categorized:
        lines.append(f"**✅ Auto-categorized ({len(categorized)} transactions)**")
        for t in categorized:
            sign = "+" if t.get("amount", 0) < 0 else "-"
            lines.append(f"- {t.get('date','')} | {t.get('merchant','')} | ${abs(t.get('amount',0)):.2f} → {t.get('category','')}")
        lines.append("")

    if needs_review:
        lines.append(f"**⚠️ Needs Your Input ({len(needs_review)} transactions)**")
        for t in needs_review:
            lines.append(f"- {t.get('date','')} | {t.get('merchant','')} | ${t.get('amount',0):.2f} → suggested: {t.get('suggested_category','')} ({t.get('confidence','')})")
        lines.append("")

    if anomalies:
        lines.append(f"**🚨 Anomalies ({len(anomalies)})**")
        for a in anomalies:
            lines.append(f"- {a['merchant']} ${a['amount']:.2f}: {a['reason']}")
        lines.append("")

    lines += [
        f"Saved to vault: `{os.path.basename(vault_path)}`",
        f"",
        f"Reply with: `approve all`, `MERCHANT -> Category`, or `ignore MERCHANT`",
    ]

    return "\n".join(lines)


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No transaction data received on stdin.")
        sys.exit(1)

    try:
        transactions = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse transaction JSON: {e}")
        sys.exit(1)

    state = load_state()

    categorized = []
    needs_review = []
    anomalies = []

    # Track duplicates
    seen = {}

    for t in transactions:
        merchant = t.get("merchant", t.get("description", "Unknown"))
        amount = float(t.get("amount", 0))
        date = t.get("date", "")
        account = t.get("account", "")
        existing_category = t.get("category", "")

        # Skip income and transfers from anomaly/review (they're expected)
        skip_review = existing_category in ("Income", "Savings Transfer", "Internal Transfers", "Credit Card Payment")

        # Categorize
        if existing_category and existing_category != "Uncategorized":
            category = existing_category
            confidence = "HIGH"
        else:
            category, confidence = find_category(merchant, state)

        t["category"] = category
        t["confidence"] = confidence
        t["merchant"] = merchant

        # Duplicate detection
        dedup_key = f"{merchant}:{amount}:{date}"
        if dedup_key in seen:
            anomalies.append({"merchant": merchant, "amount": amount, "reason": "Possible duplicate transaction"})
        else:
            seen[dedup_key] = True

        # Anomaly detection
        if not skip_review and amount > 0:
            anomaly_reason = detect_anomaly(merchant, amount, state)
            if anomaly_reason:
                anomalies.append({"merchant": merchant, "amount": amount, "reason": anomaly_reason})

        # Update merchant average
        if amount > 0 and not skip_review:
            update_merchant_average(merchant, amount, state)

        # Route to categorized or needs_review
        if confidence == "HIGH" or skip_review:
            categorized.append(t)
        else:
            t["suggested_category"] = category
            needs_review.append(t)

    # Get week label from first transaction date
    first_date = transactions[0].get("date") if transactions else None
    week_label = get_week_label(first_date)

    # Write vault file
    vault_path = write_vault_file(week_label, transactions, categorized, needs_review, anomalies)

    # Update state
    state["last_scrape_date"] = datetime.now().isoformat()
    save_state(state)

    # Output Discord report
    print(format_discord_report(week_label, categorized, needs_review, anomalies, vault_path))


if __name__ == "__main__":
    main()
