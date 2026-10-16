"""Native TV controls shared by the Frame window and background service."""
import json
import subprocess
import xbmc, xbmcgui
from common import api

def rpc(method, **params):
    result = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0', 'id':1, 'method':method, 'params':params})))
    if 'error' in result: raise ValueError(result['error'].get('message', 'Kodi command failed'))
    return result.get('result')

def audio_status():
    state = rpc('Application.GetProperties', properties=['volume','muted'])
    state['tracks'] = []
    players = rpc('Player.GetActivePlayers')
    video = next((p for p in players if p['type'] == 'video'), None)
    if video:
        details = rpc('Player.GetProperties', playerid=video['playerid'], properties=['audiostreams','currentaudiostream'])
        state['tracks'] = details.get('audiostreams', [])
        state['track'] = details.get('currentaudiostream', {}).get('index', -1)
    state['output'] = rpc('Settings.GetSettingValue', setting='audiooutput.audiodevice').get('value', '')
    state['passthrough'] = rpc('Settings.GetSettingValue', setting='audiooutput.passthrough').get('value', False)
    return state

def power_status():
    result = rpc('System.GetProperties', properties=['canreboot', 'canshutdown'])
    return {'reboot':result.get('canreboot', False), 'shutdown':result.get('canshutdown', False)}

def execute_power(action):
    if not power_status().get(action): raise ValueError('Kodi does not have permission to ' + action)
    rpc('System.Reboot' if action == 'reboot' else 'System.Shutdown')

def power_menu():
    choice = xbmcgui.Dialog().select('Power', ['Restart Raspberry Pi', 'Shut down Raspberry Pi'])
    if choice < 0: return
    message = 'Stop playback and restart the Pi?' if choice == 0 else 'Stop playback and shut down the Pi? Power it on physically to use Frame again.'
    if xbmcgui.Dialog().yesno('Frame power', message): execute_power('reboot' if choice == 0 else 'shutdown')

def set_track(index):
    players = rpc('Player.GetActivePlayers')
    video = next((p for p in players if p['type']=='video'), None)
    if not video: raise ValueError('Start a movie to choose an audio track')
    rpc('Player.SetAudioStream', playerid=video['playerid'], stream=index)

def audio_menu():
    state = audio_status()
    choice = xbmcgui.Dialog().select('Audio · Volume {}%{}'.format(state['volume'], ' · Muted' if state['muted'] else ''),
        ['Volume up', 'Volume down', 'Unmute' if state['muted'] else 'Mute', 'Movie audio track', 'HDMI / speaker output settings', 'AirPlay receiver settings', 'Configure HDMI for TV speakers', 'Test left / right sound'])
    if choice in (0, 1) and state.get('passthrough'):
        return xbmcgui.Dialog().ok('Passthrough audio', 'Adjust volume on your TV or receiver while passthrough is enabled.')
    if choice == 0: rpc('Application.SetVolume', volume=min(100,state['volume']+5))
    elif choice == 1: rpc('Application.SetVolume', volume=max(0,state['volume']-5))
    elif choice == 2: rpc('Application.SetMute', mute='toggle')
    elif choice == 3:
        tracks = state['tracks']
        if not tracks: return xbmcgui.Dialog().ok('Audio tracks', 'Start a movie to select its language or audio track.')
        selected = xbmcgui.Dialog().select('Movie audio track', [track_label(t) for t in tracks])
        if selected >= 0: set_track(tracks[selected]['index'])
    elif choice == 4: xbmc.executebuiltin('ActivateWindow(systemsettings)')
    elif choice == 5: xbmc.executebuiltin('ActivateWindow(servicesettings)')
    elif choice == 6: hdmi_setup()
    elif choice == 7: test_sound()

def track_label(track):
    return '{} · {} · {} channels'.format(track.get('name') or track.get('language') or 'Track '+str(track['index']+1), track.get('codec',''), track.get('channels','?'))

def update_menu():
    state = api('/api/update')
    if not state['staged']:
        release=api('/api/update/github/check',{},timeout=45)
        if not release['available']:return xbmcgui.Dialog().ok('Hyperdrive updates','You are up to date.')
        if not xbmcgui.Dialog().yesno('Download '+release['version']+'?', 'Download and verify the GitHub release? Installation requires a separate confirmation.'):return
        api('/api/update/github/download',{'version':release['version'],'digest':release['digest']},timeout=120)
        state=api('/api/update')
    if not state['staged']:
        return xbmcgui.Dialog().ok('Frame ' + state['installed'], 'No update is staged. Use Software updates in the dashboard.')
    if xbmc.Player().isPlaying():
        return xbmcgui.Dialog().ok('Finish playback first', 'Stop playback before installing a Frame update.')
    if not xbmcgui.Dialog().yesno('Install Frame ' + state['staged'] + '?',
            'Install the bundle uploaded through your portal? Only approve bundles from a source you trust. Movies and library data are preserved. Restart Kodi afterward.'): return
    result = api('/api/update/apply', {'version':state['staged'], 'digest':state['digest'], 'confirmed':True}, timeout=120)
    xbmcgui.Dialog().ok('Update installed', 'Restart Kodi or the Pi to load the new TV software. ' + ('The portal is restarting automatically.' if result['automatic_restart'] else 'Restart the Frame server manually too.'))

