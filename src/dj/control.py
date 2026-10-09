"""State, bounded controller and deterministic scheduler shared by simulation."""
from dataclasses import dataclass, asdict
import heapq
from .util import finite


@dataclass
class DeckState:
    track_id: str = ''
    duration: float = 0
    position: float = 0
    playing: bool = False
    volume: float = 1
    rate: float = 1
    loaded: bool = False

    def validate(self):
        finite(self.duration,'duration',0)
        finite(self.position,'position',0,self.duration)
        finite(self.volume,'volume',0,1)
        finite(self.rate,'rate',.75,1.25)
        if self.playing and not self.loaded:
            raise ValueError('Deck vuoto in riproduzione')

    def advance(self, dt):
        self.validate()
        dt = finite(dt,'dt',0,1)
        if self.playing:
            self.position = min(self.duration,self.position+dt*self.rate)
            if self.position >= self.duration:
                self.playing = False


class Safety:
    def __init__(self, max_slew=1.0, timeout=.5):
        self.max_slew = finite(max_slew,'max_slew',.01,10)
        self.timeout = finite(timeout,'timeout',.05,10)

    def crossfader(self, current, requested, dt, age=0):
        current = finite(current,'current',-1,1)
        requested = finite(requested,'requested')
        dt = finite(dt,'dt',0,1)
        age = finite(age,'feedback_age',0)
        if age > self.timeout:
            raise TimeoutError('Feedback scaduto: mantenere ultimo controllo, intervento manuale')
        requested = max(-1,min(1,requested))
        limit = self.max_slew*dt
        return max(current-limit,min(current+limit,requested))


class RuleController:
    def target(self, progress, **features):
        progress = finite(progress,'progress',0,1)
        return -1 + 2*progress


class Scheduler:
    def __init__(self):
        self.queue=[]
        self.counter=0
        self.last=0.0

    def at(self, when, callback):
        when=finite(when,'when',self.last)
        self.counter+=1
        heapq.heappush(self.queue,(when,self.counter,callback))

    def run_due(self, now):
        now=finite(now,'now',self.last)
        self.last=now
        while self.queue and self.queue[0][0] <= now+1e-9:
            _,_,callback=heapq.heappop(self.queue)
            callback()


def simulate(plan,a,b,hz=50,controller=None,safety=None):
    from .transitions import validate_plan
    plan=validate_plan(plan,a,b)
    hz=finite(hz,'hz',10,100)
    controller=controller or RuleController()
    safety=safety or Safety()
    decks=[DeckState(a['id'],a['duration'],plan['start_a'],True,1,1,True),
           DeckState(b['id'],b['duration'],plan['start_b'],False,1,plan['rate_b'],True)]
    scheduler=Scheduler()
    scheduler.at(0,lambda: setattr(decks[1],'playing',True))
    # Include exact endpoint even when duration*hz is fractional.
    import numpy as np
    times=np.append(np.arange(0,plan['duration'],1/hz),plan['duration'])
    rows=[]
    cross=-1.0
    previous=0.0
    for now in times:
        dt=float(now-previous)
        for deck in decks:
            deck.advance(dt)
        scheduler.run_due(float(now))
        progress=float(now/plan['duration'])
        target=controller.target(progress,energy_a=a['energy'],energy_b=b['energy'],phase_error=0.0,tempo_error=0.0)
        cross=safety.crossfader(cross,target,dt)
        if now >= plan['duration'] and cross >= .98:
            decks[0].playing=False
        rows.append(dict(t=float(now),crossfader=cross,a=asdict(decks[0]),b=asdict(decks[1])))
        previous=now
    return rows
