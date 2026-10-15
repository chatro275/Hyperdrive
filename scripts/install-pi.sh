#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -s)" != Linux || ! -f /etc/os-release ]]; then
  echo 'Run this installer on your Raspberry Pi, as your regular Pi user.' >&2
  exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
  echo 'Run without sudo: bash scripts/install-pi.sh (it requests sudo when needed).' >&2
  exit 1
fi
frame_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$frame_dir"
# Keep generated systemd and desktop paths unambiguous.
if [[ "$frame_dir" =~ [[:space:]%\\\"] ]]; then
  echo 'Place HyperMedia in a path without spaces, percent signs, quotes or backslashes.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3 kodi pulseaudio-utils
python3 -m unittest discover -s tests -v
python3 scripts/package-kodi.py
mkdir -p "$frame_dir/movies" "$HOME/.config/autostart"
frame_unit="$(mktemp)"
trap 'rm -f "$frame_unit"' EXIT
cat > "$frame_unit" <<EOF
[Unit]
Description=Hyperdrive local portal and Frame movie library
After=network.target

[Service]
User=$(id -un)
WorkingDirectory=$frame_dir
EnvironmentFile=-$frame_dir/frame.env
Environment=FRAME_MANAGED=1
ExecStart=/usr/bin/python3 $frame_dir/server.py
Restart=on-failure
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$frame_unit" /etc/systemd/system/frame.service
sudo systemctl daemon-reload
sudo systemctl enable frame.service
sudo systemctl restart frame.service
cat > "$HOME/.config/autostart/frame-kodi.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Hyperdrive
Comment=Start Hyperdrive at desktop login
Exec=kodi --standalone
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
printf '\nHyperdrive portal is running. Kodi will launch at your next desktop login.\n'
printf 'On the TV, open Kodi now from the desktop menu.\n'
printf 'Enable Settings > System > Add-ons > Unknown sources.\n'
printf 'Then Add-ons > Install from zip file > Home folder > HyperMedia > frame-kodi.zip.\n'
printf 'Also install hyperdrive-kodi.zip, then restart Kodi. Hyperdrive opens first; select Frame to launch your cinema.\n'
printf 'Portal: http://raspberrypi.local:8080 (or use the IP from hostname -I).\n'
printf 'Enable HDMI-CEC on your TV and in Kodi > System > Input > Peripherals.\n'
