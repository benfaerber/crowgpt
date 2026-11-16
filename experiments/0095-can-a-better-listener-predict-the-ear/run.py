"""0095: does a better listener than 0082's predict Ben's grades?

Read-only against field.db. Every judge is scored on a pool it never saw.
The unanswered trials of voice-0078 and capacity-0086 get a sealed
prediction from the judge chosen on the five completed pools alone.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import soundfile as sf
import torch

from crowgpt.embed import AstEmbedder, _to_rate
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from lib.dustprobe import clip_features

from judging import OPEN_POOLS, POOLS_DIR, TRAIN_POOLS, Scorer, Trials

OUT = Path(__file__).resolve().parent
CACHE = REPO / "data" / "experiments" / "0095" / "features"
ALPHAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class Listener:
    """Turns a clip into one vector. Subclasses say how."""

    name = ""

    def vector(self, audio, sr):
        raise NotImplementedError

    def of(self, pool, clip):
        path = CACHE / self.name / pool / f"{clip}.npy"
        if path.exists():
            return np.load(path)
        audio, sr = sf.read(POOLS_DIR / pool / clip, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        vector = np.asarray(self.vector(audio, sr), dtype=np.float32)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, vector)
        return vector


class AstDustListener(Listener):
    """0082's judge input, unchanged, so its 0.48 is reproduced here."""

    name = "ast+dust"

    def __init__(self):
        self.segmenter = Segmenter()
        self.embedder = AstEmbedder(device="cpu")

    def vector(self, audio, sr):
        emb = self.embedder.embed([audio], sr)[0]
        f = clip_features(self.segmenter, audio, sr) or {}
        return np.concatenate([emb, [f.get("pitch_strength", 0.0),
                                     f.get("flatness", 0.0), len(audio) / sr]])


