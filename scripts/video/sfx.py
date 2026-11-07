"""Sound effects for the peer-vote video, synthesised with numpy (no samples, no licences).

Each sound is a stereo float array at 48 kHz, peak-normalised to 0.9. To use your own sound instead (for example
from ElevenLabs Sound Effects), put audio/sfx_<name>.mp3 next to the voice clips; it replaces the synthetic one (the
whoosh-type sounds then lose their variants).

    whoosh   scene change (low, the biggest)  swish    big camera snap
    swoosh   text sliding in (soft)           pop      something popping in
    impact   a word slamming in               thump    a low hit (truck lines, second slams)
    riser    tension before a reveal          ticker   the € counter rolling
"""
import os
import subprocess
from pathlib import Path

import numpy as np

SR = 48_000
AUDIO = Path(__file__).resolve().parent / "audio"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def _bandpass(x: np.ndarray, fc: np.ndarray, q: float) -> np.ndarray:
    """State-variable band-pass with a moving centre frequency (Chamberlin)."""
    f = 2 * np.sin(np.pi * np.minimum(fc, SR / 6) / SR)
    damp, low, band = 1 / q, 0.0, 0.0
    out = np.empty_like(x)
    for i in range(len(x)):
        low += f[i] * band
        band += f[i] * (x[i] - low - damp * band)
        out[i] = band
    return out


def _sweep(n: int, points: list[tuple[float, float]]) -> np.ndarray:
    """Exponential frequency curve through (position 0–1, Hz) points."""
    t = np.linspace(0, 1, n)
    xs, fs = zip(*points)
    return np.exp(np.interp(t, xs, np.log(fs)))


def _stereo(x: np.ndarray, pan_from: float = 0.0, pan_to: float = 0.0) -> np.ndarray:
    pan = np.linspace(pan_from, pan_to, len(x))
    th = (pan + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)], axis=1)


def _norm(x: np.ndarray) -> np.ndarray:
    return (0.9 * x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def _lowpass(x: np.ndarray, fc: float) -> np.ndarray:
    """Zero-phase low-pass (2nd-order Butterworth magnitude) that takes the hiss off the top."""
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (f / fc) ** 4), len(x))


def _air(dur: float, f: list, q: float, peak: float, seed: int, pan=(-0.6, 0.6), body=0.1, top=4000.0) -> np.ndarray:
    """Band-passed noise swept along f; `body` mixes in a wide layer an octave lower, `top` is the low-pass corner."""
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n)
    fc = _sweep(n, f)
    x = _bandpass(_bandpass(rng.standard_normal(n), fc, q), fc, q)          # 4th order: air, not hiss
    low = _bandpass(rng.standard_normal(n), fc * 0.5, 0.7)
    x = x / (np.abs(x).max() + 1e-9) + body * low / (np.abs(low).max() + 1e-9)
    env = np.where(t < peak, (t / peak) ** 2.2, (1 - (t - peak) / (1 - peak)) ** 1.8)
    return _norm(_stereo(_lowpass(x, top) * env, *pan))


# The whoosh-type sounds, lowest and longest for the biggest move: scene changes, camera snaps, text sliding in.
# Each has VARIANTS versions (another noise seed, pitch and length) so no clip is heard twice in a row.
AIR = {  # duration s, frequency curve (position 0–1, Hz), q, envelope peak, seed, pan, low body, low-pass corner Hz
    "whoosh": (0.60, [(0, 140), (0.55, 1200), (1, 260)], 1.3, 0.55, 1, (-0.6, 0.6), 0.45, 2400),
    "swish": (0.28, [(0, 320), (0.4, 1700), (1, 600)], 1.2, 0.4, 2, (-0.3, 0.3), 0.25, 3200),
    "swoosh": (0.22, [(0, 500), (0.35, 2200), (1, 1000)], 1.2, 0.35, 3, (0.2, -0.2), 0.1, 4200),
}
VARIANTS = 4
PITCH = (1.0, 0.87, 1.12, 0.94)
LENGTH = (1.0, 1.12, 0.9, 1.05)


def _air_variant(name: str, v: int) -> np.ndarray:
    dur, f, q, peak, seed, pan, body, top = AIR[name]
    v %= VARIANTS
    k = PITCH[v]
    return _air(dur * LENGTH[v], [(x, hz * k) for x, hz in f], q, peak, seed + 100 * v, pan, body, top * k)


def _tone(n: int, f0: float, f1: float, tau: float, glide: float) -> np.ndarray:
    t = np.arange(n) / SR
    freq = f1 + (f0 - f1) * np.exp(-t / glide)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / tau)


def _hit(dur: float, f0: float, f1: float, tau: float, click: float, seed: int) -> np.ndarray:
    """A low hit: a falling sine for weight, a mid knock so small speakers hear it too, and a click on top."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    sub = _tone(n, f0, f1, tau, 0.06)
    knock = _tone(n, f0 * 2.6, f1 * 2.4, tau * 0.3, 0.03)
    mid = _bandpass(_bandpass(rng.standard_normal(n), np.full(n, 520.0), 1.4), np.full(n, 520.0), 1.4)
    mid = mid / (np.abs(mid).max() + 1e-9) * np.exp(-t / 0.07)
    noise = np.diff(rng.standard_normal(n + 1)) * np.exp(-t / 0.003) * click * 0.5
    x = np.tanh(1.4 * (sub + 1.3 * knock + 1.8 * mid + noise))
    x[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return _norm(_stereo(x))


def _pop() -> np.ndarray:
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    freq = 420 + 560 * (1 - np.exp(-t / 0.018))
    x = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.032)
    x[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return _norm(_stereo(x + 0.2 * np.sin(4 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.015)))


def _riser(dur: float = 1.4) -> np.ndarray:
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    rng = np.random.default_rng(5)
    x = _bandpass(rng.standard_normal(n), _sweep(n, [(0, 300), (1, 5200)]), 2.2)
    tone = np.sin(2 * np.pi * np.cumsum(_sweep(n, [(0, 180), (1, 760)])) / SR)
    x = (x + 0.35 * tone) * t ** 2.4
    x[-int(0.015 * SR):] *= np.linspace(1, 0, int(0.015 * SR))
    return _norm(_stereo(x, -0.3, 0.3))


def _ticker(dur: float = 0.55, clicks: int = 16) -> np.ndarray:
    n = int(dur * SR)
    x = np.zeros(n)
    k = np.arange(int(0.012 * SR)) / SR
    blip = np.sin(2 * np.pi * 2900 * k) * np.exp(-k / 0.0025)
    for i in range(clicks):
        at = int(n * 0.92 * (1 - (1 - i / clicks) ** 0.5) ** 1.0)   # dense at first, like the counter
        x[at:at + len(blip)] += blip[: n - at]
    return _norm(_stereo(x))


SYNTH = {
    "impact": lambda: _hit(1.3, 105, 42, 0.32, 1.0, 4),
    "thump": lambda: _hit(0.45, 150, 70, 0.11, 0.5, 6),
    "pop": _pop,
    "riser": _riser,
    "ticker": _ticker,
}


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def load(name: str, variant: int = 0) -> np.ndarray:
    """Your own audio/sfx_<name>.mp3 (or .wav) if it exists, else the synthetic sound (whoosh-types: that variant)."""
    for ext in ("mp3", "wav"):
        own = AUDIO / f"sfx_{name}.{ext}"
        if own.exists():
            return _norm(decode(own))
    return _air_variant(name, variant) if name in AIR else SYNTH[name]()
