"""Did the decoder finetune clear its gate, on audio it never saw?

Training and its running evals lived on the train and val splits. This is the
TEST split — grouped, stratified, untouched by every stage of the finetune —
and the three-part gate 0058 designed after finding the original STFT gate
Goodharted: AST-FAD votes, the segmenter unit delta votes, STFT is logged and
voteless. The final judge is Ben's ear on the page this writes.

Three decoders, same frozen encoder, bit-identical tokens:

    frozen       facebook/encodec_24khz as shipped — the incumbent
    spectral     best.pt of the 20-pass spectral-only control
    adversarial  best.pt of the 50-pass adversarial arm (best val FAD 40.4
                 at step 130k; the last three-quarters of training never beat
                 it, which is what best-checkpoint selection is for)

Numbers to carry in: on VAL the frozen decoder read FAD 57.7, spectral best
50.6, adversarial best 40.4. If the test split tells a similar story the
improvement is real rather than val-overfit; the page then asks the only
question left — does K=8 still scratch (0057's word) through the new decoder?
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import ComparePage
from crowgpt.embed import AstEmbedder
from crowgpt.metrics import frechet_distance, multi_res_stft_distance
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
FINETUNE = HERE / "results" / "decoder-finetune"
PAGE = HERE / "results" / "compare-decoder-finetune.html"

SPECIES = "american-crow"
N_BOUTS = 64
N_PAGE = 8
BANDWIDTH = 6.0

ARMS = [
    ("frozen", None),
    ("spectral", FINETUNE / "spectral" / "best.pt"),
    ("adversarial", FINETUNE / "adversarial" / "best.pt"),
]


def test_bouts(store, limit):
    splits = store.split(seed=0)
    seen, rows = set(), []
    for i in splits["test"]:
        row = store.index[i]
        if row["species"] != SPECIES or row["recording_id"] in seen \
                or row["n_samples"] < SAMPLE_RATE:
            continue
        seen.add(row["recording_id"])
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def units(segmenter, audio):
    db, fps = segmenter.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, segmenter.floor_pctl)
    return len(segmenter.bursts(db, fps, floor))


def main():
    from transformers import EncodecModel

    run = Run("0063 — DECODER FINETUNE TEST GATE",
              ["encode", "decode", "metrics", "page"])
    results = {}
    try:
        store = BoutStore(DATA / "bouts")
        rows = test_bouts(store, N_BOUTS)
        raw = [normalise(store.audio(r)) for r in rows]
        segmenter = Segmenter()
        model = EncodecModel.from_pretrained("facebook/encodec_24khz").to("cuda")
        pristine = {k: v.clone() for k, v in model.decoder.state_dict().items()}

        with run.stage("encode") as stage:
            codes = []
            for n, clip in enumerate(raw, 1):
                batch = torch.from_numpy(clip)[None, None].to("cuda")
                with torch.no_grad():
                    codes.append(model.encode(batch, bandwidth=BANDWIDTH).audio_codes[0])
                stage.update(n, len(raw))

        decoded = {}
        with run.stage("decode") as stage:
            for a, (arm, ckpt) in enumerate(ARMS):
                if ckpt is None:
                    model.decoder.load_state_dict(pristine)
                else:
                    state = torch.load(ckpt, map_location="cuda", weights_only=True)
                    model.decoder.load_state_dict(state["decoder"])
                    results.setdefault("checkpoint_steps", {})[arm] = state["step"]
                model.decoder.eval()
                decoded[arm] = []
                with torch.no_grad():
                    for c, clip in zip(codes, raw):
                        out = model.decode(c.unsqueeze(0), [None]).audio_values
                        decoded[arm].append(out[0, 0].cpu().numpy()[: clip.size])
                stage.update(a + 1, len(ARMS), extra=arm)

        with run.stage("metrics") as stage:
            embedder = AstEmbedder()
            raw_emb = embedder.embed(raw, SAMPLE_RATE)
            half = len(raw_emb) // 2
            results["fad_floor_raw_vs_raw"] = round(float(
                frechet_distance(raw_emb[:half], raw_emb[half:])), 3)
            raw_units = [units(segmenter, r) for r in raw]
            for n, (arm, _) in enumerate(ARMS, 1):
                emb = embedder.embed(decoded[arm], SAMPLE_RATE)
                results[arm] = {
                    "ast_fad": round(float(
                        frechet_distance(raw_emb[:half], emb[half:])), 3),
                    "unit_delta": round(float(np.mean([
                        units(segmenter, d) - u
                        for d, u in zip(decoded[arm], raw_units)])), 3),
                    "stft_logged": round(float(np.mean([
                        multi_res_stft_distance(r, d)
                        for r, d in zip(raw, decoded[arm])])), 4),
                }
                run.note(f"{arm}: FAD {results[arm]['ast_fad']} · "
                         f"unit Δ {results[arm]['unit_delta']} · "
                         f"stft {results[arm]['stft_logged']} (logged)")
                stage.update(n, len(ARMS), extra=arm)

        with run.stage("page") as stage:
            page_rows = []
            for n in range(min(N_PAGE, len(raw))):
                page_rows.append({
                    "species": f"test bout {n + 1}",
                    "arms": [
                        ("RAW — the recording", "untouched", raw[n], None),
                        ("K=8 · frozen decoder", "the incumbent — 0057 called this scratchy", decoded["frozen"][n], None),
                        ("K=8 · spectral finetune", "control arm, 20 passes", decoded["spectral"][n], None),
                        ("K=8 · adversarial finetune", "the candidate, best of 50 passes", decoded["adversarial"][n], None),
                    ],
                })
            ComparePage(page_rows, {
                "Question": "does K=8 still scratch through the finetuned decoder",
                "Bouts": f"held-out TEST split, never seen by the finetune",
                "Verdicts wanted": "describe each arm — scratchy / hoarse / clean, and which is closest to RAW",
            }).write(PAGE)
            stage.say(PAGE.name)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
        run.note(f"page at {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