class WhisperListener(Listener):
    """Mean and spread of one Whisper encoder layer over the clip's frames."""

    MODEL = "openai/whisper-large-v3-turbo"
    FRAMES_PER_SECOND = 50
    shared = None

    def __init__(self, layer):
        self.layer = layer
        self.name = f"whisper-L{layer}"

    @classmethod
    def load(cls):
        if cls.shared is None:
            from transformers import WhisperFeatureExtractor, WhisperModel
            extractor = WhisperFeatureExtractor.from_pretrained(cls.MODEL)
            encoder = WhisperModel.from_pretrained(cls.MODEL).encoder.float().to(DEVICE).eval()
            cls.shared = (extractor, encoder)
        return cls.shared

    def vector(self, audio, sr):
        extractor, encoder = self.load()
        wave = _to_rate(audio, sr, 16000)
        inputs = extractor(wave, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            states = encoder(inputs.input_features.to(DEVICE),
                             output_hidden_states=True).hidden_states
        frames = max(2, int(np.ceil(len(wave) / 16000 * self.FRAMES_PER_SECOND)))
        hidden = states[self.layer][0, :frames]
        return torch.cat([hidden.mean(0), hidden.std(0)]).cpu().numpy()


class ClapListener(Listener):
    name = "clap"
    MODEL = "laion/clap-htsat-unfused"

    def __init__(self):
        from transformers import ClapModel, ClapProcessor
        self.processor = ClapProcessor.from_pretrained(self.MODEL)
        self.model = ClapModel.from_pretrained(self.MODEL).to(DEVICE).eval()

    def vector(self, audio, sr):
        wave = _to_rate(audio, sr, 48000)
        try:
            inputs = self.processor(audio=wave, sampling_rate=48000, return_tensors="pt")
        except TypeError:
            inputs = self.processor(audios=wave, sampling_rate=48000, return_tensors="pt")
        with torch.no_grad():
            out = self.model.get_audio_features(**{k: v.to(DEVICE) for k, v in inputs.items()})
        out = getattr(out, "pooler_output", out)
        return out[0].cpu().numpy()


class EncodecListener(Listener):
    """Mean and spread of the codec's continuous latents: what the generator's
    own tokenizer hears."""

    name = "encodec"
    MODEL = "facebook/encodec_24khz"

    def __init__(self):
        from transformers import EncodecModel
        self.model = EncodecModel.from_pretrained(self.MODEL).to(DEVICE).eval()

    def vector(self, audio, sr):
        wave = torch.from_numpy(_to_rate(audio, sr, 24000)).to(DEVICE)[None, None]
        with torch.no_grad():
            latent = self.model.encoder(wave)[0]
        return torch.cat([latent.mean(1), latent.std(1)]).cpu().numpy()


class MelListener(Listener):
    """No network: band energies, how they move, and how periodic the clip is."""

    name = "mel"

    def vector(self, audio, sr):
        import librosa
        wave = _to_rate(audio, sr, 24000)
        mel = librosa.power_to_db(librosa.feature.melspectrogram(
            y=wave, sr=24000, n_fft=1024, hop_length=256, n_mels=64), top_db=80)
        flux = np.abs(np.diff(mel, axis=1))
        flatness = librosa.feature.spectral_flatness(y=wave, n_fft=1024, hop_length=256)[0]
        return np.concatenate([mel.mean(1), mel.std(1), flux.mean(1),
                               [flatness.mean(), flatness.std(), len(wave) / 24000]])


class Combined(Listener):
    def __init__(self, name, parts):
        self.name = name
        self.parts = parts

    def of(self, pool, clip):
        return np.concatenate([part.of(pool, clip) for part in self.parts])


class PairJudge:
    """A ridge on the difference between the two clips. Fitted on each pair
    in both orders with no intercept, so swapping the clips flips the answer
    exactly. `anchored` adds how far each clip sits from the real reference."""

    def __init__(self, listener, anchored=False):
        self.listener = listener
        self.anchored = anchored
        self.name = listener.name + ("+anchor" if anchored else "")

    def row(self, trial):
        pool = trial["pool"]
        first = self.listener.of(pool, trial["first_clip"])
        second = self.listener.of(pool, trial["second_clip"])
        if not self.anchored:
            return first - second
        anchor = self.listener.of(pool, trial["anchor_clip"])
        return np.concatenate([first - second, np.abs(first - anchor) - np.abs(second - anchor)])

    def matrix(self, trials):
        return np.stack([self.row(t) for t in trials])

    def fit(self, trials, alpha):
        from sklearn.linear_model import Ridge
        x = self.matrix(trials)
        y = np.asarray([t["grade"] for t in trials], dtype=float)
        self.scale = x.std(axis=0) + 1e-6
        self.model = Ridge(alpha=alpha * x.shape[1] / 100, fit_intercept=False).fit(
            np.concatenate([x, -x]) / self.scale, np.concatenate([y, -y]))
        return self

    def predict(self, trials):
        return self.model.predict(self.matrix(trials) / self.scale)


class Ensemble:
    """The mean of several judges' answers, each first put on its own scale."""

    def __init__(self, name, judges):
        self.name = name
        self.judges = judges

    def fit(self, trials, alpha):
        self.spread = []
        for judge in self.judges:
            judge.fit(trials, alpha)
            self.spread.append(judge.predict(trials).std() + 1e-9)
        return self

    def predict(self, trials):
        return np.mean([judge.predict(trials) / spread
                        for judge, spread in zip(self.judges, self.spread)], axis=0)


class ArmVerdicts:
    """What a pre-screen is for: which arm of a pool is better overall. One
    row per pair of arms, the ear's mean margin beside the judge's."""

    @staticmethod
    def of(predictions, trials):
        pairs = {}
        for prediction, trial in zip(predictions, trials):
            if trial["kind"] != "compare":
                continue
            pair = tuple(sorted((trial["first_arm"], trial["second_arm"])))
            sign = 1 if trial["first_arm"] == pair[0] else -1
            pairs.setdefault(pair, []).append((sign * trial["grade"], sign * prediction))
        return [{"toward": pair[0], "against": pair[1], "n": len(rows),
                 "ear": round(float(np.mean([r[0] for r in rows])), 3),
                 "judge": round(float(np.mean([r[1] for r in rows])), 3)}
                for pair, rows in sorted(pairs.items())]


class Tournament:
    """Leave one pool out. The ridge strength is chosen inside the training
    pools, never on the pool being scored."""

    def __init__(self, graded):
        self.graded = graded

    def trials(self, pools):
        return [t for pool in pools for t in self.graded[pool]]

    def best_alpha(self, judge, pools):
        if len(pools) < 2:
            return 100.0
        scores = {}
        for alpha in ALPHAS:
            folds = []
            for held in pools:
                rest = [p for p in pools if p != held]
                judge.fit(self.trials(rest), alpha)
                folds.append(Scorer.spearman(judge.predict(self.graded[held]),
                                             [t["grade"] for t in self.graded[held]]))
            scores[alpha] = float(np.mean(folds))
        return max(scores, key=scores.get)

    def score(self, judge):
        held_out = {}
        for pool in TRAIN_POOLS:
            rest = [p for p in TRAIN_POOLS if p != pool]
            alpha = self.best_alpha(judge, rest)
            judge.fit(self.trials(rest), alpha)
            fold = Scorer.fold(judge.predict(self.graded[pool]), self.graded[pool])
            fold["alpha"] = alpha
            fold["arms"] = ArmVerdicts.of(judge.predict(self.graded[pool]), self.graded[pool])
            held_out[pool] = fold
        catches = [(f["catch_picks_real"], f["catch_n"]) for f in held_out.values()]
        arms = [row for fold in held_out.values() for row in fold["arms"]]
        return {
            "arm_pairs": len(arms),
            "arm_verdicts_agreeing": sum((row["ear"] > 0) == (row["judge"] > 0) for row in arms),
            "held_out": held_out,
            "mean_spearman": round(float(np.mean([f["spearman"] for f in held_out.values()])), 3),
            "min_spearman": min(f["spearman"] for f in held_out.values()),
            "catch_picks_real": round(sum(a * n for a, n in catches) / sum(n for _, n in catches), 3),
        }

    def final(self, judge):
        alpha = self.best_alpha(judge, list(TRAIN_POOLS))
        return judge.fit(self.trials(TRAIN_POOLS), alpha), alpha


def listeners():
    whisper = [WhisperListener(layer) for layer in (4, 8, 16, 24, 32)]
    singles = [AstDustListener(), *whisper, ClapListener(), EncodecListener(), MelListener()]
    by_name = {listener.name: listener for listener in singles}
    return singles + [
        Combined("whisper-L8+L24", [by_name["whisper-L8"], by_name["whisper-L24"]]),
        Combined("whisper-L8+encodec+mel",
                 [by_name["whisper-L8"], by_name["encodec"], by_name["mel"]]),
    ]


def main():
    run = Run("0095 — A BETTER LISTENER", ["embed", "tournament", "seal"])
    trials = Trials()
    graded = {pool: trials.graded(pool) for pool in TRAIN_POOLS + OPEN_POOLS}
    everything = [t for pool in TRAIN_POOLS + OPEN_POOLS for t in trials.of(pool)]
    all_listeners = listeners()

    with run.stage("embed") as stage:
        clips = list(dict.fromkeys(
            (t["pool"], t[key]) for t in everything
            for key in ("anchor_clip", "first_clip", "second_clip")))
        singles = [listener for listener in all_listeners if not isinstance(listener, Combined)]
        done, total = 0, len(clips) * len(singles)
        for listener in singles:
            for pool, clip in clips:
                listener.of(pool, clip)
                done += 1
                if done % 25 == 0:
                    stage.update(done, total, extra=listener.name)
        stage.update(total, total)

    tournament = Tournament(graded)
    judges = [PairJudge(listener, anchored) for listener in all_listeners
              for anchored in (False, True)]
    plain = {judge.name: judge for judge in judges}
    judges.append(Ensemble("ensemble(whisper-L32,clap,ast+dust,mel)",
                           [plain[name] for name in ("whisper-L32", "clap", "ast+dust", "mel")]))
    report = {"answers": {pool: len(graded[pool]) for pool in graded}, "judges": {}}

    with run.stage("tournament") as stage:
        for n, judge in enumerate(judges):
            report["judges"][judge.name] = tournament.score(judge)
            stage.update(n + 1, len(judges), extra=judge.name)
            run.note(f"{judge.name}: {report['judges'][judge.name]['mean_spearman']}")

    with run.stage("seal") as stage:
        winner = max(judges, key=lambda j: report["judges"][j.name]["mean_spearman"])
        fitted, alpha = tournament.final(winner)
        report["chosen"] = {"judge": winner.name, "alpha": alpha,
                            "chosen_on": "mean held-out Spearman over the five completed pools"}
        report["already_answered"] = {
            pool: Scorer.fold(fitted.predict(graded[pool]), graded[pool])
            for pool in OPEN_POOLS if graded[pool]}
        sealed = {}
        for pool in OPEN_POOLS:
            waiting = trials.ungraded(pool)
            predictions = fitted.predict(waiting)
            sealed[pool] = [
                {"trial": t["id"], "kind": t["kind"], "first_arm": t["first_arm"],
                 "second_arm": t["second_arm"], "toward_first": round(float(p), 3)}
                for t, p in zip(waiting, predictions)]
            compare = [(t, p) for t, p in zip(waiting, predictions) if t["kind"] == "compare"]
            arms = sorted({t["first_arm"] for t, _ in compare} | {t["second_arm"] for t, _ in compare})
            margins = [p if t["first_arm"] == arms[0] else -p for t, p in compare]
            report.setdefault("sealed_summary", {})[pool] = {
                "favoured_if_positive": arms[0], "other": arms[1:],
                "mean_margin": round(float(np.mean(margins)), 3),
                "share_favouring": round(float(np.mean([m > 0 for m in margins])), 3),
                "n_compare_trials": len(margins)}
        (OUT / "sealed.json").write_text(json.dumps(
            {"judge": winner.name, "alpha": alpha, "predictions": sealed}, indent=1) + "\n")
        stage.update(1, 1)

    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, result in sorted(report["judges"].items(), key=lambda kv: -kv[1]["mean_spearman"]):
        print(f"{name:32s} mean {result['mean_spearman']:.3f}  min {result['min_spearman']:.3f}"
              f"  catches {result['catch_picks_real']:.3f}"
              f"  arm verdicts {result['arm_verdicts_agreeing']}/{result['arm_pairs']}")
    print(json.dumps({k: report[k] for k in ("chosen", "already_answered", "sealed_summary")}, indent=2))


if __name__ == "__main__":
    main()
