# Hyperdrive 2.4

Hyperdrive is the top-level home on the TV and at `http://raspberrypi.local:8080/`. Frame remains a separate Kodi add-on and a separate web section at `/frame`. Hyperdrive launches Frame; Back from Frame's library returns to Hyperdrive. Both use Kodi as their TV runtime, retaining HDMI-CEC remote navigation. Raspberry Pi OS must use desktop autologin and the existing Kodi autostart entry. Hyperdrive is the first application screen after Kodi loads; OS/Kodi startup screens may still appear.

Files accepts every extension, including documents, images, archives, programs and extensionless files. Files are downloaded as attachments, never executed or rendered as portal pages. Videos with supported extensions also appear in Frame. Limits are actual free storage (with 256 MiB reserved), 100 GiB per file, and the USB filesystem's own limits. The file picker supports multiple files, progress and cancellation. Existing filenames are preserved by giving duplicates a new name. From version 2.6, the file browser supports nested folders, folder creation and uploads/downloads in the current folder. Each supported video upload asks whether to display it in Frame. Files-only choices persist across library scans.

## Upgrade an existing 2.2.x or 2.3.0 installation

1. Through **Frame → Manage library → Software updates**, upload `frame-updater-bootstrap-2.3.1.zip`. Approve on the TV and restart the Pi. This only prepares the updater to accept the new Hyperdrive files.
2. Upload `frame-update-2.4.0.zip` through the same updater, approve and restart again. The portal now opens Hyperdrive. Frame's updater is at `/frame`.
3. On the Pi run `cd ~/HyperMedia` then `python3 scripts/package-kodi.py`. This creates `hyperdrive-kodi.zip` and `frame-kodi.zip` locally.
4. In Kodi, use **Add-ons → Install from zip file → Home folder → HyperMedia → hyperdrive-kodi.zip**. Frame was updated by the portal; its ZIP is not needed again. Restart Kodi or the Pi. Hyperdrive opens automatically and launches Frame from its tile.

Do not give a portal update ZIP to Kodi, or a Kodi add-on ZIP to the portal updater. Future updates refresh both installed add-ons. Hyperdrive's first installation must be completed through Kodi so Kodi registers/enables it.

## USB setup

Default assumption: Raspberry Pi OS, Hyperdrive code, configuration and library database remain on the boot drive. The 128 GB USB stick holds uploaded files and movies under `Hyperdrive/files`. This release does not change the Pi boot device or format any disk.

Run in Raspberry Pi Connect:

```bash
lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS
```

Use the output to identify the intended USB volume and a stable mount point. Configure automatic mounting by UUID before relying on it at boot; the correct fstab entry depends on the filesystem and user IDs. See the [official Raspberry Pi external storage instructions](https://www.raspberrypi.com/documentation/computers/configuration.html#external-storage). Do not guess `/dev/sda1` or format the drive. FAT32 limits individual file sizes; an existing exFAT/ext4 filesystem may be more suitable for large movies, but this tool never reformats.

After the intended USB volume is mounted and writable by `hyper`, run (replace the example path with the verified mount point):

```bash
cd ~/HyperMedia
sudo systemctl stop frame
python3 scripts/configure-storage.py --mount /mnt/YOUR_VERIFIED_USB_MOUNT
sudo systemctl start frame
```

If configuration reports an error, resolve it before treating the USB setup as complete. The portal can still be started with the previous configuration. The helper copies existing files, leaves the originals in place, refuses conflicting files, saves a database backup, updates movie paths, backs up `frame.env` and records the USB UUID. It requires free space for the copy and does not delete files to make room. Do not unplug the drive during migration.

When configured, missing or wrong USB storage blocks uploads and media access while the home/health pages stay available. Reconnecting the correct mounted drive restores access. Until configuration is complete the portal clearly labels storage as “USB not configured” and retains the previous storage location.

Automated tests cover HTTP uploads/downloads, missing or wrong storage identity, unsafe paths, add-on packaging, updates and existing Frame behavior. TV startup, CEC, USB hotplug and audio still require validation on the Pi.
