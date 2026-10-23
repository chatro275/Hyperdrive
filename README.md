# Hyperdrive

Hyperdrive is a Raspberry Pi TV launcher and USB file portal. Frame is its separate movie app, controlled with a TV remote through Kodi/HDMI-CEC.

## GitHub updates (2.5)

Source and releases: https://github.com/chatro275/Hyperdrive

Every push to main runs the tests. When VERSION changes, a successful build publishes a GitHub release with the portal update and both Kodi installers. Release versions are never overwritten. In Frame's web Settings, choose **Check GitHub for updates → Download update**, then approve through **Frame → Settings → Software updates** on the TV and restart the Pi. The Pi checks the GitHub asset SHA-256 digest, validates the bundle, and keeps application backups. No manual ZIP transfer is needed after this setup.

### Move an existing 2.4.x Pi to GitHub updates

After the first GitHub release is published, run on the Pi:

```bash
curl -fL https://raw.githubusercontent.com/chatro275/Hyperdrive/main/scripts/github-update.py -o /tmp/hyperdrive-update.py
python3 /tmp/hyperdrive-update.py --root ~/HyperMedia
```

Approve the downloaded update on the TV, then restart the Pi. This bridge needs the 2.4 updater; older 2.2/2.3 installations need the preparatory upgrade described below. Source code, tests and release workflows go to GitHub; movies, databases, environment files, microphone settings, health logs and private keys do not.

The default release repository is `chatro275/Hyperdrive`. An override may be set as `HYPERDRIVE_GITHUB_REPO=owner/repository` in frame.env. Private repositories additionally require a read-only `HYPERDRIVE_GITHUB_TOKEN` in that file (never entered into the web UI or committed). Internet is required for release checks/downloads; local movies still work offline.

GitHub hosts code and releases, not the live Python/USB/TV server. On the home network use **http://raspberrypi.local:8080** and **http://raspberrypi.local:8080/frame** instead of a numeric IP. Remote access needs a separate authenticated connection; no public dashboard or router port forwarding is configured by this release.

# Hyperdrive with Frame Cinema

Hyperdrive 2.4 is now the main TV launcher and web home. Frame is its separate movie app. The portal accepts all file types under Files; supported videos appear in Frame. See `HYPERDRIVE-SETUP.md` for the two-stage upgrade and USB setup.

# Frame — Raspberry Pi TV box

Frame has two connected interfaces:

- **On the TV:** a fullscreen Kodi add-on with a remote-friendly movie library, watchlist, resume playback, and native HDMI video/audio output.
- **On your phone or Mac:** a local portal for uploading videos, editing their details, saving a watchlist, and requesting playback on the TV.

The browser does not play your movies. Kodi on the Pi opens the local files. The TV remote controls Kodi through HDMI-CEC, including navigation and playback. Hardware decoding and supported resolutions depend on the Pi, Kodi build and video codec.

## Upgrade your current installation

On your Mac, copy the updated source to your Pi:

```sh
scp -r /Users/lindsaytrombley/HyperMedia hyper@raspberrypi.local:~/
```

In **Raspberry Pi Connect → Remote shell**:

```sh
cd ~/HyperMedia
bash scripts/install-pi.sh
```

Run as your regular Pi user, not with `sudo`. The installer requests sudo for packages and the system service. It installs Python and Kodi, runs server tests, builds the add-on ZIP, updates/restarts the Frame portal service, and adds Kodi to desktop autostart. Existing `movies/` and `library.db` are preserved. Close an old manually launched `python3 server.py` first if it is still using port 8080.

This installer targets **Raspberry Pi OS with a desktop**, Python 3.9+, and Kodi 19+. No OS reflash is needed, and Raspberry Pi Connect remains installed. A Lite/headless image needs a different Kodi launch setup; the installer does not provision a desktop or enable desktop autologin. Exact Pi model and OS must be checked before assuming video acceleration works.

## One-time setup on the TV

