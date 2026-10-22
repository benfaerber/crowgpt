"""Do crowgpt's BOUTS carry call type at all, or is the unit wrong?

The shipped head scores AUC 0.90-0.98 on crow-tools' ~1 s segments and collapses
to "alarm call" on bouts. Either bouts are out of its domain, or a bout — 2.4 s
holding ~3.8 calls — is simply not a thing that has one call type. Training a
fresh classifier on bouts separates those two.
"""
import importlib.util, json, sys
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path("/home/ben/Code/cawtalker"); HERE = REPO/"crowgpt"
sys.path.insert(0, str(HERE/"src"))
from crowgpt.gpu import claim
claim()
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from crowgpt.birdnet import BirdNet
from crowgpt.codec import normalise
from crowgpt.tokens import BoutStore

spec = importlib.util.spec_from_file_location("ct", REPO/"pipelines/ingest/corpus.py")
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)

labels = json.loads((REPO/"pipelines/ingest/crowtools/labels.json").read_text())
by_file = defaultdict(list)
for key, flags in labels["labels"].items():
    fid, s, e = key.rsplit("-", 2)
    c = {core for flag, core in ct.FLAG_TO_CORE.items() if flags.get(flag)}
    if c: by_file[fid].append((int(s), int(e), c))

store = BoutStore(REPO/"data/crowgpt/bouts")
rows, truth, groups = [], [], []
for row in store.index:
    if row["species"] != "american-crow" or row["recording_id"] not in by_file: continue
    lo, hi = row["start_sec"], row["start_sec"]+row["dur_sec"]
    got = set()
    for s, e, c in by_file[row["recording_id"]]:
        if min(hi, e) - max(lo, s) > 0.25: got |= c
    if len(got) == 1:
        rows.append(row); truth.append(next(iter(got))); groups.append(row["group_key"])
print(f"{len(rows)} single-label bouts, {len(set(groups))} recording groups", flush=True)

cache = Path("/tmp/claude-1000/-home-ben-Code-cawtalker/606cbb31-476b-4ed9-88b8-d5b1e2a456f1/scratchpad/bout_emb.npz")
if cache.exists():
    z = np.load(cache, allow_pickle=True); X, y, g = z["X"], z["y"], z["g"]
else:
    keep, vecs = [], []
    B = BirdNet(sample_rate=24000)
    for i in range(0, len(rows), 400):
        chunk = rows[i:i+400]
        e, idx = B.embed_indexed([normalise(store.audio(r)) for r in chunk])
        if len(e):
            vecs.append(e); keep.extend(i + j for j in idx)
        print(f"  embedded {min(i+400,len(rows))}/{len(rows)} (kept {len(keep)})", flush=True)
    X = np.concatenate(vecs)
    y = np.array([truth[i] for i in keep]); g = np.array([groups[i] for i in keep])
    np.savez(cache, X=X, y=y, g=g)
print("features:", X.shape, flush=True)

keep = np.isin(y, [c for c, n in Counter(y).items() if n >= 25])
X, y, g = X[keep], y[keep], g[keep]
print("classes:", dict(Counter(y)))
cv = StratifiedGroupKFold(n_splits=5)
model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced"))
print("\nRECORDING-GROUPED one-vs-rest AUC on BOUTS:")
for c in sorted(set(y)):
    yb = (y == c).astype(int)
    p = cross_val_predict(model, X, yb, cv=cv, groups=g, method="predict_proba")[:, 1]
    print("  %-12s n=%-5d AUC %.3f" % (c, yb.sum(), roc_auc_score(yb, p)))
print("\n  (the same head on crow-tools' 1 s segments: 0.904 - 0.975)")
