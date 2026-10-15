#!/usr/bin/env python3
"""One-time bridge for existing 2.4.x installations; stage a GitHub release."""
import argparse, hashlib, json, sys
from pathlib import Path
from urllib.request import Request, urlopen

REPO='chatro275/Hyperdrive'

def fetch(url,limit):
    with urlopen(Request(url,headers={'User-Agent':'Hyperdrive-Setup'}),timeout=30) as response:
        raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Download exceeds size limit')
    return raw

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path.home()/'HyperMedia');args=parser.parse_args()
    root=args.root.resolve();sys.path.insert(0,str(root))
    from updater import Updater,validate,MAX_ARCHIVE
    release=json.loads(fetch('https://api.github.com/repos/'+REPO+'/releases/latest',2*1024**2))
    version=release['tag_name'].removeprefix('v')
    assets=[a for a in release['assets'] if a['name']=='frame-update-'+version+'.zip']
    if len(assets)!=1:raise ValueError('No unique update bundle in release')
    asset=assets[0];url=asset['browser_download_url']
    if not url.startswith('https://github.com/'+REPO+'/releases/download/'):raise ValueError('Unexpected asset location')
    if not 0<asset['size']<=MAX_ARCHIVE:raise ValueError('Bundle too large')
    raw=fetch(url,MAX_ARCHIVE)
    if len(raw)!=asset['size'] or asset.get('digest')!='sha256:'+hashlib.sha256(raw).hexdigest():raise ValueError('Release integrity check failed')
    manifest,_=validate(raw)
    if manifest['version']!=version:raise ValueError('Release version mismatch')
    Updater(root,Path.home()/'.kodi/addons/script.frame').stage(raw)
    print('Downloaded and verified Hyperdrive '+version+'. On the TV open Frame → Settings → Software updates, approve, then restart the Pi.')

if __name__=='__main__':
    try:main()
    except Exception as exc:sys.exit('Update was not staged: '+str(exc))
