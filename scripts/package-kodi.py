"""Build and validate a Kodi-only ZIP, including explicit directory entries."""
import shutil
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent

def validate_package(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        roots = {name.split('/')[0] for name in names}
        if len(roots) != 1 or len(names) != len(set(names)):
            raise ValueError('Kodi requires exactly one add-on folder, without duplicate entries')
        addon_id = next(iter(roots))
        if addon_id + '/' not in names or not archive.getinfo(addon_id + '/').is_dir():
            raise ValueError('Missing explicit add-on root directory')
        for name in names:
            if name.startswith('/') or '..' in PurePosixPath(name).parts or '\\' in name:
                raise ValueError('Unsafe archive path')
            if any(part.startswith('.') or part == '__pycache__' for part in PurePosixPath(name).parts):
                raise ValueError('Unexpected hidden/cache file in add-on')
        manifest = ET.fromstring(archive.read(addon_id + '/addon.xml'))
        if manifest.tag != 'addon' or manifest.get('id') != addon_id:
            raise ValueError('Add-on folder and manifest ID must match')
        for extension in manifest.findall('extension'):
            library = extension.get('library')
            if library and addon_id + '/' + library not in names:
                raise ValueError('Missing add-on entrypoint: ' + library)
        if archive.testzip() is not None: raise ValueError('Corrupt ZIP member')
        return manifest.get('version')

def build(root=ROOT, addon_id="script.frame"):
    addon = root / 'kodi' / addon_id
    manifest = ET.parse(addon/'addon.xml').getroot()
    if manifest.get('id') != addon.name: raise ValueError('Unexpected add-on ID')
    output = root / (addon.name + '-' + manifest.get('version') + '.zip')
    temporary = output.with_suffix('.zip.tmp')
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
            archive.write(addon, addon.name + '/')
            for path in sorted(addon.rglob('*')):
                parts = path.relative_to(addon).parts
                if any(p.startswith('.') or p == '__pycache__' for p in parts) or path.suffix == '.pyc': continue
                if path.is_symlink(): raise ValueError('Symlinks are not allowed in the Kodi package')
                name = path.relative_to(root/'kodi').as_posix()
                archive.write(path, name + '/' if path.is_dir() else name)
        validate_package(temporary)
        temporary.replace(output)
        shutil.copyfile(output, root/('frame-kodi.zip' if addon_id=='script.frame' else 'hyperdrive-kodi.zip'))
    finally: temporary.unlink(missing_ok=True)
    return output

if __name__ == '__main__':
    output = build()
    print('Kodi installer: ' + str(output))
    print('Hyperdrive installer: ' + str(build(addon_id='script.hyperdrive')))
    print('Validated: one add-on root, manifest, entrypoints and ZIP integrity.')
    print('Use this ZIP in Kodi. frame-update-*.zip belongs in the Frame web portal only.')
