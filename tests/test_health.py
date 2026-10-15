import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import server

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.monitor=server.HealthMonitor(self.root/'health.json')
        self.settings=self.root/'voice.json'
        self.patches=[patch.object(server,'VOICE_SETTINGS',self.settings),
                      patch.object(server,'MEDIA',self.root),
                      patch.object(server,'connect'),
                      patch.object(server,'tv_status',return_value={'online':True,'error':'','audio':{}}),
                      patch.dict(server.VOICE,{'seen':time.monotonic(),'error':'','utterances':3,'wakes':0,'commands':0})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def fail_mic(self):
        server.VOICE.update(seen=time.monotonic(),error='Cannot open microphone: busy')
        self.monitor.started=time.monotonic()-120
        for _ in range(3):self.monitor.check()
    def test_recovery_is_bounded_and_persists(self):
        self.fail_mic()
        self.assertEqual(json.loads(self.settings.read_text())['revision'],1)
        for _ in range(5):self.monitor.check()
        self.assertEqual(json.loads(self.settings.read_text())['revision'],1)
        restored=server.HealthMonitor(self.monitor.path)
        self.assertEqual(len(restored.attempts),1)
        self.monitor.attempts=[time.time()-350,time.time()-700,time.time()-1000]
        self.monitor.check()
        self.assertEqual(json.loads(self.settings.read_text())['revision'],1)
    def test_disabled_recovery_and_parser_errors_do_not_restart(self):
        self.monitor.auto=False;self.fail_mic()
        self.assertFalse(self.settings.exists())
        self.monitor.auto=True;server.VOICE['error']='No matching movie found'
        for _ in range(4):self.monitor.check()
        self.assertFalse(self.settings.exists())
    def test_healthy_heartbeat_records_recovery(self):
        self.fail_mic();server.VOICE['error']='';self.monitor.check()
        self.assertTrue(any(e['component']=='Microphone' and e['message'].startswith('Recovered') for e in self.monitor.events))
    def test_bounded_redacted_history_and_deduplication(self):
        self.monitor.event('test','password=secret token=abc sk-example')
        text=json.dumps(self.monitor.snapshot())
        self.assertNotIn('password=secret',text);self.assertNotIn('sk-example',text)
        count=len(self.monitor.events);self.monitor.event('test','password=secret token=abc sk-example')
        self.assertEqual(len(self.monitor.events),count)
        for i in range(110):self.monitor.event('test',str(i))
        self.assertEqual(len(self.monitor.events),100)
    def test_storage_failure_does_not_kill_monitor(self):
        with patch.object(Path,'write_text',side_effect=OSError('disk full')):
            self.monitor.event('test','error')
        self.assertIn('Cannot save',self.monitor.snapshot()['storage_error'])
    def test_voice_disabled_is_not_an_error(self):
        self.settings.write_text(json.dumps({'enabled':False}))
        server.VOICE.update(seen=0,error='Cannot open microphone: busy')
        self.monitor.check()
        self.assertTrue(next(c for c in self.monitor.checks if c['name']=='Microphone')['ok'])
