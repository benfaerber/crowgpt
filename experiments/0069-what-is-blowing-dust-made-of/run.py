"""0069: what is blowing dust made of — probe, decoder A/B, sampling grid.

Labels are Ben's per-clip descriptions from pool longctx-0067b, parsed by
the same keyword families the sitting analysis used. Stage gates: the
decoder A/B and the grid interpret their numbers through the probe, so if
no feature separates dust from clean the later stages still run but the
README's decision rule sends the search embedding-side instead.
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"
                       / "0067-does-context-length-unlock-the-structure"))

from crowgpt.gpu import claim

claim()

import numpy as np
import soundfile as sf
import torch

from analyse_sitting2 import families_of, split_note
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import codec_from_manifest

DB = REPO / "fieldserver" / "instance" / "field.db"
OUT = Path(__file__).resolve().parent
POOL_DIR = HERE / "results" / "listening-pools" / "longctx-0067b"
POOL_SPEC = (REPO / "experiments"
             / "0067-does-context-length-unlock-the-structure" / "pool2.json")
SPECIES = "american-crow"
CKPT = HERE / "results" / "model-longctx" / "model.pt"
MAX_FRAMES = {"model-longctx": 460, "model-units": 230}

TEMPERATURES = (0.85, 0.95, 1.0, 1.1)
TOP_KS = (50, 100, 200, 400)
DRAWS_PER_CELL = 40
MIN_BURST_S = 0.05
FEATURES = ("pitch_strength", "flatness", "centroid_hz", "attack_ms")


def bursts_of(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, seg.floor_pctl)
    out = []
    for a, b in seg.bursts(db, fps, floor):
        lo, hi = int(a / fps * SAMPLE_RATE), int(b / fps * SAMPLE_RATE)
        if (hi - lo) / SAMPLE_RATE >= MIN_BURST_S:
            out.append(audio[lo: hi])
    return out


def pitch_strength(burst):
    """Peak normalised autocorrelation in the 60-1200 Hz F0 lag range."""
    x = burst - burst.mean()
    if not x.any():
        return 0.0
    lags = np.arange(int(SAMPLE_RATE / 1200), int(SAMPLE_RATE / 60) + 1)
    n = len(x)
    spectrum = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(spectrum * np.conj(spectrum))[: n]
    ac /= ac[0] + 1e-12
    lags = lags[lags < n]
    return float(ac[lags].max()) if len(lags) else 0.0


def spectral(burst):
    window = np.hanning(len(burst))
    power = np.abs(np.fft.rfft(burst * window)) ** 2
    freqs = np.fft.rfftfreq(len(burst), 1 / SAMPLE_RATE)
    band = (freqs >= 100) & (freqs <= 8000)
    p = power[band] + 1e-20
    flatness = float(np.exp(np.mean(np.log(p))) / p.mean())
    centroid = float((freqs[band] * p).sum() / p.sum())
    return flatness, centroid


def attack_ms(burst):
    envelope = np.abs(burst)
    kernel = max(1, int(0.005 * SAMPLE_RATE))
    envelope = np.convolve(envelope, np.ones(kernel) / kernel, mode="same")
    peak_i = int(np.argmax(envelope))
    peak = envelope[peak_i]
    if peak <= 0:
        return 0.0
    before = envelope[: peak_i + 1]
    over10 = np.nonzero(before >= 0.1 * peak)[0]
    over90 = np.nonzero(before >= 0.9 * peak)[0]
    if not len(over10) or not len(over90):
        return 0.0
    return float((over90[0] - over10[0]) / SAMPLE_RATE * 1000)


def clip_features(seg, audio):
    bursts = bursts_of(seg, audio)
    if not bursts:
        return None
    rows = []
    for burst in bursts:
        flatness, centroid = spectral(burst)
        rows.append((pitch_strength(burst), flatness, centroid,
                     attack_ms(burst)))
    return {name: float(np.mean([r[i] for r in rows]))
            for i, name in enumerate(FEATURES)} | {"n_bursts": len(bursts)}


def auc(pos, neg):
    """Rank AUC: P(random positive scores above random negative)."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return None
    wins = (pos[:, None] > neg[None, :]).sum() \
        + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(wins / (len(pos) * len(neg)))


