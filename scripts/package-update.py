"""Build a Frame application update for upload through the local portal."""
import hashlib, json, sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from updater import FILES, validate
files = {name:(root/name).read_bytes() for name in FILES}
manifest = {'format':1, 'version':files['VERSION'].decode().strip(),
            'sha256':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
out = root / ('frame-update-' + manifest['version'] + '.zip')
with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('manifest.json', json.dumps(manifest))
    for name, data in files.items(): archive.writestr(name, data)
validate(out.read_bytes())
print(out.name)