1. Connect the Pi directly to the TV with HDMI (start with HDMI0 if your Pi has two outputs).
2. Open **Kodi** from the Pi's desktop application menu. Use a keyboard/mouse for setup if your remote is not working yet.
3. In Kodi, enable **Settings → System → Add-ons → Unknown sources** so you can install this local add-on.
4. Choose **Add-ons → Install from zip file → Home folder → HyperMedia → frame-kodi.zip**.
5. Frame Cinema should open automatically when its service starts. You can also open it from **Add-ons → Program add-ons → Frame Cinema**. Keep Kodi's default **Estuary** skin, which supplies Frame's fonts.
6. Enable **HDMI-CEC** in your TV settings. Common names include Samsung **Anynet+**, LG **SIMPLINK**, and Sony **BRAVIA Sync**. In Kodi, check **Settings → System → Input → Peripherals → CEC Adapter** is enabled. You may need the Advanced settings level.
7. Try the TV remote: arrows move focus, OK selects/plays, Back returns, and playback buttons control the movie. Available buttons vary by TV. During playback, OK opens Kodi's playback controls. Back may return to the library while playback continues; use Stop to end playback.

The add-on opens whenever Kodi starts and the Frame server is available. Kodi is configured to start on desktop login. For unattended boot, enable desktop autologin through Raspberry Pi Configuration if desired. If desktop autostart is unsupported by your OS session, launch Kodi from the desktop and check that OS's autostart mechanism.

