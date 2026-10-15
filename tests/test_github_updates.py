import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
import updater
from test_updates import bundle

class GitHubUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'VERSION').write_text('2.4.1')
        self.u=updater.Updater(root,root/'addon');self.raw=bundle();self.version=json.loads(__import__('zipfile').ZipFile(__import__('io').BytesIO(self.raw)).read('manifest.json'))['version']
        self.digest='sha256:'+hashlib.sha256(self.raw).hexdigest()
        self.release={'tag_name':'v'+self.version,'assets':[{'name':'frame-update-'+self.version+'.zip','digest':self.digest,'id':12,'size':len(self.raw)}]}
    def tearDown(self):self.tmp.cleanup()
    def test_download_verifies_and_stages(self):
        with patch('updater.github_fetch',side_effect=[json.dumps(self.release).encode(),self.raw]):
            self.u.stage_github(self.version,self.digest)
        self.assertEqual(self.u.status()['staged'],self.version)
    def test_corrupt_download_not_staged(self):
        with patch('updater.github_fetch',side_effect=[json.dumps(self.release).encode(),b'corrupt']):
            with self.assertRaises(ValueError):self.u.stage_github(self.version,self.digest)
        self.assertIsNone(self.u.status()['staged'])
    def test_changed_release_and_missing_digest_rejected(self):
        with patch('updater.github_fetch',return_value=json.dumps(self.release).encode()):
            with self.assertRaises(ValueError):self.u.stage_github('1.0.0',self.digest)
        del self.release['assets'][0]['digest']
        with patch('updater.github_fetch',return_value=json.dumps(self.release).encode()):
            with self.assertRaises(ValueError):self.u.github_release()
    def test_redirect_strips_auth_and_rejects_other_hosts(self):
        handler=updater.GitHubRedirect();request=Request('https://api.github.com/asset',headers={'Authorization':'Bearer private'})
        result=handler.redirect_request(request,None,302,'found',{},'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(result.get_header('Authorization'))
        with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'found',{},'https://evil.example/file')
