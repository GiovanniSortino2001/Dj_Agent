"""Offline auditable preview: equal-power fade, linear tempo resampling."""
import numpy as np
from .audio import read_wav, write_wav
from .control import simulate
from .transitions import validate_plan


def render(catalog,plan,path,controller=None,hz=50,safety=None):
    a,b=catalog.get(plan['a']),catalog.get(plan['b'])
    p=validate_plan(plan,a,b)
    xa,sa=read_wav(catalog.audio_path(a))
    xb,sb=read_wav(catalog.audio_path(b))
    sr=22050
    n=max(1,int(round(p['duration']*sr)))
    t=np.arange(n)/sr
    def take(x,s,start,rate):
        if x.shape[1]==1:
            x=np.repeat(x,2,axis=1)
        indexes=(start+t*rate)*s
        return np.stack([np.interp(indexes,np.arange(len(x)),x[:,c]) for c in range(2)],axis=1)
    trace=simulate(p,a,b,controller=controller,hz=hz,safety=safety)
    cross=np.interp(t,[r['t'] for r in trace],[r['crossfader'] for r in trace])
    angle=(cross+1)*np.pi/4
    mix=.7*(take(xa,sa,p['start_a'],1)*np.cos(angle)[:,None]+take(xb,sb,p['start_b'],p['rate_b'])*np.sin(angle)[:,None])
    peak=float(np.max(abs(mix)))
    gain=min(1,.98/max(peak,1e-12))
    write_wav(path,mix*gain,sr)
    return dict(sample_rate=sr,frames=n,duration=n/sr,peak_before_limiter=peak,
                global_peak_gain=gain,peak_after_limiter=peak*gain,
                note='Solo sovrapposizione; resampling lineare altera pitch, non time-stretch professionale'),trace
