#!/usr/bin/env python3
"""Frame: dependency-free, LAN movie library with range-aware streaming."""
import argparse, json, mimetypes, os, re, sqlite3, threading, time, tempfile, shutil, uuid
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs, quote
from updater import Updater, MAX_ARCHIVE
from voice import parse_command, search_web, normalize
from storage import require_storage, file_path, directory_path

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'library.db'
MEDIA = Path(os.environ.get('FRAME_MEDIA', str(ROOT / 'movies'))).resolve()
LOCK = threading.Lock()
TV_LOCK = threading.Lock()
TV = {'seen': 0, 'playing': False, 'title': '', 'error': ''}
COMMANDS = []
VIDEO_TYPES = {'.mp4', '.m4v', '.webm', '.mkv', '.mov', '.avi', '.ts'}
UPDATER = Updater(ROOT, Path.home() / '.kodi/addons/script.frame')
VOICE_LOCK = threading.Lock()
VOICE = {'seen':0, 'device':'', 'error':'', 'last_command':'', 'message':'', 'results':[]}
VOICE_PENDING = {}
VOICE_SETTINGS = ROOT / 'voice-settings.json'
AUDIO_VERIFICATION = {'heard':False, 'output':'', 'time':None}

def voice_settings():
    defaults={'enabled':True, 'device':'', 'secondary_device':'', 'revision':0,'enhancement':'balanced'}
    try: defaults.update(json.loads(VOICE_SETTINGS.read_text()))
    except (OSError, ValueError, TypeError): pass
    return defaults

def voice_enabled():
    return voice_settings()['enabled'] is True

def voice_folder(name):
    if not name:return directory_path(MEDIA,'')
    current=MEDIA
    for part in name.split('/'):
        file_path(current,part)  # Reject traversal, control characters and symlinks.
        matches=[p for p in current.iterdir() if p.is_dir() and not p.is_symlink() and normalize(p.name)==normalize(part)]
        if len(matches)!=1:raise ValueError('Folder name must match exactly one folder')
        current=directory_path(MEDIA,matches[0].relative_to(MEDIA).as_posix())
    return current

