import json, tempfile, threading, unittest, urllib.request, urllib.error, time
from unittest.mock import patch
from pathlib import Path
import server

class FrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old_health=server.HEALTH;server.HEALTH=server.HealthMonitor(Path(self.tmp.name)/'health.json'); self.old=(server.DB,server.MEDIA,server.VOICE_SETTINGS)
        server.VOICE_SETTINGS=Path(self.tmp.name)/'voice-settings.json'
        server.DB=Path(self.tmp.name)/'test.db'; server.MEDIA=(Path(self.tmp.name)/'media').resolve(); server.MEDIA.mkdir()
        (server.MEDIA/'Example.2024.mp4').write_bytes(b'0123456789')
        server.init(); self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        server.TV.update(seen=0, playing=False, title='', error=''); server.COMMANDS.clear()
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.base='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown();self.http.server_close();server.HEALTH=self.old_health;server.DB,server.MEDIA,server.VOICE_SETTINGS=self.old;self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {}))
    def test_scan_persistence_and_stream(self):
        self.assertEqual(json.load(self.request('/api/scan',{}))['count'],1)
        self.request('/api/scan',{}).close()
        movies=json.load(self.request('/api/movies')); self.assertEqual(len(movies),1);self.assertEqual(movies[0]['title'],'Example')
        self.request('/api/movies/1',{'favorite':True,'progress':.4,'title':'New title'}).close()
        movie=json.load(self.request('/api/movies'))[0];self.assertEqual(movie['progress'],.4);self.assertEqual(movie['favorite'],1)
        with self.request('/media/1',headers={'Range':'bytes=2-5'}) as r:
            self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345');self.assertEqual(r.headers['Content-Range'],'bytes 2-5/10')
        with self.request('/media/1',headers={'Range':'bytes=-3'}) as r:self.assertEqual(r.read(),b'789')
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/media/1',headers={'Range':'bytes=99-'})
        self.assertEqual(e.exception.code,416)
    def test_origin_and_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/scan',{}, {'Origin':'https://other.example'})
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/../server.py')
        self.assertEqual(e.exception.code,403)
        with self.request('/frame') as r:self.assertIn(b'Your personal',r.read().replace(b'YOUR PERSONAL',b'Your personal'))

    def upload(self, name, body=b'movie data', headers=None):
        from urllib.parse import quote
        return urllib.request.urlopen(urllib.request.Request(self.base+'/api/upload?name='+quote(name, safe=''), data=body, headers=headers or {}))

    def test_upload_indexes_and_preserves_existing_file(self):
        with self.upload('My Film.2025.mkv') as r: self.assertTrue(json.load(r)['ok'])
        with self.upload('My Film.2025.mkv', b'second version') as r:
            self.assertNotEqual(json.load(r)['filename'], 'My Film.2025.mkv')
        self.assertEqual((server.MEDIA/'My Film.2025.mkv').read_bytes(), b'movie data')
        self.assertEqual(len(json.load(self.request('/api/movies'))), 3)
        self.assertEqual(list(server.MEDIA.glob('*.part')), [])

    def test_upload_rejects_unsafe_names_and_low_space(self):
        for name in ('../escape.mp4', 'folder/movie.mp4', 'file.py', 'bad\\movie.mp4'):
            with self.assertRaises(urllib.error.HTTPError) as e: self.upload(name)
            self.assertEqual(e.exception.code, 400)
        with patch('server.shutil.disk_usage', return_value=type('Disk', (), {'free':0})()):
            with self.assertRaises(urllib.error.HTTPError): self.upload('valid.mp4')
        self.assertFalse((server.MEDIA/'valid.mp4').exists())
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.upload('valid.mp4', headers={'Origin':'https://other.example'})
        self.assertEqual(e.exception.code, 403)

    def test_tv_queue_offline_delivery_and_expiry(self):
        server.scan()
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/tv/play', {'id':1})
        self.assertEqual(json.load(self.request('/api/tv/poll', {'playing':False}))['commands'], [])
        self.request('/api/tv/play', {'id':1}).close()
        commands=json.load(self.request('/api/tv/poll', {'playing':False}))['commands']
        self.assertEqual(commands[0]['path'], str(server.MEDIA/'Example.2024.mp4'))
        self.assertEqual(commands[0]['action'], 'play')
        self.assertEqual(json.load(self.request('/api/tv/poll', {}))['commands'], [])
        self.request('/api/tv/control', {'action':'pause'}).close()
        server.COMMANDS[0]['expires']=time.monotonic()-1
        self.assertEqual(json.load(self.request('/api/tv/poll', {}))['commands'], [])
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/tv/control', {'action':'arbitrary-code'})

    def test_missing_movie_cannot_be_queued(self):
        server.scan()
        self.request('/api/tv/poll', {}).close()
        (server.MEDIA/'Example.2024.mp4').unlink()
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/tv/play', {'id':1})
        self.assertEqual(server.COMMANDS, [])

    def test_power_confirmation_capabilities_and_audio_validation(self):
        self.request('/api/tv/poll', {'power':{'reboot':False}, 'audio':{'volume':42}}).close()
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/tv/control', {'action':'reboot','confirmed':True})
        self.request('/api/tv/poll', {'power':{'reboot':True}}).close()
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/tv/control', {'action':'reboot'})
        self.request('/api/tv/control', {'action':'reboot','confirmed':True}).close()
        for value in (-1, 101, '60', True):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/tv/control', {'action':'volume','value':value})
        self.request('/api/tv/control', {'action':'volume','value':60}).close()
        commands=json.load(self.request('/api/tv/poll', {}))['commands']
        self.assertEqual([c['action'] for c in commands],['reboot','volume'])
        self.assertEqual(commands[1]['value'],60)

    def test_voice_local_commands_never_call_web_and_pause_switch(self):
        server.scan();self.request('/api/tv/poll',{}).close()
        with patch('server.search_web',side_effect=AssertionError('Local commands must not search online')):
            self.request('/api/voice/command',{'text':'play example'}).close()
            commands=json.load(self.request('/api/tv/poll',{}))['commands']
            self.assertEqual(commands[0]['action'],'play')
            self.assertEqual(commands[0]['title'],'Example')
            self.request('/api/voice/settings',{'enabled':False}).close()
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/voice/command',{'text':'pause'})
        self.assertFalse(json.load(self.request('/api/voice'))['enabled'])

    def test_web_failure_keeps_local_controls_working(self):
        self.request('/api/tv/poll',{}).close()
        with patch('server.search_web',side_effect=OSError('offline')):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/voice/command',{'text':'search for movies'})
        self.request('/api/voice/command',{'text':'pause'}).close()
        commands=json.load(self.request('/api/tv/poll',{}))['commands']
        self.assertIn('pause_only',[c['action'] for c in commands])

    def test_microphone_settings_persist_without_resetting_listener(self):
        self.request('/api/voice/settings',{'enabled':False}).close()
        self.request('/api/voice/settings',{'device':'2'}).close()
        config=json.load(self.request('/api/voice/poll',{'device':'USB mic','devices':[{'id':'2','name':'USB mic'}],'level':150}))
        self.assertFalse(config['enabled']);self.assertEqual(config['device'],'2')
        self.request('/api/voice/settings',{'refresh':True}).close()
        state=json.load(self.request('/api/voice'))
        self.assertEqual(state['settings']['revision'],1)
        self.assertEqual(state['settings']['device'],'2')
        self.assertEqual(state['devices'],[{'id':'2','name':'USB mic'}])
        self.assertEqual(state['level'],100)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/voice/settings',{'device':{'bad':True}})


    def test_health_report_and_recovery_toggle(self):
        state=json.load(self.request('/api/health/check',{}))
        self.assertGreater(state['checked'],0)
        self.assertTrue(any(c['name']=='Library' and c['ok'] for c in state['checks']))
        self.request('/api/health/settings',{'auto_recovery':False}).close()
        self.assertFalse(json.load(self.request('/api/health'))['auto_recovery'])
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/health/settings',{'auto_recovery':'false'})
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request('/api/health/check',{}, {'Origin':'https://other.example'})
        self.assertEqual(err.exception.code,403)

    def test_unexpected_server_error_is_recorded(self):
        with patch('server.connect',side_effect=RuntimeError('test exception')):
            with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/movies')
        self.assertEqual(err.exception.code,500)
        report=json.load(self.request('/api/health'))
        self.assertTrue(any('test exception' in e['message'] for e in report['events']))

    def test_hyperdrive_is_home_and_frame_is_separate(self):
        with self.request('/') as r:self.assertIn(b'hyperdrive.',r.read())
        with self.request('/frame') as r:self.assertIn(b'YOUR PERSONAL CINEMA',r.read())

    def test_any_file_upload_is_download_only_and_zero_bytes_allowed(self):
        import urllib.parse
        for name,body in [('document.html',b'<script>alert(1)</script>'),('script.py',b'print(1)'),('empty.bin',b'')]:
            url=self.base+'/api/files/upload?name='+urllib.parse.quote(name)
            with urllib.request.urlopen(urllib.request.Request(url,data=body,method='POST')) as r:
                self.assertEqual(json.load(r)['filename'],name)
            with self.request('/api/files/download?name='+urllib.parse.quote(name)) as r:
                self.assertEqual(r.headers['Content-Type'],'application/octet-stream')
                self.assertIn('attachment',r.headers['Content-Disposition'])
                self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')
                self.assertEqual(r.read(),body)
        self.assertEqual(json.load(self.request('/api/movies')),[])
        self.assertTrue(any(f['name']=='empty.bin' for f in json.load(self.request('/api/files'))))

    def test_disconnected_usb_does_not_fall_back_to_local_storage(self):
        with patch('server.require_storage',side_effect=ValueError('USB disconnected')):
            with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/files')
            self.assertEqual(err.exception.code,503)
            self.assertFalse(json.load(self.request('/api/status'))['available'])
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(self.base+'/api/files/upload?name=test.txt',data=b'no'))
        self.assertFalse((server.MEDIA/'test.txt').exists())

    def test_file_download_rejects_traversal_and_symlinks(self):
        outside=Path(self.tmp.name)/'private.txt';outside.write_text('private')
        (server.MEDIA/'link.txt').symlink_to(outside)
        for name in ('..%2Fprivate.txt','link.txt','..'):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/files/download?name='+name)

if __name__=='__main__':unittest.main()
