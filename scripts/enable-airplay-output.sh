#!/usr/bin/env bash
# Optional: discover AirPlay speakers on an existing PipeWire desktop.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$EUID" -eq 0 ]]; then
  echo 'Run on the Pi as the desktop user, without sudo.' >&2
  exit 1
fi
if ! systemctl --user is-active --quiet pipewire; then
  echo 'An active PipeWire desktop session is required. No audio configuration changed.' >&2
  exit 1
fi
raop_module="$(find /usr/lib -name libpipewire-module-raop-discover.so -print -quit 2>/dev/null || true)"
if [[ -z "$raop_module" ]]; then
  echo 'The PipeWire RAOP discovery module is missing. Install your OS package providing libpipewire-module-raop-discover.so first.' >&2
  exit 1
fi
mkdir -p "$HOME/.config/pipewire/pipewire.conf.d"
cat > "$HOME/.config/pipewire/pipewire.conf.d/80-frame-airplay.conf" <<'EOF'
context.modules = [
  { name = libpipewire-module-raop-discover
    flags = [ ifexists nofail ]
    args = { }
  }
]
EOF
echo 'AirPlay discovery configured. Log out and back in (or reboot) to activate it.'
echo 'Then in Kodi System > Audio, select the discovered speaker through the PulseAudio/PipeWire backend.'
echo 'Use PCM stereo (disable passthrough). Availability depends on speaker compatibility and Kodi build.'
echo 'To undo: remove ~/.config/pipewire/pipewire.conf.d/80-frame-airplay.conf and log in again.'
