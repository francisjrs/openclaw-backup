#!/usr/bin/env python3
"""
rocket_money_processor.py — Rocket Money transaction processor for Robotina Finance.

Receives a JSON array of transactions on stdin, applies categorization rules,
detects anomalies, writes a weekly markdown file to the Obsidian vault, and
prints a Discord-ready report to stdout.

Usage:
    echo '<json>' | python3 rocket_money_processor.py [--week YYYY-WNN] [--dry-run]

Input JSON schema (each transaction):
    {
        "date":     "YYYY-MM-DD",
        "merchant": "Merchant Name",
        "amount":   12.34,          # positive = expense, negative = credit
        "category": "Optional",     # existing category from Rocket Money
        "account":  "Account Name"
    }

Exit codes:
    0  — always (errors go to stderr)

Author: Robotina Finance 🤖
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

STATE_FILE    = Path("/home/node/.openclaw/workspace/state/rocket_money_state.json")
VAULT_DIR     = Path("/home/node/obsidian-vault/Finance/Spending")
BUDGET_FILE   = Path("/home/node/obsidian-vault/Finance/Budget.md")

ANOMALY_SPIKE_PCT   = 0.30    # flag if amount is >30% above rolling average
EMA_ALPHA           = 0.30    # weight for new value in exponential moving average

# Categories that are never flagged as anomalies or sent to "needs review"
PASS_THROUGH_CATEGORIES = frozenset({
    "Income",
    "Savings Transfer",
    "Internal Transfers",
    "Credit Card Payment",
})

# Heuristic keyword → category mapping (checked if no state match found)
HEURISTICS: list[tuple[list[str], str]] = [
    (["payroll", "paycheck", "direct deposit", "direct dep"], "Income"),
    (["savings booster", "transfer to savings", "transfer from savings"], "Savings Transfer"),
    (["credit card payment", "card payment", "autopay"], "Credit Card Payment"),
    (["venmo", "zelle", "cashapp", "cash app", "paypal"], "Transfer"),
    (["amazon", "amzn", "walmart", "target", "costco", "sam's club"], "Shopping"),
    (["uber", "lyft", "parking", "shell", "chevron", "exxon", "sunoco", "valero"], "Auto & Transport"),
    (["netflix", "spotify", "apple.com/bill", "google play", "hulu", "disney+", "youtube premium"], "Entertainment"),
    (["restaurant", "cafe", "coffee", "chipotle", "mcdonald", "starbucks",
       "doordash", "grubhub", "uber eats", "instacart", "pizza"], "Food & Dining"),
    (["whataburger", "chick-fil-a", "taco bell", "subway", "wendy"], "Food & Dining"),
    (["heb", "kroger", "whole foods", "trader joe", "aldi"], "Groceries"),
    (["gym", "fitness", "planet fitness", "anytime fitness", "la fitness"], "Health & Fitness"),
    (["cvs", "walgreens", "pharmacy", "rite aid", "duane reade"], "Health & Fitness"),
    (["electric", "energy", "oncor", "txu", "atmos", "gas company"], "Bills & Utilities"),
    (["water", "sewer", "mud ", "municipal utility"], "Bills & Utilities"),
    (["insurance", "geico", "allstate", "state farm", "progressive"], "Insurance"),
    (["school", "tuition", "rrisd", "linda harrington"], "Education"),
    (["daycare", "babysitter", "childcare", "amaya"], "Childcare"),
]

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="[rocket_money] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    date:     str
    merchant: str
    amount:   float
    category: str = ""
    account:  str = ""

    # Set during processing
    resolved_category:    str   = field(default="", repr=False)
    confidence:           str   = field(default="LOW", repr=False)   # HIGH / MEDIUM / LOW
    suggested_category:   str   = field(default="", repr=False)
    anomaly_reason:       str   = field(default="", repr=False)
    is_duplicate:         bool  = field(default=False, repr=False)

    @property
    def merchant_key(self) -> str:
        """Normalized lowercase merchant key for state lookups."""
        return self.merchant.lower().strip()

    @property
    def is_pass_through(self) -> bool:
        return self.resolved_category in PASS_THROUGH_CATEGORIES

    @property
    def is_expense(self) -> bool:
        return self.amount > 0

    @property
    def dedup_key(self) -> str:
        return f"{self.merchant_key}:{self.amount}:{self.date}"


@dataclass
class AppState:
    """Persistent state loaded from / saved to STATE_FILE."""

    known_merchants:    dict[str, str]   = field(default_factory=dict)
    approved_categories: dict[str, str]  = field(default_factory=dict)
    merchant_averages:  dict[str, float] = field(default_factory=dict)
    ignored_merchants:  list[str]        = field(default_factory=list)
    last_scrape_date:   Optional[str]    = None

    @classmethod
    def load(cls, path: Path) -> "AppState":
        if not path.exists():
            log.info("State file not found — starting fresh: %s", path)
            return cls()
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                known_merchants=data.get("known_merchants", {}),
                approved_categories=data.get("approved_categories", {}),
                merchant_averages=data.get("merchant_averages", {}),
                ignored_merchants=data.get("ignored_merchants", []),
                last_scrape_date=data.get("last_scrape_date"),
            )
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load state file: %s — starting fresh.", exc)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as exc:
            log.error("Failed to save state file: %s", exc)

    def to_dict(self) -> dict:
        return {
            "last_scrape_date":    self.last_scrape_date,
            "known_merchants":     self.known_merchants,
            "approved_categories": self.approved_categories,
            "merchant_averages":   self.merchant_averages,
            "ignored_merchants":   self.ignored_merchants,
        }

    def update_average(self, key: str, amount: float) -> None:
        """Update exponential moving average for a merchant."""
        if amount <= 0:
            return
        current = self.merchant_averages.get(key)
        self.merchant_averages[key] = round(
            amount if current is None else current * (1 - EMA_ALPHA) + amount * EMA_ALPHA,
            2,
        )


# ── Categorization engine ──────────────────────────────────────────────────────

def categorize(txn: Transaction, state: AppState) -> tuple[str, str]:
    """
    Return (category, confidence) for a transaction.
    Priority: existing RM category → known_merchants → approved_categories
              → heuristics → Uncategorized
    """
    key = txn.merchant_key

    # Existing category from Rocket Money (trust it)
    if txn.category and txn.category not in ("", "Uncategorized"):
        return txn.category, "HIGH"

    # Exact known-merchant match
    if key in state.known_merchants:
        return state.known_merchants[key], "HIGH"

    # Approved override
    if key in state.approved_categories:
        return state.approved_categories[key], "HIGH"

    # Partial match in known_merchants
    for stored_key, cat in state.known_merchants.items():
        if stored_key in key or key in stored_key:
            return cat, "MEDIUM"

    # Keyword heuristics
    for keywords, cat in HEURISTICS:
        if any(kw in key for kw in keywords):
            return cat, "MEDIUM"

    return "Uncategorized", "LOW"


# ── Processing pipeline ────────────────────────────────────────────────────────

def process_transactions(
    transactions: list[Transaction],
    state: AppState,
) -> tuple[list[Transaction], list[Transaction], list[Transaction]]:
    """
    Categorize, deduplicate, and detect anomalies.

    Returns:
        (auto_approved, needs_review, anomalies)
    """
    auto_approved: list[Transaction] = []
    needs_review:  list[Transaction] = []
    anomalies:     list[Transaction] = []
    seen_keys: set[str] = set()

    for txn in transactions:
        # Duplicate detection
        if txn.dedup_key in seen_keys:
            txn.is_duplicate = True
            txn.anomaly_reason = "Possible duplicate transaction"
            anomalies.append(txn)
            continue
        seen_keys.add(txn.dedup_key)

        # Skip ignored merchants
        if txn.merchant_key in state.ignored_merchants:
            log.info("Skipping ignored merchant: %s", txn.merchant)
            continue

        # Categorize
        txn.resolved_category, txn.confidence = categorize(txn, state)

        # Pass-through categories skip anomaly checks and go straight to approved
        if txn.resolved_category in PASS_THROUGH_CATEGORIES:
            auto_approved.append(txn)
            continue

        # Anomaly detection (expenses only)
        if txn.is_expense:
            avg = state.merchant_averages.get(txn.merchant_key)
            if avg and avg > 0:
                pct = (txn.amount - avg) / avg
                if pct > ANOMALY_SPIKE_PCT:
                    txn.anomaly_reason = f"+{pct * 100:.0f}% above avg (avg ${avg:.2f})"
                    anomalies.append(txn)
            # Update rolling average
            state.update_average(txn.merchant_key, txn.amount)

        # Route by confidence
        if txn.confidence == "HIGH":
            auto_approved.append(txn)
        else:
            txn.suggested_category = txn.resolved_category
            needs_review.append(txn)

    return auto_approved, needs_review, anomalies


# ── Vault writer ───────────────────────────────────────────────────────────────

def write_vault_file(
    week_label: str,
    all_txns: list[Transaction],
    auto_approved: list[Transaction],
    needs_review: list[Transaction],
    anomalies: list[Transaction],
) -> Path:
    """Write the weekly transaction markdown to the Obsidian vault."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = VAULT_DIR / f"{week_label}-transactions.md"

    total_spending = sum(
        t.amount for t in all_txns
        if t.is_expense and t.resolved_category not in PASS_THROUGH_CATEGORIES
    )

    now = datetime.now().isoformat(timespec="seconds")

    lines: list[str] = [
        "---",
        f"week: {week_label}",
        "source: rocket-money",
        "status: pending-review",
        f"total_spending: {total_spending:.2f}",
        f"scraped_at: {now}",
        "---",
        "",
        f"# Transactions: {week_label}",
        "",
        "## Summary",
        f"- Total transactions: {len(all_txns)}",
        f"- Total spending: ${total_spending:,.2f}",
        f"- Auto-categorized: {len(auto_approved)}",
        f"- Needs review: {len(needs_review)}",
        f"- Anomalies: {len(anomalies)}",
        "",
    ]

    if auto_approved:
        lines += [
            "## Categorized",
            "| Date | Merchant | Amount | Category | Account |",
            "|------|----------|--------|----------|---------|",
        ]
        for t in auto_approved:
            lines.append(
                f"| {t.date} | {t.merchant} | ${t.amount:,.2f} | {t.resolved_category} | {t.account} |"
            )
        lines.append("")

    if needs_review:
        lines += [
            "## Needs Review",
            "| Date | Merchant | Amount | Suggested | Confidence |",
            "|------|----------|--------|-----------|------------|",
        ]
        for t in needs_review:
            lines.append(
                f"| {t.date} | {t.merchant} | ${t.amount:,.2f} | {t.suggested_category} | {t.confidence} |"
            )
        lines.append("")

    if anomalies:
        lines += ["## Anomalies", ""]
        for t in anomalies:
            lines.append(f"- **{t.merchant}** ${t.amount:,.2f}: {t.anomaly_reason}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote vault file: %s", filepath)
    return filepath


