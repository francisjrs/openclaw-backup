#!/usr/bin/env node
/**
 * mermaid-gen.js
 * Generates a mermaid.live shareable URL from Mermaid diagram code.
 *
 * Usage:
 *   echo "flowchart TD\n  A-->B" | node mermaid-gen.js
 *   node mermaid-gen.js --code "flowchart TD\n  A-->B"
 *   node mermaid-gen.js --file diagram.mmd
 *
 * Output:
 *   https://mermaid.live/edit#base64:<encoded>
 */

const fs = require('fs');

function generateMermaidUrl(code, theme = 'default') {
  const payload = JSON.stringify({
    code: code.trim(),
    mermaid: { theme }
  });
  const encoded = Buffer.from(payload).toString('base64');
  const editUrl = `https://mermaid.live/edit#base64:${encoded}`;
  const viewUrl = `https://mermaid.live/view#base64:${encoded}`;
  return { editUrl, viewUrl, encoded };
}

// Parse args
const args = process.argv.slice(2);
let code = null;

if (args.includes('--file')) {
  const idx = args.indexOf('--file');
  const filePath = args[idx + 1];
  code = fs.readFileSync(filePath, 'utf8');
} else if (args.includes('--code')) {
  const idx = args.indexOf('--code');
  code = args[idx + 1].replace(/\\n/g, '\n');
} else {
  // Read from stdin
  const stdin = fs.readFileSync('/dev/stdin', 'utf8');
  if (stdin.trim()) code = stdin;
}

if (!code) {
  console.error('Usage: node mermaid-gen.js --code "..." | --file diagram.mmd | <stdin>');
  process.exit(1);
}

const { editUrl, viewUrl } = generateMermaidUrl(code);
console.log('\n🔗 Edit URL (you can modify the diagram):');
console.log(editUrl);
console.log('\n👁️  View URL (read-only, clean):');
console.log(viewUrl);