def voice_command(text):
    if not voice_enabled(): raise ValueError('Voice control is disabled')
    with connect() as c: movies = [dict(r) for r in c.execute('SELECT id,title,path,progress FROM movies')]
    command = parse_command(text, movies)
    action=command['action']
    def feedback(message):
        with VOICE_LOCK:VOICE.update(last_command=text,message=message,results=[])
        try:queue_command({'action':'voice_feedback','message':message[:200]})
        except ValueError:pass
        return {'ok':True,'message':message}
    if action=='check_updates':
        release=UPDATER.github_release()
        return feedback(('Update '+release['version']+' is available. Say update Hyperdrive to review it on TV.') if release['available'] else 'Hyperdrive is up to date.')
    if action=='voice_help':
        return feedback('Try: play a movie, pause, resume, skip forward thirty seconds, subtitles on, add a movie to watchlist, storage space, list files, list folders, find files called holiday, create folder called holidays, scan movies, open Hyperdrive.')
    if action=='now_playing':
        tv=tv_status();return feedback(('Playing: '+tv.get('title','')) if tv.get('playing') else 'Nothing is playing on the TV.')
    if action in ('play_random','continue_movie'):
        import random
        candidates=movies if action=='play_random' else sorted([m for m in movies if 0<m['progress']<.97],key=lambda m:m['title'])
        if not candidates:raise ValueError('No movies available for this request')
        selected=random.choice(candidates) if action=='play_random' else candidates[0]
        command={'action':'play','id':selected['id']}
    if action=='watchlist':
        with connect() as c:c.execute('UPDATE movies SET favorite=? WHERE id=?',(int(command['favorite']),command['id']))
        return feedback('Watchlist updated.')
    if action in ('move_file','rename_file'):
        require_storage(MEDIA)
        matches=[]
        for index,path in enumerate(MEDIA.rglob('*')):
            if index>=10000:break
            if path.is_file() and not path.is_symlink() and normalize(path.name)==normalize(command['name']):matches.append(path)
        if len(matches)!=1:raise ValueError('Say the exact filename including its extension. It must match one file only.')
        source=matches[0]
        # Validate every parent against symlinks and traversal.
        source_parent=directory_path(MEDIA,source.parent.relative_to(MEDIA).as_posix() if source.parent!=MEDIA else '')
        source=file_path(source_parent,source.name)
        if action=='rename_file':
            name=command['destination']
            if not Path(name).suffix:name+=source.suffix
            target=file_path(source_parent,name)
        else:
            folder=voice_folder(command['destination'])
            target=file_path(folder,source.name)
        if target.exists():raise ValueError('The destination already exists; no files were changed.')
        stat=source.stat()
        with VOICE_LOCK:
            VOICE_PENDING.clear();VOICE_PENDING.update(token=uuid.uuid4().hex,source=source.relative_to(MEDIA).as_posix(),destination=target.relative_to(MEDIA).as_posix(),expires=time.time()+120,stamp=[stat.st_ino,stat.st_size,stat.st_mtime_ns])
        return feedback('Review and confirm the file change in Hey Hyper microphone settings. No file has been changed yet.')
    if action in ('storage_space','list_files','list_folders','find_files','create_folder','scan_movies'):
        require_storage(MEDIA)
        if action=='storage_space':
            disk=shutil.disk_usage(MEDIA);return feedback('{:.1f} GB free of {:.1f} GB.'.format(disk.free/1024**3,disk.total/1024**3))
        if action=='scan_movies':return feedback('Library scanned: '+str(scan())+' movie files.')
        if action=='create_folder':
            target=file_path(MEDIA,command['name'])
            with LOCK:target.mkdir()
            return feedback('Created folder: '+target.name)
        folder=voice_folder(command.get('name','')) if action=='list_files' else MEDIA
        if action=='find_files':
            term=command['name'].casefold();found=[]
            for index,path in enumerate(MEDIA.rglob('*')):
                if index>=10000:break
                if path.is_file() and not path.is_symlink() and term in path.name.casefold():
                    found.append(path.relative_to(MEDIA).as_posix())
                    if len(found)>=10:break
            return feedback('Matching files (up to 10): '+', '.join(found) if found else 'No matching files found in the first 10,000 entries.')
        names=[]
        for path in folder.iterdir():
            if path.is_symlink() or path.name.startswith(('.upload-','.migration-')):continue
            if action=='list_folders' and not path.is_dir():continue
            names.append(path.name+('/' if path.is_dir() else ''))
            if len(names)>=10:break
        return feedback('Entries (up to 10): '+', '.join(names) if names else 'This folder is empty.')
    if command['action'] == 'web_search':
        results = search_web(command['query'])
        with VOICE_LOCK: VOICE.update(results=results, message='Search results for ' + command['query'], last_command=text)
        try: queue_command({'action':'voice_results'})
        except ValueError: pass
        return {'ok':True, 'message':'Search results are on the TV and portal', 'results':results}
    if command['action'] == 'play':
        require_storage(MEDIA)
        movie = next(m for m in movies if m['id'] == command['id'])
        path=Path(movie['path']).resolve()
        if not path.is_relative_to(MEDIA) or not path.is_file(): raise ValueError('Movie file is missing')
        command.update(path=str(path), title=movie['title'], progress=movie['progress'])
    queue_command(command)
    message='Playing ' + command['title'] if command['action']=='play' else 'Sent to TV: ' + command['action'].replace('_',' ')
    with VOICE_LOCK: VOICE.update(last_command=text, message=message, results=[])
    return {'ok':True, 'message':message}

def voice_pending():
    with VOICE_LOCK:
        if VOICE_PENDING.get('expires',0)<time.time():return None
        return {k:v for k,v in VOICE_PENDING.items() if k!='stamp'}

