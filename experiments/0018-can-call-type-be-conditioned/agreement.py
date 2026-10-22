"""Does the shipped call-type head agree with humans on the bouts we can label?

If it does not, pseudo-labelling 57,000 bouts with it is pseudo-noise and the
whole conditioning route dies here for twenty minutes instead of hours.
"""
import importlib.util, json, sys
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path("/home/ben/Code/cawtalker"); HERE = REPO/"crowgpt"
sys.path.insert(0, str(HERE/"src"))
from crowgpt.gpu import claim
claim()
import joblib, numpy as np
from crowgpt.birdnet import BirdNet
from crowgpt.codec import normalise
from crowgpt.tokens import BoutStore

spec = importlib.util.spec_from_file_location("ct", REPO/"pipelines/ingest/corpus.py")
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
spec2 = importlib.util.spec_from_file_location("pl", REPO/"pipelines/training/pooling.py")
pl = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pl)

labels = json.loads((REPO/"pipelines/ingest/crowtools/labels.json").read_text())
by_file = defaultdict(list)
for key, flags in labels["labels"].items():
    fid, s, e = key.rsplit("-", 2)
    c = {core for flag, core in ct.FLAG_TO_CORE.items() if flags.get(flag)}
    if c: by_file[fid].append((int(s), int(e), c))

store = BoutStore(REPO/"data/crowgpt/bouts")
tagged = []
for row in store.index:
    if row["species"] != "american-crow" or row["recording_id"] not in by_file: continue
    lo, hi = row["start_sec"], row["start_sec"] + row["dur_sec"]
    got = set()
    for s, e, c in by_file[row["recording_id"]]:
        if min(hi, e) - max(lo, s) > 0.25: got |= c
    if got: tagged.append((row, got))
print(f"{len(tagged)} human-labelled bouts", flush=True)

bundle = joblib.load(REPO/"pipelines/training/models/american-crow/calltype_clf.joblib")
clf, classes = bundle["model"], list(bundle["classes"])
print("head classes:", classes, flush=True)

clips = [normalise(store.audio(r)) for r, _ in tagged]
emb = BirdNet(sample_rate=24000).embed(clips)
print("embedded:", emb.shape, flush=True)
if len(emb) != len(tagged):
    print("WARNING: %d clips produced no embedding" % (len(tagged)-len(emb)))
X = np.array([pl.pool(v) for v in emb])
pred = clf.predict(X)

truth = [t for _, t in tagged][:len(pred)]
hit = sum(1 for p, t in zip(pred, truth) if p in t)
print("\nAGREEMENT: head's top class is in the human label set for %d of %d  (%.0f%%)"
      % (hit, len(pred), 100*hit/len(pred)))
single = [(p, t) for p, t in zip(pred, truth) if len(t) == 1]
hit1 = sum(1 for p, t in single if p in t)
print("on single-label bouts only:  %d of %d  (%.0f%%)" % (hit1, len(single), 100*hit1/len(single)))
print("\nconfusion (human -> head), single-label bouts:")
conf = defaultdict(Counter)
for p, t in single: conf[next(iter(t))][p] += 1
for human in sorted(conf):
    total = sum(conf[human].values())
    top = ", ".join(f"{k} {v}" for k, v in conf[human].most_common(4))
    print("  %-12s n=%-5d %s" % (human, total, top))
print("\nbase rate if it always guessed the commonest human label: %.0f%%"
      % (100*Counter(next(iter(t)) for _, t in single).most_common(1)[0][1]/len(single)))