Official references: [Kodi HDMI-CEC](https://kodi.wiki/view/CEC), [Kodi add-on installation](https://kodi.wiki/view/Add-on_manager), [Raspberry Pi configuration](https://www.raspberrypi.com/documentation/computers/configuration.html).

## Upload and watch

Open **http://raspberrypi.local:8080**, or **http://192.168.0.194:8080** while your Pi retains that address.

1. Select **Manage library → Choose movies to upload**.
2. Choose one or more videos. The portal shows upload progress and available disk space. Keep the tab open until completion; Cancel stops the current upload and remaining queue.
3. On the TV, select **Refresh library** and pick a film with the remote. You can also select **Play on TV** in the portal.

Uploads stream to temporary files instead of being held in RAM. Completed files are moved into the media folder and indexed. Incomplete transfers are cleaned up when the server detects the disconnect; duplicates get a new name instead of replacing an existing movie. There is a 100 GB per-file limit and a 256 MB free-space reserve. Uploads are not resumable; retry a failed upload. A server power failure can leave `.upload-*.part` files, which are ignored by scanning and can be removed manually.

Supported indexing extensions: MP4, M4V, MKV, WebM, MOV, AVI, TS. Actual playback depends on Kodi and the Pi's codec support. Frame does not transcode. Watch positions are saved approximately every five seconds while playing; watchlists and edits persist in `library.db`.

For files already on the Pi, copy them into `movies/` and select **Scan media folder**. Scanning does not remove database records for missing files. Frame reports a missing-file error if you try to play one.

## USB movie storage

By default, files go into `~/HyperMedia/movies`. To use another mounted folder, create `frame.env` in the project:

```ini
FRAME_MEDIA=/media/hyper/Movies
```

The path must be writable by the `hyper` account (or your actual Pi user). Then:

```sh
sudo systemctl restart frame
```

Ensure the disk is mounted before starting Frame. Changing folders does not migrate existing files or database records. Do not change the portal's default port 8080 without also changing `BASE` in the Kodi add-on's `common.py` and reinstalling its ZIP.

## Status and troubleshooting

The portal displays **TV connected** when the Kodi add-on is polling. **TV offline** means Kodi or its Frame service is not running; commands are rejected instead of unexpectedly playing later. Commands expire after 15 seconds. A successful play request means queued, not verified video/audio output; the portal's playing state updates when Kodi starts playback.

```sh
sudo systemctl status frame --no-pager
journalctl -u frame -n 50 --no-pager
```

Kodi diagnostics are normally in `~/.kodi/temp/kodi.log`. If the TV remote does not work, check CEC is enabled at both ends, try a direct HDMI connection without adapters/receivers, and confirm the CEC adapter appears in Kodi. A TV without working CEC needs a separate USB/Bluetooth remote.

To disable Kodi desktop autostart, remove `~/.config/autostart/frame-kodi.desktop`. To stop the portal, run `sudo systemctl disable --now frame`.

This is a trusted home-network portal with no login: devices that can reach it can upload, edit, stream files and control the TV. Do not port-forward it onto the internet. Playback and the TV interface work offline. The portal uses optional external fonts/landscape artwork with local styling fallbacks.

## Development and checks

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
python3 scripts/package-kodi.py
```

Server tests exercise uploads, duplicate handling, unsafe names, disk-space rejection, cross-origin requests, streaming ranges, TV command delivery/expiry, and offline/missing-file failures. Actual video output, Kodi GUI rendering, CEC mapping and autostart need verification on the Pi/TV hardware.

## Power, HDMI audio and AirPlay (Frame 2.1)

The TV sidebar now includes **Audio**, **Software updates**, and **Power**. The portal has **Sound & power** beneath the connection status.

- **Power:** Restart and shut down the Pi, with confirmation. Frame checks Kodi's reported OS permissions; unavailable actions remain disabled. It does not grant blanket sudo access. Shutdown disconnects the portal and requires powering the Pi on physically afterward. These controls power the Pi, not independently the TV.
- **HDMI:** Open **Audio → HDMI / speaker output settings**, then select **Audio → Audio output device** in Kodi's System settings. Choose the HDMI device connected to your TV/receiver. Volume, mute, and movie audio-track selection are available in Frame. When passthrough is enabled, use the TV/receiver volume; the portal disables its software volume slider.
- **AirPlay receiving:** **Audio → AirPlay receiver settings** opens Kodi's Services settings. Enable AirPlay and Zeroconf (under General, if required). Disable AirPlay video/picture support for modern iOS audio streaming. Set an AirPlay password there if desired, then choose Kodi from your phone/Mac's AirPlay audio destinations on the same network. This is audio reception, not modern screen mirroring or guaranteed AirPlay 2 support. Kodi's build must include AirPlay support.
- **AirPlay speaker output:** This is a separate optional path, supported through an existing PipeWire desktop with its RAOP discovery module. Run `bash scripts/enable-airplay-output.sh` on the Pi, then log out/in. It stops without changes if PipeWire/the module is missing. Select the discovered speaker in Kodi's System → Audio settings using its PulseAudio/PipeWire backend; use stereo PCM without passthrough. Not all speakers/authentication modes are supported. Wireless latency can affect movie lip-sync; adjust Kodi's playback audio offset if needed. HDMI remains the simplest direct TV output. Speaker discovery and playback require testing on your actual devices.

References: [Kodi audio settings](https://kodi.wiki/view/Settings/System/Audio), [Kodi AirPlay receiver](https://kodi.wiki/view/Settings/Services/Airplay), [PipeWire AirPlay discovery](https://docs.pipewire.org/page_module_raop_discover.html).

## Native application updates

For this first upgrade from 2.0, copy the updated project and rerun `bash scripts/install-pi.sh`, then reinstall `frame-kodi.zip` in Kodi and restart Kodi. This adds the update controls and enables automatic portal restarts under systemd.

Future updates do not require SCP:

1. Build a release from the new project source with `python3 scripts/package-update.py` (or obtain that generated bundle).
2. In the portal, open **Manage library → Software updates → Choose update ZIP**.
3. On the TV, select **Software updates**, review the version, and approve installation. Stop playback first.
4. The portal restarts automatically when installed as a managed service. Restart Kodi or the Pi to load the new TV code. If running the portal manually, restart it manually too.

Bundles contain only application files. Movies, `library.db`, environment settings and OS packages are not replaced. Both the project and installed Kodi add-on are updated. Frame validates paths, file checksums and Python syntax, binds approval to the reviewed bundle's digest, backs up overwritten files in `.updates/backups/`, and restores them if file installation fails. Checksums detect corruption; they are **not a publisher signature**, so approve only bundles you trust. This is a local bundle updater; no public automatic release feed is configured. It does not upgrade Kodi or Raspberry Pi OS.

Backups contain a `restore.json` map of destination files to their saved originals. File-write failures are rolled back automatically; power-loss recovery or an update that starts but malfunctions requires restoring that backup manually. Tests do not establish compatibility of future bundles. Application restarts and HDMI/CEC/AirPlay behavior must be checked on the Pi.

### Kodi reports “invalid structure”

Use **`script.frame-2.1.1.zip`** in Kodi's **Install from zip file**. It is the Kodi-only installer, rebuilt with explicit folder entries and validated manifest/entrypoints. `frame-kodi.zip` is an identical compatibility copy. **`frame-update-*.zip` is for the Frame web portal, not Kodi**; Kodi will reject its multi-file application layout.

Copy the new, uniquely named ZIP to the Pi and select that file without extracting or recompressing it. If Kodi still rejects it, the relevant lines in `~/.kodi/temp/kodi.log` are needed to distinguish a package-loading error from a version/platform issue.

## Hey Frame voice update (2.2.0)

Speech is recognized locally with Vosk and a small English model. Microphone audio is processed in memory and is not uploaded or recorded to disk. Say **“Hey Frame”**, then a command within eight seconds, or say both together:

- “Hey Frame, play Interstellar” (uses your own library; ambiguous titles are not played).
- “Hey Frame, pause” / “resume” / “stop”.
- “Hey Frame, mute” / “unmute” / “volume up” / “set volume to fifty”.
- “Hey Frame, show library” / “test sound”.
- “Hey Frame, search the web for Raspberry Pi” (requires internet).

Only explicit search commands send query text to Bing’s public search feed (with DuckDuckGo HTML search as a fallback). Results/snippets appear on the TV and portal; links can be opened on your phone/computer. This is web search, not a conversational AI or spoken-answer service. Network errors, provider blocking and response-format changes can make search unavailable, while local movie commands continue to work. No API key is required. Other room speech is not sent to the server until the wake phrase is recognized; the last accepted command is visible on the local portal. Power and software installation are deliberately not voice commands.

### Install this update on the existing Pi

The old updater only accepts its original fixed file list. The voice release adds new files, so use this order in **Manage library → Software updates**, approving each stage on the TV:

1. Upload **frame-updater-bootstrap-2.1.2.zip** first. This upgrades the updater while retaining the previous application. Wait for the portal to restart.
2. Upload **frame-update-2.2.0.zip**, approve on the TV, then restart Kodi/the Pi.
3. In Raspberry Pi Connect's remote shell, run the one-time microphone setup:

```sh
cd ~/HyperMedia
bash scripts/install-voice.sh
```

The setup installs dependencies, downloads the approximately 40 MB English speech model from the official Vosk site, and enables a user service that starts with your Pi user session. Internet is needed for this initial installation; wake phrase recognition and movie commands work offline afterward. Models/venv are kept outside application bundles. Raspberry Pi Zero/ARMv6 is not a supported voice target; usable recognition speed and accuracy depend on Pi model, microphone and background noise.

If your updater is not present, copy the complete updated project from the Mac, run `bash scripts/install-pi.sh`, install `script.frame-2.2.0.zip` in Kodi, then run the voice installer. Only the `script.frame-*.zip` package belongs in Kodi's Install from ZIP screen.

### Microphone selection and troubleshooting

```sh
cd ~/HyperMedia
.voice-venv/bin/python voice_worker.py --list-devices
systemctl --user status frame-voice --no-pager
journalctl --user -u frame-voice -n 30 --no-pager
```

It uses the default input device unless overridden. To select a listed input, put its index or unique name into `voice.env`, for example `FRAME_MIC_DEVICE=2`, then run `systemctl --user restart frame-voice`. Device indices can change after reboot; a unique name is preferable. If using a different model, set `FRAME_VOSK_MODEL` to its absolute folder path there too. No microphone permissions are granted to all users. The voice daemon runs as your desktop user to access that user's audio session.

Use **Listen for Hey Frame** in the portal to stop microphone capture at the next settings poll (normally within two seconds). To stop the microphone service entirely, run `systemctl --user stop frame-voice`; use `disable --now` to prevent automatic starts. Wake detection is local phrase recognition, not a trained dedicated wake-word model. Keep the mic away from the TV speakers: there is no acoustic echo cancellation and loud movie dialogue can impair recognition or cause false triggers. Feedback is shown on screen, not spoken aloud.

### Verify movie sound on the actual TV

In Frame's TV **Audio** menu (or via the portal's buttons):

1. Choose **Configure HDMI for TV speakers**, select the connected HDMI device and approve stereo PCM with passthrough off. This unmutes Kodi and raises its volume to 50% only if it was zero. Frame 2.2.2 also discovers HDMI outputs through the desktop PulseAudio/PipeWire server, selects the chosen output, unmutes it and moves existing Kodi audio to it. Nonzero volume is preserved. On existing installations, run `sudo apt-get install -y pulseaudio-utils` once in Raspberry Pi Connect to enable desktop audio control. If no HDMI device is exposed, Frame directs you to Kodi/System audio and the Pi desktop output selector instead of guessing a device ID. Desktop routing changes apply to the desktop default output as well as Kodi.
2. Stop any playback, set a comfortable TV/Kodi volume and choose **Test left / right sound**. You should hear a lower tone on the left and a higher tone on the right. Confirm on the TV only if you heard both. The portal distinguishes this human confirmation from an untested or changed output; it resets when the server restarts.
3. Play a real movie. Check its audio track in Frame's Audio menu. If test tones work but that movie is silent, check the file has an audio stream, try another track, and check Kodi's codec support/log. The sound test verifies a PCM path, not every movie codec.

No HDMI, microphone, CEC or speaker hardware is connected to the development Mac for end-to-end validation. Automated tests cover command gating, matching, update compatibility and audio-setting requests; actual audible output still requires the TV test above.

References: [Vosk models](https://alphacephei.com/vosk/models), [Vosk microphone example](https://github.com/alphacep/vosk-api/blob/master/python/example/test_microphone.py), [Kodi audio setup](https://kodi.wiki/view/Audio_quickstart_guide).

## Dashboard microphone menu (2.2.1)

Open **Hey Frame → Microphone settings** in the web dashboard. Select a listed input and press **Save microphone**; the voice worker switches inputs on its next settings poll. The meter shows recent peak input level while listening is enabled. It helps check that audio reaches the Pi; it is not a speech-recognition accuracy test. **System default / voice.env** uses `FRAME_MIC_DEVICE` if configured, otherwise the OS default.

**Refresh devices** restarts the user voice service through its existing restart policy so PortAudio can detect newly connected hardware. Model reload may take several seconds. Device indices can change after reboot. Missing/busy microphone errors are shown in the dashboard, and the worker keeps polling so you can choose another input.

Upload `frame-update-2.2.1.zip` through the web updater (after the earlier bootstrap if still on 2.1.x), approve on the TV, then run this once in Raspberry Pi Connect to replace the already-running 2.2.0 microphone process:

```sh
systemctl --user restart frame-voice
```

Reload the dashboard. Future versions of the new worker detect changes to their own source and restart automatically. If the voice service has never been installed, first run `bash scripts/install-voice.sh` from `~/HyperMedia`.


## System health (2.3.0)

Manage library → System health checks the database, media disk space, Kodi and microphone heartbeats every 15 seconds while the portal is running. It displays speech utterance, wake-detection and successful command counters (since the voice worker started), without capturing recordings or ambient transcripts. These counters show activity, not proof of recognition accuracy. The sound check remains a human listening test.

The last 100 incidents and recovery events persist in `health-history.json`. Repeated adjacent errors are deduplicated for five minutes. Reports include application versions, health checks, sanitized error messages and server exception stack locations; common secret patterns and home/application paths are redacted. Review reports before sharing because arbitrary error text may contain other sensitive information. Raw system journals, environment files, media contents and voice transcripts are excluded. Logs remain local; there is no cloud upload or automatic AI code repair connection.

Known microphone open/start errors lasting at least three checks trigger a capture refresh after the portal's 60-second startup grace period. Attempts are persisted, limited to three per hour with a five-minute cooldown, and marked requested until a healthy heartbeat is received. Turn recovery off in the dashboard at any time. Disconnected/stopped services, unknown errors, speech recognition failures, database faults and muted audio are reported but do not trigger this action. Existing systemd `Restart=on-failure` settings recover crashed portal/voice processes; this in-process monitor cannot detect its own frozen or stopped portal, repair arbitrary code, or verify audible sound.

Install `frame-update-2.3.0.zip` using the dashboard updater and restart the Pi. No new Python dependencies or updater bootstrap are needed when updating from 2.2.x. For unresolved incidents, use **Download error report** and attach it to the support chat. A separate authenticated agent service would be required for unattended AI diagnosis and code changes.

## Frame 2.4.1 interface

Frame opens directly to movies, with a compact layout matching Hyperdrive. The TV has Movies, Filter, Settings and Back to Hyperdrive controls. Sound, refresh, updates and power are in Settings. The web library has an explicit Back to Hyperdrive link; microphone, sound and management controls are in Settings. Install frame-update-2.4.1.zip through the existing 2.4 updater, approve on TV and restart the Pi.

## Folders and movie visibility (2.6)

Hyperdrive Files supports creating and browsing nested folders, uploading into the current folder and downloading files within it. Each supported video upload asks Show in Frame or Files only, with a separate cancel action. Files-only choices persist across restarts and library scans. Existing movies stay visible. Uploads made through Frame itself still go directly into its library. This release does not add moving/deleting folders or uploading whole directory trees.


## Hey Hyper (2.7)

Say **Hey Hyper**, followed by a command, then pause briefly. The old Hey Frame name remains an alias. A standalone wake phrase opens an eight-second window for one command. Recognition stays offline, with on-screen feedback; there is no spoken reply. Internet is used only for explicit web search and software releases.

Hyperdrive home → Microphone & voice controls opens the configuration. Enhancement modes are Off, Balanced (up to 4× gain) and Strong (up to 8× gain). A 70 Hz high-pass filter reduces rumble/DC, a 3.6 kHz low-pass filter reduces high-frequency noise, and gain is bounded by output peaks. Near-silence is not boosted. This is lightweight speech-band filtering, not AI denoising or acoustic echo cancellation. Loud TV audio, heavily clipped recordings, and inaudible speech still need a quieter room or better mic placement. Compare Off and Balanced on your actual mic; Strong may amplify room noise too. RMS, clipping percentage and dropped capture blocks are visible in settings. No ambient transcripts or recordings are saved. Command requests run separately from audio recognition so a web search does not block capture.

Supported examples:

- “Hey Hyper, play Interstellar”, “pause”, “resume”, “stop”, “start over”, “play a random movie”, “continue watching” (chooses the first unfinished title alphabetically).
- “Skip forward thirty seconds”, “go back”, “subtitles on/off”, “volume up/down”, “set volume to fifty”, “mute/unmute”, “what is playing”, “open Frame”, “open Hyperdrive”.
- “Add Interstellar to watchlist”, “remove Interstellar from watchlist”, “scan movies”.
- “Storage space”, “list files”, “list folders”, “list files in Holidays”, “find files called holiday”, “create folder called Holidays”. Folder creation is in the storage root. Listing returns up to ten entries; search examines at most 10,000 entries.
- “Move file Example.mp4 to folder Holidays”, “rename file Example.mp4 to New name”. These require one unambiguous filename including its extension. Review the exact paths in the microphone panel and confirm within two minutes; nothing moves until then. Existing destinations are never intentionally overwritten; stale requests and changed source files are rejected. Stop playback before confirming. Movie library paths and Files-only visibility are preserved. Deletion/formatting are not voice commands.
- “Help”, “search the web for a topic”.

The software does not guarantee recognition with every microphone. Automated checks exercise synthetic audio, command parsing and storage confirmation; speech accuracy and CEC/audio still require Pi hardware testing. No new speech dependencies are needed. Install the GitHub update and restart the Pi to load the new worker and Kodi code.

## Audio, dual microphones and commands (2.8)

Settings now groups Library, Sound & power, Hey Hyper, Updates and System. While a movie plays, use Diagnose current movie audio to inspect Kodi mute, zero volume, audio tracks and passthrough. Fix HDMI sound selects stereo PCM and saves the desktop HDMI sink; new movie streams are routed back to that sink without overriding subsequent user mute or volume changes. Run the audible tone test too. Diagnostics cannot prove that the TV speakers produce sound.

Hey Hyper accepts polite phrases such as “could you pause the movie please”, “take me home”, “end the movie”, “check for software updates”, “update Hyperdrive” and “fix movie audio”. Home opens Hyperdrive; end movie stops playback, preserves resume progress and returns home. Updating checks GitHub on TV, asks before downloading and separately before installation; it never silently installs or restarts. This is expanded offline phrase matching, not unrestricted conversational AI.

In Hey Hyper settings select a primary and optional second microphone, then Save microphone. Separate streams and recognizers share the offline model. The first microphone detecting a wake owns that turn; a brief cooldown suppresses the other mic's duplicate command. A failed input is retried while the working input continues. This is independent listening, not beamforming or echo cancellation; it may increase CPU use and needs testing on your Pi with both devices.

## Simple dashboard and private remote access (2.9)

Files is now the landing page: upload, create folders, search the current folder and download. Files, Movies and Settings are the main navigation. Settings separates library management, sound/power, voice, updates, remote access and diagnostics; movie grids and TV controls are hidden when working in unrelated settings.

Remote access uses Tailscale on the Pi and each client device. Its personal plan is free for personal use; see https://tailscale.com/pricing. On your Pi after installing this update:

```sh
cd ~/HyperMedia
bash scripts/install-pi.sh --remote-access
```

The optional installer downloads the official Tailscale Linux installer, enables its system service and runs `tailscale up`. Complete its account sign-in. Install Tailscale on your Mac/phone from https://tailscale.com/download, sign in to the same account, and connect. In Hyperdrive Settings → Remote access select Check connection. Bookmark the `http://100.x.y.z:8080/` address it shows. HTTP is transported inside the encrypted private network; this is not a public website or a separate cloud file store. No Tailscale Serve/Funnel or router port forwarding is configured. Files remain on the Pi USB drive.

The Pi, USB and both devices need internet/network connectivity; uploads depend on both connections and are not resumable after interruption. Test from a phone with Wi-Fi disabled and Tailscale connected: upload a small file, download it and compare it. Local status checks cannot prove worldwide reachability. A firewall or custom Tailscale access policy may need to allow TCP 8080. Only trust devices/users that should manage the whole portal: there is no separate application login. Keep port 8080 off the public internet. Tailscale authentication happens in its own app/browser, never in Hyperdrive. `sudo tailscale down` disconnects remote access while local access remains. Reauthentication may be needed if device keys expire.

Official installation and connection instructions: https://tailscale.com/docs/install/linux and https://tailscale.com/docs/how-to/connect-to-devices. No changes have been made to a live Pi by publishing this release; installation and sign-in on the Pi are required.
