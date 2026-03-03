# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod

### Notes

- obsidian-vault → /home/node/obsidian-vault
```

## Local Setup

### Notes

- Obsidian vault path: `/home/node/obsidian-vault`
- Treat this as the default directory for saving/retrieving notes and useful reference docs for Franco.
- When Franco says to "save a note" (or similar), write it in this vault unless he specifies a different location.

### Nodes

- **bot-server** → Linux box (Ubuntu x86_64), node host conectado al gateway
  - Capabilities: `browser`, `system`
  - 65 safeBins disponibles sin aprobación (ls, cat, grep, docker, git, curl, etc.)
  - Cualquier otro comando requiere aprobación de Franco
  - Útil para: browser automation en el server, exec de comandos, acceder a Circle.so sin relay

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Email Rules

- **ALWAYS show the draft first** before sending any email
- Wait for Franco's explicit approval ("send it", "looks good", etc.)
- Never send without human-in-the-loop confirmation
- This applies to replies, new emails, and drafts

## Mermaid Diagrams

- **Always save to Obsidian** when generating diagrams — use `--save-obsidian` flag
- Script: `/app/skills/mermaid/scripts/mermaid-gen.js`
- Vault folder: `Diagrams/` (auto-created)
- Each diagram produces: `.md` note (with embedded PNG + mermaid source) and `.png` image
- Use descriptive kebab-case `--name`, e.g. `--name "media-server-architecture"`
- PNG rendered via mermaid.ink API (no extra deps)
- Syncthing syncs `Diagrams/` to Franco's Mac automatically

### Quick command
```bash
node /app/skills/mermaid/scripts/mermaid-gen.js \
  --code "flowchart TD\n  A-->B" \
  --save-obsidian \
  --name "descriptive-name"
```
