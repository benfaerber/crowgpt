"""Can the Poe family's crows be told apart by voice?

"Crow A cawed at 3 s, Crow B at 8 s" needs a per-call identity, and this corpus
has none: no crows table, no caller column on labels, and a recordist who says he
cannot attribute a call to a bird even listening back. The five names exist —
Thrasher, Ripjaw, Killer, Shredder and Edgar — and none of them is attached to a
single second of audio. So clustering cannot be validated, and an experiment that
clusters and names the clusters after birds would be unfalsifiable in exactly the
way 0016 was.

This is built to bound the answer rather than find one, on four recordings chosen
for what they rule out:

  87 vs 88  THE SAME BIRD, TWICE. Recorded 44 seconds apart on the same phone at
            the same distance band, both "a single crow on top of a tall
            building", 87 named for Edgar — and 9.3 dB of band SNR apart. If the
            features separate two recordings of one bird more cleanly than they
            find structure inside a five-bird recording, the experiment is over
            and the answer is one number. Success here is failure.
  88        ONE bird. The floor: whatever apparent cluster structure appears here
            was produced with no individuals to find, so it bounds every other
            number.
  104       Fledglings (begging) and an adult (call), human-labelled — the only
            real ground truth in the corpus, and the easiest possible version of
            the question, since an age class is not an individual.
  113       Five birds, 49 units, one call type, so call type cannot be what any
            structure is made of.

WHAT IS DELIBERATELY NOT A FEATURE: anything that encodes loudness. 0016 showed
range dominates this corpus, and birds in a flock stand at different distances,
so log-energy is a position sensor. That means no RMS term and **no MFCC 0**,
which is log energy wearing a cepstral hat and is the quiet way this experiment
would have fooled itself. Loudness is kept, but only on the other side of the
ledger, as a confound the clusters get scored against.

Classical features only, deliberately. BirdNET is documented in this repo as the
wrong tool (crowgpt/judge.py: "that space is trained to be invariant to level,
EQ, noise and time shift"), and if the one-bird floor already reaches the
five-bird recording then no embedding changes the conclusion.

Run from the repo root:
    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0017-can-we-tell-the-crows-apart/run.py
"""

import json
import sqlite3
import sys
from pathlib import Path

import librosa
import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.model_selection import LeaveOneOut, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.segment import ANALYSIS_SR, BAND, Segmenter  # noqa: E402
from experiments.lib.media import audio_for, field_db  # noqa: E402

SEED = 20260731
PERMUTATIONS = 200
SUBSAMPLES = 2000
MIN_UNITS = 6
MIN_PER_CLASS = 4
SAME_BIRD = (87, 88)
CONTROL = 88
CEILING = 104
MAIN = 113


class Unit:
    """One detected call. Its features carry no loudness term, on purpose."""

    def __init__(self, samples, rate, start_sec, end_sec, bout, call_type):
        self.start_sec = start_sec
        self.duration = end_sec - start_sec
        self.bout = bout
        self.call_type = call_type
        # Kept for the confound battery, never for the feature vector.
        self.amp_db = float(20 * np.log10(np.sqrt(np.mean(samples ** 2)) + 1e-12))

        spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
        freqs = np.fft.rfftfreq(len(samples), 1 / rate)
        band = (freqs >= BAND[0]) & (freqs <= BAND[1])
        power = spectrum[band] ** 2
        total = power.sum() or 1e-12
        self.peak_hz = float(freqs[band][np.argmax(power)])
        self.centroid_hz = float((freqs[band] * power).sum() / total)
        positive = power[power > 0]
        self.flatness = float(np.exp(np.log(positive).mean()) / positive.mean()) \
            if positive.size else 0.0
        self.high_fraction = float(power[freqs[band] >= 2000].sum() / total)

        # MFCCs describe the spectral envelope, which is where a vocal tract
        # leaves its mark. Coefficient 0 is dropped: it is log energy, and
        # keeping it would put range straight into the feature matrix.
        mfcc = librosa.feature.mfcc(y=samples, sr=rate, n_mfcc=13, n_fft=512,
                                    hop_length=128, n_mels=26, fmin=BAND[0],
                                    fmax=BAND[1])[1:]
        self.mfcc_mean = mfcc.mean(axis=1)
        self.mfcc_std = mfcc.std(axis=1)

    @property
    def vector(self):
        return np.concatenate([
            [self.duration, self.peak_hz, self.centroid_hz,
             self.flatness, self.high_fraction],
            self.mfcc_mean, self.mfcc_std])


