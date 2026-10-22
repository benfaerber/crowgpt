"""Is capture 87's 13-22s wash wind on the mic, or a passing vehicle?

They need different money. Wind is a $15 windshield; traffic is a directional
mic or a different spot.

Wind on a capsule is overwhelmingly sub-200 Hz, rises and falls in gusts over
seconds, and has no harmonic structure. Traffic carries further up the spectrum
and is steadier.
"""
import sys, numpy as np
from scipy.io import wavfile
from scipy.signal import stft
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import audio_for  # noqa: E402

rate, data = wavfile.read(audio_for(87))
x = data.astype(np.float64) / 32768.0
f, t, Z = stft(x, fs=rate, nperseg=4096, noverlap=3072)
p = np.abs(Z) ** 2

def frac(lo, hi, mask):
    sel = (f >= lo) & (f < hi)
    return p[sel][:, mask].mean()

wash = (t >= 13.0) & (t <= 22.0)
calm = (t >= 3.0) & (t <= 8.0)

print("band energy, wash (13-22s) vs calm (3-8s)")
for lo, hi in ((0, 100), (100, 200), (200, 500), (500, 1000), (1000, 4000), (4000, 12000)):
    w, c = frac(lo, hi, wash), frac(lo, hi, calm)
    print(f"  {lo:5d}-{hi:<6d} Hz   {10*np.log10(w/c):+6.1f} dB")

sub = (f < 200)
env = np.sqrt(p[sub].mean(axis=0))
w = env[wash]
print(f"\n  sub-200 Hz during the wash: {10*np.log10(w.max()/w.min()):.1f} dB "
      f"peak-to-trough over {t[wash][-1]-t[wash][0]:.0f}s")
print(f"  gust-like variation (std/mean): {w.std()/w.mean():.2f}")
