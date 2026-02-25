#!/usr/bin/env node
/**
 * Google Calendar Bill Manager
 * Manages recurring bill events in the Pagar calendar.
 * Usage:
 *   node gcal_bills.js list
 *   node gcal_bills.js sync          -- create/update all bills from state
 *   node gcal_bills.js add <json>    -- add single bill
 *   node gcal_bills.js remove <title>
 */

const { google } = require('googleapis');
const fs = require('fs');

const CREDS_PATH = '/home/node/.config/gogcli/credentials.json';
const TOKEN_PATH = '/home/node/.openclaw/workspace/scripts/.secrets/gcal_token.json';
const STATE_PATH = '/home/node/.openclaw/workspace/state/rocket_money_state.json';
const PAGAR_CAL_ID = 'j1nlm9okach2cuugob8n2ig24s@group.calendar.google.com';
const BILL_TAG = '[BILL]'; // prefix to identify managed events

function getCalendar() {
  const creds = JSON.parse(fs.readFileSync(CREDS_PATH));
  const token = [TOKEN]
  const auth = new google.auth.OAuth2(creds.client_id, creds.client_secret, 'http://localhost');
  auth.setCredentials(token);
  // Auto-save refreshed tokens
  auth.on('tokens', (tokens) => {
    const current = JSON.parse(fs.readFileSync(TOKEN_PATH));
    fs.writeFileSync(TOKEN_PATH, JSON.stringify({ ...current, ...tokens }, null, 2));
  });
  return google.calendar({ version: 'v3', auth });
}

function makeRecurringEvent(bill) {
  // bill: { title, amount, dayOfMonth, color, reminders, notes }
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(bill.dayOfMonth).padStart(2, '0');

  // Find next occurrence
  let startDate = new Date(`${year}-${month}-${day}`);
  if (startDate < now) {
    startDate.setMonth(startDate.getMonth() + 1);
  }
  const dateStr = startDate.toISOString().split('T')[0];

  return {
    summary: `${BILL_TAG} ${bill.title} — $${bill.amount}`,
    description: [
      `💳 Bill: ${bill.title}`,
      `💵 Amount: $${bill.amount}`,
      bill.notes ? `📝 Notes: ${bill.notes}` : '',
      ``,
      `Managed by Robotina Finance Agent`,
    ].filter(Boolean).join('\n'),
    start: { date: dateStr },
    end: { date: dateStr },
    recurrence: ['RRULE:FREQ=MONTHLY'],
    colorId: bill.colorId || '6', // tangerine
    reminders: {
      useDefault: false,
      overrides: bill.reminders || [
        { method: 'popup', minutes: 3 * 24 * 60 }, // 3 days before
        { method: 'popup', minutes: 24 * 60 },      // 1 day before
      ],
    },
  };
}

function makeWeeklyEvent(bill) {
  // bill: { title, amount, dayOfWeek (0=Sun..6=Sat), color, reminders, notes }
  const now = new Date();
  let startDate = new Date(now);
  const targetDay = bill.dayOfWeek ?? 5; // default Friday
  const diff = (targetDay - startDate.getDay() + 7) % 7;
  startDate.setDate(startDate.getDate() + diff);
  const dateStr = startDate.toISOString().split('T')[0];
  const days = ['SU','MO','TU','WE','TH','FR','SA'];

  return {
    summary: `${BILL_TAG} ${bill.title} — $${bill.amount}`,
    description: [
      `💳 Bill: ${bill.title}`,
      `💵 Amount: $${bill.amount}`,
      bill.notes ? `📝 Notes: ${bill.notes}` : '',
      ``,
      `Managed by Robotina Finance Agent`,
    ].filter(Boolean).join('\n'),
    start: { date: dateStr },
    end: { date: dateStr },
    recurrence: [`RRULE:FREQ=WEEKLY;BYDAY=${days[targetDay]}`],
    colorId: bill.colorId || '5', // banana
    reminders: {
      useDefault: false,
      overrides: bill.reminders || [
        { method: 'popup', minutes: 24 * 60 }, // 1 day before
      ],
    },
  };
}

async function listManagedEvents(cal) {
  const res = await cal.events.list({
    calendarId: PAGAR_CAL_ID,
    q: BILL_TAG,
    singleEvents: false,
    maxResults: 100,
  });
  return res.data.items || [];
}

async function syncBills(bills) {
  const cal = getCalendar();
  const existing = await listManagedEvents(cal);

  const results = [];
  for (const bill of bills) {
    const eventData = bill.weekly ? makeWeeklyEvent(bill) : makeRecurringEvent(bill);
    const title = eventData.summary;

    // Check if already exists
    const match = existing.find(e => e.summary === title);
    if (match) {
      // Update
      await cal.events.update({ calendarId: PAGAR_CAL_ID, eventId: match.id, requestBody: eventData });
      results.push({ action: 'updated', title });
    } else {
      // Create
      const created = await cal.events.insert({ calendarId: PAGAR_CAL_ID, requestBody: eventData });
      results.push({ action: 'created', title, id: created.data.id });
    }
  }
  return results;
}

async function removeEvent(titleFragment) {
  const cal = getCalendar();
  const existing = await listManagedEvents(cal);
  const match = existing.find(e => e.summary.toLowerCase().includes(titleFragment.toLowerCase()));
  if (!match) { console.log('Not found:', titleFragment); return; }
  await cal.events.delete({ calendarId: PAGAR_CAL_ID, eventId: match.id });
  console.log('Removed:', match.summary);
}

// --- MAIN ---
const cmd = process.argv[2];

if (cmd === 'list') {
  const cal = getCalendar();
  listManagedEvents(cal).then(events => {
    if (!events.length) { console.log('No managed bill events found.'); return; }
    events.forEach(e => console.log(`  [${e.id}] ${e.summary}`));
  });
} else if (cmd === 'remove') {
  removeEvent(process.argv[3] || '');
} else if (cmd === 'sync' || !cmd) {
  // Default bill list — derived from Rocket Money transactions
  const bills = [
    { title: 'TXU Energy (Electricity)',   amount: 206.00, dayOfMonth: 15, colorId: '11', notes: 'Electric bill — varies seasonally' },
    { title: 'ATMOS ENERGY (Gas)',          amount: 194.75, dayOfMonth: 15, colorId: '11', notes: 'Gas bill — higher in winter (~$113 avg)' },
    { title: 'Paloma Lake MUD (Water)',     amount: 66.36,  dayOfMonth: 18, colorId: '11', notes: 'Water bill, Round Rock MUD' },
    { title: 'Real Green Services (Lawn)',  amount: 67.57,  dayOfMonth: 14, colorId: '2',  notes: 'Monthly lawn care' },
    { title: 'Rocket Money Premium',        amount: 6.40,   dayOfMonth: 20, colorId: '8',  notes: 'Subscription' },
    { title: 'Chase Credit Card',           amount: 0,      dayOfMonth: 17, colorId: '6',  notes: 'Amount varies — check statement' },
    { title: 'Apple Card',                  amount: 0,      dayOfMonth: 1,  colorId: '6',  notes: 'Amount varies — check statement' },
    // Weekly
    { title: 'Amaya Babysitter',            amount: 330.00, dayOfWeek: 5,   colorId: '5',  notes: 'Weekly childcare — Fridays', weekly: true },
  ];

  syncBills(bills).then(results => {
    results.forEach(r => console.log(`  ${r.action === 'created' ? '✅' : '🔄'} ${r.action}: ${r.title}`));
    console.log('\nDone! All bills synced to Pagar calendar.');
  }).catch(err => console.error('Error:', err.message));
}
