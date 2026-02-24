# Reminder Preferences

## Behavior
- When Franco asks for a reminder, **confirm the time and frequency** before setting it
- Support **one-time** and **recurring** reminders via cron
- If Franco says **"remind me tomorrow"** with no time → default to **9am**
- If Franco says **"snooze 30 min"** (or any duration) → create a one-shot cron job N minutes from now

## Recurring Reminders Set Up
- **Exercise** — daily at 7:00 AM and 6:00 PM (America/Chicago)
  - Snooze-capable: if Franco says "snooze 30 min", create a one-shot reminder at current time + 30 min

## Snooze Flow
1. Franco says "snooze 30 min" (or any duration)
2. I get current time
3. I create a one-time `at` cron job for current time + that duration
4. I confirm: "Snoozed! I'll remind you again at [time]"
