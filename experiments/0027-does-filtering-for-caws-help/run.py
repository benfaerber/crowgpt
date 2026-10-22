"""Train on confidently caw-like audio only, and ask whether it sounds better.

Ben's, from the 0026 sitting: "I think filtering for caw like sounds might work."
It is the most promising untested lever, and by now nearly everything else has
been tested. "It sounds robotic" has survived the fine codebooks (0024, dropping
them is inaudible), density and recording quality (0026), capacity and
regularisation (0023, 0.164 nats bought nothing audible), the codec bitrate, and
both a 433M and a 1.4B pretrained base (0022).

THE CASE FOR THE DATA BEING THE PROBLEM is written in the project's own notes and
has never been acted on. segment.py's burst detector is "a bootstrap, not a call
detector" — 0013 measured it passing 1.02 units per window even in its emptiest
BirdNET confidence band. So a real fraction of every training run so far has been
audio that is not a crow call, and the model has been learning it faithfully.
0026 puts real audio at 25/28 rated good and the model at 6/24; if part of the
gap is the model reproducing junk it was fed, this closes it and nothing else
tried has.

THE FILTER, deliberately strict:

  every species     BirdNET corvid confidence >= 0.8
  american crow     AND the 0021 head confidently calls it `alarm call` or `call`

That is the caw-like pair; `song` is softsong and `begging` is juvenile, and
neither is what Ben means by a caw. 81,389 bouts become 37,183 — American Crow
57,479 becomes 21,685.

SAME SPLIT SEED as every other run, so the held-out recordings stay held out and
the real clips in the listening test remain audio no model has seen.

SAME HYPERPARAMETERS as sweep-0023/batch-32-dropout-0, which is the checkpoint
0026 rated. Batch 32, dropout 0, 40k steps, d384 / 8 layers / 6 heads. The only
thing that changes is which bouts go in — otherwise this measures two things and
resolves neither.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

from collections import Counter

from crowgpt.progress import Run
from crowgpt.tokens import BoutStore, TokenWriter
from crowgpt.train import Trainer

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
TOKENS = DATA / "tokens-cawfiltered"
MODEL = HERE / "results" / "model-cawfiltered"
OUT = Path(__file__).resolve().parent

MIN_CONF = 0.8
CAW = ("alarm call", "call")
STEPS = 40_000


def main():
    run = Run("0027 — DOES FILTERING FOR CAWS HELP",
              ["filter", "tokenise", "train"])
    try:
        store = BoutStore(DATA / "bouts")
        payload = json.loads((DATA / "bouts" / "call_types.json").read_text())
        types = {int(k): v for k, v in payload["call_types"].items()}

        with run.stage("filter") as stage:
            def passes(position, row):
                if row["crow_conf"] < MIN_CONF:
                    return False
                if row["species"] == "american-crow":
                    return types.get(position) in CAW
                return True

            keep = {i for i, row in enumerate(store.index) if passes(i, row)}
            splits = store.split(seed=0)
            filtered = {name: [i for i in idxs if i in keep] for name, idxs in splits.items()}
            mix = Counter(store.index[i]["species"] for i in keep)
            stage.say(f"{len(keep)} of {len(store.index)} bouts kept")
            run.note("kept per species: " + ", ".join(f"{k} {v}" for k, v in sorted(mix.items())))
            run.note("splits: " + ", ".join(f"{k} {len(v)}" for k, v in filtered.items()))

        with run.stage("tokenise") as stage:
            if (TOKENS / "manifest.json").exists():
                manifest = json.loads((TOKENS / "manifest.json").read_text())
                stage.say(f"reused {manifest['splits']['train']['sequences']} sequences")
            else:
                manifest = TokenWriter(store, TOKENS, bandwidth=6.0, variants=1,
                                       call_types=types).run(filtered)
                stage.say(f"{manifest['splits']['train']['sequences']} sequences")
            run.note("call types in vocabulary: " + ", ".join(manifest["call_types"]))

        with run.stage("train") as stage:
            trainer = Trainer(TOKENS, MODEL, steps=STEPS, n_embd=384, n_layer=8,
                              n_head=6, seed=0, dropout=0.0,
                              memory_budget=1_200_000_000)
            stage.say(f"{trainer.model.n_params()/1e6:.1f}M params, "
                      f"batch {trainer.effective_batch}, dropout {trainer.config.dropout}")
            history = trainer.run(on_eval=lambda step, val: stage.update(
                step, STEPS, extra=f"val {val:.4f}"))
            last = history["history"][-1]
            run.note(f"best val {history['best_val']:.4f}, final gap {last['gap']:+.4f}")
            (OUT / "results.json").write_text(json.dumps({
                "kept_bouts": len(keep), "of": len(store.index),
                "best_val": history["best_val"], "final": last,
                "min_conf": MIN_CONF, "caw_types": list(CAW),
            }, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("done")


if __name__ == "__main__":
    main()
