"""Heuristic analysis with explicit, uncalibrated confidence scores."""
import logging
import numpy as np
from .audio import read_wav, resample

LOG = logging.getLogger(__name__)
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def fallback(x, sr):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 1 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError('Analisi: input mono non vuoto e finito richiesto')
    duration = len(x) / sr
    rms = float(np.sqrt(np.mean(x.astype(np.float64)**2)))
    result = dict(duration=duration, sample_rate=sr, backend='numpy', silent=rms < 1e-5,
                  bpm=None, tempo_confidence=0.0, beats=[], key=None, key_pc=None,
                  mode=None, key_confidence=0.0, energy=rms, energy_confidence=1.0,
                  structure=[], structure_confidence=0.0, vocals=None,
                  confidence_note='Indici euristici non calibrati; energy è RMS misurato; vocals non stimata')
    if result['silent']:
        return result
    # 100 Hz envelope, positive novelty; tempo autocorrelation 70–180 BPM.
    hop = max(1, int(sr / 100))
    n = len(x) // hop
    if n >= 300:
        env = np.sqrt(np.mean(x[:n*hop].reshape(n, hop).astype(np.float64)**2, axis=1))
        onset = np.maximum(0, np.diff(env, prepend=env[0]))
        fps = sr / hop
        lags = np.arange(int(fps*60/180), int(fps*60/70)+1)
        scores = np.array([np.dot(onset[:-lag], onset[lag:]) / (np.linalg.norm(onset[:-lag])*np.linalg.norm(onset[lag:]) + 1e-12) for lag in lags])
        k = int(np.argmax(scores))
        lag = float(lags[k])
        if 0 < k < len(scores)-1:
            a,b,c = scores[k-1:k+2]
            den = a - 2*b + c
            if abs(den) > 1e-12:
                lag += float(np.clip(.5*(a-c)/den, -.5, .5))
        conf = float(np.clip(scores[k], 0, 1))
        if conf >= .12:
            period = lag / fps
            phases = np.arange(0, period, 1/fps)
            phase_scores = [np.interp(np.arange(p, duration, period)*fps, np.arange(n), onset).sum() for p in phases]
            phase = float(phases[int(np.argmax(phase_scores))])
            result.update(bpm=60/period, tempo_confidence=conf,
                          beats=np.arange(phase, duration, period).round(5).tolist())
    # FFT chroma, capped at 512 frames. Chord/pitch profiles, no key certainty.
    y = resample(x, sr, 11025)
    size = 4096
    if len(y) >= size:
        starts = np.linspace(0, len(y)-size, min(512, max(1, len(y)//2048))).astype(int)
        freqs = np.fft.rfftfreq(size, 1/11025)
        mask = (freqs > 65) & (freqs < 2200)
        bins = np.rint(69+12*np.log2(freqs[mask]/440)).astype(int) % 12
        chroma = np.zeros(12)
        for start in starts:
            spec = abs(np.fft.rfft(y[start:start+size]*np.hanning(size)))**2
            chroma += np.bincount(bins, weights=spec[mask], minlength=12)
        profiles = [np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]), np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])]
        candidates = []
        for mode, profile in zip(('major','minor'), profiles):
            for pc in range(12):
                score = float(np.corrcoef(chroma, np.roll(profile, pc))[0,1]) if chroma.std() > 1e-12 else 0
                candidates.append((score, pc, mode))
        candidates.sort(reverse=True)
        score, pc, mode = candidates[0]
        confidence = float(np.clip((score-candidates[1][0])*3, 0, 1))
        if score > .1:
            result.update(key=f'{NOTES[pc]} {mode}', key_pc=pc, mode=mode, key_confidence=confidence)
    # Coarse fixed 2 s windows: energy regions, NOT verse/chorus/vocal detection.
    windows = [(i/sr, min(len(x), i+2*sr)/sr, float(np.sqrt(np.mean(x[i:i+2*sr].astype(np.float64)**2)))) for i in range(0, len(x), 2*sr)]
    med = np.median([w[2] for w in windows])
    result['structure'] = [dict(start=a, end=b, energy=e, label='low_energy' if e < med*.8 else 'high_energy' if e > med*1.2 else 'mid_energy', confidence=.25) for a,b,e in windows]
    result['structure_confidence'] = .25
    return result


def analyze(path, backend='auto'):
    if backend not in ('auto', 'numpy', 'essentia'):
        raise ValueError('Backend sconosciuto')
    x, sr = read_wav(path)
    # Avoid stereo antiphase cancellation; analyze louder channel.
    channel = int(np.argmax(np.mean(x.astype(np.float64)**2, axis=0)))
    mono = x[:, channel]
    result = fallback(mono, sr)
    if backend == 'numpy' or result['silent'] or result['duration'] < 6:
        return result
    try:
        import essentia.standard as es
        y = resample(mono, sr, 44100)
        bpm, beats, confidence, _, _ = es.RhythmExtractor2013(method='multifeature')(y)
        key, mode, strength = es.KeyExtractor(sampleRate=44100)(y)
        if not np.isfinite([bpm, confidence, strength]).all() or not np.isfinite(beats).all():
            raise ValueError('Essentia ha restituito valori non finiti')
        aliases = {'Db':'C#', 'Eb':'D#', 'Gb':'F#', 'Ab':'G#', 'Bb':'A#'}
        key = aliases.get(key, key)
        result.update(backend='essentia', bpm=float(bpm) if bpm > 0 else None,
                      beats=[float(b) for b in beats if 0 <= b < result['duration']],
                      tempo_confidence=float(np.clip(confidence/5, 0, 1)),
                      tempo_confidence_raw=float(confidence), key=f'{key} {mode}',
                      key_pc=NOTES.index(key), mode=mode, key_confidence=float(np.clip(strength,0,1)))
    except ImportError:
        if backend == 'essentia':
            raise ValueError('Essentia non installata: pip install -e ".[essentia]"')
        LOG.info('Essentia non presente: fallback NumPy')
    except Exception as e:
        if backend == 'essentia':
            raise ValueError(f'Analisi Essentia fallita: {e}') from e
        LOG.warning('Essentia fallita, fallback NumPy: %s', e)
        result['backend_warning'] = str(e)
    return result
