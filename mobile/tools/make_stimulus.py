"""Looping A/B stimulus: 300 ms log chirp 200 Hz -> 12 kHz, then 300 ms silence.

The chirp gives a full frequency response in one shot; the silent gaps expose
noise floor behavior (AGC gain recovery, NS gating) between bursts.
"""
import sys
import wave

import numpy as np

SR = 48000
CHIRP_MS = 300
GAP_MS = 300
CYCLES = 80
AMPLITUDE_DBFS = -20.0

n_chirp = int(SR * CHIRP_MS / 1000)
n_gap = int(SR * GAP_MS / 1000)
t = np.arange(n_chirp) / SR
f0, f1 = 200.0, 12000.0
k = np.log(f1 / f0)
phase = 2 * np.pi * f0 * (CHIRP_MS / 1000) / k * (np.exp(k * t / (CHIRP_MS / 1000)) - 1)
chirp = np.sin(phase)

fade = int(SR * 0.005)
window = np.ones(n_chirp)
window[:fade] = np.linspace(0, 1, fade)
window[-fade:] = np.linspace(1, 0, fade)
chirp *= window
chirp *= 10 ** (AMPLITUDE_DBFS / 20)

period = np.concatenate([chirp, np.zeros(n_gap)])
signal = np.tile(period, CYCLES)
pcm = (signal * 32767).astype("<i2")

out = sys.argv[1] if len(sys.argv) > 1 else "stimulus.wav"
with wave.open(out, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print(f"{out}: {len(signal)/SR:.1f}s, period {(CHIRP_MS+GAP_MS)}ms, {AMPLITUDE_DBFS} dBFS")
