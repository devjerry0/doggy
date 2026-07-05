#!/usr/bin/env bash
# Set up a Bluetooth speaker on the doggy Pi so it AUTO-RECONNECTS across power
# loss — even for cheap "Just Works" speakers whose bond never persists (see
# scripts/bt-agent-daemon.py for the store_hint=0 explanation).
#
# What it does (all idempotent):
#   - installs pi-bluetooth (Pi 4 onboard BT firmware) + adds the user to the
#     `bluetooth` group
#   - BlueZ: JustWorksRepairing=always + reconnect policy (/etc/bluetooth/main.conf)
#   - WirePlumber: disable bluez seat-monitoring so A2DP endpoints load headless
#   - deploys bt-agent-daemon.py + installs the doggy-bt.service (persistent agent
#     + reconnect loop, runs as the app user so it can reach that user's PipeWire
#     A2DP endpoint — running it as root gives avdtp "Permission denied")
#   - runs the one-time interactive pair (you must put the speaker in pairing mode)
#
# IMPORTANT: run this BEFORE harden-pi.sh — installing pi-bluetooth needs apt
# (internet), which the egress firewall later blocks.
#
# Usage:   ./scripts/setup-bt-speaker.sh <user@host> <speaker_mac>
# Example: ./scripts/setup-bt-speaker.sh doggy@doggypi.local AA:BB:CC:DD:EE:FF
set -euo pipefail

TARGET="${1:?usage: setup-bt-speaker.sh <user@host> <speaker_mac>}"
MAC="${2:?usage: setup-bt-speaker.sh <user@host> <speaker_mac>   (e.g. AA:BB:CC:DD:EE:FF)}"
USER_NAME="${TARGET%@*}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Setting up BT speaker $MAC on $TARGET"

# Ship the two helper scripts to the Pi user's home.
scp -q "$HERE/bt-agent-daemon.py" "$HERE/bt-pair.py" "$TARGET:~/"

ssh "$TARGET" "MAC='$MAC' USER_NAME='$USER_NAME' bash -s" <<'REMOTE'
set -euo pipefail

echo "==> pi-bluetooth + bluetooth group"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq pi-bluetooth || true
fi
sudo usermod -aG bluetooth "$USER_NAME"

echo "==> BlueZ: JustWorksRepairing + reconnect policy (edit main.conf in place)"
# Stock main.conf ships these keys commented; uncomment+set them by key name.
sudo sed -i \
  -e 's/^[#[:space:]]*JustWorksRepairing[[:space:]]*=.*/JustWorksRepairing = always/' \
  -e 's/^[#[:space:]]*AutoEnable[[:space:]]*=.*/AutoEnable = true/' \
  -e 's/^[#[:space:]]*ReconnectAttempts[[:space:]]*=.*/ReconnectAttempts = 7/' \
  -e 's/^[#[:space:]]*ReconnectIntervals[[:space:]]*=.*/ReconnectIntervals = 1,2,4,8,16,32,64/' \
  /etc/bluetooth/main.conf
# JustWorksRepairing is the critical one — if it wasn't present to uncomment, add it.
grep -qE '^JustWorksRepairing = always' /etc/bluetooth/main.conf \
  || sudo sed -i '/^\[General\]/a JustWorksRepairing = always' /etc/bluetooth/main.conf

echo "==> WirePlumber: load bluez A2DP endpoints headless (no seat/session)"
mkdir -p "$HOME/.config/wireplumber/wireplumber.conf.d"
cat > "$HOME/.config/wireplumber/wireplumber.conf.d/bluetooth.conf" <<'WP'
wireplumber.profiles = {
  main = {
    monitor.bluez.seat-monitoring = disabled
  }
}
WP

echo "==> persistent-agent reconnect service (runs as $USER_NAME, not root)"
sudo tee /etc/systemd/system/doggy-bt.service >/dev/null <<UNIT
[Unit]
Description=Persistent BT agent + speaker reconnect
After=bluetooth.service
Wants=bluetooth.service

[Service]
User=$USER_NAME
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u "$USER_NAME")
Environment=DOGGY_BT_MAC=$MAC
ExecStart=/usr/bin/python3 $HOME/bt-agent-daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl restart bluetooth
sudo systemctl daemon-reload
sudo systemctl enable doggy-bt
REMOTE

echo
echo "==> Config done. Now the ONE-TIME pairing:"
echo "    1) Put the speaker in pairing mode (hold its BT button until the LED blinks fast)."
read -r -p "    2) Press Enter here once it's blinking... " _
ssh "$TARGET" "XDG_RUNTIME_DIR=/run/user/\$(id -u) DOGGY_BT_MAC='$MAC' python3 ~/bt-pair.py"
ssh "$TARGET" "sudo systemctl restart doggy-bt"

echo
echo "==> Done. The speaker will auto-reconnect on every boot (agent daemon)."
echo "    Verify with a power cycle: it reconnects ~10-15s after boot, no touches."
echo "    NOTE: keyless speakers store no link key; the persistent agent is what"
echo "          makes hands-off reconnect work. See scripts/bt-agent-daemon.py."