def confirm_voice_storage(token):
    require_storage(MEDIA)
    with LOCK,VOICE_LOCK:
        pending=dict(VOICE_PENDING)
        if not token or token!=pending.get('token') or pending.get('expires',0)<time.time():raise ValueError('File request expired. Ask again.')
        if tv_status().get('playing'):raise ValueError('Stop playback before changing file locations.')
        def checked(relative):
            p=Path(relative);parent='' if str(p.parent)=='.' else p.parent.as_posix()
            return file_path(directory_path(MEDIA,parent),p.name)
        source=checked(pending['source']);target=checked(pending['destination']);stat=source.stat()
        if [stat.st_ino,stat.st_size,stat.st_mtime_ns]!=pending['stamp']:raise ValueError('The source file changed. Ask again.')
        if target.exists():raise ValueError('The destination already exists.')
        moved=False
        try:
            with connect() as c:
                c.execute('UPDATE movies SET path=? WHERE path=?',(str(target),str(source)))
                c.execute('DELETE FROM frame_visibility WHERE path=?',(pending['destination'],))
                c.execute('UPDATE frame_visibility SET path=? WHERE path=?',(pending['destination'],pending['source']))
                source.rename(target);moved=True
        except Exception:
            if moved:target.rename(source)
            raise
        VOICE_PENDING.clear()
        VOICE.update(message='File moved to '+pending['destination'])
        return {'ok':True}

def tv_status():
    with TV_LOCK:
        return {**TV, 'online': time.monotonic() - TV['seen'] < 10}

def queue_command(command):
    with TV_LOCK:
        if time.monotonic() - TV['seen'] >= 10:
            raise ValueError('TV is offline. Open Kodi and enable the Frame add-on on your Pi.')
        if len(COMMANDS) >= 20:
            raise ValueError('TV is busy. Try again in a moment.')
        COMMANDS.append({**command, 'expires': time.monotonic() + 15})

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY, path TEXT UNIQUE, title TEXT, genre TEXT DEFAULT "Unsorted", year TEXT DEFAULT "", favorite INTEGER DEFAULT 0, progress REAL DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS frame_visibility (path TEXT PRIMARY KEY, visible INTEGER NOT NULL)')

def scan():
    count = 0
    require_storage(MEDIA)
    if not MEDIA.is_dir():
        raise ValueError('Media folder does not exist: ' + str(MEDIA))
    with LOCK, connect() as c:
        hidden={r['path'] for r in c.execute('SELECT path FROM frame_visibility WHERE visible=0')}
        for p in MEDIA.rglob('*'):
            if p.suffix.lower() not in VIDEO_TYPES or not p.is_file(): continue
            p = p.resolve()
            if not p.is_relative_to(MEDIA): continue
            if str(p.relative_to(MEDIA)) in hidden:continue
            year = re.search(r'\b(19\d{2}|20\d{2})\b', p.stem)
            title = re.sub(r'[._]', ' ', p.stem)
            if year: title = title[:year.start()].strip(' -([')
            c.execute('INSERT OR IGNORE INTO movies(path,title,year) VALUES(?,?,?)', (str(p), title, year.group() if year else ''))
            count += 1
    return count

