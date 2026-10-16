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

class Microphone:
    def __init__(self, sd, recognizer_factory, model, device, mode):
        self.stream=None;self.queue=queue.Queue(maxsize=12);self.dropped=0;self.level=0
        self.gate=WakeGate();self.announced=False
        self.info=sd.query_devices(device,'input');rate=int(self.info['default_samplerate'])
        self.enhancer=AudioEnhancer(rate,mode);self.recognizer=recognizer_factory(model,rate)
        def callback(data,frames,info,status):
            if status:self.dropped+=1
            try:self.queue.put_nowait(bytes(data))
            except queue.Full:self.dropped+=1
        self.stream=sd.RawInputStream(samplerate=rate,blocksize=int(rate/4),device=device,dtype='int16',channels=1,callback=callback)
        try:self.stream.start()
        except Exception:self.stream.close();raise
    def close(self):
        if self.stream:self.stream.close()
    def reset(self):
        self.recognizer.Reset();self.gate=WakeGate();self.announced=False
        while True:
            try:self.queue.get_nowait()
            except queue.Empty:break
    def read(self):
        from array import array
        try:data=self.queue.get_nowait()
        except queue.Empty:return None
        self.level=int(max((abs(v) for v in array('h',data)),default=0)/32768*100)
        if self.recognizer.AcceptWaveform(self.enhancer.process(data)):
            self.announced=False
            text=json.loads(self.recognizer.Result()).get('text','')
            return ('final',text)
        partial=json.loads(self.recognizer.PartialResult()).get('partial','')
        if not self.announced and partial.startswith(('hey hyper','hey high per','hey frame')):
            self.announced=True;return ('wake',partial)
        return None

class MicArbiter:
    """One microphone owns a wake/command turn; never blend unsynchronised audio."""
    def __init__(self):self.owner=None;self.until=0
    def claim(self, index, now=None):
        now=time.monotonic() if now is None else now
        if now>=self.until:self.owner=None
        if self.owner not in (None,index):return False
        self.owner=index;self.until=now+10;return True
    def finished(self,now=None):self.until=(time.monotonic() if now is None else now)+3

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--list-devices',action='store_true');args=parser.parse_args()
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer, SetLogLevel
    from concurrent.futures import ThreadPoolExecutor
    if args.list_devices:print(sd.query_devices());return
    path=Path(os.environ.get('FRAME_VOSK_MODEL',str(Path(__file__).parent/'models/vosk-model-small-en-us-0.15')))
    if not path.is_dir():raise RuntimeError('Speech model missing. Run scripts/install-voice.sh on the Pi.')
    SetLogLevel(-1);model=Model(str(path));mics={};errors={};signature=None;revision=None
    stamp=Path(__file__).stat().st_mtime_ns;last_poll=0;retry_at=0;enabled=False;error=''
    counters={'utterances':0,'wakes':0,'commands':0};arbiter=MicArbiter();pending=None;is_command=False
    executor=ThreadPoolExecutor(max_workers=1)
    try:
        while True:
            if pending is not None and pending.done():
                try:
                    pending.result();error=''
                    if is_command:counters['commands']+=1
                except Exception as exc:error=str(exc)[:200]
                pending=None
            if time.monotonic()-last_poll>2:
                if Path(__file__).stat().st_mtime_ns!=stamp:raise SystemExit(75)
                try:
                    devices=[{'id':str(i),'name':d['name']} for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]
                    best=max(mics.values(),key=lambda m:m.level,default=None)
                    config=api('/api/voice/poll',{'device':' + '.join(m.info['name'] for m in mics.values()),'devices':devices,'level':best.level if best else 0,'audio_quality':best.enhancer.metrics if best else {},'error':'; '.join([error]+list(errors.values())).strip('; '),'dropped_blocks':sum(m.dropped for m in mics.values()),**counters},timeout=3)
                    enabled=config['enabled']
                    if revision is not None and revision!=config.get('revision',0):raise SystemExit(75)
                    revision=config.get('revision',0)
                    primary=config.get('device') or os.environ.get('FRAME_MIC_DEVICE') or str(sd.default.device[0])
                    secondary=config.get('secondary_device','')
                    requested=[primary]+([secondary] if secondary and secondary!=primary else [])
                    new_signature=(tuple(requested),config.get('enhancement','balanced'),enabled)
                    if signature!=new_signature:
                        for mic in mics.values():mic.close()
                        mics={};errors={};arbiter=MicArbiter();signature=new_signature;retry_at=0
                    if enabled and time.monotonic()>=retry_at:
                        for index,device in enumerate(requested):
                            if index in mics:continue
                            try:
                                mics[index]=Microphone(sd,KaldiRecognizer,model,int(device) if device.isdigit() else device,new_signature[1]);errors.pop(index,None)
                            except Exception as exc:errors[index]='Mic '+str(index+1)+': '+str(exc)[:120]
                        retry_at=time.monotonic()+5
                except Exception as exc:
                    enabled=False;error=str(exc)[:200]
                    for mic in mics.values():mic.reset()
                last_poll=time.monotonic()
            if enabled:
                for index,mic in list(mics.items()):
                    try:event=mic.read()
                    except Exception as exc:
                        mic.close();del mics[index];errors[index]=str(exc)[:120];continue
                    if not event:continue
                    kind,text=event
                    if kind=='wake':
                        if arbiter.claim(index) and pending is None:
                            is_command=False;pending=executor.submit(api,'/api/voice/listening',{})
                        continue
                    if text:counters['utterances']+=1
                    command=mic.gate.feed(text)
                    if command is None:continue
                    if not arbiter.claim(index):mic.reset();continue
                    if text.startswith(('hey hyper','hey high per','hey frame')):counters['wakes']+=1
                    if command=='__listening__':continue
                    if pending is not None:
                        # Listening notification is short; retain a final result until it finishes.
                        if not is_command:
                            try:pending.result(timeout=3)
                            except Exception:pass
                            pending=None
                        else:continue
                    is_command=True;pending=executor.submit(api,'/api/voice/command',{'text':command},120)
                    arbiter.finished()
                    for other in mics.values():other.reset()
            time.sleep(.02)
    finally:
        for mic in mics.values():mic.close()
        executor.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:api('/api/voice/poll',{'error':str(exc)[:200],'device':''})
        except Exception:pass
        raise
