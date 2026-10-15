"""Local, reviewed update bundles. No remote shell commands or package-manager access."""
import ast
import hashlib
import io
import json
import os
import re
import shutil
import threading
import uuid
import tempfile
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import URLError
from pathlib import Path
from zipfile import ZipFile, BadZipFile

MAX_ARCHIVE = 10 * 1024**2
MAX_EXPANDED = 20 * 1024**2
REQUIRED_FILES = (
    'VERSION', 'server.py', 'updater.py', 'README.md',
    'static/index.html', 'static/app.js', 'static/style.css',
    'scripts/enable-airplay-output.sh', 'scripts/package-update.py', 'scripts/package-kodi.py',
    'kodi/script.frame/addon.xml', 'kodi/script.frame/common.py',
    'kodi/script.frame/default.py', 'kodi/script.frame/service.py',
    'kodi/script.frame/controls.py',
    'kodi/script.frame/resources/skins/Default/1080i/Frame.xml',
    'kodi/script.frame/resources/skins/Default/media/white.png',
)
FILES = REQUIRED_FILES + ('voice.py', 'voice_worker.py', 'scripts/install-voice.sh', 'scripts/download-voice-model.py',
    'storage.py','HYPERDRIVE-SETUP.md','static/hyperdrive.html','static/hyperdrive.css','static/hyperdrive.js',
    'scripts/install-pi.sh','scripts/configure-storage.py',
    'kodi/script.hyperdrive/addon.xml','kodi/script.hyperdrive/default.py','kodi/script.hyperdrive/service.py',
    'kodi/script.hyperdrive/resources/skins/Default/1080i/Hyperdrive.xml',
    'kodi/script.hyperdrive/resources/skins/Default/media/white.png')