def set_setting(name, value):
    if rpc('Settings.SetSettingValue', setting=name, value=value) is not True:
        raise ValueError('Kodi could not change ' + name)

def pactl(*args):
    try:
        return subprocess.run(['pactl', *args], check=True, capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Cannot access Pi desktop audio. Install pulseaudio-utils and run Kodi as your desktop user.') from exc

def desktop_sinks():
    try:
        return json.loads(pactl('--format=json', 'list', 'sinks'))
    except (ValueError, TypeError):
        return []

def audible_volume():
    state=rpc('Application.GetProperties', properties=['volume','muted'])
    rpc('Application.SetMute', mute=False)
    if state['volume']==0:rpc('Application.SetVolume', volume=50)

def route_desktop(sink):
    # This runs inside Kodi's desktop session, not the system web service.
    name=sink['name']
    pactl('set-default-sink', name)
    pactl('set-sink-mute', name, '0')
    volumes=sink.get('volume', {})
    if volumes and all(v.get('value', 0)==0 for v in volumes.values()):
        pactl('set-sink-volume', name, '50%')
    streams=json.loads(pactl('--format=json', 'list', 'sink-inputs'))
    for stream in streams:
        props=stream.get('properties', {})
        app=(props.get('application.name','')+' '+props.get('application.process.binary','')).lower()
        if 'kodi' not in app:continue
        index=str(stream['index'])
        pactl('move-sink-input', index, name)
        pactl('set-sink-input-mute', index, '0')
        levels=stream.get('volume', {})
        if levels and all(v.get('value',0)==0 for v in levels.values()):
            pactl('set-sink-input-volume', index, '50%')

def hdmi_setup():
    settings=rpc('Settings.GetSettings', level='expert', filter={'section':'system','category':'audio'}).get('settings',[])
    output=next((s for s in settings if s['id']=='audiooutput.audiodevice'),{})
    options=output.get('options',[])
    devices=[dict(o) for o in options if 'hdmi' in (str(o.get('label',''))+' '+str(o.get('value',''))).lower()]
    pulse_default=next((o for o in options if str(o.get('value','')).upper()=='PULSE:DEFAULT'),None)
    sinks=desktop_sinks() if any(str(o.get('value','')).upper().startswith('PULSE:') for o in options) else []
    for sink in sinks:
        if 'hdmi' not in (sink.get('name','')+' '+sink.get('description','')).lower():continue
        device=next((d for d in devices if d['value']=='PULSE:'+sink['name']),None)
        if device is not None:device['sink']=sink
        elif pulse_default:
            devices.append({'label':sink.get('description',sink['name'])+' (Pi desktop)', 'value':pulse_default['value'], 'sink':sink})
    if not devices:
        xbmcgui.Dialog().ok('HDMI output not found', 'Check the HDMI cable and TV, then choose an output in Kodi System → Audio. If Kodi uses a default PipeWire output, select HDMI in the Pi desktop sound settings.')
        xbmc.executebuiltin('ActivateWindow(systemsettings)');return
    choice=xbmcgui.Dialog().select('Choose your TV HDMI output', [str(d['label']) for d in devices])
    if choice<0:return
    if not xbmcgui.Dialog().yesno('Fix HDMI sound?', 'Use this HDMI output with stereo PCM and unmute audio? Zero volume will be raised to 50%. For desktop audio, this also selects and unmutes the Pi HDMI output.'):return
    values={'audiooutput.audiodevice':devices[choice]['value'], 'audiooutput.passthrough':False,'audiooutput.channels':1}
    old={key:rpc('Settings.GetSettingValue',setting=key)['value'] for key in values}
    changed=[]
    try:
        for key,value in values.items():set_setting(key,value);changed.append(key)
        if devices[choice].get('sink'):route_desktop(devices[choice]['sink'])
        audible_volume()
    except Exception:
        for key in reversed(changed):set_setting(key,old[key])
        raise
    audio_profile().write_text(json.dumps({'sink':devices[choice].get('sink',{}).get('name','')}))
    if xbmcgui.Dialog().yesno('HDMI configured', 'Run the left and right sound test now? Stop any current movie first. If sound is still missing, check the TV mute/volume and selected HDMI port.'):
        test_sound()

def test_sound():
    import math, struct, wave
    from pathlib import Path
    import xbmcaddon, xbmcvfs
    if xbmc.Player().isPlaying():
        xbmcgui.Dialog().ok('Stop playback first', 'Stop the movie or music before running the sound test.');return
    folder=Path(xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile')));folder.mkdir(parents=True,exist_ok=True)
    path=folder/'sound-test.wav';rate=48000
    with wave.open(str(path),'wb') as sound:
        sound.setparams((2,2,rate,0,'NONE','not compressed'))
        frames=bytearray()
        for n in range(rate*4):
            t=n/rate;left=0;right=0
            if .2<t<1.4:left=int(6500*math.sin(2*math.pi*440*t)*min(1,(t-.2)*20,(1.4-t)*20))
            if 2.2<t<3.4:right=int(6500*math.sin(2*math.pi*660*t)*min(1,(t-2.2)*20,(3.4-t)*20))
            frames.extend(struct.pack('<hh',left,right))
        sound.writeframes(frames)
    xbmcgui.Dialog().notification('Sound test', 'Left tone, then right tone. Check TV volume and mute.')
    audible_volume()
    player=xbmc.Player();monitor=xbmc.Monitor()
    player.play(str(path))
    started=False
    for _ in range(50):
        if monitor.waitForAbort(.1):return
        if player.isPlaying() and player.getPlayingFile()==str(path):
            started=True;break
    if not started:
        api('/api/audio/verification',{'heard':False,'output':audio_status().get('output','')})
        xbmcgui.Dialog().ok('Sound test could not start', 'Kodi did not start the test file. Check Kodi System → Audio and the Kodi log.');return
    if monitor.waitForAbort(4):return
    heard=xbmcgui.Dialog().yesno('Sound test', 'Did you hear both tones from the intended speakers?')
    state=audio_status()
    api('/api/audio/verification',{'heard':heard,'output':state.get('output','')})
    if not heard:xbmcgui.Dialog().ok('Sound is not confirmed', 'Check TV mute/volume, select the connected HDMI output, and disable passthrough for TV speakers. Then repeat the test.')

def voice_results():
    state=api('/api/voice');results=state.get('results',[])
    if not results:return xbmcgui.Dialog().ok('Hey Hyper',state.get('message') or 'No search results yet.')
    choice=xbmcgui.Dialog().select('Web search results', [r['title'] for r in results])
    if choice>=0:
        result=results[choice]
        xbmcgui.Dialog().textviewer(result['title'],result['snippet']+'\n\n'+result['url']+'\n\nOpen the link in the Frame portal on your phone or computer.')


def audio_profile():
    from pathlib import Path
    import xbmcaddon, xbmcvfs
    folder=Path(xbmcvfs.translatePath(xbmcaddon.Addon('script.frame').getAddonInfo('profile')))
    folder.mkdir(parents=True,exist_ok=True)
    return folder/'audio-route.json'

def restore_movie_route():
    # Desktop streams are recreated for each movie; keep the explicitly chosen sink.
    try: saved=json.loads(audio_profile().read_text())
    except (OSError,ValueError):return
    name=saved.get('sink')
    if not name:return
    sinks=desktop_sinks()
    if not any(s.get('name')==name for s in sinks):raise ValueError('Saved HDMI output is missing. Run Fix HDMI sound again.')
    for stream in json.loads(pactl('--format=json','list','sink-inputs')):
        props=stream.get('properties',{})
        if 'kodi' in (props.get('application.name','')+' '+props.get('application.process.binary','')).lower():
            pactl('move-sink-input',str(stream['index']),name)

def diagnose_movie_audio():
    state=audio_status();issues=[]
    if state.get('muted'):issues.append('Kodi is muted.')
    if state.get('volume')==0:issues.append('Kodi volume is zero.')
    if not state.get('tracks'):issues.append('No movie audio tracks detected. Start a movie; the file may have no audio.')
    elif state.get('track',-1)<0:issues.append('No active audio track. Select a track in Sound settings.')
    if state.get('passthrough'):issues.append('Passthrough is enabled. TV speakers may need stereo PCM; use Fix HDMI sound.')
    if not state.get('output'):issues.append('No Kodi output device is selected.')
    message='Output: '+str(state.get('output','unknown'))+'\n'+'\n'.join(issues or ['Kodi reports an active audio track and nonzero, unmuted volume. This does not prove sound reaches the TV.'])
    xbmcgui.Dialog().textviewer('Movie audio diagnosis',message)
    return issues
