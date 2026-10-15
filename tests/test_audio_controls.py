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
