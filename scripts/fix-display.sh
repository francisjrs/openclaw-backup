#!/bin/bash
# Fix DISPLAY + XAUTHORITY for openclaw-node so Playwright Chromium can start
set -e

DROPIN_DIR="$HOME/.config/systemd/user/openclaw-node.service.d"
mkdir -p "$DROPIN_DIR"

cat > "$DROPIN_DIR/display.conf" << 'EOF'
[Service]
Environment=DISPLAY=:10
Environment=XAUTHORITY=/home/framos/.Xauthority
EOF

systemctl --user daemon-reload
systemctl --user restart openclaw-node

echo "Done! openclaw-node restarted with DISPLAY=:10 and XAUTHORITY"
