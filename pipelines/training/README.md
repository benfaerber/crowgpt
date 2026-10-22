# Phase 4 — Training

Train a call-type classifier on the BirdNET embeddings from
[Phase 3](../representation/), and wrap it as an end-to-end detector.

## Honest scale note

The corpus is ~117 clips. At that size the right model is a **regularized linear
classifier**, not a deep net — confirmed here (logreg CV macro-F1 **0.48** beats
the GPU MLP's **0.35**). The GPU MLP path exists for when the corpus grows to
thousands, where a nonlinear head starts to pay off.

## Files

- `train.py` — the original Phase 4 classifier (logreg on BirdNET embeddings),
  retired as the served head 2026-08-09; `train_head.py` writes the
  `models/american-crow/` bundle the analyzer serves now. Kept as the record.
- `gpu_mlp.py` — small MLP on the GPU (torch), held-out eval. Scaling infra +
  comparison; runs in system python.
- `predict.py` — **the working detector.** `audio in -> call type + confidence`,
  end-to-end in the BirdNET venv, reading the served `american-crow` bundle.
- `models/<species>/calltype_clf.joblib` — one served bundle per species, each
  carrying the `feature`/`backbone`/`dim` metadata the analyzer checks at load.

## Results (cross-validated, honest)

| | value |
|--|--|
| accuracy | 0.65 (baseline 0.61) |
| macro-F1 | 0.48 |
| **flight-call detector AUC** | **0.87** |
| per-class | `call` F1 0.75, `flight call` F1 0.58, `alarm call` 0.46, `song` 0.13 |

`call` and `flight call` work; `alarm call`/`song` are label-limited (few, noisy
samples) — the gold set is the fix for those, not a better model.

## Run

```sh
# train (BirdNET venv)
../representation/.venv-birdnet/bin/python train.py
# GPU comparison (system python)
python3 gpu_mlp.py
# detect on any clip
../representation/.venv-birdnet/bin/python predict.py path/to/clip.mp3
```

## Next

- The flight-call detector (AUC 0.87) is the demoable Phase 5 result.
- To lift `alarm`/`song` and add behavioral classes (threat), the lever is the
  own-recording gold set, not more modeling.
- When the corpus reaches thousands, revisit `gpu_mlp.py` — that's where the GPU
  earns its keep.
