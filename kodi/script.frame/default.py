import sys
import xbmc, xbmcaddon, xbmcgui
from common import api
from controls import audio_menu, power_menu, update_menu, hdmi_setup, test_sound, voice_results

def menu(action):
    try: {'audio':audio_menu, 'power_menu':power_menu, 'updates':update_menu, 'audio_setup':hdmi_setup, 'audio_test':test_sound, 'voice_results':voice_results}[action]()
    except Exception as exc: xbmcgui.Dialog().ok('Frame', str(exc))

class Cinema(xbmcgui.WindowXML):
    def onInit(self):
        xbmcgui.Window(10000).setProperty('frame.window', str(xbmcgui.getCurrentWindowId()))
        self.category = 'all'
        self.reload()
        self.setFocusId(50 if self.movies else 10)

    def reload(self):
        try:
            self.movies = api('/api/movies')
            if self.category == 'favorites': self.movies = [m for m in self.movies if m['favorite']]
            if self.category == 'continue': self.movies = [m for m in self.movies if 0 < m['progress'] < .97]
            listing = self.getControl(50)
            listing.reset()
            for movie in self.movies:
                item = xbmcgui.ListItem(movie['title'], '{}  ·  {}'.format(movie['year'] or 'LOCAL', movie['genre']))
                item.setProperty('progress', '{}% watched'.format(int(movie['progress'] * 100)) if movie['progress'] else 'READY TO PLAY')
                listing.addItem(item)
            self.getControl(20).setLabel('{} films  ·  OK to play  ·  Menu to save to watchlist'.format(len(self.movies)) if self.movies else 'Upload your first film from the Frame portal on your phone or computer.')
        except Exception:
            self.movies = []
            self.getControl(20).setLabel('Portal is offline. Start the Frame server, then select Settings > Refresh movies.')

    def onClick(self, controlId):
        if controlId == 17:
            if not xbmc.getCondVisibility('System.HasAddon(script.hyperdrive)'):
                xbmcgui.Dialog().ok('Hyperdrive is not installed', 'Install hyperdrive-kodi.zip through Kodi Add-ons first.')
                return
            self.close()
            return
        if controlId == 12:
            choice=xbmcgui.Dialog().select('Frame settings', ['Refresh movies', 'Sound', 'Software updates', 'Power'])
            if choice==0:self.reload()
            elif choice>0:menu({1:'audio',2:'updates',3:'power_menu'}[choice])
            return
        if controlId in (10,11):
            if controlId==10:self.category='all'
            else:
                choice=xbmcgui.Dialog().select('Show movies', ['All movies','Watchlist','Continue watching'])
                if choice<0:return
                self.category=['all','favorites','continue'][choice]
            self.reload()
            if self.movies:self.setFocusId(50)
        elif controlId == 50 and self.movies:
            movie = self.movies[self.getControl(50).getSelectedPosition()]
            try: api('/api/tv/play', {'id':movie['id']})
            except Exception: xbmcgui.Dialog().ok('Frame', 'Could not start playback. Check the Frame portal and service.')

    def onAction(self, action):
        if action.getId() in (9, 10, 92): self.close()
        elif action.getId() == 117 and self.getFocusId() == 50 and self.movies:
            movie = self.movies[self.getControl(50).getSelectedPosition()]
            try:
                api('/api/movies/' + str(movie['id']), {'favorite':not movie['favorite']})
                self.reload()
            except Exception: xbmcgui.Dialog().notification('Frame', 'Could not save watchlist')

home = xbmcgui.Window(10000)
if len(sys.argv) > 1 and sys.argv[1] in ('audio', 'updates', 'power_menu', 'audio_setup', 'audio_test', 'voice_results'):
    menu(sys.argv[1])
elif home.getProperty('frame.open') != 'true':
    home.setProperty('frame.open', 'true')
    window = Cinema('Frame.xml', xbmcaddon.Addon().getAddonInfo('path'), 'Default', '1080i')
    try: window.doModal()
    finally:
        home.clearProperty('frame.open')
        home.clearProperty('frame.window')
        del window

    if xbmc.getCondVisibility('System.HasAddon(script.hyperdrive)') and not xbmc.Monitor().abortRequested():
        xbmc.executebuiltin('RunScript(script.hyperdrive)')

elif home.getProperty('frame.window').isdigit():
    xbmc.executebuiltin('ActivateWindow({})'.format(home.getProperty('frame.window')))