def labelled_clips():
    """(clip_name, arm, label) from Ben's notes; dust and clean only."""
    db = sqlite3.connect(DB)
    rows = db.execute(
        """SELECT t.first_clip, t.second_clip, t.first_arm, t.second_arm, a.note
           FROM listening_answers a JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'longctx-0067b'""")
    out = []
    for first, second, first_arm, second_arm, note in rows:
        parts = split_note(note)
        if not parts:
            continue
        for clip, arm, text in ((first, first_arm, parts[0]),
                                (second, second_arm, parts[1])):
            fams = families_of(text)
            if arm == "real":
                out.append((clip, arm, "real"))
            elif "blowing-dust" in fams and "clean" not in fams:
                out.append((clip, arm, "dust"))
            elif "clean" in fams and "blowing-dust" not in fams:
                out.append((clip, arm, "clean"))
    return out


def main():
    run = Run("0069 — BLOWING DUST", ["probe", "decoder", "grid", "verdict"])
    seg, results = Segmenter(), {}
    try:
        with run.stage("probe") as stage:
            clips = labelled_clips()
            by_label = defaultdict(list)
            feats = {}
            for n, (name, arm, label) in enumerate(clips):
                audio, sr = sf.read(POOL_DIR / name, dtype="float32")
                assert sr == SAMPLE_RATE
                f = clip_features(seg, normalise(audio))
                if f:
                    feats[name] = f
                    by_label[label].append(name)
                stage.update(n + 1, len(clips), extra=name)
            results["probe_n"] = {k: len(v) for k, v in by_label.items()}
            results["probe_auc_dust_vs_clean"] = {}
            for feature in FEATURES:
                dust = [feats[n][feature] for n in by_label["dust"]]
                clean = [feats[n][feature] for n in by_label["clean"]]
                real = [feats[n][feature] for n in by_label["real"]]
                # Signed so "higher = dustier" for every feature: pitch
                # strength inverts, the noise features do not.
                a = auc(dust, clean)
                results["probe_auc_dust_vs_clean"][feature] = {
                    "auc_dust_higher": round(a, 3) if a is not None else None,
                    "dust_mean": round(float(np.mean(dust)), 4) if dust else None,
                    "clean_mean": round(float(np.mean(clean)), 4) if clean else None,
                    "real_mean": round(float(np.mean(real)), 4) if real else None,
                }
                run.note(f"{feature}: {results['probe_auc_dust_vs_clean'][feature]}")

            scored = {f: abs(v["auc_dust_higher"] - 0.5)
                      for f, v in results["probe_auc_dust_vs_clean"].items()
                      if v["auc_dust_higher"] is not None}
            best = max(scored, key=scored.get)
            best_auc = results["probe_auc_dust_vs_clean"][best]["auc_dust_higher"]
            dust_high = best_auc > 0.5
            dust_scores = [feats[n][best] for n in by_label["dust"]]
            clean_scores = [feats[n][best] for n in by_label["clean"]]
            candidates = sorted(set(dust_scores + clean_scores))
            youden, threshold = -1.0, candidates[0]
            for c in candidates:
                tpr = np.mean([(s >= c) if dust_high else (s <= c)
                               for s in dust_scores])
                fpr = np.mean([(s >= c) if dust_high else (s <= c)
                               for s in clean_scores])
                if tpr - fpr > youden:
                    youden, threshold = tpr - fpr, c
            results["probe_choice"] = {
                "feature": best, "auc": best_auc, "dust_is_high": dust_high,
                "threshold": round(float(threshold), 4),
                "youden": round(float(youden), 3),
                "validated": abs(best_auc - 0.5) >= 0.2,
            }
            run.note(f"probe: {results['probe_choice']}")

        def is_dusty(f):
            value = f[results["probe_choice"]["feature"]]
            if results["probe_choice"]["dust_is_high"]:
                return value >= results["probe_choice"]["threshold"]
            return value <= results["probe_choice"]["threshold"]

        with run.stage("decoder") as stage:
            spec = json.loads(POOL_SPEC.read_text())["spec"]
            wanted = defaultdict(list)
            for name, arm, label in labelled_clips():
                if arm == "real":
                    continue
                index = int(Path(name).stem.rsplit("-", 1)[1])
                seeds = spec["longctx_seeds"] if arm == "model-longctx" \
                    else spec["units_seeds"]
                wanted[arm].append((name, label, seeds[index]))

            paired, done, total = [], 0, sum(len(v) for v in wanted.values())
            for arm, items in wanted.items():
                sampler = Sampler(CKPT if arm == "model-longctx" else
                                  HERE / "results" / "model-units" / "model.pt",
                                  token_dir=None, decoder_state="finetuned")
                frozen = codec_from_manifest(sampler.manifest,
                                             device=sampler.device)
                for name, label, seed in items:
                    flat = sampler.tokens(SPECIES, seed=seed,
                                          max_frames=MAX_FRAMES[arm])
                    grid = torch.from_numpy(sampler.codec.unflatten(flat))
                    fine = clip_features(seg, normalise(np.asarray(
                        sampler.codec.decode(grid)[0], dtype=np.float32)))
                    froz = clip_features(seg, normalise(np.asarray(
                        frozen.decode(grid)[0], dtype=np.float32)))
                    if fine and froz:
                        paired.append((label, fine, froz))
                    done += 1
                    stage.update(done, total, extra=f"{arm} seed {seed}")
                del sampler, frozen
                torch.cuda.empty_cache()

            feature = results["probe_choice"]["feature"]
            diffs = [fine[feature] - froz[feature] for _, fine, froz in paired]
            results["decoder_ab"] = {
                "n": len(paired),
                "feature": feature,
                "mean_finetuned_minus_frozen": round(float(np.mean(diffs)), 4),
                "dusty_finetuned": sum(is_dusty(fine) for _, fine, _ in paired),
                "dusty_frozen": sum(is_dusty(froz) for _, _, froz in paired),
            }
            run.note(f"decoder A/B: {results['decoder_ab']}")

        with run.stage("grid") as stage:
            sampler = Sampler(CKPT, token_dir=None, decoder_state="finetuned")
            cells, done = {}, 0
            total = len(TEMPERATURES) * len(TOP_KS) * DRAWS_PER_CELL
            for temperature in TEMPERATURES:
                for top_k in TOP_KS:
                    rows, seed = [], 5000
                    while len(rows) < DRAWS_PER_CELL \
                            and seed < 5000 + DRAWS_PER_CELL * 6:
                        flat = sampler.tokens(
                            SPECIES, temperature=temperature, top_k=top_k,
                            seed=seed, max_frames=MAX_FRAMES["model-longctx"])
                        grid = sampler.codec.unflatten(flat)
                        audio = np.asarray(sampler.codec.decode(
                            torch.from_numpy(grid))[0], dtype=np.float32)
                        seed += 1
                        if audio.size / SAMPLE_RATE < MIN_GRADEABLE_SECONDS:
                            continue
                        f = clip_features(seg, normalise(audio))
                        if f:
                            gaps = max(0, f["n_bursts"] - 1)
                            rows.append((is_dusty(f), f, gaps))
                        done = min(done + 1, total)
                        stage.update(done, total,
                                     extra=f"T={temperature} k={top_k}")
                    key = f"T{temperature}_k{top_k}"
                    cells[key] = {
                        "n": len(rows),
                        "keep_rate": round(len(rows) / max(1, seed - 5000), 2),
                        "dust_rate": round(float(np.mean(
                            [r[0] for r in rows])), 3) if rows else None,
                        "mean_units": round(float(np.mean(
                            [r[1]["n_bursts"] for r in rows])), 2) if rows else None,
                        "gaps_per_clip": round(float(np.mean(
                            [r[2] for r in rows])), 2) if rows else None,
                    }
                    run.note(f"{key}: {cells[key]}")
            results["grid"] = cells

        with run.stage("verdict") as stage:
            default = results["grid"].get("T1.0_k200")
            results["default_cell"] = default
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