# ── Discord report formatter ───────────────────────────────────────────────────

def format_report(
    week_label: str,
    auto_approved: list[Transaction],
    needs_review: list[Transaction],
    anomalies: list[Transaction],
    vault_path: Path,
) -> str:
    """Build a Discord-ready markdown report."""
    lines: list[str] = [
        f"## 💰 Weekly Transaction Review — {week_label}",
        "",
    ]

    total_spending = sum(
        t.amount for t in auto_approved + needs_review
        if t.is_expense and t.resolved_category not in PASS_THROUGH_CATEGORIES
    )
    lines += [f"> **Total spending this week: ${total_spending:,.2f}**", ""]

    if auto_approved:
        lines.append(f"**✅ Auto-categorized ({len(auto_approved)})**")
        for t in auto_approved:
            lines.append(
                f"- `{t.date}` {t.merchant} — ${t.amount:,.2f} → {t.resolved_category}"
            )
        lines.append("")

    if needs_review:
        lines.append(f"**⚠️ Needs your input ({len(needs_review)})**")
        for t in needs_review:
            lines.append(
                f"- `{t.date}` **{t.merchant}** — ${t.amount:,.2f} → suggested: *{t.suggested_category}* ({t.confidence})"
            )
        lines.append("")

    if anomalies:
        lines.append(f"**🚨 Anomalies ({len(anomalies)})**")
        for t in anomalies:
            lines.append(f"- **{t.merchant}** ${t.amount:,.2f}: {t.anomaly_reason}")
        lines.append("")

    lines += [
        f"> Saved: `{vault_path.name}`",
        "",
        "Reply with: `approve all` · `MERCHANT -> Category` · `ignore MERCHANT`",
    ]

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process Rocket Money transactions and generate a weekly review."
    )
    parser.add_argument(
        "--week", type=str, default=None,
        help="Force week label as YYYY-WNN (default: inferred from transaction dates)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Process transactions but do not write vault file or update state",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging to stderr",
    )
    return parser.parse_args()


