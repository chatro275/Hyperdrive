"""USB identity checks and attachment-only file storage for Hyperdrive."""
import os
import subprocess
from pathlib import Path


def require_storage(media):
    mount=os.environ.get('HYPERDRIVE_USB_MOUNT','')
    uuid=os.environ.get('HYPERDRIVE_USB_UUID','')
    if mount:
        root=Path(mount)
        if not root.is_mount() or not Path(media).resolve().is_relative_to(root.resolve()):
            raise ValueError('USB storage is disconnected. Reconnect the configured drive.')
        if uuid:
            try:
                actual=subprocess.run(['findmnt','-n','-o','UUID','--target',str(root)],capture_output=True,text=True,check=True,timeout=3).stdout.strip()
            except (OSError,subprocess.SubprocessError) as exc:
                raise ValueError('Could not verify the USB drive identity') from exc
            if actual!=uuid:raise ValueError('A different drive is mounted. Reconnect the configured USB stick.')
    if not Path(media).is_dir():raise ValueError('Storage folder is unavailable')


def file_path(media,name):
    if not name or name in ('.','..') or '/' in name or '\\' in name or len(name.encode())>200 or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Invalid filename')
    root=Path(media).resolve();path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Unsafe file path')
    return path
