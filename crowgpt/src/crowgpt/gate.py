"""Can a neural codec carry a caw?

EnCodec is trained on speech and music. A corvid call is neither, and if the
codec cannot round-trip one then a model trained on its tokens is finished
before it starts — no amount of training fixes a tokenizer that has already
thrown the signal away. So this runs before anything is trained, and it is
allowed to come back negative.

Six arms on the same 3-second crow-positive windows:

  native          the file as recorded — the reference BirdNET is scored against
  resample_24k    native -> 24 kHz, no codec. Separates band loss from codec
                  loss, and is the reference every spectral distance is measured
                  against so the two are never conflated.
  encodec_*       2/4/8/16/32 codebooks
  encodec_x2      3 kbps encoded and decoded twice, to expose artefacts that
                  accumulate rather than showing up once
  lowpass_2k      deliberately ruined, to prove the metrics can fail

BirdNET retention is the SECONDARY metric, deliberately. It was trained on
archive mp3s with heavy augmentation and is robust to exactly the spectral
smearing a codec produces, so it will happily pass a reconstruction that a
spectrogram shows to be mush. The primary metric is multi-resolution STFT
distance, and the tie-breaker for how many codebooks to keep is per-stage code
entropy: a residual stage well under its 10-bit ceiling costs sequence length
and buys nothing.
"""

import contextlib
import os
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfiltfilt

from crowgpt.codec import SAMPLE_RATE
from crowgpt.corpus import Corpus, REPO
from crowgpt.metrics import codebook_entropy, multi_res_stft_distance

WINDOW_SEC = 3.0
RETAIN_MIN = 0.90
DELTA_CONF_MIN = -0.05
# The spectral bar is set against the deliberately-ruined arm, not against the
# resample-only one. resample_24k is the REFERENCE every distance is measured
# from, so its distance to itself is zero by construction and any criterion
# phrased as a multiple of it can never be met by anything. That was the first
# version of this threshold and it failed all six codec arms for a reason that
# had nothing to do with the codec.
STFT_MAX_SHARE_OF_ANCHOR = 0.5
ANCHOR_ARM = "lowpass_2k"


