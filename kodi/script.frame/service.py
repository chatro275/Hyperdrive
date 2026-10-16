import json, time
import xbmc, xbmcgui
from common import api
from controls import rpc, audio_status, power_status, set_track, execute_power

class Playback(xbmc.Player):
    movie = None
    pending_resume = 0
    progress = 0
    error = ''
    tracking = False

    def save(self, ended=False):
        if self.movie and self.tracking:
            try: api('/api/movies/' + str(self.movie['id']), {'progress':1 if ended else self.progress})
            except Exception as exc: xbmc.log('Frame progress save: ' + str(exc), xbmc.LOGWARNING)

    def onAVStarted(self):
        self.tracking = bool(self.movie and self.getPlayingFile() == self.movie['path'])
        if self.pending_resume and self.tracking:
            try: self.seekTime(self.getTotalTime() * self.pending_resume)
            except RuntimeError: pass
            self.pending_resume = 0

    def onPlayBackStopped(self):
        self.save()
        self.tracking = False

    def onPlayBackEnded(self):
        self.save(ended=True)
        self.progress = 1
        self.tracking = False

    def onPlayBackError(self):
        self.error = 'Kodi could not play this file. Check the file and codec support.'
        xbmcgui.Dialog().notification('Frame', self.error)

    def command(self, command):
        action = command['action']
        if action == 'play':
            self.save()
            self.movie = command
            self.tracking = False
            self.error = ''
            self.progress = command.get('progress', 0)
            self.pending_resume = self.progress if self.progress < .97 else 0
            item = xbmcgui.ListItem(command['title'])
            item.setInfo('video', {'title':command['title'], 'mediatype':'movie'})
            self.play(command['path'], item)
        elif action == 'pause' and self.isPlaying(): self.pause()
        elif action in ('pause_only','resume'):
            for active in rpc('Player.GetActivePlayers'):
                rpc('Player.PlayPause',playerid=active['playerid'],play=action=='resume')
        elif action in ('mute_on','mute_off'): rpc('Application.SetMute',mute=action=='mute_on')
        elif action in ('volume_up','volume_down'):
            state=audio_status()
            if state.get('passthrough'):raise ValueError('Use TV or receiver volume while passthrough is enabled')
            rpc('Application.SetVolume',volume=max(0,min(100,state['volume']+(5 if action=='volume_up' else -5))))
        elif action in ('seek_forward','seek_backward','seek_seconds','restart_movie'):
            if not self.isPlayingVideo():raise ValueError('Start a movie first')
            offset=command.get('value',30 if action=='seek_forward' else -30)
            target=0 if action=='restart_movie' else max(0,min(self.getTotalTime()-1,self.getTime()+offset))
            self.seekTime(target)
        elif action in ('subtitles_on','subtitles_off'):
            video=next((p for p in rpc('Player.GetActivePlayers') if p['type']=='video'),None)
            if not video:raise ValueError('Start a movie first')
            rpc('Player.SetSubtitle',playerid=video['playerid'],subtitle='on' if action=='subtitles_on' else 'off')
        elif action == 'stop': self.stop()
        elif action == 'volume':
            if audio_status().get('passthrough'):raise ValueError('Use TV or receiver volume while passthrough is enabled')
            rpc('Application.SetVolume', volume=command['value'])
        elif action == 'mute': rpc('Application.SetMute', mute='toggle')
        elif action == 'audio_track': set_track(command['value'])
        elif action == 'audio_settings': xbmc.executebuiltin('ActivateWindow(systemsettings)')
        elif action == 'airplay_settings': xbmc.executebuiltin('ActivateWindow(servicesettings)')
        elif action in ('updates', 'power_menu', 'audio_setup', 'audio_test', 'voice_results'): xbmc.executebuiltin('RunScript(script.frame,{})'.format(action))
        elif action == 'voice_listening': xbmcgui.Dialog().notification('Hey Hyper', 'Listening for a command…', time=2500)
        elif action == 'voice_feedback': xbmcgui.Dialog().notification('Hey Hyper', command['message'], time=5000)
        elif action in ('reboot', 'shutdown'):
            self.save()
            execute_power(action)
        elif action == 'hyperdrive':
            xbmc.executebuiltin('RunScript(script.hyperdrive)')
        elif action == 'home':
            window = xbmcgui.Window(10000).getProperty('frame.window')
            if window.isdigit(): xbmc.executebuiltin('ActivateWindow({})'.format(window))
            else: xbmc.executebuiltin('RunScript(script.frame)')
        elif action in ('left','right','up','down','select','back'):
            xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':'Input.' + action.capitalize()}))

monitor = xbmc.Monitor()
player = Playback()
opened = False
last_save = 0
while not monitor.abortRequested():
    try:
        if player.isPlayingVideo() and player.movie and player.getPlayingFile() == player.movie['path']:
            duration = player.getTotalTime()
            if duration: player.progress = player.getTime() / duration
            if time.monotonic() - last_save > 5:
                player.save(); last_save = time.monotonic()
        try: audio = audio_status()
        except Exception: audio = {}
        try: power = power_status()
        except Exception: power = {}
        title = player.movie['title'] if player.movie and player.isPlayingVideo() else ''
        if player.isPlayingAudio():
            try: title = player.getMusicInfoTag().getTitle() or 'Audio playback'
            except Exception: title = 'Audio playback'
        result = api('/api/tv/poll', {'playing':player.isPlaying(), 'title':title, 'error':player.error, 'audio':audio, 'power':power})
        if not opened:
            if not xbmc.getCondVisibility('System.HasAddon(script.hyperdrive)'):
                xbmc.executebuiltin('RunScript(script.frame)')
            opened = True
        for command in result['commands']:
            try:
                player.command(command)
                player.error = ''
            except Exception as exc:
                player.error = str(exc)
                xbmcgui.Dialog().notification('Frame', player.error)
    except Exception as exc:
        xbmc.log('Frame service: ' + str(exc), xbmc.LOGWARNING)
    if monitor.waitForAbort(1): break
player.save()
