"""Does the generator hold one voice?

Ben, 2026-08-03: "Why does CrowGPT sound bad? What am I missing here?"

The listener's description has been stable for thirty experiments and nobody has
measured the thing it actually says. Not "robotic" — that is a summary. The
distinctive half is **"xylophone-esque, choppy, CHANGES TONE RAPIDLY"**, which is
a claim about how fast timbre moves inside one clip, and it has never been
turned into a number.

0020 tried six hand-crafted timbre measures and found no separation at n=40, and
that null has been read since as "no cheap instrument can hear the defect". But
every one of those six is a WITHIN-FRAME or WHOLE-CLIP statistic — HNR, jitter,
spectral flatness, the frame-grid stitch. None of them measures a RATE of
change, and none of them looks across clips. The listener's complaint is about
both.

So three questions, one instrument:

    1. Within a clip, does generated timbre move FASTER frame to frame than real
       audio does?  ("changes tone rapidly")
    2. Across clips, does the generator produce as much timbral VARIETY as real
       audio does?  (does it commit to a bird, or emit an average of all of them)
    3. In the corpus, how much of real timbre variation is the RECORDING rather
       than the bird?  (the scale the other two numbers have to be read against)

THE CODEC ARM IS NOT OPTIONAL. 0024 established that the round-trip is itself
audibly scratchy, so a generated-vs-real difference is uninterpretable: it could
be the tokenizer. Arm B is the same real clips encoded and decoded through the
shipped codec, and every claim here is generated-against-B, not
generated-against-raw. B-against-A is reported too, as the check that the
instrument is not simply reading the codec.

MEASURED ON BURST FRAMES ONLY, AND WITHOUT c0. Two confounds this project has
already paid for. Generated clips carry fewer call units than real ones (0024:
1.37 against 3.37), so any statistic over whole clips is partly a density
statistic — restricting to frames above the 12 dB burst floor removes it.  And
level is a cue (0022 had to peak-normalise four arms before scoring), so the
MFCC's c0 is dropped and every vector is unit-normalised; what is left is timbre
shape alone.

Distances are cosine, so all four numbers below live on one scale and can be
read against each other:

    frame-to-frame   mean distance between CONSECUTIVE burst frames of a clip
    within-clip      mean distance from a clip's burst frames to its own centroid
    between-clip     spread of clip centroids around the arm's centroid
    within/between   how much of an arm's variety is inside its clips

Bootstrap 95% CIs on everything, resampling clips. Reads cached clips only — no
GPU for arms A and C, one short encode pass for B.
"""

import collections
import json
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crowgpt" / "src"))

from crowgpt.segment import Segmenter  # noqa: E402

SR = 24000
HOP = 256
N_MFCC = 13
MIN_BURST_FRAMES = 6
HERE = Path(__file__).resolve().parent
CLIPS = ROOT / "crowgpt" / "results" / "clips"
SEG = Segmenter()


def burst_mask(y):
    """Frames above the segmenter's own 12 dB floor, on its frame grid."""
    db, _ = SEG.envelope(y, SR)
    return db > np.percentile(db, SEG.floor_pctl) + SEG.burst_db


def timbre(y):
    """Unit-normalised MFCC 1..12 on burst frames, or None if too few."""
    mfcc = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=N_MFCC, n_fft=512, hop_length=HOP)[1:]
    hot = burst_mask(y)
    n = min(mfcc.shape[1], hot.size)
    mfcc, hot = mfcc[:, :n], hot[:n]
    if hot.sum() < MIN_BURST_FRAMES:
        return None
    v = mfcc[:, hot].T
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def unit(v):
    return v / np.linalg.norm(v)


def spread(centroids):
    """Mean cosine distance of unit vectors to their own centroid."""
    return float(np.mean(1 - centroids @ unit(centroids.mean(0))))


def per_clip(vectors):
    """frame-to-frame and within-clip distance, one value per clip."""
    jump = np.array([float(np.mean(1 - np.sum(v[1:] * v[:-1], axis=1))) for v in vectors])
    within = np.array([float(np.mean(1 - v @ unit(v.mean(0)))) for v in vectors])
    return jump, within


def boot_mean_diff(a, b, rng, n=10000):
    d = [rng.choice(a, a.size).mean() - rng.choice(b, b.size).mean() for _ in range(n)]
    return np.percentile(d, [2.5, 97.5])


def boot_spread_diff(A, B, rng, n=10000):
    d = [spread(A[rng.integers(0, len(A), len(A))]) - spread(B[rng.integers(0, len(B), len(B))])
         for _ in range(n)]
    return np.percentile(d, [2.5, 97.5])


def codec_arm(meta, clips):
    """Arm B: the same real clips through the shipped tokenizer."""
    import torch

    from crowgpt import gpu

    gpu.claim()
    from crowgpt.codec import Codec

    codec = Codec(bandwidth=6.0)
    out = {}
    for i, c in enumerate(meta):
        if c["arm"] != "A_real":
            continue
        codes = codec.encode(clips[str(i)].astype(np.float32))
        out[i] = np.squeeze(codec.decode(torch.from_numpy(np.asarray(codes)))).astype(np.float64)
    return out


