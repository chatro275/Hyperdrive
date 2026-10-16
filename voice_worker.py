#!/usr/bin/env python3
"""Microphone daemon: Vosk inference and wake-phrase matching remain on-device."""
import argparse, json, os, queue, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from voice import WakeGate, AudioEnhancer

BASE = 'http://127.0.0.1:8080'
def api(path, data, timeout=15):
    try:
        with urlopen(Request(BASE+path, data=json.dumps(data).encode(), headers={'Content-Type':'application/json'}), timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        detail=json.load(exc).get('error','Frame request failed')
        raise ValueError(detail) from exc

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--list-devices',action='store_true');args=parser.parse_args()
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer, SetLogLevel
    if args.list_devices: print(sd.query_devices());return
    device=os.environ.get('FRAME_MIC_DEVICE') or None
    if device and device.isdigit():device=int(device)
    model_path=Path(os.environ.get('FRAME_VOSK_MODEL', str(Path(__file__).parent/'models/vosk-model-small-en-us-0.15')))
    if not model_path.is_dir():raise RuntimeError('Speech model missing. Run scripts/install-voice.sh on the Pi.')
    SetLogLevel(-1);model=Model(str(model_path))
    from array import array
    audio=queue.Queue(maxsize=12);gate=WakeGate();stream=None;recognizer=None
    selected=None;info={};enabled=False;last_poll=0;error='';level=0;revision=None;retry_at=0
    source_stamp=Path(__file__).stat().st_mtime_ns
    counters={'utterances':0,'wakes':0,'commands':0,'dropped_blocks':0}
    enhancer=None;enhancement='balanced';announced=False
    from concurrent.futures import ThreadPoolExecutor
    executor=ThreadPoolExecutor(max_workers=1);pending=None;pending_command=False
    def callback(data, frames, time_info, status):
        try:audio.put_nowait(bytes(data))
        except queue.Full:counters['dropped_blocks']+=1
    def clear_audio():
        while not audio.empty():
            try:audio.get_nowait()
            except queue.Empty:break
    try:
        while True:
            if pending is not None and pending.done():
                try:
                    pending.result();error=''
                    if pending_command:counters['commands']+=1
                except Exception as exc:error=str(exc)[:200]
                pending=None
            if time.monotonic()-last_poll>2:
                if Path(__file__).stat().st_mtime_ns!=source_stamp:raise SystemExit(75)
                try:
                    devices=[{'id':str(i),'name':d['name']} for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]
                    config=api('/api/voice/poll',{'device':info.get('name',''),'devices':devices,'level':level if enabled else 0,'error':error,'audio_quality':enhancer.metrics if enhancer else {},**counters},timeout=3)
                    level=0;enabled=config['enabled']
                    new_mode=config.get('enhancement','balanced')
                    if new_mode!=enhancement and enhancer:
                        enhancer=AudioEnhancer(rate,new_mode)
                        recognizer.Reset();clear_audio();gate=WakeGate();announced=False
                    enhancement=new_mode
                    if revision is not None and revision!=config.get('revision',0):raise SystemExit(75)
                    revision=config.get('revision',0)
                    requested=config.get('device') or os.environ.get('FRAME_MIC_DEVICE') or None
                    if requested and requested.isdigit():requested=int(requested)
                    if requested!=selected or stream is None:
                        if stream is not None:stream.close();stream=None
                        if requested!=selected:retry_at=0
                        selected=requested;clear_audio();gate=WakeGate();info={}
                        if time.monotonic()>=retry_at:
                            try:
                                info=sd.query_devices(selected,'input');rate=int(info['default_samplerate'])
                                stream=sd.RawInputStream(samplerate=rate,blocksize=int(rate/4),device=selected,dtype='int16',channels=1,callback=callback)
                                recognizer=KaldiRecognizer(model,rate);enhancer=AudioEnhancer(rate,enhancement);error='';announced=False
                            except Exception as exc:
                                if stream is not None:stream.close();stream=None
                                error='Cannot open microphone: '+str(exc)[:150];retry_at=time.monotonic()+5
                except Exception as exc:
                    enabled=False;error=str(exc)[:200]
                last_poll=time.monotonic()
            if not enabled or stream is None:
                if stream is not None and stream.active:stream.stop()
                clear_audio()
                if recognizer:recognizer.Reset()
                gate=WakeGate();announced=False;time.sleep(.2);continue
            if not stream.active:
                try:stream.start()
                except Exception as exc:
                    error='Cannot start microphone: '+str(exc)[:150];stream.close();stream=None;retry_at=time.monotonic()+5;continue
            try:data=audio.get(timeout=.5)
            except queue.Empty:continue
            samples=array('h',data)
            level=max(level, int(max((abs(v) for v in samples),default=0)/32768*100))
            data=enhancer.process(data)
            if recognizer.AcceptWaveform(data):
                announced=False
                result=json.loads(recognizer.Result());text=result.get('text','')
                if text:counters['utterances']+=1
                command=gate.feed(text)
                if command is None:continue
                if text.startswith(('hey hyper','hey high per','hey frame')):counters['wakes']+=1
                if pending is not None:
                    error='Still handling the previous command. Please try again.'
                else:
                    pending_command=command!='__listening__'
                    pending=executor.submit(api,'/api/voice/command' if pending_command else '/api/voice/listening',{'text':command} if pending_command else {})
                clear_audio();recognizer.Reset()
            elif not announced:
                partial=json.loads(recognizer.PartialResult()).get('partial','')
                if partial.startswith(('hey hyper','hey high per','hey frame')):
                    announced=True
                    try:api('/api/voice/listening',{},timeout=3)
                    except Exception:pass
    finally:
        executor.shutdown(wait=False,cancel_futures=True)
        if stream is not None:stream.close()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:api('/api/voice/poll',{'error':str(exc)[:200],'device':''})
        except Exception:pass
        raise
