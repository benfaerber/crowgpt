"""What separates the draw that screams from five that don't?

0057 ended with Ben's decomposition — "codec makes it scratchy, generated
makes it scream" — and one tagged exemplar: model-fair-k8 seed 4 (row 11 of
compare-scream-source.html), called "a scream. That is a clear example"
against five same-model, same-page draws that were not (seeds 2, 3, 5, 6, 7).

0046 is the precedent and the method: "modem" was a described defect until the
instruments found its token signature (a stuck coarse codebook). This asks the
same question of "scream" with every cheap instrument the project has
validated, over the six clips Ben has already tagged by ear:

    churn0        stage-0 codebook churn (0046; real audio 0.868)
    longest run   longest identical stage-0 token run, seconds — the stuck-
                  codebook statistic itself
    units         0013's burst detector at its validated 12 dB (real bouts:
                  mean 3.37 units, 0024)
    duty          fraction of frames in-burst — a scream is sustained where a
                  caw is pulsed, so this and units/sec are the shape axes
    crest         peak-over-RMS dB — sustained voiced sound is low-crest
    hf share      energy above 4 kHz over total — roughness lives high

n = 6, one tagged positive. Nothing here is a finding at power; the job is to
nominate a signature worth testing properly. If one statistic separates seed 4
cleanly, the follow-up is tag-then-correlate over ~30 fresh draws — Ben tags
scream/no-scream blind, the statistic predicts it or dies. If nothing
separates, that is worth writing down too: the scream would be the first
defect with no signature in the token stream, which points at the decode.

Seeds regenerate bit-exactly (Sampler seeds its own generator), so these are
the same six clips Ben heard; durations are cross-checked against 0057's
manifest to prove it.
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

from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter

OUT = Path(__file__).resolve().parent
MANIFEST_0057 = OUT.parent / "0057-does-the-round-trip-scream" / "manifest.json"

MODEL = HERE / "results" / "model-fair-k8"
SPECIES = "american-crow"
SR = 24000
FRAME_SECONDS = 1 / 75  # EnCodec frame rate

#: Ben's tags from 0057, verbatim enough to re-read later.
TAGS = {
    2: "no clear scream — C+, 'matches shape, coarse'",
    3: "no clear scream — D+",
    4: "SCREAM — 'That is a scream. That is a clear example.' (D+)",
    5: "no clear scream — D+",
    6: "no clear scream — C- to C+",
    7: "no clear scream — D+",
}

#: References from prior experiments, for scale.
REAL_CHURN0 = 0.868   # 0046
REAL_UNITS = 3.37     # 0024, mean units per real bout


def longest_run(codes):
    """Longest run of one repeated token, in frames."""
    if codes.size == 0:
        return 0
    changes = np.flatnonzero(np.diff(codes) != 0)
    edges = np.concatenate(([0], changes + 1, [codes.size]))
    return int(np.max(np.diff(edges)))


def describe(audio, grid, segmenter):
    duration = audio.size / SR
    db, fps = segmenter.envelope(audio, SR)
    floor = np.percentile(db, segmenter.floor_pctl)
    units = segmenter.bursts(db, fps, floor)
    hot = sum(e - s for s, e in units)
    peak = float(np.max(np.abs(audio)) + 1e-12)
    rms = float(np.sqrt(np.mean(audio**2)) + 1e-12)
    spectrum = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(audio.size, 1 / SR)
    total = float(np.sum(spectrum**2) + 1e-12)
    stage0 = grid[0]
    return {
        "seconds": round(duration, 2),
        "churn0": round(float((stage0[1:] != stage0[:-1]).mean()), 3),
        "longest_run_s": round(longest_run(stage0) * FRAME_SECONDS, 3),
        "units": len(units),
        "units_per_sec": round(len(units) / duration, 2),
        "duty_cycle": round(hot / db.size, 3),
        "crest_db": round(20 * np.log10(peak / rms), 1),
        "hf_share": round(float(np.sum(spectrum[freqs > 4000] ** 2)) / total, 3),
    }


def main():
    manifest = json.loads(MANIFEST_0057.read_text())
    expected = {row["seed"]: row["seconds"] for row in manifest["generated"]}

    sampler = Sampler(MODEL / "model.pt", token_dir=None)
    segmenter = Segmenter()

    rows = {}
    for seed in sorted(TAGS):
        flat = sampler.tokens(SPECIES, seed=seed)
        grid = sampler.codec.unflatten(flat)
        audio = np.asarray(sampler.codec.decode(torch.from_numpy(grid))[0],
                           dtype=np.float32)
        row = describe(audio, grid, segmenter)
        row["tag"] = TAGS[seed]
        row["matches_0057"] = abs(row["seconds"] - expected[seed]) < 0.05
        rows[str(seed)] = row
        print(f"seed {seed}: {json.dumps(row)}")

    results = {
        "reference": {"real_churn0": REAL_CHURN0, "real_units_per_bout": REAL_UNITS},
        "clips": rows,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
