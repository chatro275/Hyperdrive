import json, subprocess, unittest
from unittest.mock import patch
from types import SimpleNamespace
import server

class RemoteTests(unittest.TestCase):
    def test_missing_client(self):
        with patch('shutil.which',return_value=None):
            self.assertFalse(server.remote_status()['ready'])
    def test_private_address_only_and_no_identity_leak(self):
        state={'BackendState':'Running','TailscaleIPs':['100.80.1.2'],'User':{'email':'private@example.com'},'Peer':{'secret':'hidden'}}
        with patch('shutil.which',return_value='/usr/bin/tailscale'),patch('subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(state))) as run:
            result=server.remote_status(8080)
        self.assertEqual(result['url'],'http://100.80.1.2:8080/')
        self.assertNotIn('private@example',json.dumps(result));self.assertNotIn('secret',json.dumps(result))
        self.assertEqual(run.call_args.args[0],['/usr/bin/tailscale','status','--json'])
    def test_disconnected_public_invalid_and_timed_out(self):
        with patch('shutil.which',return_value='/usr/bin/tailscale'):
            for state in [{'BackendState':'NeedsLogin'},{'BackendState':'Running','TailscaleIPs':['8.8.8.8']},{'BackendState':'Running','TailscaleIPs':['bad']}]:
                with patch('subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(state))):self.assertFalse(server.remote_status()['ready'])
            with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('tailscale',3)):self.assertFalse(server.remote_status()['ready'])
