import ast, types, unittest
from pathlib import Path
from unittest.mock import Mock

class PlaybackTests(unittest.TestCase):
    def setUp(self):
        source=ast.parse((Path(__file__).resolve().parent.parent/'kodi/script.frame/service.py').read_text())
        definition=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Playback')
        self.kodi=types.SimpleNamespace(Player=object,executebuiltin=Mock())
        self.route=Mock();self.api=Mock();self.rpc=Mock(return_value=[{'type':'video','playerid':1}])
        scope={'xbmc':self.kodi,'restore_movie_route':self.route,'api':self.api,'rpc':self.rpc}
        exec(compile(ast.Module(body=[definition],type_ignores=[]),'service.py','exec'),scope)
        self.player=scope['Playback']();self.player.stop=Mock();self.player.seekTime=Mock()
        self.player.getPlayingFile=Mock(return_value='/movie.mp4');self.player.getTotalTime=Mock(return_value=100)
        self.player.movie={'id':3,'path':'/movie.mp4'}
    def test_movie_start_restores_route_and_resume(self):
        self.player.pending_resume=.4
        self.player.onAVStarted()
        self.route.assert_called_once();self.player.seekTime.assert_called_once_with(40)
    def test_end_movie_preserves_resume_and_returns_home(self):
        self.player.tracking=True;self.player.progress=.4
        self.player.command({'action':'end_movie'})
        self.api.assert_called_once_with('/api/movies/3',{'progress':.4})
        self.player.stop.assert_called_once();self.kodi.executebuiltin.assert_called_once_with('RunScript(script.hyperdrive)')
    def test_movie_audio_route_failure_is_reported(self):
        self.route.side_effect=ValueError('HDMI missing')
        self.player.onAVStarted();self.assertEqual(self.player.error,'HDMI missing')
    def test_subtitles_use_active_video(self):
        self.player.command({'action':'subtitles_on'})
        self.rpc.assert_called_with('Player.SetSubtitle',playerid=1,subtitle='on')