class Gate:
    """The codec feasibility measurement."""

    def __init__(self, per_species=50, seed=0, bandwidths=(1.5, 3.0, 6.0, 12.0, 24.0)):
        self.per_species = per_species
        self.rng = random.Random(seed)
        self.bandwidths = list(bandwidths)
        self.analyzer = None

    def _birdnet(self):
        """Deliberately absent: BirdNET must not be imported in a process that
        also wants the GPU. Use crowgpt.birdnet, which runs it as a subprocess.
        See crowgpt/gpu.py for what happens otherwise."""
        raise RuntimeError(
            "gate.py must not load BirdNET in-process — use crowgpt.birdnet. "
            "Experiment 0017's run.py is the worked example."
        )

    def _constants(self):
        # thresholds, not birdnet: the constants module loads no model, so this
        # no longer needs a muted stdout or the price of every call-type head.
        sys.path.insert(0, str(REPO))
        from analyzer import thresholds
        return (thresholds.CROW_TERMS, thresholds.CROW_MIN_CONF,
                thresholds.CANDIDATE_MIN_CONF)

    def confidence(self, samples, sr):
        """Max corvid confidence BirdNET gives this clip.

        Written to a temp WAV because birdnetlib takes a path. The location
        filter stays off for every arm, so the species prior cannot differ
        between them.
        """
        from birdnetlib import Recording as BirdRecording

        terms, _, candidate_min = self._constants()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = handle.name
        try:
            sf.write(path, samples, sr, subtype="PCM_16")
            with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
                rec = BirdRecording(self._birdnet(), path, min_conf=candidate_min)
                rec.analyze()
            best = 0.0
            for det in rec.detections:
                name = f"{det.get('common_name', '')} {det.get('scientific_name', '')}".lower()
                if any(term in name for term in terms):
                    best = max(best, float(det["confidence"]))
            return best
        finally:
            Path(path).unlink(missing_ok=True)

    def windows(self):
        """Crow-positive 3-second windows, stratified by species.

        American Crow is drawn from as many distinct recordings as possible —
        only 173 exist, so a naive sample would keep re-reading the same bird.
        """
        import librosa

        from birdnetlib import Recording as BirdRecording

        terms, crow_min, candidate_min = self._constants()
        chosen = []
        for slug, recordings in sorted(Corpus().recordings().items()):
            picks = list(recordings)
            self.rng.shuffle(picks)
            kept = []
            for rec in picks:
                if len(kept) >= self.per_species:
                    break
                try:
                    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
                        analysis = BirdRecording(self._birdnet(), str(rec.path), min_conf=candidate_min)
                        analysis.analyze()
                    starts = sorted(
                        {
                            int(det["start_time"] // WINDOW_SEC) * WINDOW_SEC
                            for det in analysis.detections
                            if float(det["confidence"]) >= crow_min
                            and any(
                                term
                                in f"{det.get('common_name','')} {det.get('scientific_name','')}".lower()
                                for term in terms
                            )
                        }
                    )
                    if not starts:
                        continue
                    y, sr = librosa.load(str(rec.path), sr=None, mono=True)
                    start = self.rng.choice(starts)
                    begin = int(start * sr)
                    chunk = y[begin : begin + int(WINDOW_SEC * sr)]
                    if chunk.size < int(WINDOW_SEC * sr):
                        continue
                    kept.append(
                        {
                            "species": slug,
                            "recording_id": rec.recording_id,
                            "start_sec": start,
                            "native_sr": int(sr),
                            "audio": chunk.astype(np.float32),
                        }
                    )
                except Exception:
                    continue
            chosen.extend(kept)
            print(f"   {slug}: {len(kept)} windows from {len({k['recording_id'] for k in kept})} recordings", flush=True)
        return chosen

    def arms(self, window):
        """Every processed version of one window, at 24 kHz unless native."""
        from crowgpt.codec import Codec

        native, sr = window["audio"], window["native_sr"]
        at_24k = self._to_24k(native, sr)

        out = {
            "native": (native, sr),
            "resample_24k": (at_24k, SAMPLE_RATE),
            "lowpass_2k": (self._lowpass(at_24k, 2000), SAMPLE_RATE),
        }
        codes_by_arm = {}
        for bandwidth in self.bandwidths:
            codec = self._codec(bandwidth)
            codes = codec.encode(at_24k)
            restored = codec.decode(codes[0])[0]
            name = f"encodec_{bandwidth:g}kbps"
            out[name] = (restored, SAMPLE_RATE)
            codes_by_arm[name] = codes[0].numpy()
            if bandwidth == 3.0:
                twice = codec.decode(codec.encode(restored)[0])[0]
                out["encodec_3kbps_x2"] = (twice, SAMPLE_RATE)
        return out, codes_by_arm

    def _codec(self, bandwidth):
        from crowgpt.codec import Codec

        if not hasattr(self, "_codecs"):
            self._codecs = {}
        if bandwidth not in self._codecs:
            self._codecs[bandwidth] = Codec(bandwidth=bandwidth)
        return self._codecs[bandwidth]

    @staticmethod
    def _to_24k(samples, sr):
        if sr == SAMPLE_RATE:
            return np.asarray(samples, dtype=np.float32)
        from math import gcd

        divisor = gcd(int(sr), SAMPLE_RATE)
        return resample_poly(samples, SAMPLE_RATE // divisor, int(sr) // divisor).astype(np.float32)

    @staticmethod
    def _lowpass(samples, cutoff, sr=SAMPLE_RATE):
        sos = butter(8, cutoff / (sr / 2), btype="low", output="sos")
        return sosfiltfilt(sos, samples).astype(np.float32)

    def run(self):
        windows = self.windows()
        if not windows:
            raise SystemExit("no crow-positive windows found — is DATA_DIR right?")

        per_arm = {}
        entropy_totals = {}
        for i, window in enumerate(windows, 1):
            arms, codes_by_arm = self.arms(window)
            reference = arms["resample_24k"][0]
            baseline_conf = self.confidence(*arms["native"])

            for name, (samples, sr) in arms.items():
                slot = per_arm.setdefault(name, {"conf": [], "base": [], "stft": []})
                slot["conf"].append(self.confidence(samples, sr))
                slot["base"].append(baseline_conf)
                if name != "native":
                    slot["stft"].append(multi_res_stft_distance(reference, samples))

            for name, codes in codes_by_arm.items():
                entropy_totals.setdefault(name, []).append(codes)
            if i % 25 == 0 or i == len(windows):
                print(f"   {i}/{len(windows)} windows", flush=True)

        return self._summarise(windows, per_arm, entropy_totals)

    def _summarise(self, windows, per_arm, entropy_totals):
        _, crow_min, _ = self._constants()
        results = {
            "n_windows": len(windows),
            "per_species": {
                slug: sum(1 for w in windows if w["species"] == slug)
                for slug in sorted({w["species"] for w in windows})
            },
            "criterion": {
                "retain_min": RETAIN_MIN,
                "median_delta_conf_min": DELTA_CONF_MIN,
                "stft_max_share_of_anchor": STFT_MAX_SHARE_OF_ANCHOR,
                "anchor_arm": ANCHOR_ARM,
            },
            "arms": {},
        }

        for name, slot in per_arm.items():
            conf = np.array(slot["conf"])
            base = np.array(slot["base"])
            detected = base >= crow_min
            deltas = (conf - base)[detected]
            results["arms"][name] = {
                "mean_conf": round(float(conf.mean()), 4),
                "retain_rate": round(float((conf[detected] >= crow_min).mean()), 4)
                if detected.any()
                else None,
                "median_delta_conf": round(float(np.median(deltas)), 4) if deltas.size else None,
                "stft_distance": round(float(np.mean(slot["stft"])), 4) if slot["stft"] else None,
            }

        for name, code_list in entropy_totals.items():
            stacked = np.concatenate(code_list, axis=1)
            results["arms"][name]["codebook_entropy_bits"] = [
                round(b, 2) for b in codebook_entropy(stacked)
            ]
            results["arms"][name]["n_codebooks"] = int(stacked.shape[0])

        anchor = results["arms"][ANCHOR_ARM]["stft_distance"]
        for name, arm in results["arms"].items():
            if not name.startswith("encodec"):
                continue
            arm["checks"] = {
                "retain": arm["retain_rate"] is not None and arm["retain_rate"] >= RETAIN_MIN,
                "delta_conf": arm["median_delta_conf"] is not None
                and arm["median_delta_conf"] >= DELTA_CONF_MIN,
                "spectral": anchor is not None
                and arm["stft_distance"] <= anchor * STFT_MAX_SHARE_OF_ANCHOR,
            }
            arm["passes"] = all(arm["checks"].values())

        passing = [n for n, a in results["arms"].items() if a.get("passes")]
        results["passing_arms"] = sorted(passing)
        results["recommended_bandwidth"] = self._recommend(results)
        return results

    @staticmethod
    def _recommend(results):
        """Cheapest passing bandwidth whose every codebook is carrying signal."""
        candidates = []
        for name, arm in results["arms"].items():
            if not arm.get("passes"):
                continue
            bandwidth = float(name.replace("encodec_", "").replace("kbps", ""))
            entropy = arm.get("codebook_entropy_bits") or []
            if entropy and min(entropy) < 6.0:
                continue
            candidates.append(bandwidth)
        return min(candidates) if candidates else None
