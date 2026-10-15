import hashlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import updater

SOURCE = Path(__file__).resolve().parent.parent

def bundle(change=None):
    files = {name:(SOURCE/name).read_bytes() for name in updater.FILES}
    if change: files.update(change)
    manifest={'format':1, 'version':files['VERSION'].decode().strip(), 'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
    stream=io.BytesIO()
    with ZipFile(stream,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest))
        for name,data in files.items():z.writestr(name,data)
    return stream.getvalue()

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        (self.root/'VERSION').write_text('2.0.0')
        (self.root/'server.py').write_text('# old server\n')
        (self.root/'library.db').write_bytes(b'keep library')
        self.addon=self.root/'installed-addon';self.addon.mkdir()
        (self.addon/'addon.xml').write_text('<addon/>')
        self.u=updater.Updater(self.root,self.addon)
    def tearDown(self):self.temp.cleanup()
    def test_apply_updates_app_and_addon_preserves_data_and_backup(self):
        self.u.stage(bundle());s=self.u.status();result=self.u.apply(s['staged'],s['digest'])
        self.assertEqual((self.root/'library.db').read_bytes(),b'keep library')
        self.assertEqual((self.addon/'controls.py').read_bytes(),(SOURCE/'kodi/script.frame/controls.py').read_bytes())
        self.assertEqual((Path(result['backup'])/'app/server.py').read_text(),'# old server\n')
        self.assertIsNone(self.u.status()['staged'])
        self.assertEqual(self.u.status()['running'],'2.0.0')
    def test_rejects_unexpected_path_and_invalid_python(self):
        for changes in ({'../escape':b'no'}, {'server.py':b'invalid python ('}):
            with self.assertRaises(ValueError):self.u.stage(bundle(changes))
        self.assertFalse((self.root/'escape').exists())
    def test_rejects_replaced_bundle_after_review(self):
        self.u.stage(bundle());s=self.u.status();self.u.stage(bundle({'server.py':b'# different bundle\n'}))
        with self.assertRaises(ValueError):self.u.apply(s['staged'],s['digest'])
        self.assertEqual((self.root/'server.py').read_text(),'# old server\n')
    def test_failed_install_restores_prior_files(self):
        self.u.stage(bundle());s=self.u.status();original=updater.os.replace
        def fail(src,dest):
            if Path(dest)==self.root/'updater.py':raise OSError('simulated disk failure')
            return original(src,dest)
        with patch('updater.os.replace',side_effect=fail):
            with self.assertRaises(OSError):self.u.apply(s['staged'],s['digest'])
        self.assertEqual((self.root/'VERSION').read_text(),'2.0.0')
        self.assertEqual((self.root/'server.py').read_text(),'# old server\n')
        self.assertTrue((self.u.folder/'pending.zip').exists())
    def test_checksum_tampering_rejected(self):
        raw=bundle();original=ZipFile(io.BytesIO(raw));out=io.BytesIO()
        with ZipFile(out,'w') as z:
            for name in original.namelist():z.writestr(name,b'# tampered' if name=='server.py' else original.read(name))
        with self.assertRaises(ValueError):self.u.stage(out.getvalue())

    def test_updates_installed_hyperdrive_addon(self):
        hub=self.addon.parent/'script.hyperdrive';hub.mkdir();(hub/'addon.xml').write_text('<addon/>')
        self.u.stage(bundle());state=self.u.status();self.u.apply(state['staged'],state['digest'])
        self.assertEqual((hub/'default.py').read_bytes(),(SOURCE/'kodi/script.hyperdrive/default.py').read_bytes())