class Recording:
    def __init__(self, capture_id, name, birds, distance, snr, units):
        self.id = capture_id
        self.name = name
        self.birds = birds
        self.distance = distance
        self.snr = snr
        self.units = units

    def __len__(self):
        return len(self.units)

    @property
    def matrix(self):
        return StandardScaler().fit_transform(
            np.array([u.vector for u in self.units]))

    def cluster(self, k):
        return KMeans(n_clusters=k, n_init=10, random_state=SEED).fit_predict(self.matrix)

    def silhouette(self, k):
        if len(self) <= k:
            return float("nan")
        labels = self.cluster(k)
        return float(silhouette_score(self.matrix, labels)) if len(set(labels)) > 1 \
            else float("nan")


def eta_squared(values, labels):
    """Share of a continuous variable's variance explained by the clustering."""
    values = np.asarray(values, dtype=float)
    grand = values.mean()
    total = ((values - grand) ** 2).sum()
    if total <= 0:
        return float("nan")
    between = sum(len(values[labels == c]) * (values[labels == c].mean() - grand) ** 2
                  for c in set(labels))
    return float(between / total)


class Corpus:
    def __init__(self):
        self.conn = sqlite3.connect(f"file:{field_db()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.segmenter = Segmenter()

    def assert_no_ground_truth(self):
        """Fail loudly the day a caller field lands, rather than quietly measuring
        the wrong thing. This experiment is only correct while identity is absent."""
        tables = {r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(labels)")}
        offenders = ({"crows", "birds", "individuals"} & tables) | \
                    ({"caller", "caller_id", "crow_id", "bird_id"} & columns)
        if offenders:
            raise SystemExit(
                f"individual ground truth now exists ({sorted(offenders)}) — "
                "this experiment measures the absence of it and must be rewritten")
        return len(tables), len(columns)

    def _units_from(self, samples, rate, offset, call_type, bout_prefix):
        units = []
        bouts, found = self.segmenter.segment(samples, rate)
        for a, b in found:
            piece = samples[int(a * rate):int(b * rate)]
            if len(piece) < 256:
                continue
            inside = next((i for i, (lo, hi) in enumerate(bouts) if lo <= a < hi), -1)
            units.append(Unit(piece, rate, offset + a, offset + b,
                              f"{bout_prefix}_{inside}", call_type))
        return units

    def load(self, capture_id, whole_file=False):
        row = self.conn.execute(
            "SELECT c.name, c.adult_count, c.juvenile_count, c.unaged_count, "
            "       c.distance_band, q.band_snr_db "
            "FROM captures c LEFT JOIN capture_quality q ON q.capture_id = c.id "
            "WHERE c.id = ?", (capture_id,)).fetchone()
        samples, rate = librosa.load(audio_for(capture_id), sr=ANALYSIS_SR, mono=True)
        if whole_file:
            units = self._units_from(samples, rate, 0.0, "unlabelled", "w")
        else:
            units = []
            spans = self.conn.execute(
                "SELECT start_sec, end_sec, call_type FROM labels "
                "WHERE capture_id = ? AND label_source = 'human' "
                "AND call_type NOT IN ('not_a_crow', 'unsure') ORDER BY start_sec",
                (capture_id,)).fetchall()
            for i, span in enumerate(spans):
                clip = samples[int(span["start_sec"] * rate):int(span["end_sec"] * rate)]
                if len(clip) >= rate // 2:
                    units += self._units_from(clip, rate, span["start_sec"],
                                              span["call_type"], str(i))
        birds = sum(row[c] or 0 for c in
                    ("adult_count", "juvenile_count", "unaged_count"))
        return Recording(capture_id, row["name"], birds, row["distance_band"],
                         row["band_snr_db"], units)


class Report:
    def __init__(self, corpus, recordings):
        self.corpus = corpus
        self.by_id = recordings
        self.result = {}
        self.rng = np.random.default_rng(SEED)

    def _inventory(self, tables, columns):
        print("=" * 86)
        print("A. WHAT GROUND TRUTH EXISTS")
        print("=" * 86)
        print(f"  {tables} tables, {columns} columns on `labels`, and no per-bird")
        print("  record in any of them. The Poe family has five names — Thrasher,")
        print("  Ripjaw, Killer, Shredder, Edgar — and zero of them is attached to")
        print("  a single call. That absence is what this experiment measures.")
        print()
        print(f"  {'cap':>4} {'birds':>5} {'units':>5} {'bouts':>5} {'snr':>5} {'dist':>9}  name")
        for r in sorted(self.by_id.values(), key=lambda r: r.id):
            snr = f"{r.snr:.1f}" if r.snr else "-"
            print(f"  {r.id:>4} {r.birds:>5} {len(r):>5} "
                  f"{len({u.bout for u in r.units}):>5} {snr:>5} "
                  f"{str(r.distance or '-'):>9}  {r.name}")
        self.result["units"] = {r.id: len(r) for r in self.by_id.values()}

    def _same_bird(self):
        print()
        print("=" * 86)
        print("B. THE SAME BIRD, TWICE — captures 87 and 88, 44 seconds apart")
        print("=" * 86)
        a, b = (self.by_id.get(i) for i in SAME_BIRD)
        if not a or not b or min(len(a), len(b)) < MIN_PER_CLASS:
            print(f"  Gated: {len(a) if a else 0} and {len(b) if b else 0} units.")
            print("  Worth noting either way — the 9 dB quieter recording of the same")
            print("  bird yielding fewer units is 0016's finding restated.")
            self.result["same_bird"] = {"gated": True,
                                        "units": [len(a) if a else 0, len(b) if b else 0]}
            return
        X = StandardScaler().fit_transform(
            np.array([u.vector for u in a.units + b.units]))
        y = np.array([0] * len(a) + [1] * len(b))
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
        real = float(cross_val_score(model, X, y, cv=LeaveOneOut()).mean())
        null = [float(cross_val_score(model, X, self.rng.permutation(y),
                                      cv=LeaveOneOut()).mean())
                for _ in range(30)]
        p = float((np.array(null) >= real).mean())
        print(f"  Assumed same bird: both 'a single crow on top of a tall building',")
        print(f"  same phone, same distance band, 44 s apart, 87 named for Edgar.")
        print(f"  SNR {a.snr:.1f} dB vs {b.snr:.1f} dB — a {abs(a.snr-b.snr):.1f} dB gap.")
        print()
        print(f"  leave-one-out accuracy telling the two recordings apart: {real:.3f}")
        print(f"  chance (shuffled labels): {np.mean(null):.3f} ± {np.std(null):.3f}   p = {p:.3f}")
        self.result["same_bird"] = {"accuracy": real, "chance": float(np.mean(null)),
                                    "p": p, "snr_gap": abs(a.snr - b.snr)}
        print()
        if real > 0.8 and p < 0.05:
            print("  HIGH, AND THAT IS A FAILURE. The features separate one bird recorded")
            print("  twice better than any method could be trusted to separate five birds")
            print("  recorded once. Whatever they encode, it changes between recordings of")
            print("  the same animal — which is what a voice must not do.")
        else:
            print("  Not separable, which is the good outcome: the features do not simply")
            print("  encode which recording a call came from.")

    def _floor(self):
        print()
        print("=" * 86)
        print(f"C. THE FLOOR — capture {CONTROL} is one crow, so its structure is spurious")
        print("=" * 86)
        control, main = self.by_id.get(CONTROL), self.by_id.get(MAIN)
        if not control or len(control) < MIN_UNITS:
            print(f"  Capture {CONTROL} has {len(control) if control else 0} units — too few.")
            return
        n = len(control)
        print(f"  Capture {MAIN} is subsampled to n={n} to match, because silhouette")
        print("  climbs with sample size even on structureless data.")
        print()
        print(f"  {'k':>3}  {'cap 88 (1 bird)':>16}  {'cap 113 (5 birds), n=6':>34}")
        floor = {}
        for k in (2, 3):
            here = control.silhouette(k)
            draws = []
            for _ in range(SUBSAMPLES):
                pick = self.rng.choice(len(main), size=n, replace=False)
                subset = main.matrix[pick]
                labels = KMeans(n_clusters=k, n_init=10,
                                random_state=SEED).fit_predict(subset)
                if len(set(labels)) > 1:
                    draws.append(silhouette_score(subset, labels))
            lo, med, hi = np.percentile(draws, [5, 50, 95])
            beats = lo > here
            print(f"  {k:>3}  {here:>16.3f}  {med:>10.3f}  [{lo:.3f}, {hi:.3f}]  "
                  f"{'ABOVE the floor' if beats else 'inside the floor'}")
            floor[k] = {"control": here, "main_median": float(med), "main_p5": float(lo),
                        "main_p95": float(hi), "separates": bool(beats)}
        self.result["floor"] = floor

    def _ceiling(self):
        print()
        print("=" * 86)
        print(f"D. THE CEILING — capture {CEILING}, fledgling (begging) vs adult (call)")
        print("=" * 86)
        rec = self.by_id.get(CEILING)
        truth = ["juvenile" if u.call_type == "begging" else "adult" for u in rec.units]
        counts = {c: truth.count(c) for c in set(truth)}
        print(f"  units by age class: {counts}")
        thin = [c for c, n in counts.items() if n < MIN_PER_CLASS]
        if len(counts) < 2 or thin:
            print()
            print("  GATED, and the reason is the finding. The adult's only call sits in")
            print("  one 42-51 s span and the segmenter finds nothing in it at 12 dB: the")
            print("  adult is too far off to clear the threshold that the begging")
            print("  fledglings clear easily.")
            print()
            print("  So the corpus cannot support the EASIEST version of this question —")
            print("  telling a begging fledgling from an adult caw, with time-in-recording")
            print("  confounded helpfully in its favour. Individual identity is not merely")
            print("  unproven here, it is untestable.")
            self.result["ceiling"] = {"gated": True, "counts": counts}
            return
        labels = rec.cluster(2)
        real = adjusted_rand_score(truth, labels)
        null = [adjusted_rand_score(self.rng.permutation(truth), labels)
                for _ in range(PERMUTATIONS)]
        p = float((np.array(null) >= real).mean())
        print(f"  ARI(clusters, age class) = {real:+.3f}   p = {p:.3f}")
        self.result["ceiling"] = {"ari": real, "p": p, "counts": counts}

    def _confounds(self):
        print()
        print("=" * 86)
        print("E. WHAT THE CLUSTERS ACTUALLY TRACK")
        print("=" * 86)
        print("  ARI 1.0 = the clusters ARE that variable; eta^2 1.0 = the same for a")
        print("  continuous one. 0006: two caws from one bout are nearly the same data")
        print("  point, so a high bout score means bouts were found, not birds.")
        print()
        print(f"  {'cap':>4} {'k':>3} {'bout ARI':>9} {'loudness n2':>12} "
              f"{'time n2':>9} {'type ARI':>9}")
        table = {}
        for r in sorted(self.by_id.values(), key=lambda r: r.id):
            k = max(2, min(r.birds or 2, len(r) // 3))
            if len(r) < MIN_UNITS or len(r) <= k:
                continue
            labels = r.cluster(k)
            types = [u.call_type for u in r.units]
            scores = {
                "bout": adjusted_rand_score([u.bout for u in r.units], labels),
                "loudness": eta_squared([u.amp_db for u in r.units], labels),
                "time": eta_squared([u.start_sec for u in r.units], labels),
                "call_type": adjusted_rand_score(types, labels)
                if len(set(types)) > 1 else float("nan"),
            }
            table[r.id] = {"k": k, **scores}
            print(f"  {r.id:>4} {k:>3} {scores['bout']:>9.3f} {scores['loudness']:>12.3f} "
                  f"{scores['time']:>9.3f} {scores['call_type']:>9.3f}")
        self.result["confounds"] = table
        main = table.get(MAIN)
        if main:
            worst = max(("loudness", main["loudness"]), ("time", main["time"]),
                        ("bout", main["bout"]), key=lambda kv: kv[1])
            print()
            print(f"  Capture {MAIN}'s clusters are best explained by {worst[0]} "
                  f"({worst[1]:.3f}).")
            if worst[0] in ("loudness", "time"):
                print("  Both are position: loudness is how far the bird was, time is where")
                print("  it had moved to. In a static flock position partly IS identity —")
                print("  but it is not voice, and it stops working the moment they move.")

    def run(self, tables, columns):
        self._inventory(tables, columns)
        self._same_bird()
        self._floor()
        self._ceiling()
        self._confounds()
        return self.result


def main():
    print(f"reading {field_db()}\n")
    corpus = Corpus()
    tables, columns = corpus.assert_no_ground_truth()
    recordings = {}
    for capture_id in (87, 88, 100, 103, 104, 113, 114):
        recordings[capture_id] = corpus.load(capture_id, whole_file=(capture_id == 87))
    result = Report(corpus, recordings).run(tables, columns)
    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
