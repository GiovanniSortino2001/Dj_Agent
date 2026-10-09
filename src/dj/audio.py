"""Base decoder: bounded uncompressed PCM WAV; no hidden codec dependencies."""
from pathlib import Path
import wave
import numpy as np
from .util import finite

MAX_SECONDS = 1800
MAX_BYTES = 256 * 1024 * 1024


def read_wav(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("WAV oltre 256 MiB: convertire/downsample prima")
    try:
        with wave.open(str(path), "rb") as f:
            sr, channels, width, n = f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getnframes()
            if not 8000 <= sr <= 192000 or channels not in (1, 2) or width not in (1, 2, 3, 4):
                raise ValueError("Richiesto WAV PCM 8/16/24/32 bit, mono/stereo, 8–192 kHz")
            if n == 0 or n / sr > MAX_SECONDS or f.getcomptype() != "NONE":
                raise ValueError("WAV vuoto, compresso o più lungo di 30 minuti")
            raw = f.readframes(n)
        if len(raw) != n * channels * width:
            raise ValueError("WAV troncato")
        if width == 1:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
        elif width == 3:
            a = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
            v = a[:, 0] | a[:, 1] << 8 | a[:, 2] << 16
            v = (v ^ 0x800000) - 0x800000
            x = v.astype(np.float32) / 8388608
        else:
            x = np.frombuffer(raw, '<i2' if width == 2 else '<i4').astype(np.float32) / (2 ** (8 * width - 1))
        return x.reshape(-1, channels), sr
    except (wave.Error, EOFError) as e:
        raise ValueError(f"WAV non valido: {path.name}: {e}") from e


def write_wav(path, x, sr=22050):
    sr = int(finite(sr, 'sample_rate', 8000, 192000))
    x = np.asarray(x)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or x.shape[1] not in (1, 2) or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("Audio vuoto, forma errata o campioni non finiti")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as f:
        f.setparams((x.shape[1], 2, sr, 0, 'NONE', 'not compressed'))
        f.writeframes(np.rint(np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())


def resample(x, source_rate, target_rate):
    """Linear resampler for demo only: NOT bandlimited/time-stretch/key-lock."""
    source_rate = finite(source_rate, 'source_rate', 1)
    target_rate = finite(target_rate, 'target_rate', 1)
    x = np.asarray(x)
    if not len(x) or not np.isfinite(x).all():
        raise ValueError('Resampling: input vuoto/non finito')
    n = max(1, int(round(len(x) * target_rate / source_rate)))
    if n > 192000 * MAX_SECONDS:
        raise ValueError('Resampling troppo grande')
    p = np.arange(n) * source_rate / target_rate
    if x.ndim == 1:
        return np.interp(p, np.arange(len(x)), x).astype(np.float32)
    return np.stack([np.interp(p, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1).astype(np.float32)


def synth(path, bpm=120, root=0, seconds=24, seed=0, sr=22050):
    bpm = finite(bpm, 'bpm', 60, 200)
    seconds = finite(seconds, 'seconds', 8, 300)
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    envelope = np.where(t < seconds / 4, .35, np.where(t > seconds * .75, .5, 1.0))
    y = np.zeros_like(t)
    # Major chord plus kick and hats; no copyrighted recordings.
    for note in (48 + root, 52 + root, 55 + root):
        y += .055 * np.sin(2 * np.pi * 440 * 2 ** ((note - 69) / 12) * t) * envelope
    for beat in np.arange(.1, seconds, 60 / bpm):
        start = int(beat * sr)
        n = min(int(.14 * sr), len(y) - start)
        u = np.arange(n) / sr
        y[start:start+n] += .6 * np.exp(-u * 35) * np.sin(2*np.pi*(65*u + 1.8*(1-np.exp(-u*35))))
        y[start:start+n] += .08 * rng.normal(size=n) * np.exp(-u*90)
    write_wav(path, y, sr)
    return {'path': str(path), 'bpm': bpm, 'root_pc': int(root) % 12, 'seconds': seconds, 'seed': seed}
