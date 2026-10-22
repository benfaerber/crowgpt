"""Does it sound like a crow, and did the model just copy one?

BIRDNET IS THE JUDGE because it is the same gate that selected the training
data: the detector that decided which windows were corvid now scores what came
out. Nothing new has to be trained or labelled to run this.

FOUR ARMS, because real-versus-generated on its own conflates two different
failures — a codec that threw the caw away and a model that never learned it.

  A  real held-out bouts, resampled only          upper anchor
  B  arm A round-tripped through the codec        the real ceiling
  C  generated
  D  tokens from each codebook's marginal         lower anchor

The claim "the model learned the distribution" is B versus C. A versus C cannot
separate the model from its tokenizer.

TWO THINGS ABOUT BIRDNET THAT MAKE OR BREAK THIS. It breaks out of its chunking
loop on anything under 1.5 s and returns zero detections without an error, so a
0.4 s bout judged alone reads as rejection when nothing was even analysed. And
it zero-pads between 1.5 and 3.0 s, where digital silence is itself out of
distribution and depresses confidence. So every arm is rendered as exactly 3.0 s
with real ambience from held-out recordings, never zeros, and the location
filter stays off so the species prior cannot differ between arms.
"""

from pathlib import Path

import numpy as np

from crowgpt.codec import SAMPLE_RATE
from crowgpt.segment import ANALYSIS_SR, Segmenter

CLIP_SEC = 3.0
CLIP_SAMPLES = int(CLIP_SEC * SAMPLE_RATE)
AMBIENCE_RMS = 0.01
NGRAM_FRAMES = (8, 16, 32)


class Ambience:
    """Quiet stretches from held-out recordings, to sit generated calls in."""

    def __init__(self, recordings, wanted=24, seed=0):
        self.rng = np.random.default_rng(seed)
        self.clips = self._collect(recordings, wanted)

    def _collect(self, recordings, wanted):
        import librosa
        from scipy.signal import resample_poly

        segmenter = Segmenter()
        clips = []
        for rec in recordings:
            if len(clips) >= wanted:
                break
            try:
                y, sr = librosa.load(str(rec.path), sr=ANALYSIS_SR, mono=True)
            except Exception:
                continue
            db, fps = segmenter.envelope(y, sr)
            floor = float(np.percentile(db, segmenter.floor_pctl))
            quiet = db <= floor + 3.0
            need = int(CLIP_SEC * fps)
            for start in range(0, max(1, quiet.size - need), need):
                if quiet[start : start + need].all():
                    chunk = y[int(start / fps * sr) : int((start / fps + CLIP_SEC) * sr)]
                    if chunk.size < int(CLIP_SEC * sr):
                        continue
                    clips.append(resample_poly(chunk, SAMPLE_RATE, sr)[:CLIP_SAMPLES].astype(np.float32))
                    break
        if not clips:
            clips = [np.zeros(CLIP_SAMPLES, dtype=np.float32)]
        return clips

    def clip(self):
        chosen = self.clips[self.rng.integers(len(self.clips))].copy()
        if chosen.size < CLIP_SAMPLES:
            chosen = np.pad(chosen, (0, CLIP_SAMPLES - chosen.size))
        rms = float(np.sqrt(np.mean(chosen**2)))
        if rms > 0:
            chosen = chosen / rms * AMBIENCE_RMS
        return chosen

    def place(self, bout):
        """Drop a bout into 3 s of ambience at a random offset."""
        canvas = self.clip()
        bout = np.asarray(bout, dtype=np.float32)[:CLIP_SAMPLES]
        if bout.size == 0:
            return canvas
        start = int(self.rng.integers(0, max(1, CLIP_SAMPLES - bout.size + 1)))
        canvas[start : start + bout.size] += bout
        peak = float(np.max(np.abs(canvas)))
        return canvas / peak * 0.89 if peak > 0 else canvas


