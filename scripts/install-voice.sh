#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$EUID" -eq 0 ]]; then
  echo 'Run on the Pi as your regular desktop user, without sudo.' >&2; exit 1
fi
frame_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$frame_dir" =~ [[:space:]%\\\"] ]]; then
  echo 'The project path must not contain spaces, quotes, percent signs or backslashes.' >&2;exit 1
fi
cd "$frame_dir"
sudo apt-get update
sudo apt-get install -y python3-venv libportaudio2 libasound2-plugins
python3 -m venv .voice-venv
.voice-venv/bin/python -m pip install 'vosk>=0.3.45,<0.4' 'sounddevice>=0.5,<0.6'
.voice-venv/bin/python scripts/download-voice-model.py
.voice-venv/bin/python voice_worker.py --list-devices
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/frame-voice.service" <<EOF
[Unit]
Description=Hey Hyper offline microphone
After=pipewire.service pipewire-pulse.service

[Service]
WorkingDirectory=$frame_dir
EnvironmentFile=-$frame_dir/voice.env
ExecStart=$frame_dir/.voice-venv/bin/python $frame_dir/voice_worker.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now frame-voice.service
systemctl --user restart frame-voice.service
printf '\nHey Hyper installed. Check microphone status in the Frame portal.\n'
printf 'If the wrong microphone is selected, set FRAME_MIC_DEVICE in voice.env and restart frame-voice.\n'
printf 'The model is now local. Internet is only used for explicit web-search commands.\n'