def validate(raw):
    if not raw or len(raw) > MAX_ARCHIVE: raise ValueError('Update bundle is too large or empty')
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            supplied = set(names) - {'manifest.json'}
            if len(names) != len(set(names)) or 'manifest.json' not in names or not set(REQUIRED_FILES).issubset(supplied) or not supplied.issubset(set(FILES)):
                raise ValueError('Update contains missing or unexpected Frame application files')
            if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED:
                raise ValueError('Expanded update is too large')
            manifest = json.loads(archive.read('manifest.json'))
            version = manifest.get('version', '')
            if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
                raise ValueError('Invalid update version')
            if manifest.get('format') != 1 or set(manifest.get('sha256', {})) != supplied:
                raise ValueError('Invalid update manifest')
            files = {name:archive.read(name) for name in FILES if name in supplied}
            if files['VERSION'].decode().strip() != version: raise ValueError('Version mismatch')
            for name, content in files.items():
                if hashlib.sha256(content).hexdigest() != manifest['sha256'][name]:
                    raise ValueError('Update checksum mismatch: ' + name)
                if name.endswith('.py'): ast.parse(content, filename=name)
            return manifest, files
    except (BadZipFile, KeyError, UnicodeError, SyntaxError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid Frame update bundle') from exc

class GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed=urlsplit(newurl)
        if parsed.scheme!='https' or parsed.hostname not in {'api.github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','github.com'}:
            raise ValueError('Unexpected GitHub download redirect')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None:redirected.remove_header('Authorization')
        return redirected

def github_fetch(url, limit, binary=False):
    headers={'Accept':'application/octet-stream' if binary else 'application/vnd.github+json','User-Agent':'Hyperdrive-Updater'}
    token=os.environ.get('HYPERDRIVE_GITHUB_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    try:
        with build_opener(GitHubRedirect()).open(Request(url,headers=headers),timeout=30) as response:
            raw=response.read(limit+1)
        if len(raw)>limit:raise ValueError('GitHub response exceeds the size limit')
        return raw
    except (URLError,TimeoutError,OSError) as exc:
        raise ValueError('Cannot download from GitHub. Check your internet connection, repository access and published releases.') from exc

class Updater:
    def __init__(self, root, addon):
        self.root, self.addon = Path(root).resolve(), Path(addon).resolve()
        self.folder = self.root / '.updates'
        self.lock = threading.Lock()
        self.running = (self.root / 'VERSION').read_text().strip()

    def github_release(self):
        repo=os.environ.get('HYPERDRIVE_GITHUB_REPO','chatro275/Hyperdrive').strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
            raise ValueError('GitHub repository is not configured. Set HYPERDRIVE_GITHUB_REPO=owner/repository in frame.env.')
        raw=github_fetch('https://api.github.com/repos/'+repo+'/releases/latest',2*1024**2)
        try:
            release=json.loads(raw);version=release['tag_name'].removeprefix('v')
            if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Expected a stable versioned release')
            name='frame-update-'+version+'.zip'
            assets=[a for a in release['assets'] if a.get('name')==name]
            if len(assets)!=1:raise ValueError('Release has no unique Hyperdrive update bundle')
            asset=assets[0];digest=asset.get('digest','')
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Release asset has no SHA-256 digest')
            if not 0<asset['size']<=MAX_ARCHIVE:raise ValueError('Release bundle is too large')
            if type(asset['id']) is not int or asset['id']<=0:raise ValueError('Invalid release asset')
            installed=(self.root/'VERSION').read_text().strip()
            newer=tuple(map(int,version.split('.')))>tuple(map(int,installed.split('.')))
            return {'repository':repo,'version':version,'installed':installed,'available':newer,'digest':digest,
                    'asset_id':asset['id'],'size':asset['size']}
        except (KeyError,TypeError,json.JSONDecodeError) as exc:raise ValueError('Invalid GitHub release metadata') from exc

    def stage_github(self, version, digest):
        release=self.github_release()
        if release['version']!=version or release['digest']!=digest:raise ValueError('GitHub release changed. Check for updates again.')
        if not release['available']:raise ValueError('You already have this version or a newer version')
        url='https://api.github.com/repos/'+release['repository']+'/releases/assets/'+str(release['asset_id'])
        raw=github_fetch(url,MAX_ARCHIVE,binary=True)
        if len(raw)!=release['size'] or 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Downloaded release failed its integrity check')
        manifest,_=validate(raw)
        if manifest['version']!=version:raise ValueError('Bundle version does not match GitHub release')
        return self.stage(raw)

    def status(self):
        with self.lock:
            staged = None
            digest = None
            if (self.folder / 'pending.zip').is_file():
                raw = (self.folder / 'pending.zip').read_bytes()
                staged = validate(raw)[0]['version']
                digest = hashlib.sha256(raw).hexdigest()
            return {'running':self.running, 'installed':(self.root/'VERSION').read_text().strip(), 'staged':staged, 'digest':digest}

    def stage(self, raw):
        manifest, _ = validate(raw)
        with self.lock:
            self.folder.mkdir(exist_ok=True)
            temporary = self.folder / ('stage-' + uuid.uuid4().hex)
            try:
                temporary.write_bytes(raw)
                os.replace(temporary, self.folder / 'pending.zip')
            finally: temporary.unlink(missing_ok=True)
        return {'version':manifest['version']}

    def apply(self, expected, digest):
        with self.lock:
            raw = (self.folder/'pending.zip').read_bytes()
            manifest, files = validate(raw)
            if manifest['version'] != expected or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('The staged update changed. Review it again.')
            if not (self.addon/'addon.xml').is_file(): raise ValueError('Install the Frame Kodi add-on first')
            backup = self.folder/'backups'/uuid.uuid4().hex
            backup.mkdir(parents=True)
            operations = []
            for name, content in files.items():
                targets = [(self.root, name, 'app/' + name)]
                if name.startswith('kodi/script.frame/'):
                    relative = name[len('kodi/script.frame/'):]
                    targets.append((self.addon, relative, 'addon/' + relative))
                if name.startswith('kodi/script.hyperdrive/'):
                    hub=self.addon.parent/'script.hyperdrive'
                    if (hub/'addon.xml').is_file():
                        relative=name[len('kodi/script.hyperdrive/'):]
                        targets.append((hub,relative,'hyperdrive/'+relative))
                for base, relative, backup_name in targets:
                    target = base/relative
                    if target.is_symlink() or not target.resolve().is_relative_to(base):
                        raise ValueError('Unsafe update destination: ' + relative)
                    old = backup/backup_name
                    exists = target.exists()
                    if exists:
                        old.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, old)
                    operations.append((target, old, exists, content))
            (backup/'restore.json').write_text(json.dumps([
                {'target':str(target), 'backup':str(old) if exists else None}
                for target, old, exists, _ in operations], indent=2))
            changed = []
            try:
                for target, old, exists, content in operations:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.frame-new-', delete=False) as f:
                            temp = Path(f.name)
                            f.write(content)
                        os.replace(temp, target)
                    finally:
                        if temp: temp.unlink(missing_ok=True)
                    changed.append((target, old, exists))
            except Exception:
                for target, old, exists in reversed(changed):
                    if exists: shutil.copy2(old, target)
                    else: target.unlink(missing_ok=True)
                raise
            (self.folder/'pending.zip').unlink()
            return {'version':manifest['version'], 'backup':str(backup), 'restart_required':True}
