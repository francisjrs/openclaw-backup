#!/usr/bin/env node
/**
 * bill_reminders.js — Daily bill due-date checker
 * Reads all bill markdown files, checks for bills due within N days,
 * and prints a formatted reminder table (or nothing if nothing is due).
 *
 * Usage: node bill_reminders.js [--days 3]
 * Exit 0: always (errors are printed to stderr, not thrown)
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Config ────────────────────────────────────────────────────────────────────
const BILLS_DIR    = '/home/node/obsidian-vault/Finance/Bills';
const LOOK_AHEAD   = parseInt(process.argv[process.argv.indexOf('--days') + 1] || '3', 10);
const DAY_NAMES    = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Parse YAML-like front-matter from a markdown string */
function parseFrontMatter(content) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return {};
  const result = {};
  for (const line of match[1].split('\n')) {
    const kv = line.match(/^(\w[\w_-]*):\s*(.+)$/);
    if (kv) {
      let val = kv[2].trim().replace(/^['"]|['"]$/g, '');
      // coerce booleans and numbers
      if (val === 'true')  val = true;
      else if (val === 'false') val = false;
      else if (!isNaN(val) && val !== '') val = parseFloat(val);
      result[kv[1]] = val;
    }
  }
  return result;
}

/**
 * Given a bill object, return the next due Date (or null if can't determine).
 * Supports:
 *   due_day         (integer 1-31)  → monthly
 *   due_day_of_week (string name or 0-6) → next matching weekday
 */
function nextDueDate(bill, from) {
  const today = new Date(from);
  today.setHours(0, 0, 0, 0);

  // Weekly bill
  if (bill.due_day_of_week !== undefined) {
    const target = typeof bill.due_day_of_week === 'number'
      ? bill.due_day_of_week
      : DAY_NAMES.findIndex(d => d.toLowerCase() === String(bill.due_day_of_week).toLowerCase());
    if (target === -1) return null;
    const d = new Date(today);
    const diff = (target - d.getDay() + 7) % 7 || 7;
    d.setDate(d.getDate() + diff);
    return d;
  }

  // Monthly bill
  if (bill.due_day !== undefined) {
    const dom = parseInt(bill.due_day, 10);
    if (isNaN(dom)) return null;
    // Try this month first, then next month
    const candidates = [0, 1].map(offset => {
      const d = new Date(today.getFullYear(), today.getMonth() + offset, dom);
      return d;
    });
    // Pick first one that is >= today
    return candidates.find(d => d >= today) || null;
  }

  return null;
}

/** Format a Date as "Mon Mar 1" */
function fmtDate(d) {
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

/** Days between two dates (floor) */
function daysUntil(target, from) {
  const t = new Date(target); t.setHours(0,0,0,0);
  const f = new Date(from);   f.setHours(0,0,0,0);
  return Math.round((t - f) / 86400000);
}

// ── Main ──────────────────────────────────────────────────────────────────────
function main() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Validate directory
  if (!fs.existsSync(BILLS_DIR)) {
    process.stderr.write(`[bill_reminders] Bills directory not found: ${BILLS_DIR}\n`);
    process.exit(0);
  }

  const stat = fs.statSync(BILLS_DIR);
  if (!stat.isDirectory()) {
    process.stderr.write(`[bill_reminders] Bills path is not a directory: ${BILLS_DIR}\n`);
    process.exit(0);
  }

  // Read all .md files
  let files;
  try {
    files = fs.readdirSync(BILLS_DIR).filter(f => f.endsWith('.md') && !f.startsWith('.'));
  } catch (err) {
    process.stderr.write(`[bill_reminders] Could not read bills directory: ${err.message}\n`);
    process.exit(0);
  }

  if (!files.length) {
    process.stdout.write('No bill files found.\n');
    process.exit(0);
  }

  // Parse each bill file
  const due = [];
  for (const file of files) {
    const filePath = path.join(BILLS_DIR, file);
    let content;
    try {
      const fileStat = fs.statSync(filePath);
      if (!fileStat.isFile()) continue;          // skip subdirectories
      content = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      process.stderr.write(`[bill_reminders] Skipping ${file}: ${err.message}\n`);
      continue;
    }

    const bill = parseFrontMatter(content);
    if (!bill.name) continue;                    // skip files without front-matter

    const dueDate = nextDueDate(bill, today);
    if (!dueDate) continue;

    const days = daysUntil(dueDate, today);
    if (days < 0 || days > LOOK_AHEAD) continue;

    due.push({
      name:     bill.name,
      amount:   bill.amount != null ? bill.amount : (bill.amount_avg != null ? bill.amount_avg : '?'),
      dueDate,
      days,
      autoPay:  bill.auto_pay,
      notes:    bill.notes || '',
    });
  }

  if (!due.length) {
    // Nothing due — silent exit (cron will send NO_REPLY)
    process.exit(0);
  }

  // Sort by urgency
  due.sort((a, b) => a.days - b.days);

  // Build output
  const lines = [
    `📅 **Upcoming Bills — Next ${LOOK_AHEAD} Days**\n`,
    '| Bill | Amount | Due | Auto-pay | |',
    '|------|--------|-----|----------|---|',
  ];

  for (const b of due) {
    const urgency  = b.days === 0 ? '🔴 TODAY' : b.days === 1 ? '⚠️ Tomorrow' : `🔔 ${b.days}d`;
    const amtStr   = b.amount === '?' ? 'check stmt' : `$${parseFloat(b.amount).toFixed(2)}`;
    const autoStr  = b.autoPay ? '✅ Yes' : '❌ No';
    const dateStr  = b.days === 0 ? 'Today' : b.days === 1 ? 'Tomorrow' : fmtDate(b.dueDate);
    lines.push(`| ${b.name} | ${amtStr} | ${dateStr} | ${autoStr} | ${urgency} |`);
  }

  if (due.some(b => !b.autoPay && b.days <= 2)) {
    lines.push('\n> ⚠️ One or more bills require **manual payment** — don\'t forget!');
  }

  process.stdout.write(lines.join('\n') + '\n');
}

main();
