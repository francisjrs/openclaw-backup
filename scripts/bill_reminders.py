#!/usr/bin/env python3
"""
bill_reminders.py — Daily bill due-date checker for Robotina Finance.

Reads structured markdown front-matter from bill files, computes next due
dates, and prints a formatted Discord-ready reminder table for bills due
within the look-ahead window.

Usage:
    python3 bill_reminders.py [--days N] [--bills-dir PATH] [--dry-run]

Exit codes:
    0  — always (failures are logged to stderr; never crash the cron)

Output:
    stdout — formatted reminder table, or empty if nothing is due
    stderr — warnings and errors (never surfaced to Discord)

Author: Robotina Finance 🤖
"""

from __future__ import annotations

import argparse
import calendar
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_BILLS_DIR = Path("/home/node/obsidian-vault/Finance/Bills")
DEFAULT_LOOK_AHEAD = 3

DAY_NAMES = [
    "sunday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday",
]

# Weekday mapping (Python weekday() is Mon=0; we use Sun=0 convention in data)
# We normalize both sides at lookup time.

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="[bill_reminders] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class Bill:
    """Parsed representation of a single bill markdown file."""

    name: str
    source_file: Path
    due_day: Optional[int] = None           # day-of-month (1–31)
    due_day_of_week: Optional[int] = None   # 0=Sun … 6=Sat
    amount: Optional[float] = None
    amount_avg: Optional[float] = None
    auto_pay: bool = False
    notes: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    # ── Computed ──────────────────────────────────────────────────────────────

    def display_amount(self) -> str:
        """Return a human-readable amount string."""
        value = self.amount if self.amount is not None else self.amount_avg
        if value is None:
            return "check stmt"
        return f"${value:,.2f}"

    def next_due_date(self, from_date: date) -> Optional[date]:
        """
        Return the next due date on or after *from_date*.
        Returns None if the due schedule cannot be determined.
        """
        if self.due_day_of_week is not None:
            return self._next_weekday(self.due_day_of_week, from_date)
        if self.due_day is not None:
            return self._next_monthly(self.due_day, from_date)
        return None

    @staticmethod
    def _next_weekday(target_wd: int, from_date: date) -> date:
        """Next occurrence of *target_wd* (0=Sun) strictly after from_date."""
        # Convert Sun=0 → Python Mon=0 convention
        py_wd = (target_wd - 1) % 7  # Sun(0)→6, Mon(1)→0, …
        current_py = from_date.weekday()
        days_ahead = (py_wd - current_py) % 7
        if days_ahead == 0:
            days_ahead = 7  # never return today; always ≥ tomorrow
        return from_date + timedelta(days=days_ahead)

    @staticmethod
    def _next_monthly(dom: int, from_date: date) -> Optional[date]:
        """Next occurrence of day-of-month *dom* on or after *from_date*."""
        for month_offset in range(3):  # try up to 3 months ahead
            y = from_date.year
            m = from_date.month + month_offset
            if m > 12:
                y, m = y + 1, m - 12
            max_dom = calendar.monthrange(y, m)[1]
            clamped = min(dom, max_dom)
            candidate = date(y, m, clamped)
            if candidate >= from_date:
                return candidate
        return None  # shouldn't happen in practice


@dataclass
class DueBill:
    """A bill that falls within the reminder window."""

    bill: Bill
    due_date: date
    days_until: int


# ── Front-matter parser ────────────────────────────────────────────────────────

# Simple YAML-subset parser — avoids a PyYAML dependency.
_FM_PATTERN = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
_KV_PATTERN = re.compile(r"^([\w][\w_-]*):\s*(.+)$")


def parse_front_matter(text: str) -> dict:
    """
    Extract key-value pairs from a YAML-style front-matter block.
    Handles strings, booleans, integers, and floats.
    Returns an empty dict if no front-matter is present.
    """
    match = _FM_PATTERN.match(text)
    if not match:
        return {}

    result: dict = {}
    for line in match.group(1).splitlines():
        kv = _KV_PATTERN.match(line.strip())
        if not kv:
            continue
        key = kv.group(1)
        raw_val = kv.group(2).strip().strip("\"'")

        if raw_val.lower() == "true":
            result[key] = True
        elif raw_val.lower() == "false":
            result[key] = False
        else:
            try:
                result[key] = int(raw_val)
            except ValueError:
                try:
                    result[key] = float(raw_val)
                except ValueError:
                    result[key] = raw_val

    return result


def _resolve_day_of_week(raw: object) -> Optional[int]:
    """
    Normalize due_day_of_week to an integer (0=Sun … 6=Sat).
    Accepts ints and day-name strings (case-insensitive).
    Returns None on failure.
    """
    if isinstance(raw, int):
        return raw % 7
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        try:
            return DAY_NAMES.index(normalized)
        except ValueError:
            log.warning("Unknown day name %r — skipping bill.", raw)
            return None
    return None


# ── Bill file reader ───────────────────────────────────────────────────────────