class BirdNetJudge:
    """Corvid confidence, scored in a subprocess that has no torch in it.

    This used to import birdnetlib here. That is what made torch unable to see
    the GPU and cost a night of training at 1/240th speed, so it now goes
    through crowgpt.birdnet and the boundary is enforced from both sides.

    Scoring is batched because each call pays interpreter and model startup.
    `confidence` on one clip still works and is the slow way to do it.
    """

    def __init__(self, birdnet=None):
        from crowgpt.birdnet import BirdNet

        self.birdnet = birdnet or BirdNet(sample_rate=SAMPLE_RATE)
        self.crow_min = 0.25  # replaced by the worker's own value on first call

    def confidences(self, clips):
        """Scores for a list of clips, in order. None where a clip was empty."""
        values, crow_min = self.birdnet.confidence(clips)
        self.crow_min = crow_min
        return values

    def confidence(self, samples, sr=SAMPLE_RATE):
        value = self.confidences([samples])[0]
        return (value if value is not None else 0.0), None


class NgramIndex:
    """Exact token n-gram overlap against the canonical training set.

    Nearest neighbour in BirdNET's embedding space cannot do this job: that
    space is trained to be invariant to level, EQ, noise and time shift, which
    are exactly the axes a memorised copy varies along, so it saturates. Token
    n-grams are exact, and the tokens already exist.

    The base rate matters as much as the number. Held-out real sequences share
    plenty of n-grams with training data purely because crows sound like crows,
    so the question is never "did any match" but "did the generated audio match
    more often than real audio the model has never seen".
    """

    def __init__(self, n_codebooks, stages=None):
        self.n_codebooks = n_codebooks
        self.stages = stages or n_codebooks
        self.tables = {}

    def _frame_ids(self, flat):
        """One id per frame, from the first `stages` codebooks.

        Using all eight is exact and useless: matching eight consecutive frames
        across eight codebooks means 64 tokens identical in a row, which no two
        independent recordings ever are. Measured, it returns zero for generated
        AND for held-out real audio, so it cannot tell them apart. Restricting
        to the coarse stages — codebook 0 carries the bulk of the spectrum —
        gives the test something it can actually detect.
        """
        usable = (flat.size // self.n_codebooks) * self.n_codebooks
        if usable == 0:
            return np.zeros(0, dtype=np.uint64)
        grid = flat[:usable].reshape(-1, self.n_codebooks)[:, : self.stages].astype(np.uint64)
        weights = (1024 ** np.arange(self.stages)).astype(np.uint64)
        return (grid * weights).sum(axis=1)

    @staticmethod
    def _hash(frame_ids, n):
        if frame_ids.size < n:
            return np.zeros(0, dtype=np.uint64)
        windows = np.lib.stride_tricks.sliding_window_view(frame_ids, n)
        out = np.zeros(windows.shape[0], dtype=np.uint64)
        for column in range(n):
            out = out * np.uint64(1000003) + windows[:, column]
        return out

    def build(self, sequences):
        for n in NGRAM_FRAMES:
            chunks = [self._hash(self._frame_ids(s), n) for s in sequences]
            chunks = [c for c in chunks if c.size]
            self.tables[n] = np.unique(np.concatenate(chunks)) if chunks else np.zeros(0, dtype=np.uint64)
        return {n: int(t.size) for n, t in self.tables.items()}

    def hit_rate(self, sequences):
        """Fraction of sequences containing at least one training n-gram.

        The lookup is searchsorted rather than np.isin because the table holds
        millions of hashes and np.unique already returned it sorted; np.isin
        would re-sort the whole thing once per sequence.
        """
        out = {}
        for n, table in self.tables.items():
            hits, eligible = 0, 0
            for sequence in sequences:
                hashed = self._hash(self._frame_ids(sequence), n)
                if hashed.size == 0:
                    continue
                eligible += 1
                if table.size:
                    where = np.searchsorted(table, hashed)
                    where[where >= table.size] = table.size - 1
                    if (table[where] == hashed).any():
                        hits += 1
            out[f"{n}_frames"] = round(hits / eligible, 4) if eligible else None
        return out


class Judgement:
    """Builds the four arms and scores them."""

    def __init__(self, sampler, token_dir, bout_root, per_species=12, seed=0,
                 max_frames=225):
        from crowgpt.tokens import BoutStore, TokenDataset

        self.sampler = sampler
        self.token_dir = Path(token_dir)
        self.store = BoutStore(bout_root)
        self.test_set = TokenDataset(token_dir, "test")
        self.train_set = TokenDataset(token_dir, "train")
        self.per_species = per_species
        # 225 frames is a full 3-second bout. A smoke test lowers it because an
        # untrained model never emits EOS early, so every bout runs to the cap
        # and generation dominates the run.
        self.max_frames = max_frames
        self.rng = np.random.default_rng(seed)
        self.judge = BirdNetJudge()

    def _held_out_bouts(self):
        """Real test-split bouts, matched to the index they came from."""
        by_species = {}
        wanted = {row["group_key"] for row in self.test_set.records}
        for row in self.store.index:
            if row["group_key"] not in wanted:
                continue
            by_species.setdefault(row["species"], []).append(row)
        picked = {}
        for slug, rows in by_species.items():
            self.rng.shuffle(rows)
            picked[slug] = rows[: self.per_species]
        return picked

    def run(self, ambience_recordings):
        from crowgpt.codec import normalise

        ambience = Ambience(ambience_recordings)
        held_out = self._held_out_bouts()
        arms = {name: [] for name in ("A_real", "B_real_codec", "C_generated", "D_unigram")}
        clips = []

        for slug, rows in sorted(held_out.items()):
            for row in rows:
                real = normalise(self.store.audio(row))
                arms["A_real"].append((slug, ambience.place(real)))
                arms["B_real_codec"].append(
                    (slug, ambience.place(self.sampler.codec.roundtrip(real)[0][: real.size]))
                )
            for i in range(len(rows)):
                generated = self.sampler.audio(slug, seed=int(self.rng.integers(2**31)),
                                               max_frames=self.max_frames)
                arms["C_generated"].append((slug, ambience.place(generated)))
                frames = max(8, generated.size // 320)
                arms["D_unigram"].append(
                    (slug, ambience.place(self.sampler.unigram(frames, seed=int(self.rng.integers(2**31)))))
                )

        results = {}
        for name, entries in arms.items():
            scores, correct = [], 0
            batch = self.judge.confidences([samples for _, samples in entries])
            for (slug, samples), confidence in zip(entries, batch):
                confidence = confidence if confidence is not None else 0.0
                scores.append(confidence)
                if name in ("A_real", "C_generated"):
                    clips.append({"arm": name, "species": slug, "audio": samples,
                                  "conf": round(confidence, 3), "called": None})
            scores = np.array(scores)
            results[name] = {
                "n": len(entries),
                "mean_conf": round(float(scores.mean()), 4) if scores.size else None,
                "median_conf": round(float(np.median(scores)), 4) if scores.size else None,
                "detected_rate": round(float((scores >= self.judge.crow_min).mean()), 4) if scores.size else None,
                "species_correct_rate": round(correct / len(entries), 4) if entries else None,
            }

        results["memorisation"] = self._memorisation()
        return results, clips

    def _memorisation(self, generated=None):
        """Two resolutions, because the exact one has no power at all.

        The number only means something against the held-out base rate: real
        audio the model has never seen still shares n-grams with training data,
        simply because crows sound like crows. Generated much above that rate is
        copying; generated at or below it is not.
        """
        n_codebooks = self.sampler.vocabulary.n_codebooks
        canonical = [
            self.train_set.sequence(i)[2:-1]
            for i in range(len(self.train_set))
            if self.train_set.records[i]["canonical"]
        ]
        held_out = [self.test_set.sequence(i)[2:-1] for i in range(len(self.test_set))]
        if generated is None:
            generated = [
                self.sampler.tokens(slug, seed=int(self.rng.integers(2**31)),
                                    max_frames=self.max_frames)
                for slug in self.sampler.species
                for _ in range(self.per_species)
            ]

        out = {"canonical_train_sequences": len(canonical), "generated_sequences": len(generated)}
        for label, stages in (("all_codebooks", n_codebooks), ("codebook_0", 1)):
            index = NgramIndex(n_codebooks, stages=stages)
            out[label] = {
                "index_ngrams": index.build(canonical),
                "held_out_real": index.hit_rate(held_out),
                "generated": index.hit_rate(generated),
            }
        return out
