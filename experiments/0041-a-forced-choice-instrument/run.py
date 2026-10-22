"""A forced-choice instrument, validated on a question we already know.

0038 found the rating page is contrast-sensitive: `model-fair-k8` — identical
weights — scored 0.21 in one sitting and 0.54 in the next, while the real anchor
sat at 0.92 in both. Across every repeated arm the score tracked the arm's RANK
inside its sitting. A listener grades a clip against the company it keeps.

A forced choice has no company. "Which of these two is less robotic" cannot
drift with the rest of the sitting, and it estimates one quantity — P(A
preferred) — against a null of exactly 0.5, rather than differencing two noisy
rates.

THREE PAIR TYPES, because a new instrument that only produces new answers cannot
be trusted.

    OPEN    fairk8 vs dac44_gen, 40 pairs. 0037 could not separate these (0.25
            against 0.21, interval [-0.21, +0.29]) and it is the question that
            decides whether DAC-44 was worth anything at the generator. If the
            forced choice resolves it, the instrument has earned its place.

    KNOWN   fairk8 vs k5_matched, 15 pairs. Absolute rating settled this
            decisively last night — 0.54 against 0.17, interval excluding zero.
            The forced choice must agree, strongly. If it does not, the new
            instrument is wrong and nothing else in the run counts.

    CATCH   real vs fairk8, 10 pairs. Should be near-unanimous for real. These
            confirm the listener is engaged and are excluded from every model
            comparison — Ben's own objection is why they are not a test arm:
            real rates 0.85-0.97 against generated 0.22, so a real-versus-
            generated trial has a known answer and measures nothing about
            models.

WHY NOT PAIR EVERY ARM AGAINST EVERY OTHER. Pairs grow as n(n-1)/2 and the ear
is the budget. Two models, one known comparison and a catch set is 65 trials,
which is one sitting at the pace the last seven ran.
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

from crowgpt.progress import Run

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BOUTS = DATA / "bouts"
RESULTS = HERE / "results"
PAGE = RESULTS / "rate-pairwise-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
MODELS = {
    "fairk8": (RESULTS / "model-fair-k8", 225),
    "dac44": (RESULTS / "model-dac44", 260),
    "k5_matched": (RESULTS / "model-k5-matched", 230),
}
N_OPEN, N_KNOWN, N_CATCH = 40, 15, 10
MIN_SECONDS = 1.0
SKIP = 380
ALREADY_USED = 360     # 0033 120, 0034 120, 0035 72, 0037 24, 0038 24
SR = 24000
KEEP, FULL = 5, 8


def load_marginals():
    """0038's measured stage 5-7 marginals, for the k5 arm's fill."""
    cache = REPO / "experiments/0038-stop-paying-for-inaudible-codebooks/fine_marginals.json"
    return np.array(json.loads(cache.read_text()))


def main():
    run = Run("0041 — A FORCED-CHOICE INSTRUMENT",
              ["generate", "page"])
    try:
        from crowgpt.codec import Codec, normalise
        from crowgpt.sample import Sampler
        from crowgpt.tokens import BoutStore

        store = BoutStore(BOUTS)
        marginals = load_marginals()
        rng = np.random.default_rng(0)

        with run.stage("generate") as stage:
            need = {"fairk8": N_OPEN + N_KNOWN + N_CATCH,
                    "dac44": N_OPEN, "k5_matched": N_KNOWN}
            total = sum(need.values()) + N_CATCH
            made, done = {}, 0
            eight = Codec(bandwidth=6.0)
            for name, count in need.items():
                folder, max_frames = MODELS[name]
                sampler = Sampler(folder / "model.pt", token_dir=None)
                clips = []
                for i in range(count):
                    if name == "k5_matched":
                        flat = sampler.tokens(SPECIES, temperature=1.0, top_k=200,
                                              seed=5000 + i, max_frames=max_frames)
                        coarse = sampler.codec.unflatten(flat)
                        fine = np.stack([rng.choice(1024, size=coarse.shape[1], p=marginals[r])
                                         for r in range(FULL - KEEP)])
                        audio = eight.decode(torch.from_numpy(
                            np.concatenate([coarse, fine], axis=0)))[0]
                    else:
                        audio = sampler.audio(SPECIES, temperature=1.0, top_k=200,
                                              seed=5000 + i, max_frames=max_frames)
                    clips.append(normalise(np.asarray(audio, dtype=np.float32)))
                    done += 1
                    stage.update(done, total, extra=f"{name} {i + 1}/{count}")
                made[name] = clips
                del sampler
                torch.cuda.empty_cache()

            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, ordered = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                ordered.append(i)
            pool = [i for i in ordered[SKIP:]
                    if store.index[i]["n_samples"] / SR >= MIN_SECONDS][ALREADY_USED:]
            if len(pool) < N_CATCH:
                raise SystemExit(f"only {len(pool)} unused bouts remain, need {N_CATCH}")
            made["real"] = [normalise(store.audio(store.index[i])) for i in pool[:N_CATCH]]
            done += N_CATCH
            stage.update(done, total, extra="real")
            del eight
            torch.cuda.empty_cache()

        with run.stage("page") as stage:
            from crowgpt.demo import PairPage

            def clip(name, i):
                return {"audio": made[name][i], "sr": SR, "arm": name}

            pairs = []
            for i in range(N_OPEN):
                pairs.append({"a": clip("fairk8", i), "b": clip("dac44", i)})
            for i in range(N_KNOWN):
                pairs.append({"a": clip("fairk8", N_OPEN + i), "b": clip("k5_matched", i)})
            for i in range(N_CATCH):
                pairs.append({"a": clip("real", i),
                              "b": clip("fairk8", N_OPEN + N_KNOWN + i), "catch": True})

            PairPage(pairs, {
                "Question": "which of two clips is less robotic",
                "Pairs": f"{N_OPEN} fairk8 vs dac44 (open) · {N_KNOWN} fairk8 vs k5 "
                         f"(known answer) · {N_CATCH} real vs fairk8 (catch)",
                "Why pairwise": "0038 caught identical weights scoring 0.21 and 0.54 "
                                "in consecutive sittings — absolute rating moves with "
                                "the company a clip keeps",
                "Sides": "randomised per trial and recorded, so a left-button habit "
                         "cannot read as a model preference",
                "Levels": "every clip peak-normalised",
            }, seed=0).write(PAGE)
            (OUT / "pairs.json").write_text(json.dumps(
                [{"a": p["a"]["arm"], "b": p["b"]["arm"], "catch": p.get("catch", False)}
                 for p in pairs], indent=2))
            stage.say(str(PAGE))
            run.note(f"{len(pairs)} pairs -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
