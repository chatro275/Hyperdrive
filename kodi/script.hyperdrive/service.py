"""Open the launcher at Kodi startup even when the portal or USB is unavailable."""
import xbmc
monitor=xbmc.Monitor()
if not monitor.waitForAbort(2):xbmc.executebuiltin('RunScript(script.hyperdrive)')