def load_bill(path: Path) -> Optional[Bill]:
    """
    Parse a single bill markdown file.
    Returns None (and logs a warning) if the file is invalid or unreadable.
    """
    if not path.is_file():
        log.debug("Skipping non-file path: %s", path)
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Cannot read %s: %s", path.name, exc)
        return None

    fm = parse_front_matter(text)
    name = fm.get("name")
    if not name:
        log.debug("No 'name' in front-matter, skipping: %s", path.name)
        return None

    # Resolve due schedule
    due_day: Optional[int] = None
    due_dow: Optional[int] = None

    if "due_day_of_week" in fm:
        due_dow = _resolve_day_of_week(fm["due_day_of_week"])
    elif "due_day" in fm:
        raw = fm["due_day"]
        if isinstance(raw, int) and 1 <= raw <= 31:
            due_day = raw
        else:
            log.warning("Invalid due_day %r in %s — skipping.", raw, path.name)
            return None

    # Amount: prefer 'amount', fall back to 'amount_avg'
    amount: Optional[float] = None
    amount_avg: Optional[float] = None
    for key in ("amount", "amount_avg"):
        if key in fm:
            try:
                val = float(fm[key])
                if key == "amount":
                    amount = val
                else:
                    amount_avg = val
            except (TypeError, ValueError):
                log.warning("Non-numeric %s in %s.", key, path.name)

    return Bill(
        name=str(name),
        source_file=path,
        due_day=due_day,
        due_day_of_week=due_dow,
        amount=amount,
        amount_avg=amount_avg,
        auto_pay=bool(fm.get("auto_pay", False)),
        notes=str(fm.get("notes", "")),
        raw=fm,
    )


def load_bills(bills_dir: Path) -> list[Bill]:
    """Load and parse all .md bill files from *bills_dir*."""
    if not bills_dir.exists():
        log.error("Bills directory does not exist: %s", bills_dir)
        return []
    if not bills_dir.is_dir():
        log.error("Bills path is not a directory: %s", bills_dir)
        return []

    bills: list[Bill] = []
    for path in sorted(bills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue  # skip hidden files
        bill = load_bill(path)
        if bill is not None:
            bills.append(bill)

    log.info("Loaded %d bill(s) from %s", len(bills), bills_dir)
    return bills


# ── Due-date filtering ─────────────────────────────────────────────────────────

def find_due_bills(bills: list[Bill], today: date, look_ahead: int) -> list[DueBill]:
    """
    Return bills whose next due date falls within [today, today + look_ahead].
    Sorted by urgency (soonest first).
    """
    window_end = today + timedelta(days=look_ahead)
    due: list[DueBill] = []

    for bill in bills:
        next_date = bill.next_due_date(today)
        if next_date is None:
            log.warning("Could not compute due date for '%s' — skipping.", bill.name)
            continue
        if today <= next_date <= window_end:
            days = (next_date - today).days
            due.append(DueBill(bill=bill, due_date=next_date, days_until=days))

    due.sort(key=lambda d: d.days_until)
    return due


# ── Output formatting ──────────────────────────────────────────────────────────

def _urgency_badge(days: int) -> str:
    if days == 0:
        return "🔴 TODAY"
    if days == 1:
        return "⚠️ Tomorrow"
    return f"🔔 {days}d"


def _date_label(due: DueBill) -> str:
    if due.days_until == 0:
        return "Today"
    if due.days_until == 1:
        return "Tomorrow"
    return due.due_date.strftime("%a %b %-d")


def format_reminder_table(due_bills: list[DueBill], look_ahead: int) -> str:
    """Build a Discord-ready markdown table from the due bills list."""
    lines: list[str] = [
        f"📅 **Upcoming Bills — Next {look_ahead} Day{'s' if look_ahead != 1 else ''}**\n",
        "| Bill | Amount | Due | Auto-pay | |",
        "|------|--------|-----|----------|---|",
    ]

    needs_manual_action: list[str] = []

    for item in due_bills:
        bill = item.bill
        auto_str = "✅ Yes" if bill.auto_pay else "❌ No"
        row = (
            f"| {bill.name} "
            f"| {bill.display_amount()} "
            f"| {_date_label(item)} "
            f"| {auto_str} "
            f"| {_urgency_badge(item.days_until)} |"
        )
        lines.append(row)

        if not bill.auto_pay and item.days_until <= 2:
            needs_manual_action.append(bill.name)

    if needs_manual_action:
        names = ", ".join(needs_manual_action)
        lines.append(f"\n> ⚠️ **Manual payment required:** {names}")

    return "\n".join(lines) + "\n"


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check bills due within N days and print a reminder table."
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_LOOK_AHEAD,
        help=f"Look-ahead window in days (default: {DEFAULT_LOOK_AHEAD})",
    )
    parser.add_argument(
        "--bills-dir", type=Path, default=DEFAULT_BILLS_DIR,
        help=f"Path to bills directory (default: {DEFAULT_BILLS_DIR})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print parsed bill data without filtering by date",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging to stderr",
    )
    return parser.parse_args()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    today = date.today()
    bills = load_bills(args.bills_dir)

    if not bills:
        sys.exit(0)

    if args.dry_run:
        for bill in bills:
            nd = bill.next_due_date(today)
            print(f"{bill.name}: next due {nd}, amount={bill.display_amount()}, auto={bill.auto_pay}")
        sys.exit(0)

    due_bills = find_due_bills(bills, today, args.days)

    if not due_bills:
        sys.exit(0)  # Silent exit — cron will send NO_REPLY

    print(format_reminder_table(due_bills, args.days), end="")


if __name__ == "__main__":
    main()