def arms():
    meta = json.loads((CLIPS.with_suffix(".json")).read_text())
    clips = np.load(CLIPS.with_suffix(".npz"))
    roundtrip = codec_arm(meta, clips)
    out = collections.defaultdict(list)
    for i, c in enumerate(meta):
        v = timbre(clips[str(i)].astype(np.float64))
        if v is not None:
            out[c["arm"]].append(v)
        if i in roundtrip:
            v = timbre(roundtrip[i])
            if v is not None:
                out["B_codec"].append(v)
    return out


def channel_scale(rng, species="american-crow", min_bouts=8, n_recordings=60):
    """Question 3: real within-recording against real between-recording spread.

    The scale the other two numbers are read against. If the microphone moves
    timbre further than anything inside one microphone does, then the corpus's
    dominant axis of timbre is the channel, and a model with no token for it is
    averaging over that axis every time it samples.
    """
    bouts = ROOT / "data" / "crowgpt" / "bouts"
    rows = collections.defaultdict(list)
    with open(bouts / "index.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            if row["species"] == species:
                rows[row["recording_id"]].append(row)

    eligible = [k for k, v in rows.items() if len(v) >= min_bouts]
    chosen = rng.choice(eligible, min(n_recordings, len(eligible)), replace=False)
    shard = np.memmap(bouts / f"{species}.i16", dtype=np.int16, mode="r")

    within, centroids = [], []
    for rid in chosen:
        got = []
        for row in rows[rid][:min_bouts]:
            start = row["sample_offset"]
            y = shard[start:start + row["n_samples"]].astype(np.float64) / 32768.0
            v = timbre(y) if y.size >= SR * 0.3 else None
            if v is not None:
                got.append(unit(v.mean(0)))
        if len(got) >= 5:
            got = np.vstack(got)
            within.append(spread(got))
            centroids.append(unit(got.mean(0)))
    return {
        "recordings": len(within),
        "within_recording": float(np.mean(within)),
        "within_recording_median": float(np.median(within)),
        "between_recordings": spread(np.vstack(centroids)),
    }


def main():
    rng = np.random.default_rng(0)
    by_arm = arms()
    order = ["A_real", "B_codec", "C_generated"]

    stats, centroids = {}, {}
    for arm in order:
        jump, within = per_clip(by_arm[arm])
        centroids[arm] = np.vstack([unit(v.mean(0)) for v in by_arm[arm]])
        stats[arm] = {
            "n": len(by_arm[arm]),
            "frame_to_frame": float(jump.mean()),
            "within_clip": float(within.mean()),
            "between_clip": spread(centroids[arm]),
            "_jump": jump,
            "_within": within,
        }
        s = stats[arm]
        print(f"{arm:14s} n={s['n']:3d}  frame-to-frame {s['frame_to_frame']:.4f}  "
              f"within-clip {s['within_clip']:.4f}  between-clip {s['between_clip']:.4f}  "
              f"w/b {s['within_clip'] / s['between_clip']:.2f}")

    print()
    pairs = [("B_codec", "A_real"), ("C_generated", "B_codec"), ("C_generated", "A_real")]
    comparisons = {}
    for a, b in pairs:
        row = {}
        for key, label in (("_jump", "frame_to_frame"), ("_within", "within_clip")):
            lo, hi = boot_mean_diff(stats[a][key], stats[b][key], rng)
            row[label] = {"diff": float(stats[a][key].mean() - stats[b][key].mean()),
                          "ci": [float(lo), float(hi)], "resolved": bool(lo > 0 or hi < 0)}
        lo, hi = boot_spread_diff(centroids[a], centroids[b], rng)
        row["between_clip"] = {"diff": stats[a]["between_clip"] - stats[b]["between_clip"],
                               "ci": [float(lo), float(hi)], "resolved": bool(lo > 0 or hi < 0)}
        comparisons[f"{a} - {b}"] = row
        for label, r in row.items():
            mark = "RESOLVED" if r["resolved"] else ""
            print(f"{a:12s} - {b:12s} {label:15s} {r['diff']:+.4f} "
                  f"95% CI [{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}] {mark}")

    print()
    scale = channel_scale(rng)
    print(f"real american-crow, {scale['recordings']} recordings, up to 8 bouts each")
    print(f"  WITHIN one recording  {scale['within_recording']:.4f} "
          f"(median {scale['within_recording_median']:.4f})")
    print(f"  BETWEEN recordings    {scale['between_recordings']:.4f}")
    print(f"  ratio                 {scale['between_recordings'] / scale['within_recording']:.1f}x")

    (HERE / "results.json").write_text(json.dumps({
        "arms": {a: {k: v for k, v in s.items() if not k.startswith("_")}
                 for a, s in stats.items()},
        "comparisons": comparisons,
        "channel_scale": scale,
    }, indent=2))
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
