"""Conservative candidate transitions; no semantic structure assumptions."""
import math
from .util import finite


def compatibility(a, b, max_rate=.08):
    max_rate = finite(max_rate, 'max_rate', 0, .25)
    if a['id'] == b['id'] or a['silent'] or b['silent'] or not a['bpm'] or not b['bpm']:
        return dict(eligible=False, score=0.0, reason='Stesso brano, silenzio o tempo sconosciuto')
    rate = finite(a['bpm'], 'bpm_a', 1, 400) / finite(b['bpm'], 'bpm_b', 1, 400)
    tempo = math.exp(-abs(math.log(rate))*10)
    delta = None if a['key_pc'] is None or b['key_pc'] is None else (b['key_pc']-a['key_pc']) % 12
    harmonic = .5 if delta is None else (1.0 if delta == 0 and a['mode'] == b['mode'] else .8 if delta in (0,5,7) else .3)
    energy = 1-abs(a['energy']-b['energy'])/max(a['energy'],b['energy'],1e-6)
    confidence = min(a['tempo_confidence'],b['tempo_confidence'])
    return dict(eligible=abs(rate-1) <= max_rate and confidence >= .12,
                score=float(.45*tempo+.25*harmonic+.2*energy+.1*confidence), rate_b=rate,
                tempo_score=tempo, harmonic_score=harmonic, energy_score=energy,
                confidence=confidence, reason='Compatibilità euristica; ricampionamento preview altera tonalità')


def candidates(a, b, max_rate=.08):
    comp = compatibility(a,b,max_rate)
    if not comp['eligible']:
        return []
    rate = comp['rate_b']
    results = []
    for count in (8, 16, 32):
        duration = count*60/a['bpm']
        if duration > min(a['duration'], b['duration']/rate)*.6:
            continue
        desired = max(0, a['duration']-duration-1)
        options = [t for t in a['beats'] if 0 <= t <= desired]
        start_a = max(options, default=0)
        start_b = b['beats'][0] if b['beats'] else 0
        if start_b+duration*rate > b['duration']:
            continue
        results.append(dict(a=a['id'],b=b['id'],start_a=start_a,start_b=start_b,
                            duration=duration,beats=count,rate_b=rate,score=comp['score'],
                            confidence=comp['confidence'],curve='equal_power',compatibility=comp))
    return results


def validate_plan(plan, a, b):
    if plan.get('a') != a['id'] or plan.get('b') != b['id'] or a['id'] == b['id']:
        raise ValueError('Piano e catalogo non corrispondono')
    p = dict(plan)
    for k,lo,hi in [('start_a',0,a['duration']),('start_b',0,b['duration']),('duration',.1,300),('rate_b',.75,1.25)]:
        p[k] = finite(p[k],k,lo,hi)
    if p['start_a']+p['duration'] > a['duration']+1e-4 or p['start_b']+p['duration']*p['rate_b'] > b['duration']+1e-4:
        raise ValueError('Piano supera la durata disponibile')
    return p
