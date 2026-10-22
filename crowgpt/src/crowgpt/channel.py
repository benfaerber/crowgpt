"""Giving the microphone a name, so the model does not have to average over it.

0042 measured the thing this module exists for. In this corpus timbre varies
**6.2x more between recordings than within one recording** — a cosine spread of
0.163 against 0.026 — so the single largest axis of variation in the training
data is which microphone, distance, gain and MP3 encoder produced the clip, not
which bird made the sound. The generator conditions on species, call type and
duration and has no token for any of that, across 12,846 recordings averaging
11.7 seconds each. It has to marginalise over all of them every time it samples,
and 0042 measured both halves of what that costs: 23% less timbral variety
across clips than real audio, and a per-frame conditional that moves 17% faster
than it should.

A nuisance variable a model cannot name is one it has to average. Naming it is
the standard fix — it is what a speaker embedding does for multi-speaker TTS —
and it is cheap here because the token goes in the PREFIX: `Batcher` splices it
from the record at training time, so nothing has to be re-encoded.

THE DESCRIPTOR IS BUILT FROM WHAT IS NOT A CALL. This is the whole design. A
recording's mean spectrum is dominated by the caws in it, so clustering on that
would recover call type and species and hand the model a second copy of tokens
it already has. Frames BELOW the segmenter's burst floor are the room: noise
floor, wind, traffic, distant birds, the microphone's own response. That is the
channel, and it is what stays constant across a recording while the bird varies.

0031 IS THE REASON THIS CONDITIONS RATHER THAN SUBTRACTS. A denoiser was tried
on this corpus and erased the crow — 3 of 4 test captures went from a confident
detection to nothing. And 0040 found per-recording CMVN flattens the embedding
space rather than revealing structure under it. The channel is entangled with
the signal and cannot be removed; it can only be given somewhere to live.

BUCKETS, NOT RECORDING IDS. 12,846 ids would be an embedding row per recording
with a median of six bouts behind it — memorisation, not a factor. A few hundred
buckets are estimated from many recordings each, generalise to a recording the
model has never heard, and give sampling something to *choose*: pin one bucket
and every clip comes from one nominal microphone.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from crowgpt.segment import Segmenter

N_MELS = 40
N_FFT = 512
HOP = 256
SR = 24000
DEFAULT_BUCKETS = 256
MIN_QUIET_FRAMES = 8
QUIET_QUANTILE = 0.5


class ChannelDescriber:
    """One vector per recording, describing its room rather than its birds."""

    def __init__(self, sample_rate=SR, n_mels=N_MELS):
        self.sample_rate = sample_rate
        self.n_mels = n_mels
        self.segmenter = Segmenter()
        self._filters = None

    @property
    def filters(self):
        if self._filters is None:
            import librosa

            self._filters = librosa.filters.mel(
                sr=self.sample_rate, n_fft=N_FFT, n_mels=self.n_mels
            )
        return self._filters

    def quiet_spectrum(self, samples):
        """Mean log-mel of the frames that are NOT a call, or None if too few.

        Frames above the segmenter's own 12 dB floor are dropped as calls. When
        a bout is wall-to-wall burst there is no room to measure, so the
        quietest half of its frames stand in — a fallback rather than a
        discard, because a recording made entirely of loud caws still has a
        microphone and still needs a bucket.
        """
        import librosa

        samples = np.asarray(samples, dtype=np.float64)
        if samples.size < N_FFT * 2:
            return None
        power = np.abs(librosa.stft(samples, n_fft=N_FFT, hop_length=HOP)) ** 2
        db, _ = self.segmenter.envelope(samples, self.sample_rate)
        floor = np.percentile(db, self.segmenter.floor_pctl)
        quiet = db <= floor + self.segmenter.burst_db

        n = min(power.shape[1], quiet.size)
        power, quiet = power[:, :n], quiet[:n]
        if quiet.sum() < MIN_QUIET_FRAMES:
            band = db[:n]
            quiet = band <= np.quantile(band, QUIET_QUANTILE)
            if quiet.sum() < MIN_QUIET_FRAMES:
                return None
        mel = self.filters @ power[:, quiet]
        return np.log(np.maximum(mel.mean(axis=1), 1e-10))


class ChannelBuckets:
    """recording id -> bucket, learned by clustering channel descriptors.

    `fit` takes {recording_id: [descriptor, ...]}, averages within a recording,
    standardises across the corpus so no mel band dominates on units alone, and
    k-means the result. `assign` is what training and sampling read.
    """

    def __init__(self, centroids=None, mean=None, scale=None, mapping=None,
                 fallback="channel-000"):
        self.centroids = centroids
        self.mean = mean
        self.scale = scale
        self.mapping = mapping or {}
        self.fallback = fallback

    @property
    def names(self):
        if self.centroids is None:
            return []
        return [f"channel-{i:03d}" for i in range(len(self.centroids))]

    def fit(self, descriptors, n_buckets=DEFAULT_BUCKETS, seed=0):
        from sklearn.cluster import KMeans

        ids = sorted(descriptors)
        matrix = np.vstack([np.mean(descriptors[i], axis=0) for i in ids])
        self.mean = matrix.mean(axis=0)
        self.scale = matrix.std(axis=0) + 1e-8
        whitened = (matrix - self.mean) / self.scale

        n_buckets = min(n_buckets, len(ids))
        model = KMeans(n_clusters=n_buckets, random_state=seed, n_init=10)
        labels = model.fit_predict(whitened)
        self.centroids = model.cluster_centers_
        self.mapping = {rid: f"channel-{int(l):03d}" for rid, l in zip(ids, labels)}
        return self

    def assign(self, recording_id):
        """The bucket a recording belongs to, or the fallback for an unseen one.

        A recording with no bucket is not an error. The corpus grows, and a bout
        whose recording arrived after the last fit still has to train.
        """
        return self.mapping.get(recording_id, self.fallback)

    def nearest(self, descriptor):
        """The bucket a NEW recording belongs to, from its descriptor."""
        whitened = (np.asarray(descriptor) - self.mean) / self.scale
        return f"channel-{int(np.argmin(((self.centroids - whitened) ** 2).sum(axis=1))):03d}"

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "names": self.names,
            "centroids": np.asarray(self.centroids).tolist(),
            "mean": np.asarray(self.mean).tolist(),
            "scale": np.asarray(self.scale).tolist(),
            "mapping": self.mapping,
            "fallback": self.fallback,
        }))
        return path

    @classmethod
    def load(cls, path):
        blob = json.loads(Path(path).read_text())
        return cls(centroids=np.array(blob["centroids"]),
                   mean=np.array(blob["mean"]), scale=np.array(blob["scale"]),
                   mapping=blob["mapping"], fallback=blob["fallback"])


def describe_corpus(bouts_dir, per_recording=4, on_progress=None):
    """{recording_id: [descriptor, ...]} over the bout store.

    Reads at most `per_recording` bouts each: the channel is constant within a
    recording by definition, so more bouts buy precision on a quantity that
    barely moves and cost a linear pass over 6.8 GB.
    """
    bouts_dir = Path(bouts_dir)
    rows = defaultdict(list)
    with open(bouts_dir / "index.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            if len(rows[row["recording_id"]]) < per_recording:
                rows[row["recording_id"]].append(row)

    describer = ChannelDescriber()
    shards, out = {}, {}
    total = len(rows)
    for done, (rid, group) in enumerate(sorted(rows.items()), start=1):
        got = []
        for row in group:
            species = row["species"]
            if species not in shards:
                shards[species] = np.memmap(bouts_dir / f"{species}.i16",
                                            dtype=np.int16, mode="r")
            start = row["sample_offset"]
            samples = shards[species][start:start + row["n_samples"]] / 32768.0
            vector = describer.quiet_spectrum(samples)
            if vector is not None:
                got.append(vector)
        if got:
            out[rid] = got
        if on_progress and done % 200 == 0:
            on_progress(done, total)
    if on_progress:
        on_progress(total, total)
    return out
