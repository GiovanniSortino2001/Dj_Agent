"""Bidirectional virtual ALSA MIDI. Manual load/cue only; bounded one-way fade."""
import logging
import threading
import time
from .control import Safety
from .util import finite
LOG=logging.getLogger(__name__)


def encode(value,low=0,high=1):
    value=finite(value,'MIDI control',low,high)
    return int(round((value-low)/(high-low)*127))


class Feedback:
    REQUIRED={(ch,cc) for ch in (0,1) for cc in (20,21,22,23,24)} | {(0,25)}
    def __init__(self):
        self.pending={}; self.frame={}; self.updated=None; self.sequence=None
        self.lock=threading.Lock()
    def receive(self,ch,cc,value,now):
        if type(ch) is not int or type(cc) is not int or type(value) is not int or not 0<=ch<=15 or not 0<=cc<=127 or not 0<=value<=127:
            return
        with self.lock:
            if (ch,cc)==(0,117):
                self.pending={}; self.sequence=value
            elif (ch,cc)==(0,119):
                if self.sequence==value and self.REQUIRED <= self.pending.keys():
                    self.frame=dict(self.pending); self.updated=now
                self.pending={}; self.sequence=None
            elif (ch,cc) in self.REQUIRED:
                self.pending[(ch,cc)]=value
    def snapshot(self,now,timeout=.5):
        with self.lock:
            if self.updated is None or now-self.updated>timeout:
                raise TimeoutError('Feedback MIDI assente/scaduto')
            return dict(self.frame),max(0,now-self.updated)


class MidiBridge:
    def __init__(self):
        import mido
        mido.set_backend('mido.backends.rtmidi')
        self.mido=mido; self.feedback=Feedback()
        self.output=mido.open_output('DJ-to-Mixxx',virtual=True)
        try:
            self.input=mido.open_input('DJ-from-Mixxx',virtual=True,callback=self._receive)
        except Exception:
            self.output.close(); raise
    def _receive(self,msg):
        if msg.type=='control_change':
            self.feedback.receive(msg.channel,msg.control,msg.value,time.monotonic())
    def send(self,ch,cc,value):
        if not isinstance(value,int) or not 0<=value<=127:
            raise ValueError('MIDI byte non valido')
        self.output.send(self.mido.Message('control_change',channel=ch,control=cc,value=value))
    def heartbeat(self):
        self.send(0,118,127)
    def close(self):
        # Disarm script; leave audible playback and fader where they are.
        try:
            self.send(0,118,0)
        finally:
            self.input.close(); self.output.close()


def serve(duration=60):
    duration=finite(duration,'seconds',1,3600)
    bridge=MidiBridge(); end=time.monotonic()+duration
    try:
        LOG.info('Porte virtuali aperte: connettere ALSA e caricare mapping. Nessun controllo audio inviato.')
        while time.monotonic()<end:
            try:
                f,age=bridge.feedback.snapshot(time.monotonic())
                LOG.info('feedback age=%.3f xf=%.2f loaded=%s/%s playing=%s/%s',age,f[(0,25)]/127*2-1,f[(0,23)],f[(1,23)],f[(0,20)],f[(1,20)])
            except TimeoutError:
                LOG.info('In attesa di feedback')
            time.sleep(.5)
    finally:
        bridge.close()


def fade(duration=8,setup_timeout=60,safety=None):
    duration=finite(duration,'duration',4,120)
    setup_timeout=finite(setup_timeout,'setup_timeout',1,300)
    safety=safety or Safety()
    bridge=MidiBridge()
    try:
        LOG.warning('Connettere porte; A loaded+playing, B loaded+stopped e cue manuale, volumi=1, crossfader sinistra.')
        deadline=time.monotonic()+setup_timeout
        while True:
            try:
                f,_=bridge.feedback.snapshot(time.monotonic(),safety.timeout)
                break
            except TimeoutError:
                if time.monotonic()>=deadline:
                    raise TimeoutError('Timeout configurazione MIDI')
                time.sleep(.05)
        if not (f[(0,23)] and f[(1,23)] and f[(0,20)] and not f[(1,20)] and f[(0,25)]<=1 and f[(0,24)]>=125 and f[(1,24)]>=125):
            raise ValueError('Preflight MIDI fallita: verificare deck, volumi e crossfader')
        bridge.heartbeat(); bridge.send(1,10,127)
        deadline=time.monotonic()+2
        while True:
            bridge.heartbeat()
            f,_=bridge.feedback.snapshot(time.monotonic(),safety.timeout)
            if f[(1,20)]:
                break
            if time.monotonic()>deadline:
                raise TimeoutError('Nessun feedback play B')
            time.sleep(.05)
        start=last=time.monotonic(); cross=-1.0
        while True:
            now=time.monotonic(); dt=now-last
            if dt>.2:
                raise TimeoutError('Scheduler MIDI in ritardo: fade sospeso')
            f,age=bridge.feedback.snapshot(now,safety.timeout)
            if not all(f[(ch,20)] and f[(ch,23)] for ch in (0,1)):
                raise ValueError('Deck fermo/vuoto durante il fade')
            # External override or wrong feedback routing: abort, do not fight human controls.
            if abs((f[(0,25)]/127*2-1)-cross)>.2:
                raise ValueError('Crossfader esterno divergente: intervento manuale')
            progress=min(1,(now-start)/duration)
            cross=safety.crossfader(cross,-1+2*progress,dt,age)
            bridge.heartbeat(); bridge.send(0,1,encode(cross,-1,1))
            last=now
            if progress>=1 and cross>=.999:
                break
            time.sleep(.02)
        LOG.info('Fade completato. Entrambi i deck restano in play; fermare A manualmente.')
    finally:
        bridge.close()
