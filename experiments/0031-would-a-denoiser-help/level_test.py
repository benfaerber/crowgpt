import numpy as np, soundfile as sf
import denoise_lib

x, sr = sf.read("work/in/096.wav", always_2d=False)
x = x.astype(np.float32)
model = denoise_lib.load_model()

print(f"{'gain':>10}  {'in peak dBFS':>13}  {'in std':>9}  {'out/in rms':>11}  {'out/in peak':>12}")
for gain_db in (0, 12, 24, 33, 40):
    g = 10 ** (gain_db / 20)
    xg = x * g
    y = denoise_lib.denoise(model, xg) / g          # undo the exact same gain
    rms_ratio = np.sqrt((y**2).mean()) / np.sqrt((x**2).mean())
    peak_ratio = np.abs(y).max() / np.abs(x).max()
    print(f"{gain_db:>8} dB  {20*np.log10(np.abs(xg).max()):>13.1f}  "
          f"{xg.std():>9.5f}  {20*np.log10(rms_ratio):>10.1f} dB  {20*np.log10(peak_ratio):>11.1f} dB")
