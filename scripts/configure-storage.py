#!/usr/bin/env python3
"""Configure an already mounted USB volume; never formats or edits fstab."""
import argparse, filecmp, os, shutil, sqlite3, subprocess, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def configure(mount):
    mount=Path(mount).resolve()
    if mount==Path('/') or not mount.is_mount():raise ValueError('Choose the USB filesystem mount point, not a normal folder.')
    if any(c in str(mount) for c in '\n\r"\\'):raise ValueError('Use a mount path without quotes, backslashes or newlines')
    uuid=subprocess.run(['findmnt','-n','-o','UUID','--target',str(mount)],capture_output=True,text=True,check=True).stdout.strip()
    if not uuid or any(c.isspace() for c in uuid):raise ValueError('The drive must have a filesystem UUID.')
    if subprocess.run(['systemctl','is-active','--quiet','frame'],check=False).returncode==0:
        raise ValueError('Stop the portal before migration: sudo systemctl stop frame')
    env=ROOT/'frame.env';lines=env.read_text().splitlines() if env.exists() else []
    old=ROOT/'movies'
    for line in lines:
        if line.startswith('FRAME_MEDIA='):old=Path(line.split('=',1)[1].strip().strip('"'))
    old=old.resolve()
    device=mount.stat().st_dev
    target=mount/'Hyperdrive'/'files'
    if not target.resolve().is_relative_to(mount) or (mount/'Hyperdrive').is_symlink() or target.is_symlink():raise ValueError('USB storage directories must not be symbolic links')
    if old.resolve()==target.resolve():sources=[]
    elif old.exists():
        if target.is_relative_to(old.resolve()):raise ValueError('USB storage cannot be inside the old media directory')
        sources=[p for p in old.rglob('*') if p.is_file() or p.is_symlink()]
    else:sources=[]
    for source in sources:
        if source.is_symlink():raise ValueError('Remove symbolic links from the old media folder before migration.')
        dest=target/source.relative_to(old)
        if not dest.resolve().is_relative_to(target.resolve()):raise ValueError('Unsafe destination path')
        if dest.exists() and (dest.is_symlink() or not filecmp.cmp(source,dest,shallow=False)):
            raise ValueError('Conflicting USB file: '+str(dest)+'. Nothing has been overwritten.')
    needed=sum(p.stat().st_size for p in sources if not (target/p.relative_to(old)).exists())
    if shutil.disk_usage(mount).free<needed+256*1024**2:raise ValueError('Not enough free space to preserve and copy existing files')
    target.mkdir(parents=True,exist_ok=True)
    for source in sources:
        if not mount.is_mount() or mount.stat().st_dev!=device:raise ValueError('USB drive disconnected during migration')
        dest=target/source.relative_to(old)
        if dest.exists():continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=None
        try:
            with tempfile.NamedTemporaryFile(dir=dest.parent,prefix='.migration-',delete=False) as f:temp=Path(f.name)
            shutil.copyfile(source,temp);temp.replace(dest)
        finally:
            if temp:temp.unlink(missing_ok=True)
    if not mount.is_mount() or mount.stat().st_dev!=device:raise ValueError('USB drive disconnected during migration')
    keys=('FRAME_MEDIA=','HYPERDRIVE_USB_MOUNT=','HYPERDRIVE_USB_UUID=')
    lines=[line for line in lines if not line.startswith(keys)]
    for key,value in [('FRAME_MEDIA',str(target)),('HYPERDRIVE_USB_MOUNT',str(mount)),('HYPERDRIVE_USB_UUID',uuid)]:
        if any(c in value for c in '\n\r"\\'):raise ValueError('Use a mount path without quotes, backslashes or newlines')
        lines.append(key+'="'+value+'"')
    env_backup=None
    if env.exists():
        env_backup=ROOT/('frame.env.backup-'+str(time.time_ns()));shutil.copy2(env,env_backup)
    temp=env.with_suffix('.env.tmp');temp.write_text('\n'.join(lines)+'\n');temp.chmod(0o600)
    changed_env=False
    try:
        db=ROOT/'library.db'
        if db.exists():
            with sqlite3.connect(db) as c:
                with sqlite3.connect(ROOT/('library-before-usb-'+str(time.time_ns())+'.db')) as backup:c.backup(backup)
                for mid,path in c.execute('SELECT id,path FROM movies').fetchall():
                    original=Path(path).resolve()
                    if original.is_relative_to(old) and (target/original.relative_to(old)).is_file():
                        c.execute('UPDATE movies SET path=? WHERE id=?',(str(target/original.relative_to(old)),mid))
                temp.replace(env);changed_env=True
        else:temp.replace(env);changed_env=True
    except Exception:
        if changed_env:
            if env_backup:shutil.copy2(env_backup,env)
            else:env.unlink(missing_ok=True)
        raise
    finally:temp.unlink(missing_ok=True)
    print('USB storage configured: '+str(target))
    print('Original files were kept. Restart the portal: sudo systemctl restart frame')
    print('Ensure this UUID mounts at '+str(mount)+' at boot before using Hyperdrive.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mount',required=True);args=parser.parse_args()
    try:configure(args.mount)
    except (ValueError,OSError,subprocess.SubprocessError,sqlite3.Error) as exc:parser.exit(1,str(exc)+'\n')