class HealthMonitor:
    """Bounded local incident history and conservative microphone recovery."""
    def __init__(self, path):
        self.path=Path(path);self.lock=threading.RLock();self.check_lock=threading.Lock()
        self.started=time.monotonic();self.failures=0;self.checks=[];self.checked=0
        self.events=[];self.attempts=[];self.auto=True;self.storage_error=''
        try:
            saved=json.loads(self.path.read_text())
            self.events=saved.get('events',[])[-100:];self.attempts=saved.get('attempts',[])[-3:]
            self.auto=saved.get('auto',True) is True
        except (OSError,ValueError,TypeError,AttributeError):pass

    @staticmethod
    def clean(message):
        text=str(message).replace(str(ROOT),'<app>').replace(str(Path.home()),'<home>')
        text=re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+',r'\1[redacted]',text)
        text=re.sub(r'\bsk-[\w-]+','[redacted]',text)
        return text[:1200]

    def save(self):
        try:
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'events':self.events,'attempts':self.attempts,'auto':self.auto}))
            temp.chmod(0o600);temp.replace(self.path);self.storage_error=''
        except OSError:
            self.storage_error='Cannot save health history; check disk space and permissions.'

    def event(self, component, message):
        with self.lock:
            message=self.clean(message);now=time.time()
            if self.events and self.events[-1]['component']==component and self.events[-1]['message']==message and now-self.events[-1]['time']<300:return
            self.events.append({'time':now,'component':component,'message':message})
            self.events=self.events[-100:];self.save()

    def snapshot(self):
        with self.lock:
            return {'checked':self.checked,'checks':list(self.checks),'events':list(self.events),
                    'auto_recovery':self.auto,'storage_error':self.storage_error,
                    'version':UPDATER.running,'remote_reporting':'Not connected',
                    'limits':'Checks run every 15 seconds while the portal runs. Recovery only refreshes microphone capture. Hardware sound requires a listening test.'}

    def check(self):
        with self.check_lock:
            checks=[]
            def add(name, ok, message):checks.append({'name':name,'ok':ok,'message':self.clean(message)})
            add('Portal',True,'Portal process is responding')
            try:
                with connect() as c:c.execute('SELECT id FROM movies LIMIT 1').fetchone()
                add('Library',True,'Database is readable')
            except (OSError,sqlite3.Error) as exc:add('Library',False,exc)
            try:
                require_storage(MEDIA)
                free=shutil.disk_usage(MEDIA).free
                add('Storage',free>256*1024**2, str(round(free/1024**3,2))+' GB available')
            except (OSError,ValueError) as exc:add('Storage',False,exc)
            tv=tv_status()
            add('Kodi',tv['online'] and not tv.get('error'),tv.get('error') or ('Connected' if tv['online'] else 'No heartbeat. Open Kodi and enable Frame.'))
            with VOICE_LOCK:voice=dict(VOICE)
            enabled=voice_enabled();online=time.monotonic()-voice['seen']<10
            error=voice.get('error','')
            add('Microphone',not enabled or (online and not error),'Paused' if not enabled else error or ('Connected' if online else 'No heartbeat. Check frame-voice service.'))
            if enabled and online:
                add('Speech recognition',True,'Recognized utterances: {} · Wake detections: {} · Commands sent: {}'.format(voice.get('utterances',0),voice.get('wakes',0),voice.get('commands',0)))
            audio=tv.get('audio',{})
            add('Sound test',bool(AUDIO_VERIFICATION['heard'] and AUDIO_VERIFICATION['output']==audio.get('output')), 'User-confirmed test only; software cannot hear the TV speakers.')
            with self.lock:
                previous={c['name']:c for c in self.checks}
                self.checks=checks;self.checked=time.time()
                for check in checks:
                    old=previous.get(check['name'])
                    if not check['ok'] and (not old or old['ok'] or old['message']!=check['message']):self.event(check['name'],check['message'])
                    elif check['ok'] and old and not old['ok']:self.event(check['name'],'Recovered: '+check['message'])
                # Only known capture failures qualify; parser/search errors must not restart the mic.
                failed=enabled and online and error.startswith(('Cannot open microphone:', 'Cannot start microphone:'))
                self.failures=self.failures+1 if failed else 0
                now=time.time();self.attempts=[t for t in self.attempts if now-t<3600]
                if self.auto and self.failures>=3 and time.monotonic()-self.started>=60 and len(self.attempts)<3 and (not self.attempts or now-self.attempts[-1]>=300):
                    # Record the attempt first so restarting the portal cannot reset the budget.
                    self.attempts.append(now);self.save()
                    if self.storage_error:
                        return self.snapshot()
                    try:
                        with VOICE_LOCK:
                            settings=voice_settings();settings['revision']+=1
                            temp=VOICE_SETTINGS.with_suffix('.tmp');temp.write_text(json.dumps(settings));temp.replace(VOICE_SETTINGS)
                        self.event('Recovery','Requested microphone refresh; awaiting healthy heartbeat.')
                    except OSError as exc:self.event('Recovery',exc)
            return self.snapshot()

    def run(self):
        while True:
            try:self.check()
            except Exception as exc:self.event('Monitor',type(exc).__name__+': '+str(exc))
            time.sleep(15)

HEALTH=HealthMonitor(ROOT/'health-history.json')

