"""Bouts -> token sequences, split so no bird straddles the boundary.

SEQUENCE FORMAT.  [species][call type][duration bucket] codec tokens... [EOS]

The call type comes before the duration because it is asked for and the duration
is not: at generation the caller names a species and a call type, and the model
picks how long the bout should be. Most bouts carry a pseudo-label from the
bout-trained head (0018); the ones the head was unsure about, everything that is
not American Crow, and the held-out human-labelled bouts all carry "unknown", so
the token means "I am not telling you" rather than a wrong guess.

The duration bucket is not decoration. Without it the model has to guess when to
stop, and an autoregressive model with no length signal produces both runaway
and truncated bouts. At generation the bucket is sampled from the empirical
per-species distribution, so lengths come from the corpus rather than from a
hyperparameter.

AUGMENTATION IS FREE HERE, and it is the reason this trains on more than it
looks like. EnCodec's hop is 320 samples, so cropping the same audio at an
offset of 40 samples produces a genuinely different token sequence for audio no
ear can tell apart. Eight offsets is eight times the data at the cost of one
tokenisation pass and no codec calls during training. Gain jitter rides along
because the 24 kHz model does not normalise internally, so level is something
the codec actually encodes.

Only the un-augmented sequences are marked canonical. The memorisation check
counts n-grams against those alone — indexing all eight variants would inflate
the training set eightfold and make everything look like a copy.

THE SPLIT IS BY GROUP, NEVER BY BOUT.  Bouts from one recording are near
duplicates of each other, and recordists upload the same bird on the same day
under several archive ids. It is three-way because the judge's "real held
out" audio must not be the validation set the model was tuned against.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from crowgpt.codec import CODEBOOK_SIZE, SAMPLE_RATE, Codec, normalise

DURATION_EDGES = np.array([0.12, 0.25, 0.45, 0.75, 1.2, 1.8, 2.4])
N_BUCKETS = len(DURATION_EDGES) + 1
# UNIT BUCKETS: 1 / 2 / 3 / 4-5 / 6+ caws per bout. Exists because 0024
# measured generated bouts at 1.37 units against real audio's 3.37 (70%
# single-caw, p = 0.0008) and 0047 showed sampling cannot fix it — the model
# needs to be TOLD what a four-caw bout is before it can be asked for one.
# Counted by the segmenter at tokenize time; sampled by the model at
# generation exactly like the duration bucket, so counts come from the
# corpus's own distribution rather than a hyperparameter.
UNIT_EDGES = np.array([1.5, 2.5, 3.5, 5.5])
N_UNIT_BUCKETS = len(UNIT_EDGES) + 1
SUB_HOP_OFFSETS = (0, 40, 80, 120, 160, 200, 240, 280)
GAIN_DB = (0.0, -3.0, -6.0, -2.0, -4.5, -1.5, -5.0, -7.0)


class Vocabulary:
    """Codec tokens, then EOS, then the conditioning prefix."""

    def __init__(self, n_codebooks, species, call_types=(), channels=(),
                 n_unit_buckets=0):
        self.n_codebooks = n_codebooks
        self.species = list(species)
        self.call_types = list(call_types)
        self.channels = list(channels)
        self.n_unit_buckets = int(n_unit_buckets)
        self.codec_size = CODEBOOK_SIZE * n_codebooks
        self.eos = self.codec_size
        self.species_base = self.eos + 1
        self.calltype_base = self.species_base + len(self.species)
        self.duration_base = self.calltype_base + len(self.call_types)
        # Channels sit AFTER the duration buckets in id space, and the duration
        # slot is now a bounded span rather than "everything to the end" — which
        # it was, and which would have admitted a channel token where a duration
        # belongs the moment one existed.
        self.channel_base = self.duration_base + N_BUCKETS
        # Unit buckets take the top of id space; zero of them is the old
        # vocabulary bit-for-bit, which is what keeps every existing token
        # set and checkpoint readable.
        self.unit_base = self.channel_base + len(self.channels)
        self.size = self.unit_base + self.n_unit_buckets

    @property
    def prefix_len(self):
        return (2 + bool(self.call_types) + bool(self.channels)
                + bool(self.n_unit_buckets))

    @property
    def sampled_slots(self):
        """How many trailing prefix slots the MODEL fills at generation.

        Duration always; the unit bucket too when this vocabulary carries
        one. This is the number `_prefix` is shorter than `prefix_len` by —
        the seam that produced the same silent bug twice (see TODO) now has
        one owner instead of a convention."""
        return 1 + bool(self.n_unit_buckets)

    def prefix_slots(self):
        """(start, end) per prefix position, in order. The mask's only source.

        DURATION IS LAST AND HAS TO STAY LAST. `Sampler.tokens` states every
        other prefix token and lets the MODEL sample the final slot, so the
        duration bucket comes from what the corpus taught it about that species.
        Moving anything after it would make that token get sampled instead.
        """
        slots = [(self.species_base, self.species_base + len(self.species))]
        if self.call_types:
            slots.append((self.calltype_base, self.calltype_base + len(self.call_types)))
        if self.channels:
            slots.append((self.channel_base, self.channel_base + len(self.channels)))
        if self.n_unit_buckets:
            # Sampled by the model, like duration, and immediately before it:
            # the model decides how many caws, then how long that takes.
            slots.append((self.unit_base, self.unit_base + self.n_unit_buckets))
        slots.append((self.duration_base, self.duration_base + N_BUCKETS))
        return slots

    def calltype_token(self, name):
        if not self.call_types:
            raise ValueError("this vocabulary has no call types")
        return self.calltype_base + self.call_types.index(name)

    def channel_token(self, name):
        if not self.channels:
            raise ValueError("this vocabulary has no channels")
        return self.channel_base + self.channels.index(name)

    def species_token(self, slug):
        return self.species_base + self.species.index(slug)

    def duration_token(self, seconds):
        return self.duration_base + int(np.searchsorted(DURATION_EDGES, seconds))

    def unit_token(self, count):
        if not self.n_unit_buckets:
            raise ValueError("this vocabulary has no unit buckets")
        return self.unit_base + int(np.searchsorted(UNIT_EDGES, count))

    def allowed(self, position):
        """Token ids legal at a position, counting from the first codec token.

        At position t the next token necessarily belongs to codebook t % K, so
        every other codebook's ids are structurally impossible. Masking them
        costs three lines and strictly lowers loss; leaving them unmasked wastes
        most of the output layer and lets early sampling emit tokens that will
        not decode. EOS is legal only on a frame boundary, because a partial
        frame cannot be decoded at all.
        """
        stage = position % self.n_codebooks
        ids = [(stage * CODEBOOK_SIZE, (stage + 1) * CODEBOOK_SIZE)]
        return ids, stage == 0

    def mask(self, length):
        """[length, vocab] boolean mask of what may follow each position."""
        allowed = np.zeros((length, self.size), dtype=bool)
        for position in range(length):
            spans, may_end = self.allowed(position)
            for start, end in spans:
                allowed[position, start:end] = True
            if may_end:
                allowed[position, self.eos] = True
        return allowed


def codec_from_manifest(manifest, device=None, decoder_state=None):
    """Rebuild the exact tokenizer a token set was written with.

    `decoder_state` (EnCodec kinds only) decodes through a finetuned decoder
    — "finetuned" for the 0063-confirmed checkpoint. Encoding is unaffected,
    so the rebuilt tokenizer still writes bit-identical tokens.

    Bandwidth used to be enough and stopped being enough twice over: --keep made
    a 24 kbps/16 codebook manifest possible, and DAC made "bandwidth" a derived
    number rather than an operating point — DAC at 24 codebooks reports 18.0,
    which EnCodec has no setting for and would raise on. Neither mistake is loud
    on its own: unflatten reshapes by the wrong period and the audio still
    decodes, just wrongly.
    """
    kind = manifest.get("codec", "encodec-24khz")
    if kind.endswith("+delay"):
        from crowgpt.dac_codec import Delayed

        return Delayed(codec_from_manifest({**manifest, "codec": kind[: -len("+delay")]},
                                           device=device))
    if "@" in kind:
        # Written through a resampling wrapper. Rebuilding the inner codec alone
        # would decode at the model's rate instead of the corpus's, which is
        # audible and easy to mistake for the model sounding wrong.
        from crowgpt.dac_codec import Resampled

        inner_kind, source_rate = kind.rsplit("@", 1)
        inner = codec_from_manifest({**manifest, "codec": inner_kind}, device=device)
        return Resampled(inner, int(source_rate))
    if kind.startswith("dac-"):
        from crowgpt.dac_codec import DacCodec

        return DacCodec(n_codebooks=manifest["n_codebooks"],
                        model_type=kind.split("-", 1)[1], device=device)
    return Codec(bandwidth=manifest["bandwidth"], device=device,
                 keep=manifest.get("n_codebooks"), decoder_state=decoder_state)


class BoutStore:
    """The extracted bouts: an index plus one int16 shard per species."""

    def __init__(self, root):
        self.root = Path(root)
        self.index = [json.loads(line) for line in (self.root / "index.jsonl").read_text().splitlines() if line]
        self._shards = {}

    def __len__(self):
        return len(self.index)

    @property
    def species(self):
        return sorted({row["species"] for row in self.index})

    def audio(self, row):
        shard = self._shards.get(row["species"])
        if shard is None:
            shard = np.memmap(self.root / f"{row['species']}.i16", dtype=np.int16, mode="r")
            self._shards[row["species"]] = shard
        start = row["sample_offset"]
        return shard[start : start + row["n_samples"]].astype(np.float32) / 32768.0

    def split(self, val_fraction=0.08, test_fraction=0.08, seed=0):
        """Three-way, grouped, and stratified by species."""
        rng = np.random.default_rng(seed)
        by_species = defaultdict(lambda: defaultdict(list))
        for i, row in enumerate(self.index):
            by_species[row["species"]][row["group_key"]].append(i)

        assignment = {}
        for slug, groups in by_species.items():
            keys = sorted(groups)
            rng.shuffle(keys)
            n_val = max(1, int(round(len(keys) * val_fraction)))
            n_test = max(1, int(round(len(keys) * test_fraction)))
            for k, key in enumerate(keys):
                if k < n_val:
                    assignment[key] = "val"
                elif k < n_val + n_test:
                    assignment[key] = "test"
                else:
                    assignment[key] = "train"

        out = {"train": [], "val": [], "test": []}
        for i, row in enumerate(self.index):
            out[assignment[row["group_key"]]].append(i)
        return out


class TokenWriter:
    """Tokenises bouts into flat memmaps, one per split."""

    def __init__(self, store, out_dir, bandwidth=None, device=None, augment=True, variants=8,
                 call_types=None, keep=None, codec=None, unit_buckets=False):
        """`codec` overrides the EnCodec default with any codec of that shape.

        Passed in rather than named, because building it is the caller's job and
        the two implementations do not take the same arguments — EnCodec is
        chosen by bandwidth and DAC by codebook count. Anything with encode,
        flatten and n_codebooks works; 0033 and 0034 settled on DAC 24 kHz at 24
        codebooks, which is not reachable through `bandwidth` at all.
        """
        self.store = store
        self.out_dir = Path(out_dir)
        self.codec = codec or Codec(bandwidth=bandwidth, device=device, keep=keep)
        # call_types maps bout index -> name. Absent means the old two-token
        # prefix, so existing token sets stay readable.
        self.call_types = call_types or {}
        vocabulary = sorted(set(self.call_types.values())) if self.call_types else ()
        self.vocab = Vocabulary(self.codec.n_codebooks, store.species, vocabulary,
                                n_unit_buckets=N_UNIT_BUCKETS if unit_buckets else 0)
        self._segmenter = None
        self.augment = augment
        # Eight sub-hop offsets was right for 25k bouts. On a corpus several
        # times that, the real recordings supply the variety and the eighth
        # variant only costs tokenising time.
        self.n_variants = max(1, min(variants, len(SUB_HOP_OFFSETS)))

    def _units(self, samples):
        """Caws in this bout, by 0013's burst detector at its validated 12 dB —
        the same numerics 0024 used to measure the defect this token exists
        to fix, so the training signal and the gate share one instrument."""
        if self._segmenter is None:
            from crowgpt.segment import Segmenter

            self._segmenter = Segmenter()
        db, fps = self._segmenter.envelope(samples, SAMPLE_RATE)
        floor = np.percentile(db, self._segmenter.floor_pctl)
        return len(self._segmenter.bursts(db, fps, floor))

    def variants(self, samples, split):
        """Canonical first; augmented variants only for training."""
        yield samples, 0, True
        if not self.augment or split != "train":
            return
        for offset, gain in zip(SUB_HOP_OFFSETS[1:self.n_variants], GAIN_DB[1:self.n_variants]):
            if samples.size - offset < SAMPLE_RATE * 0.06:
                continue
            yield samples[offset:] * (10 ** (gain / 20.0)), offset, False

    def run(self, splits, batch_size=16, on_progress=None):
        """`on_progress(split, done, total)` for an unattended runner.

        Tokenising the corpus at sixteen codebooks is the better part of two
        hours, and until this existed it reported itself only by printing to a
        stdout nobody is watching at 2am — the progress record sat frozen on
        the stage it entered, so the dashboard showed a run that looked hung.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"bandwidth": self.codec.bandwidth, "n_codebooks": self.codec.n_codebooks,
                    "codec": getattr(self.codec, "kind", "encodec-24khz"),
                    "vocab_size": self.vocab.size, "species": self.vocab.species,
                    "call_types": self.vocab.call_types,
                    "eos": self.vocab.eos, "species_base": self.vocab.species_base,
                    "calltype_base": self.vocab.calltype_base,
                    "duration_base": self.vocab.duration_base, "n_buckets": N_BUCKETS,
                    "n_unit_buckets": self.vocab.n_unit_buckets,
                    "prefix_len": self.vocab.prefix_len, "splits": {}}

        for split, indices in splits.items():
            stream, records = [], []
            cursor = 0
            pending = []
            for position, row_index in enumerate(indices):
                row = self.store.index[row_index]
                samples = normalise(self.store.audio(row))
                call_type = self.call_types.get(row_index)
                # Counted once per bout on the canonical audio — a sub-hop
                # offset cannot change how many caws there are, and pretending
                # it could would let augmentation smear the bucket.
                units = self._units(samples) if self.vocab.n_unit_buckets else None
                for variant, offset, canonical in self.variants(samples, split):
                    pending.append(((row, call_type, units), variant, offset, canonical))
                    if len(pending) >= batch_size:
                        cursor = self._flush(pending, stream, records, cursor)
                        pending = []
                if position % 500 == 0:
                    print(f"   {split}: {position}/{len(indices)} bouts", flush=True)
                    if on_progress:
                        on_progress(split, position, len(indices))
            if pending:
                cursor = self._flush(pending, stream, records, cursor)

            flat = np.concatenate(stream) if stream else np.zeros(0, dtype=np.uint16)
            flat.astype(np.uint16).tofile(self.out_dir / f"{split}.u16")
            (self.out_dir / f"{split}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in records)
            )
            manifest["splits"][split] = {
                "sequences": len(records),
                "tokens": int(flat.size),
                "canonical": sum(1 for r in records if r["canonical"]),
            }
            print(f"   {split}: {len(records)} sequences, {flat.size} tokens", flush=True)

        (self.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest

    def _flush(self, pending, stream, records, cursor):
        """Tokenise a batch, padding to the longest and trimming each back."""
        lengths = [len(item[1]) for item in pending]
        longest = max(lengths)
        batch = np.zeros((len(pending), longest), dtype=np.float32)
        for i, (_, samples, _, _) in enumerate(pending):
            batch[i, : samples.size] = samples

        codes = self.codec.encode(batch).numpy()
        for i, ((row, call_type, units), samples, offset, canonical) in enumerate(pending):
            frames = max(1, int(np.ceil(samples.size / 320)))
            flat = self.codec.flatten(codes[i][:, :frames])
            seconds = samples.size / SAMPLE_RATE
            prefix = [self.vocab.species_token(row["species"])]
            if self.vocab.call_types:
                prefix.append(self.vocab.calltype_token(call_type or "unknown"))
            if self.vocab.n_unit_buckets:
                prefix.append(self.vocab.unit_token(units))
            prefix.append(self.vocab.duration_token(seconds))
            sequence = np.concatenate([prefix, flat, [self.vocab.eos]]).astype(np.uint16)
            stream.append(sequence)
            records.append(
                {
                    "start": cursor,
                    "length": int(sequence.size),
                    "species": row["species"],
                    "call_type": call_type or "unknown",
                    "group_key": row["group_key"],
                    "recording_id": row["recording_id"],
                    "dur_sec": round(seconds, 3),
                    "units": units,
                    "offset": offset,
                    "canonical": canonical,
                }
            )
            cursor += int(sequence.size)
        return cursor


class TokenDataset:
    """A written split, read back."""

    def __init__(self, out_dir, split):
        self.out_dir = Path(out_dir)
        self.manifest = json.loads((self.out_dir / "manifest.json").read_text())
        self.records = [
            json.loads(line)
            for line in (self.out_dir / f"{split}.jsonl").read_text().splitlines()
            if line
        ]
        self.stream = np.fromfile(self.out_dir / f"{split}.u16", dtype=np.uint16)

    def __len__(self):
        return len(self.records)

    def sequence(self, i):
        record = self.records[i]
        return self.stream[record["start"] : record["start"] + record["length"]].astype(np.int64)
