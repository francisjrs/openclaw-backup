#!/usr/bin/env node
/**
 * Google Calendar OAuth setup — run once to authorize.
 * Starts a local server on port 8765 to capture the OAuth callback.
 * Token saved to: /home/node/.openclaw/workspace/scripts/.secrets/gcal_token.json
 */

const { google } = require('googleapis');
const http = require('http');
const url = require('url');
const fs = require('fs');
const path = require('path');

const CREDENTIALS_PATH = '/home/node/.config/gogcli/credentials.json';
const TOKEN_PATH = '/home/node/.openclaw/workspace/scripts/.secrets/gcal_token.json';
const PORT = 8765;
const REDIRECT_URI = `http://localhost:${PORT}/oauth2callback`;
const SCOPES = ['https://www.googleapis.com/auth/calendar'];

const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH));
const oauth2Client = new google.auth.OAuth2(
  creds.client_id,
  creds.client_secret,
  REDIRECT_URI
);

// If token already exists, just verify it works
if (fs.existsSync(TOKEN_PATH)) {
  const token = [TOKEN]
  oauth2Client.setCredentials(token);
  const calendar = google.calendar({ version: 'v3', auth: oauth2Client });
  calendar.calendarList.list({}, (err, res) => {
    if (err) {
      console.log('Token invalid or expired. Re-authorizing...');
      startAuthFlow();
    } else {
      console.log('Token OK. Calendars:');
      res.data.items.forEach(c => console.log(` - ${c.summary} (${c.id})`));
    }
  });
} else {
  startAuthFlow();
}

function startAuthFlow() {
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
    prompt: 'consent'
  });

  console.log('\n=== GOOGLE CALENDAR AUTHORIZATION ===');
  console.log('Open this URL in your browser and authorize:');
  console.log('\n' + authUrl + '\n');
  console.log('Waiting for callback on http://localhost:' + PORT + ' ...');

  const server = http.createServer(async (req, res) => {
    const parsedUrl = url.parse(req.url, true);
    if (parsedUrl.pathname === '/oauth2callback') {
      const code = parsedUrl.query.code;
      if (code) {
        try {
          const { tokens } = await oauth2Client.getToken(code);
          oauth2Client.setCredentials(tokens);
          fs.mkdirSync(path.dirname(TOKEN_PATH), { recursive: true });
          fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens, null, 2));
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end('<h2>✅ Authorization successful! You can close this tab.</h2>');
          console.log('\nToken saved to: ' + TOKEN_PATH);
          server.close();
        } catch (err) {
          res.writeHead(500);
          res.end('Error: ' + err.message);
          server.close();
        }
      } else {
        res.writeHead(400);
        res.end('Missing code parameter');
        server.close();
      }
    }
  });

  server.listen(PORT, () => {
    console.log('Local callback server running on port ' + PORT);
  });
}