class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:super().handle_one_request()
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:
            import traceback
            frames=' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(exc.__traceback__))
            HEALTH.event('Server',type(exc).__name__+': '+str(exc)+' | '+frames)
            self.close_connection=True
            try:self.json({'error':'Unexpected server error. See System health.'},500)
            except OSError:pass
    def json(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ('/api/files','/api/storage','/api/files/download'):
            try:
                require_storage(MEDIA)
                if route=='/api/storage':
                    disk=shutil.disk_usage(MEDIA)
                    return self.json({'available':True,'usb':bool(os.environ.get('HYPERDRIVE_USB_MOUNT')),'free':disk.free,'total':disk.total})
                query=parse_qs(urlsplit(self.path).query)
                folder=directory_path(MEDIA,query.get('folder',[''])[0])
                if route=='/api/files':
                    with connect() as c:shown={r['path'] for r in c.execute('SELECT path FROM movies')}
                    entries=[]
                    for p in sorted(folder.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
                        if p.is_symlink() or (p.name.startswith('.upload-') and p.name.endswith('.part')):continue
                        if not p.is_dir() and not p.is_file():continue
                        entries.append({'name':p.name,'size':0 if p.is_dir() else p.stat().st_size,'directory':p.is_dir(),'movie':str(p.resolve()) in shown})
                    return self.json(entries)
                name=query.get('name',[''])[0]
                return self.file(file_path(folder,name),attachment=name)
            except (ValueError,OSError) as exc:return self.json({'error':str(exc)},503 if route!='/api/files/download' else 400)
        if route == '/api/health':return self.json(HEALTH.snapshot())
        if route == '/api/movies':
            with connect() as c: rows = [dict(r) for r in c.execute('SELECT id,title,genre,year,favorite,progress FROM movies ORDER BY title')]
            return self.json(rows)
        if route == '/api/status':
            try:
                require_storage(MEDIA);free=shutil.disk_usage(MEDIA).free;available=True
            except (ValueError,OSError):free=0;available=False
            return self.json({'media':str(MEDIA),'available':available,'name':'Hyperdrive','tv':tv_status(),'free':free,'audio_test':dict(AUDIO_VERIFICATION)})
        if route == '/api/update':
            try: return self.json(UPDATER.status())
            except (ValueError, OSError) as e: return self.json({'error':str(e)}, 400)
        if route == '/api/voice':
            with VOICE_LOCK: state = dict(VOICE)
            return self.json({**state, 'pending_storage':voice_pending(), 'settings':voice_settings(), 'enabled':voice_enabled(), 'online':time.monotonic()-state['seen']<10})
        if route.startswith('/media/'):
            try:require_storage(MEDIA)
            except (ValueError,OSError) as exc:return self.json({'error':str(exc)},503)
            with connect() as c: row = c.execute('SELECT path FROM movies WHERE id=?', (route.split('/')[-1],)).fetchone()
            if not row: return self.send_error(404)
            p = Path(row['path']).resolve()
            if not p.is_relative_to(MEDIA): return self.send_error(403)
            return self.file(p, True)
        page={'/':'hyperdrive.html','/frame':'index.html','/frame/':'index.html'}.get(route,route.lstrip('/'))
        p = (ROOT / 'static' / page).resolve()
        if not p.is_relative_to(ROOT / 'static'): return self.send_error(403)
        self.file(p)
    def do_POST(self):
        # Reject cross-origin mutations from other websites on the LAN.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'): return self.json({'error':'Invalid origin'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            route = urlsplit(self.path).path
            if route in ('/api/upload','/api/files/upload'):return self.upload(size,all_types=route=='/api/files/upload')
            if route == '/api/update/github/check':return self.json(UPDATER.github_release())
            if route == '/api/update/github/download':
                if not 0<size<=8192:raise ValueError('Invalid update request')
                request=json.loads(self.rfile.read(size))
                if not isinstance(request,dict):raise ValueError('Expected a JSON object')
                return self.json(UPDATER.stage_github(request.get('version'),request.get('digest')))
            if route == '/api/update/stage':
                if not 0 < size <= MAX_ARCHIVE: raise ValueError('Choose a Frame update ZIP under 10 MB')
                self.connection.settimeout(60)
                try: return self.json(UPDATER.stage(self.rfile.read(size)))
                finally: self.connection.settimeout(None)
            if size < 0: raise ValueError('Invalid request length')
            if size > 8192: return self.json({'error':'Request too large'}, 413)
            data = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data, dict): raise ValueError('Expected a JSON object')
            if route == '/api/files/folder':
                require_storage(MEDIA)
                parent=directory_path(MEDIA,data.get('folder',''))
                name=data.get('name')
                if not isinstance(name,str):raise ValueError('Enter a folder name')
                target=file_path(parent,name)
                with LOCK:target.mkdir()
                return self.json({'ok':True,'folder':target.relative_to(MEDIA).as_posix()})
            if route == '/api/health/check':return self.json(HEALTH.check())
            if route == '/api/health/settings':
                if type(data.get('auto_recovery')) is not bool:raise ValueError('Expected auto_recovery true or false')
                with HEALTH.lock:
                    HEALTH.auto=data['auto_recovery'];HEALTH.save()
                return self.json({'ok':True})
            if route == '/api/audio/verification':
                if self.client_address[0] not in {'127.0.0.1','::1'}:return self.json({'error':'Confirm on the TV'},403)
                if type(data.get('heard')) is not bool:raise ValueError('Expected test result')
                AUDIO_VERIFICATION.update(heard=data['heard'],output=str(data.get('output',''))[:300],time=time.time())
                return self.json({'ok':True})
            if route == '/api/voice/storage/confirm':return self.json(confirm_voice_storage(data.get('token')))
            if route == '/api/voice/storage/cancel':
                with VOICE_LOCK:
                    if data.get('token')!=VOICE_PENDING.get('token'):raise ValueError('File request changed')
                    VOICE_PENDING.clear()
                return self.json({'ok':True})
            if route == '/api/voice/settings':
                if 'enhancement' in data and data['enhancement'] not in ('off','balanced','strong'):raise ValueError('Invalid enhancement mode')
                if 'enabled' in data and type(data['enabled']) is not bool: raise ValueError('Expected enabled true or false')
                if 'device' in data and (not isinstance(data['device'],str) or len(data['device'])>200):raise ValueError('Invalid microphone selection')
                if 'secondary_device' in data and (not isinstance(data['secondary_device'],str) or len(data['secondary_device'])>200):raise ValueError('Invalid second microphone')
                if 'refresh' in data and type(data['refresh']) is not bool:raise ValueError('Expected refresh true or false')
                with VOICE_LOCK:
                    settings=voice_settings()
                    settings.update({k:data[k] for k in ('enabled','device','secondary_device','enhancement') if k in data})
                    if data.get('refresh'):settings['revision']+=1
                    temp=VOICE_SETTINGS.with_suffix('.tmp')
                    temp.write_text(json.dumps(settings));temp.replace(VOICE_SETTINGS)
                return self.json({'ok':True})
            if route in {'/api/voice/poll','/api/voice/listening','/api/voice/command'}:
                if self.client_address[0] not in {'127.0.0.1','::1'}: return self.json({'error':'Local microphone connection only'},403)
                if route.endswith('/poll'):
                    devices=data.get('devices',[])
                    if not isinstance(devices,list):raise ValueError('Invalid microphone list')
                    devices=[{'id':str(d['id'])[:20],'name':str(d['name'])[:200]} for d in devices[:64] if isinstance(d,dict) and 'id' in d and 'name' in d]
                    with VOICE_LOCK: VOICE.update(seen=time.monotonic(), device=str(data.get('device',''))[:200], error=str(data.get('error',''))[:200], devices=devices, level=max(0,min(100,int(data.get('level',0)))))
                    with VOICE_LOCK:
                        for key in ('utterances','wakes','commands','dropped_blocks'):
                            VOICE[key]=max(0,min(100000000,int(data.get(key,0))))
                    quality=data.get('audio_quality',{})
                    if isinstance(quality,dict):
                        with VOICE_LOCK:VOICE['audio_quality']={k:max(0,min(100,float(quality.get(k,0)))) for k in ('rms','clipped','gain')}
                    if data.get('error'):HEALTH.event('Microphone',str(data['error']))
                    return self.json(voice_settings())
                if route.endswith('/listening'):
                    if voice_enabled():queue_command({'action':'voice_listening'})
                    return self.json({'ok':True})
                text=str(data.get('text','')).strip()[:300]
                try:return self.json(voice_command(text))
                except (ValueError,OSError) as exc:
                    with VOICE_LOCK: VOICE.update(last_command=text, message=str(exc), results=[])
                    HEALTH.event('Voice command',str(exc))
                    try:queue_command({'action':'voice_feedback','message':str(exc)[:200]})
                    except ValueError:pass
                    raise
            if route == '/api/update/apply':
                if self.client_address[0] not in {'127.0.0.1', '::1'}:
                    return self.json({'error':'Approve installation on the TV'}, 403)
                if data.get('confirmed') is not True: raise ValueError('Update confirmation required')
                result = UPDATER.apply(data.get('version'), data.get('digest'))
                result['automatic_restart'] = os.environ.get('FRAME_MANAGED') == '1'
                self.json(result)
                if result['automatic_restart']:
                    threading.Timer(3, lambda: os._exit(75)).start()
                return
            if route == '/api/tv/poll':
                if self.client_address[0] not in {'127.0.0.1', '::1'}:
                    return self.json({'error': 'Local TV connection only'}, 403)
                with TV_LOCK:
                    TV.update(seen=time.monotonic(), playing=bool(data.get('playing')), title=str(data.get('title',''))[:200], error=str(data.get('error',''))[:300])
                    TV['audio'] = data.get('audio', {})
                    TV['power'] = data.get('power', {})
                    pending = [c for c in COMMANDS if c['expires'] > time.monotonic()]
                    COMMANDS.clear()
                if data.get('error'):HEALTH.event('Kodi',str(data['error']))
                return self.json({'commands': pending})
            if route == '/api/tv/play':
                require_storage(MEDIA)
                with connect() as c:
                    movie = c.execute('SELECT * FROM movies WHERE id=?', (int(data['id']),)).fetchone()
                if not movie: raise ValueError('Movie not found')
                path = Path(movie['path']).resolve()
                if not path.is_relative_to(MEDIA) or not path.is_file(): raise ValueError('Movie file is missing')
                queue_command({'action': 'play', 'id': movie['id'], 'title': movie['title'], 'path': str(path), 'progress': movie['progress']})
                return self.json({'ok': True})
            if route == '/api/tv/control':
                action = data.get('action')
                if action not in {'hyperdrive', 'pause', 'stop', 'left', 'right', 'up', 'down', 'select', 'back', 'home', 'volume', 'mute', 'audio_track', 'audio_diagnose','end_movie','audio_settings', 'audio_setup', 'audio_test', 'airplay_settings', 'updates', 'power_menu', 'reboot', 'shutdown'}:
                    raise ValueError('Unknown TV action')
                command = {'action':action}
                if action in {'volume', 'audio_track'}:
                    value = data.get('value')
                    if type(value) is not int or not 0 <= value <= (100 if action == 'volume' else 255):
                        raise ValueError('Invalid audio control value')
                    command['value'] = value
                if action in {'reboot', 'shutdown'}:
                    if data.get('confirmed') is not True: raise ValueError('Power confirmation required')
                    if not tv_status().get('power', {}).get(action): raise ValueError('Kodi does not have permission for this power action')
                queue_command(command)
                return self.json({'ok': True})
            if self.path == '/api/scan': return self.json({'count': scan()})
            if self.path.startswith('/api/movies/'):
                mid = int(self.path.rsplit('/',1)[1])
                fields = {k:v for k,v in data.items() if k in {'title','genre','year','favorite','progress'}}
                if 'progress' in fields: fields['progress'] = max(0, min(1, float(fields['progress'])))
                if 'favorite' in fields: fields['favorite'] = int(bool(fields['favorite']))
                for k in ('title','genre','year'):
                    if k in fields: fields[k] = str(fields[k])[:200]
                with connect() as c:
                    if fields: c.execute('UPDATE movies SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', [*fields.values(),mid])
                return self.json({'ok':True})
            self.send_error(404)
        except (ValueError, TypeError, KeyError, OSError) as e: self.json({'error':str(e)},400)
    def upload(self, size, all_types=False):
        query=parse_qs(urlsplit(self.path).query)
        name = query.get('name', [''])[0]
        if not name or '/' in name or '\\' in name or len(name.encode()) > 200 or any(ord(c) < 32 for c in name):
            raise ValueError('Invalid filename')
        require_storage(MEDIA)
        folder=directory_path(MEDIA,query.get('folder',[''])[0]) if all_types else MEDIA
        file_path(folder,name)
        video=Path(name).suffix.lower() in VIDEO_TYPES
        choice=query.get('frame',[''])[0]
        if all_types and video and choice not in ('true','false'):raise ValueError('Choose whether this video should appear in Frame')
        visible=not all_types or choice=='true'
        if not all_types and Path(name).suffix.lower() not in VIDEO_TYPES: raise ValueError('Choose a video file')
        if size < (0 if all_types else 1) or size > 100 * 1024**3: raise ValueError('File exceeds the 100 GB upload limit')
        if shutil.disk_usage(MEDIA).free < size + 256 * 1024**2: raise ValueError('Not enough free space on the Pi')
        temp = None
        self.connection.settimeout(120)
        try:
            with tempfile.NamedTemporaryFile(dir=folder, prefix='.upload-', suffix='.part', delete=False) as f:
                temp = Path(f.name)
                remaining = size
                while remaining:
                    block = self.rfile.read(min(1024*1024, remaining))
                    if not block: raise ValueError('Upload interrupted; please retry')
                    if MEDIA.stat().st_dev!=os.fstat(f.fileno()).st_dev:raise ValueError('Storage changed during upload')
                    f.write(block); remaining -= len(block)
            with LOCK:
                require_storage(MEDIA)
                directory_path(MEDIA,folder.relative_to(MEDIA).as_posix() if folder!=MEDIA else '')
                dest = file_path(folder,name)
                if dest.exists(): dest = folder / (Path(name).stem + '-' + uuid.uuid4().hex[:8] + Path(name).suffix)
                if video:
                    with connect() as c:
                        c.execute('INSERT OR REPLACE INTO frame_visibility(path,visible) VALUES(?,?)',(dest.relative_to(MEDIA).as_posix(),int(visible)))
                        c.commit()
                        temp.replace(dest)
                else:temp.replace(dest)
            if video and visible:scan()
            self.json({'ok': True, 'filename': dest.name})
        finally:
            if temp is not None: temp.unlink(missing_ok=True)
            self.connection.settimeout(None)
    def file(self, p, ranges=False, attachment=None):
        if not p.is_file(): return self.send_error(404)
        size = p.stat().st_size; start = 0; end = size-1; partial = False
        header = self.headers.get('Range') if ranges else None
        if header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
            if not match or not any(match.groups()): return self.send_error(416)
            a,b = match.groups()
            if a: start = int(a); end = min(int(b), size-1) if b else size-1
            else: start = max(0,size-int(b))
            if start > end or start >= size:
                self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type','application/octet-stream' if attachment else mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
        if attachment:
            self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(attachment,safe=''))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"sandbox; default-src 'none'")
        self.send_header('Content-Length',str(max(0,end-start+1)))
        if ranges: self.send_header('Accept-Ranges','bytes')
        if partial: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with p.open('rb') as f:
                f.seek(start); remaining = end-start+1
                while remaining > 0:
                    block=f.read(min(256*1024,remaining))
                    if not block: break
                    self.wfile.write(block); remaining-=len(block)
        except (BrokenPipeError, ConnectionResetError): pass

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--host',default='0.0.0.0'); parser.add_argument('--port',type=int,default=8080); args=parser.parse_args()
    if not os.environ.get('HYPERDRIVE_USB_MOUNT'):MEDIA.mkdir(parents=True,exist_ok=True)
    init()
    print(f'Frame is ready at http://localhost:{args.port}',flush=True)
    http=ThreadingHTTPServer((args.host,args.port),Handler)
    threading.Thread(target=HEALTH.run,daemon=True,name='frame-health').start()
    http.serve_forever()
