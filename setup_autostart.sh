#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/gesture-control-pi.desktop" <<EOD
[Desktop Entry]
Type=Application
Name=Gesture Control Pi
Exec=$ROOT/run_pi.sh
Path=$ROOT
Terminal=false
X-GNOME-Autostart-enabled=true
EOD
printf 'Configured desktop-session autostart. Set show_preview=false in gesture_config.json for kiosk mode.\n'
