"""Which channel bucket should generation pin, and does pinning do anything?

0044 asked whether the channel token helps and answered no. It pinned
`vocabulary.channels[0]`, and that is the wrong bucket in two independent ways.

`channel-000` IS NOT A CHANNEL. It is k-means label 0, so its identity is
sklearn's arbitrary label order and carries no meaning at all. It is also
`ChannelBuckets.fallback`, so every recording the describer could not
characterise is assigned to it by design ("A recording with no bucket is not an
error"). In the current index it collects 448 distinct American Crow recordings
against a median bucket of 46. It is the corpus's mixture bucket.

So 0044 compared "no channel token" against "a token naming the average of
everything" — approximately the averaging the token exists to prevent — at n=20,
which resolves about 25 points. It came back 0.600 in favour, unresolved. That
null is uninformative about the hypothesis, and `_prefix` says as much in its own
docstring: which bucket to pin is "a caller's choice worth making deliberately".
Nobody has yet made it.

THE BUCKETS ARE NOT INTERCHANGEABLE. Across the 143 buckets holding >=150
American Crow bouts, mean BirdNET crow confidence runs 0.566 to 0.964.
`channel-000` sits at 0.790, mid-pack.

WHAT THIS MEASURES. Stage-0 churn per pinned bucket, against real audio's 0.868
(0046). Two outcomes and both are answers:

  - churn varies across buckets and the good ones approach 0.868 -> pinning is a
    real lever, and one bucket has earned a sitting.
  - every bucket gives the same churn -> the channel token does nothing at
    generation time, the hypothesis dies for two minutes of GPU instead of a
    night and a sitting, and 0044's null stands for a better reason than it had.

THREE RANKING CRITERIA, AND ONLY ONE OF THEM IS BIRDNET. Choosing candidates by
crow confidence alone would be circular: BirdNET selected the corpus.

  human      one archive's 0-5 stars and the other's A/B/C, per recording, mapped
             to a common 0-1. Assigned by people, before this project existed,
             and independent of every instrument here. 0.00 is "unrated" in the
             archive export, not "bad", so it is dropped rather than scored.
  flatness   geometric over arithmetic mean of each bucket's mean QUIET-frame
             mel spectrum, recovered by un-whitening its centroid. A hissy
             channel is spectrally flat; a clean one has rolloff and structure.
             Shape only, so recording gain cannot drive it.
  birdnet    mean crow_conf. Reported, and used only to break ties.

Absolute quiet-frame LEVEL is deliberately not a criterion. `describe_corpus`
reads the shards without normalising, so level is the recording's gain as much as
its noise floor, and ranking on it would rank microphone trim.

WHAT THIS CANNOT DECIDE. Churn is a mechanism, not audibility — 0049 put it at 1
for 2 as a ranker and demoted it to triage. The output is a shortlist that has
earned a sitting, never a change to the sampling default.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
DATA = REPO / "data" / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

OUT = Path(__file__).resolve().parent
CHANNELLED = HERE / "results" / "model-channel256"
CONTROL = HERE / "results" / "model-fair-k8"
SPECIES = "american-crow"

N = 40
MIN_FRAMES = 40
TARGET = 0.868          # real audio's stage-0 churn, measured in 0046
MIN_BOUTS = 150         # enough bouts for the bucket's embedding to be trained
MIN_RECORDINGS = 15     # enough channels that the bucket is not memorised

XC_LETTERS = {"A": 1.0, "B": 2.0 / 3.0, "C": 1.0 / 3.0, "D": 0.0, "E": 0.0}


def human_quality(raw):
    """Stars from one archive and letters from the other on one 0-1 scale, or None.

    The two archives arrived separately and their ratings never
    reconciled, so the index carries both forms in one field. 0.00 is the
    archive export's "unrated" and must not read as the worst possible
    recording — it is 1,601 American Crow bouts of no information.
    """
    if raw is None:
        return None
    if raw in XC_LETTERS:
        return XC_LETTERS[raw]
    try:
        stars = float(raw)
    except (TypeError, ValueError):
        return None
    return None if stars <= 0 else min(stars / 5.0, 1.0)


def bucket_table(buckets):
    """One row per bucket: size, human quality, flatness, crow confidence."""
    mapping, fallback = buckets["mapping"], buckets["fallback"]
    centroids = np.asarray(buckets["centroids"])
    mean, scale = np.asarray(buckets["mean"]), np.asarray(buckets["scale"])

    rows = collections.defaultdict(
        lambda: {"bouts": 0, "recordings": set(), "quality": [], "conf": []})
    with open(DATA / "bouts" / "index.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            if row["species"] != SPECIES:
                continue
            entry = rows[mapping.get(row["recording_id"], fallback)]
            entry["bouts"] += 1
            entry["recordings"].add(row["recording_id"])
            quality = human_quality(row.get("quality"))
            if quality is not None:
                entry["quality"].append(quality)
            if row.get("crow_conf") is not None:
                entry["conf"].append(row["crow_conf"])

    # Un-whitening recovers the mean quiet log-mel spectrum the cluster stands
    # for. `fit` standardised before k-means, so the raw centroid is in units of
    # standard deviations per mel band and is not a spectrum at all.
    spectra = centroids * scale + mean
    table = {}
    for name, entry in rows.items():
        index = int(name.split("-")[1])
        spectrum = spectra[index] if index < len(spectra) else None
        flatness = None
        if spectrum is not None:
            geometric = np.exp(spectrum.mean())
            arithmetic = np.exp(spectrum).mean()
            flatness = float(geometric / max(arithmetic, 1e-30))
        table[name] = {
            "bouts": entry["bouts"],
            "recordings": len(entry["recordings"]),
            "human": float(np.mean(entry["quality"])) if entry["quality"] else None,
            "rated": len(entry["quality"]),
            "flatness": flatness,
            "birdnet": float(np.mean(entry["conf"])) if entry["conf"] else None,
        }
    return table


def choose(table, fallback, per_end=3):
    """Candidate buckets: the incumbent, plus both ends of each criterion.

    Both ends on purpose. A sweep of only the good buckets cannot tell "pinning
    works" from "churn is the same everywhere" — the bad end is the control that
    makes a spread interpretable.
    """
    eligible = {
        name: row for name, row in table.items()
        if row["bouts"] >= MIN_BOUTS
        and row["recordings"] >= MIN_RECORDINGS
        and row["human"] is not None
        and row["flatness"] is not None
        and name != fallback
    }
    picked, why = [], {}

    def take(name, reason):
        if name not in picked:
            picked.append(name)
        why.setdefault(name, []).append(reason)

    take(fallback, "incumbent: channels[0] and the fallback sink")
    for key, reverse, label in (("human", True, "human quality"),
                                ("flatness", False, "least hiss"),
                                ("flatness", True, "most hiss"),
                                ("human", False, "worst human quality")):
        ranked = sorted(eligible, key=lambda n: eligible[n][key], reverse=reverse)
        for name in ranked[:per_end]:
            take(name, f"{label} {'top' if reverse == (key == 'human') else 'bottom'}")
    return picked, why, len(eligible)


def churn(grids):
    total, seen = np.zeros(8), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


def sample(sampler, seed, channel=None, top_k=200, temperature=1.0, max_frames=225):
    """`Sampler.tokens` with the channel pinned, copied from 0047's sweep.

    Kept as a copy for the same reason 0047 gave: nothing in `src` should change
    to answer a question about whether a knob is worth having. The duration
    bucket is the first sampled token and is NOT a codec id — dropping the
    `emitted > 1` guard shifts every codec token by one, the grid unflattens to
    noise, and every arm reads about 0.99.
    """
    import torch

    vocab = sampler.vocabulary
    torch.manual_seed(seed)
    prefix = sampler._prefix(SPECIES, channel=channel)
    sequence = torch.tensor([prefix], device=sampler.device, dtype=torch.long)
    limit = min(sampler.config.block_size,
                vocab.prefix_len + max_frames * vocab.n_codebooks)
    cache = sampler.model.empty_cache()
    logits, _ = sampler.model(sequence, cache=cache, offset=0)
    codes, emitted = [], 0
    with torch.no_grad():
        for _ in range(limit - vocab.prefix_len):
            grown = sequence.size(1)
            step = logits[:, -1, :].float()
            step = step.masked_fill(sampler.legal.forbidden[grown], float("-inf"))
            step = step / max(temperature, 1e-5)
            if top_k:
                kept = min(top_k, int((~np.isinf(step.cpu().numpy())).sum()))
                if kept > 0:
                    cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                    step = step.masked_fill(step < cutoff, float("-inf"))
            probs = torch.softmax(step, dim=-1)
            total = probs.sum()
            if not torch.isfinite(total) or total <= 0:
                break
            nxt = torch.multinomial(probs / total, num_samples=1)
            if int(nxt) == vocab.eos:
                break
            emitted += 1
            if emitted > 1:
                codes.append(int(nxt))
            sequence = torch.cat([sequence, nxt], dim=1)
            logits, _ = sampler.model(nxt, cache=cache, offset=grown)
    flat = np.array(codes, dtype=np.int64)
    usable = (flat.size // vocab.n_codebooks) * vocab.n_codebooks
    return flat[:usable]


def sweep_arm(sampler, channel, run_note=None):
    grids, seed, short = [], 0, 0
    while len(grids) < N and seed < N * 5:
        flat = sample(sampler, seed, channel=channel)
        seed += 1
        grid = sampler.codec.unflatten(flat)
        if grid.shape[1] >= MIN_FRAMES:
            grids.append(grid)
        else:
            short += 1
    value = churn(grids)
    return {"stage0": round(float(value[0]), 4),
            "mean": round(float(value.mean()), 4),
            "gap": round(float(value[0] - TARGET), 4),
            "clips": len(grids), "fragments": short}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rank-only", action="store_true",
                        help="build the bucket table and candidates, no GPU")
    parser.add_argument("--per-end", type=int, default=3)
    args = parser.parse_args()

    buckets = json.loads((DATA / "channels.json").read_text())
    table = bucket_table(buckets)
    candidates, why, n_eligible = choose(table, buckets["fallback"], args.per_end)

    ranking = {"eligible": n_eligible, "buckets": table,
               "candidates": candidates, "why": why,
               "fallback": buckets["fallback"],
               "thresholds": {"min_bouts": MIN_BOUTS,
                              "min_recordings": MIN_RECORDINGS}}
    (OUT / "ranking.json").write_text(json.dumps(ranking, indent=2))

    print(f"{n_eligible} eligible buckets "
          f"(>={MIN_BOUTS} bouts, >={MIN_RECORDINGS} recordings)\n")
    print(f"{'bucket':12}{'bouts':>7}{'recs':>6}{'human':>7}{'rated':>7}"
          f"{'flat':>8}{'birdnet':>9}  why")
    for name in candidates:
        row = table[name]
        human = f"{row['human']:.3f}" if row["human"] is not None else "  -  "
        flat = f"{row['flatness']:.4f}" if row["flatness"] is not None else "  -   "
        bird = f"{row['birdnet']:.3f}" if row["birdnet"] is not None else "  -  "
        print(f"{name:12}{row['bouts']:7d}{row['recordings']:6d}{human:>7}"
              f"{row['rated']:7d}{flat:>8}{bird:>9}  {'; '.join(why[name])}")

    if args.rank_only:
        print(f"\nranking -> {OUT / 'ranking.json'}")
        return

    from crowgpt.gpu import claim

    claim()

    from crowgpt.progress import Run
    from crowgpt.sample import Sampler

    run = Run("0051 — WHICH CHANNEL BUCKET",
              ["sweep", "control", "report"])
    results = {}
    try:
        with run.stage("sweep") as stage:
            sampler = Sampler(CHANNELLED / "model.pt", token_dir=None)
            for n, name in enumerate(candidates, 1):
                results[name] = sweep_arm(sampler, name)
                results[name].update(
                    {k: table[name][k] for k in ("bouts", "recordings",
                                                 "human", "flatness", "birdnet")})
                stage.update(n, len(candidates),
                             extra=f"{name} {results[name]['stage0']:.3f}")
            del sampler

        # The unconditioned model is the arm 0044 actually beat, so without it a
        # spread across buckets still cannot say pinning helps.
        with run.stage("control") as stage:
            stage.update(0, 1)
            control = Sampler(CONTROL / "model.pt", token_dir=None)
            results["(control) fair-k8, no channel token"] = sweep_arm(control, None)
            stage.say(f"control stage-0 "
                      f"{results['(control) fair-k8, no channel token']['stage0']:.3f}")

        with run.stage("report") as stage:
            ranked = sorted(results.items(), key=lambda kv: abs(kv[1]["gap"]))
            pinned = {k: v for k, v in results.items() if k.startswith("channel-")}
            spread = (max(v["stage0"] for v in pinned.values())
                      - min(v["stage0"] for v in pinned.values()))
            (OUT / "results.json").write_text(json.dumps(
                {"target_stage0": TARGET, "n_per_arm": N,
                 "spread_across_buckets": round(spread, 4),
                 "why": why, "arms": results}, indent=2))
            for label, row in ranked[:3]:
                run.note(f"{label}: stage-0 {row['stage0']:.3f} ({row['gap']:+.3f})")
            run.note(f"spread across pinned buckets: {spread:.4f}")
            stage.say(f"best: {ranked[0][0]} · spread {spread:.4f}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise

    print(f"\n{'arm':44}{'stage0':>8}{'gap':>8}{'mean':>7}{'frags':>7}")
    for label, row in sorted(results.items(), key=lambda kv: abs(kv[1]["gap"])):
        print(f"{label:44}{row['stage0']:8.3f}{row['gap']:+8.3f}"
              f"{row['mean']:7.3f}{row['fragments']:7d}")


if __name__ == "__main__":
    main()