def infer_week_label(transactions: list[Transaction]) -> str:
    """Infer ISO week label from the first transaction's date, or use today."""
    for txn in transactions:
        try:
            d = datetime.strptime(txn.date, "%Y-%m-%d")
            return f"{d.year}-W{d.isocalendar()[1]:02d}"
        except ValueError:
            continue
    d = datetime.now()
    return f"{d.year}-W{d.isocalendar()[1]:02d}"


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Read stdin
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No transaction data on stdin.", file=sys.stderr)
        print("⚠️ No transaction data received. Please pipe a JSON array of transactions.")
        sys.exit(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("JSON parse error: %s", exc)
        print(f"⚠️ Failed to parse transaction JSON: {exc}")
        sys.exit(0)

    if not isinstance(data, list):
        print("⚠️ Expected a JSON array of transactions.")
        sys.exit(0)

    # Build transaction objects
    transactions: list[Transaction] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            log.warning("Skipping non-dict item at index %d", i)
            continue
        try:
            transactions.append(Transaction(
                date=str(item.get("date", "")),
                merchant=str(item.get("merchant", item.get("description", "Unknown"))),
                amount=float(item.get("amount", 0)),
                category=str(item.get("category", "")),
                account=str(item.get("account", "")),
            ))
        except (TypeError, ValueError) as exc:
            log.warning("Skipping malformed transaction at index %d: %s", i, exc)

    if not transactions:
        print("⚠️ No valid transactions found in input.")
        sys.exit(0)

    log.info("Processing %d transaction(s).", len(transactions))

    # Load state
    state = AppState.load(STATE_FILE)

    # Process
    auto_approved, needs_review, anomalies = process_transactions(transactions, state)

    # Determine week label
    week_label = args.week or infer_week_label(transactions)

    if args.dry_run:
        print(f"[dry-run] Week: {week_label}")
        print(f"[dry-run] Auto: {len(auto_approved)}, Review: {len(needs_review)}, Anomalies: {len(anomalies)}")
        sys.exit(0)

    # Write vault file
    vault_path = write_vault_file(week_label, transactions, auto_approved, needs_review, anomalies)

    # Update state
    state.last_scrape_date = datetime.now().isoformat(timespec="seconds")
    state.save(STATE_FILE)

    # Print Discord report
    print(format_report(week_label, auto_approved, needs_review, anomalies, vault_path))


if __name__ == "__main__":
    main()
