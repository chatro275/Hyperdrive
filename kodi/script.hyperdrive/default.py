import json
from urllib.request import urlopen
import xbmc, xbmcaddon, xbmcgui

class Hyperdrive(xbmcgui.WindowXML):
    def onInit(self):
        xbmcgui.Window(10000).setProperty('hyperdrive.window',str(xbmcgui.getCurrentWindowId()))
        self.setFocusId(10)
    def onClick(self, control):
        if control==10:
            if not xbmc.getCondVisibility('System.HasAddon(script.frame)'):
                xbmcgui.Dialog().ok('Frame is not installed','Install the Frame Cinema add-on ZIP, then return here.');return
            self.close()
            xbmc.executebuiltin('RunScript(script.frame)')
        elif control==11:
            try:
                with urlopen('http://127.0.0.1:8080/api/storage',timeout=3) as r:state=json.load(r)
                info='{:.1f} GB free of {:.1f} GB'.format(state['free']/1024**3,state['total']/1024**3)
                xbmcgui.Dialog().ok('Your files',info+'\nUpload or download any file type at http://raspberrypi.local:8080 on your phone or computer.')
            except Exception:xbmcgui.Dialog().ok('Storage unavailable','Check the USB drive and Hyperdrive portal. Open http://raspberrypi.local:8080 on your phone or computer.')
        elif control==14:xbmc.executebuiltin('RunScript(script.frame,airplay)')
        elif control==12:xbmc.executebuiltin('RunScript(script.frame,updates)')
        elif control==13:xbmc.executebuiltin('RunScript(script.frame,power_menu)')
    def onAction(self, action):
        if action.getId() in (9,10,92):
            if xbmcgui.Dialog().yesno('Leave Hyperdrive?','Open the Kodi home screen?'):self.close()

home=xbmcgui.Window(10000)
if home.getProperty('hyperdrive.open')!='true':
    home.setProperty('hyperdrive.open','true')
    window=Hyperdrive('Hyperdrive.xml',xbmcaddon.Addon().getAddonInfo('path'),'Default','1080i')
    try:window.doModal()
    finally:
        home.clearProperty('hyperdrive.open');home.clearProperty('hyperdrive.window');del window

elif home.getProperty('hyperdrive.window').isdigit():
    xbmc.executebuiltin('ActivateWindow({})'.format(home.getProperty('hyperdrive.window')))
