"""0014's gate, run against DAC — same windows, same metrics, matched bitrate."""
import json, sys
from pathlib import Path
HERE = Path("/home/ben/Code/cawtalker/crowgpt"); sys.path.insert(0, str(HERE/"src"))
from crowgpt.gpu import claim
claim()
import librosa, numpy as np
from math import gcd
from scipy.signal import resample_poly
from crowgpt.codec import Codec, normalise
from crowgpt.corpus import Corpus
from crowgpt.dac_codec import DacCodec
from crowgpt.judge import BirdNetJudge
from crowgpt.metrics import codebook_entropy, multi_res_stft_distance

SR, PER_SPECIES = 24000, 10
judge = BirdNetJudge()

def to24k(y, sr):
    if sr == SR: return y.astype(np.float32)
    g = gcd(int(sr), SR)
    return resample_poly(y, SR//g, int(sr)//g).astype(np.float32)

windows = []
for slug, recs in sorted(Corpus().recordings().items()):
    rng = np.random.default_rng(hash(slug) % 1000)
    picks = rng.choice(len(recs), min(PER_SPECIES*3, len(recs)), replace=False)
    kept = 0
    for i in picks:
        if kept >= PER_SPECIES: break
        try:
            y, sr = librosa.load(str(recs[int(i)].path), sr=None, mono=True)
        except Exception: continue
        y = to24k(y, sr)
        if y.size < SR*6: continue
        start = int(rng.integers(0, y.size - SR*3))
        windows.append(normalise(y[start:start+SR*3])); kept += 1
print(f"{len(windows)} windows", flush=True)

arms = {}
codecs = {"encodec_6kbps": Codec(bandwidth=6.0), "dac_8cb_6kbps": DacCodec(n_codebooks=8),
          "dac_12cb_9kbps": DacCodec(n_codebooks=12)}
for name, codec in codecs.items():
    outs, codes_all = [], []
    for w in windows:
        c = codec.encode(w)
        codes_all.append(c[0].numpy())
        outs.append(codec.decode(c[0])[0][:w.size])
    arms[name] = {"clips": outs, "codes": np.concatenate(codes_all, axis=1)}
    print(f"  {name} encoded", flush=True)

base = judge.confidences(windows)
results = {"n": len(windows), "arms": {}}
for name, a in arms.items():
    conf = judge.confidences(a["clips"])
    pairs = [(b, c) for b, c in zip(base, conf) if b is not None and c is not None]
    bs, cs = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    detected = bs >= judge.crow_min
    ent = codebook_entropy(a["codes"])
    results["arms"][name] = {
        "retain": round(float((cs[detected] >= judge.crow_min).mean()), 3),
        "median_delta": round(float(np.median((cs-bs)[detected])), 3),
        "stft": round(float(np.mean([multi_res_stft_distance(w, o)
                                     for w, o in zip(windows, a["clips"])])), 3),
        "entropy_mean": round(float(np.mean(ent)), 2),
        "entropy_per_stage": [round(x,1) for x in ent],
        "capacity_used": round(float(np.mean(ent)/10), 3),
    }
Path(HERE/"results"/"dac_gate.json").write_text(json.dumps(results, indent=2))
print("\n%-16s %8s %10s %8s %9s %9s" % ("arm","retain","dConf","STFT","entropy","capacity"))
for n, a in results["arms"].items():
    print("%-16s %8.3f %10.3f %8.3f %9.2f %8.0f%%" % (
        n, a["retain"], a["median_delta"], a["stft"], a["entropy_mean"], 100*a["capacity_used"]))
