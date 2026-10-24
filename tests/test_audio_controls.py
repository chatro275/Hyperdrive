import importlib.util, json, sys, types, unittest
from pathlib import Path
from unittest.mock import Mock, patch

class AudioControlsTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.values={'audiooutput.audiodevice':'OLD','audiooutput.passthrough':True,'audiooutput.channels':8}
        self.fail=None
        def call(raw):
            request=json.loads(raw);method=request['method'];params=request['params'];self.calls.append((method,params))
            if method=='Settings.GetSettings':result={'settings':[{'id':'audiooutput.audiodevice','options':[{'label':'HDMI TV','value':'ALSA:hdmi'}]}]}
            elif method=='Settings.GetSettingValue':result={'value':self.values[params['setting']]}
            elif method=='Settings.SetSettingValue':
                result=params['setting']!=self.fail
                if result:self.values[params['setting']]=params['value']
            elif method=='Application.GetProperties':result={'volume':0,'muted':True}
            else:result='OK'
            return json.dumps({'result':result})
        self.dialog=Mock();self.dialog.select.return_value=0;self.dialog.yesno.return_value=True
        kodi=types.SimpleNamespace(executeJSONRPC=call,executebuiltin=Mock())
        gui=types.SimpleNamespace(Dialog=lambda:self.dialog)
        spec=importlib.util.spec_from_file_location('frame_controls_test',Path(__file__).resolve().parent.parent/'kodi/script.frame/controls.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'xbmc':kodi,'xbmcgui':gui,'common':types.SimpleNamespace(api=Mock())}):spec.loader.exec_module(self.module)
        self.module.test_sound=Mock()
        self.module.audio_profile=Mock(return_value=Mock())
    def test_hdmi_pcm_stereo_and_unmute(self):
        self.module.hdmi_setup()
        self.assertEqual(self.values,{'audiooutput.audiodevice':'ALSA:hdmi','audiooutput.passthrough':False,'audiooutput.channels':1})
        self.assertIn(('Application.SetMute',{'mute':False}),self.calls)
        self.assertIn(('Application.SetVolume',{'volume':50}),self.calls)
    def test_hdmi_failure_restores_previous_output(self):
        self.fail='audiooutput.passthrough'
        with self.assertRaises(ValueError):self.module.hdmi_setup()
        self.assertEqual(self.values['audiooutput.audiodevice'],'OLD')
    def test_cancel_does_not_change_audio(self):
        self.dialog.yesno.return_value=False
        self.module.hdmi_setup()
        self.assertFalse(any(method=='Settings.SetSettingValue' for method,_ in self.calls))

    def test_desktop_routes_only_kodi_and_recovers_zero_volume(self):
        streams=[{'index':9,'properties':{'application.name':'Kodi'},'volume':{'left':{'value':0}}},
                 {'index':10,'properties':{'application.name':'Browser'}}]
        command=Mock(side_effect=lambda *args: json.dumps(streams) if args[0]=='--format=json' else '')
        with patch.object(self.module,'pactl',command):
            self.module.route_desktop({'name':'alsa_output.hdmi','volume':{'left':{'value':0}}})
        calls=[c.args for c in command.call_args_list]
        self.assertIn(('set-default-sink','alsa_output.hdmi'),calls)
        self.assertIn(('set-sink-mute','alsa_output.hdmi','0'),calls)
        self.assertIn(('set-sink-volume','alsa_output.hdmi','50%'),calls)
        self.assertIn(('move-sink-input','9','alsa_output.hdmi'),calls)
        self.assertNotIn(('move-sink-input','10','alsa_output.hdmi'),calls)

    def test_nonzero_volume_is_preserved(self):
        with patch.object(self.module,'rpc',return_value={'volume':35,'muted':True}) as rpc:
            self.module.audible_volume()
        self.assertFalse(any(c.args[0]=='Application.SetVolume' for c in rpc.call_args_list))

    def test_desktop_hdmi_available_when_kodi_only_lists_default(self):
        original=self.module.rpc
        def rpc(method, **params):
            if method=='Settings.GetSettings':
                return {'settings':[{'id':'audiooutput.audiodevice','options':[{'label':'Default','value':'PULSE:default'}]}]}
            return original(method, **params)
        sink={'name':'alsa_output.hdmi','description':'HDMI TV'}
        with patch.object(self.module,'rpc',side_effect=rpc), patch.object(self.module,'desktop_sinks',return_value=[sink]), patch.object(self.module,'route_desktop') as route:
            self.module.hdmi_setup()
        route.assert_called_once_with(sink)
        self.assertEqual(self.values['audiooutput.audiodevice'],'PULSE:default')

    def test_missing_desktop_audio_does_not_break_alsa(self):
        with patch.object(self.module,'pactl',side_effect=ValueError('unavailable')):
            self.assertEqual(self.module.desktop_sinks(),[])
            self.module.hdmi_setup()
        self.assertEqual(self.values['audiooutput.audiodevice'],'ALSA:hdmi')

    def test_movie_route_restored_without_changing_mute_or_volume(self):
        self.module.audio_profile.return_value.read_text.return_value='{"sink":"hdmi-tv"}'
        streams=[{'index':7,'properties':{'application.name':'Kodi'}},{'index':8,'properties':{'application.name':'Browser'}}]
        with patch.object(self.module,'desktop_sinks',return_value=[{'name':'hdmi-tv'}]), patch.object(self.module,'pactl',return_value=json.dumps(streams)) as command:
            self.module.restore_movie_route()
        self.assertEqual(command.call_args_list[-1].args,('move-sink-input','7','hdmi-tv'))
        self.assertEqual(command.call_count,2)

    def test_movie_diagnosis_reports_silent_states(self):
        with patch.object(self.module,'audio_status',return_value={'muted':True,'volume':0,'tracks':[],'passthrough':True,'output':'HDMI'}):
            issues=self.module.diagnose_movie_audio()
        self.assertEqual(len(issues),4)
        self.dialog.textviewer.assert_called_once()

    def test_update_download_requires_confirmation(self):
        self.module.api=Mock(side_effect=[{'staged':None},{'available':True,'version':'9.0.0'}])
        self.dialog.yesno.return_value=False
        self.module.update_menu()
        self.assertEqual(self.module.api.call_count,2)

    def test_update_requires_separate_install_confirmation(self):
        self.module.api=Mock(side_effect=[{'staged':None},{'available':True,'version':'9.0.0','digest':'abc'},{},{'staged':'9.0.0','digest':'abc'}])
        self.module.xbmc.Player=lambda:types.SimpleNamespace(isPlaying=lambda:False)
        self.dialog.yesno.side_effect=[True,False]
        self.module.update_menu()
        self.assertEqual(self.module.api.call_count,4)
        self.assertEqual(self.dialog.yesno.call_count,2)


class AirPlayTests(unittest.TestCase):
    setUp=AudioControlsTests.setUp
    def prepare(self):
        self.values['services.airplay']=True
        self.module.audio_profile.return_value.read_text.return_value='{"sink":"alsa_output.hdmi"}'
        process=Mock();process.poll.return_value=None
        return process
    def test_start_pairing_and_selected_audio_then_restore(self):
        import os
        process=self.prepare();receiver=self.module.AirPlayReceiver()
        with patch('shutil.which',return_value='/usr/bin/uxplay'),patch.dict(os.environ,{'DISPLAY':':0'},clear=True),patch.object(self.module.subprocess,'run',return_value=types.SimpleNamespace(stdout='-pin -fs',stderr='')),patch.object(self.module.subprocess,'Popen',return_value=process) as spawn:
            result=receiver.start();receiver.start()
        self.assertTrue(result['running']);self.assertEqual(len(result['pin']),4)
        args=spawn.call_args.args[0];self.assertIn('pulsesink device=alsa_output.hdmi',args);self.assertIn('-pin',args)
        self.assertFalse(self.values['services.airplay']);spawn.assert_called_once()
        receiver.stop();process.terminate.assert_called_once();self.assertTrue(self.values['services.airplay']);self.assertEqual(receiver.pin,'')
    def test_missing_dependency_and_headless_are_clear_errors(self):
        import os
        receiver=self.module.AirPlayReceiver()
        with patch('shutil.which',return_value=None):
            with self.assertRaisesRegex(ValueError,'--airplay'):receiver.start()
        with patch('shutil.which',return_value='/usr/bin/uxplay'),patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'desktop session'):receiver.start()
    def test_old_receiver_rejected_without_disabling_kodi(self):
        import os
        self.prepare();receiver=self.module.AirPlayReceiver()
        with patch('shutil.which',return_value='/usr/bin/uxplay'),patch.dict(os.environ,{'DISPLAY':':0'},clear=True),patch.object(self.module.subprocess,'run',return_value=types.SimpleNamespace(stdout='old',stderr='')):
            with self.assertRaisesRegex(ValueError,'1.67'):receiver.start()
        self.assertTrue(self.values['services.airplay'])
    def test_launch_failure_restores_kodi(self):
        import os
        self.prepare();receiver=self.module.AirPlayReceiver()
        with patch('shutil.which',return_value='/usr/bin/uxplay'),patch.dict(os.environ,{'DISPLAY':':0'},clear=True),patch.object(self.module.subprocess,'run',return_value=types.SimpleNamespace(stdout='-pin',stderr='')),patch.object(self.module.subprocess,'Popen',side_effect=OSError('launch failed')):
            with self.assertRaises(OSError):receiver.start()
        self.assertTrue(self.values['services.airplay']);self.assertIsNone(receiver.process);self.assertEqual(receiver.pin,'')
    def test_exited_receiver_reports_error_and_restores(self):
        receiver=self.module.AirPlayReceiver();receiver.process=Mock();receiver.process.poll.return_value=1;receiver.process.returncode=1
        receiver.previous_airplay=True;receiver.pin='1234'
        with patch('shutil.which',return_value='/usr/bin/uxplay'):result=receiver.status()
        self.assertFalse(result['running']);self.assertIn('exited',result['error']);self.assertEqual(result['pin'],'');self.assertTrue(self.values['services.airplay'])
    def test_unresponsive_owned_process_is_killed(self):
        receiver=self.module.AirPlayReceiver();process=Mock();process.poll.return_value=None
        process.wait.side_effect=[self.module.subprocess.TimeoutExpired('uxplay',3),0];receiver.process=process
        receiver.stop();process.kill.assert_called_once();self.assertIsNone(receiver.process)
