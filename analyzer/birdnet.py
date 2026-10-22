"""BirdNET inference — what a recording actually contains.

Audio (or video) in -> BirdNET locates the corvids and names the species -> a
per-species call-type head labels each call region -> a timeline of where the
calls are, which species, and (where we have a trained head) what kind.

Its own component, with no idea that a field server exists. It takes a path and
returns findings; it does not know about jobs, captures, or a database. The
worker is the thing that knows those, and it calls in here — so the model can be
run over a directory of files, or a single clip, without standing up a server.

It lived in demo/server.py, behind a Flask upload page that predated the field
server. The dashboard replaced the page; the engine inside it was always the
real thing, and it belongs on its own.

Call-type heads live under pipelines/training/models/:
  - calltype_clf.joblib          the American Crow head (Phase 4)
  - <species-slug>/calltype_clf.joblib   one head per additional species
A detected corvid with no head is still shown (species-only), never mislabeled
with another species' model.

Runs in the BirdNET venv (birdnetlib, sklearn, joblib):
  make -C fieldserver worker
"""

import contextlib
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

import joblib
import numpy as np
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

HERE = Path(__file__).resolve().parent
# analyzer/ -> repo root
TRAINING = HERE.parent / "pipelines" / "training"
MODELS_DIR = TRAINING / "models"
sys.path.insert(0, str(TRAINING))
import pooling  # noqa: E402  — same feature def as training
from pooling import pool  # noqa: E402

DEVNULL = open(os.devnull, "w")

# Re-exported so `birdnet.CROW_TERMS` etc. keep answering; the constants and
# their rationale live in thresholds.py, importable without loading a model.
# Both import spellings happen: `analyzer.birdnet` from the repo, and a flat
# `import birdnet` from scripts that put this directory on sys.path.
try:
    from .thresholds import (  # noqa: E402,F401
        ANALYSIS_FILTER,
        BIRDNET_VERSION,
        CANDIDATE_MIN_CONF,
        CROW_MIN_CONF,
        CROW_TERMS,
        DETECTION_WINDOW_SEC,
        LOCALISE_STEP,
        LOCALISE_TOLERANCE,
        LOCALISE_WINDOWS,
        REGION_GAP,
        WAVEFORM_BINS,
        WINDOW_SEC,
    )
except ImportError:
    from thresholds import (  # noqa: E402,F401
        ANALYSIS_FILTER,
        BIRDNET_VERSION,
        CANDIDATE_MIN_CONF,
        CROW_MIN_CONF,
        CROW_TERMS,
        DETECTION_WINDOW_SEC,
        LOCALISE_STEP,
        LOCALISE_TOLERANCE,
        LOCALISE_WINDOWS,
        REGION_GAP,
        WAVEFORM_BINS,
        WINDOW_SEC,
    )

#: How long one ffmpeg/ffprobe call may run before it is killed.
#:
#: The analyzer decodes whatever the worker hands it, which is whatever a phone
#: uploaded, and a malformed container can make a decoder spin instead of
#: failing. Without a bound the worker stops polling and the job queue stalls
#: behind one bad file — silently, because a stuck process logs nothing.
#:
#: Longer than the field server's, on purpose: this is a batch worker rather
#: than a request, and a long recording being slow is not a fault.
MEDIA_TIMEOUT_SEC = float(os.environ.get("ANALYZER_MEDIA_TIMEOUT_SEC", "300"))

#: Address-space ceiling for the child, or 0 to leave it alone. See the same
#: constant in fieldserver/core/transcode.py for why it is this generous.
MEDIA_MEMORY_MB = int(os.environ.get("ANALYZER_MEDIA_MEMORY_MB", "4096"))

#: `-nostdin` so a decoder cannot swallow input meant for the worker's terminal.
#:
#: ffmpeg only. ffprobe has no such option and exits 1 on it — "Failed to set
#: value '-v' for option 'nostdin': Option not found" — because it takes the
#: next argument as the value. It never reads stdin interactively anyway.
_NOSTDIN = ("-nostdin",)

_LIMIT = (MEDIA_MEMORY_MB * 1024 * 1024,) * 2


def _cap_memory() -> None:
    resource.setrlimit(resource.RLIMIT_AS, _LIMIT)


class MediaTimeout(RuntimeError):
    """A decoder ran longer than it may. The file is the suspect, not the box."""


def _guarded(cmd, *, check=False, capture=True, text=False):
    """Run a media tool under a timeout and a memory ceiling.

    A near-copy of `run_ffmpeg` in fieldserver/core/transcode.py, and kept that
    way deliberately — this package takes a path and returns findings, and
    importing the field server to decode a file would hand it a database, a job
    queue and two shared secrets. Six lines of duplication is the cheaper half
    of that trade.

    The callers below want different things from a failure — one diagnoses,
    one raises, one shrugs — so this leaves `check` to them and only takes the
    two decisions they all share.
    """
    flags = _NOSTDIN if cmd[0] == "ffmpeg" else ()
    try:
        return subprocess.run(
            [cmd[0], *flags, *cmd[1:]],
            check=check, capture_output=capture, text=text,
            timeout=MEDIA_TIMEOUT_SEC,
            preexec_fn=_cap_memory if MEDIA_MEMORY_MB else None,
        )
    except subprocess.TimeoutExpired as error:
        raise MediaTimeout(
            f"{cmd[0]} gave up on {Path(cmd[-1]).name if cmd[-1] != '-' else 'the input'} "
            f"after {MEDIA_TIMEOUT_SEC:.0f}s") from error


def reliability_tier(auc):
    if auc is None:
        return {"label": "untested", "level": "unknown", "auc": None}
    auc = round(float(auc), 2)  # tiers are coarse; don't flip on 3rd-decimal noise
    if auc >= 0.80:
        level, label = "good", "reliable"
    elif auc >= 0.70:
        level, label = "ok", "moderate"
    elif auc >= 0.60:
        level, label = "low", "low confidence"
    else:
        level, label = "bad", "unreliable"
    return {"label": label, "level": level, "auc": auc}


class HeadMismatch(RuntimeError):
    """A head was trained on a feature this analyzer does not produce."""


def head_width(bundle):
    """How many features this head expects, however its bundle was written.

    Five of the six shipped heads carry only {model, classes} — train_species.py
    and train_american_crow.py never wrote the `dim` that train.py does. But
    every one of them carries the width inside the sklearn pipeline anyway, so
    the check below works on the heads as they exist and needs no retrain.
    """
    if bundle.get("dim"):
        return int(bundle["dim"])
    model = bundle["model"]
    steps = getattr(model, "named_steps", {})
    for step in (*steps.values(), model):
        width = getattr(step, "n_features_in_", None)
        if width:
            return int(width)
    return None


def _check_bundle(bundle, model_path):
    """Refuse a head whose feature space is not the one we are producing.

    Without this a backbone swap fails at the 400th capture with a raw sklearn
    n_features error — or does not fail at all, if the widths happen to match,
    and every call type after that is a confident guess from a model reading
    someone else's coordinates.

    Strict about absence too, since 2026-08-09: every shipped bundle carries
    `feature` now (the four that predated it were stamped after their width
    proved the space), so a bundle without it is not a legacy head — it is a
    head whose provenance nobody recorded, and serving it would be a guess.
    """
    feature = bundle.get("feature")
    if not feature:
        raise HeadMismatch(
            f"{model_path} does not say which feature space it was trained "
            f"on; this analyzer produces '{pooling.FEATURE}'. Re-save the "
            f"bundle with its `feature` recorded, or retrain it."
        )
    if feature != pooling.FEATURE:
        raise HeadMismatch(
            f"{model_path} was trained on '{feature}' features; this analyzer "
            f"produces '{pooling.FEATURE}'. Retrain the head, or run the "
            f"backbone it belongs to."
        )
    width = head_width(bundle)
    if width and width != pooling.POOLED_DIM:
        raise HeadMismatch(
            f"{model_path} expects {width}-dim features "
            f"({feature or 'backbone unrecorded'}); this analyzer produces "
            f"{pooling.POOLED_DIM} ({pooling.FEATURE}). Retrain the head, or run "
            f"the backbone it belongs to."
        )
    return width


class SpeciesHead:
    """One species' call-type classifier plus its per-class reliability."""

    def __init__(self, display, model_path, metrics_path):
        bundle = joblib.load(model_path)
        self.display = display
        self.path = Path(model_path)
        self.dim = _check_bundle(bundle, model_path)
        self.feature = bundle.get("feature")
        #: A one-vs-rest head's probabilities are independent and do not sum to
        #: one, so a second high class means it heard two things. A softmax's do
        #: compete, so the same shape of number means something weaker.
        self.multi_label = bool(bundle.get("multi_label"))
        self.classifier = bundle["model"]
        self.classes = list(bundle["classes"])
        auc = {}
        if metrics_path.exists():
            auc = json.loads(metrics_path.read_text()).get("per_class_auc", {})
        self.reliability = {c: reliability_tier(auc.get(c)) for c in self.classes}

    @property
    def fingerprint(self):
        """Six hex of the bundle's bytes — which *build* of this head, not which.

        `make train-crow` has been run more than once and every analysis it
        produced records the same model_version string, so there is no way to
        tell which of them a stored call type came from. The species name says
        what the head is for; this says which one actually ran.
        """
        return hashlib.sha256(self.path.read_bytes()).hexdigest()[:6]

    #: Below this a runner-up is not worth a second look. Not a decision
    #: threshold — the top answer is still whatever scored highest — only the
    #: bar for mentioning that something else was also heard.
    ALTERNATE_MIN = 0.30

    def probabilities(self, embeddings):
        """{class: probability} for one pooled span. The shared primitive."""
        proba = self.classifier.predict_proba(pool(embeddings).reshape(1, -1))[0]
        return dict(zip(self.classes, (float(p) for p in proba)))

    def localise(self, windows, wanted):
        """Where inside a region each `wanted` class peaks.

        The region-level answer says an 18-second span holds a beg AND a caw; it
        cannot say the caw is at 26s. This slides a shorter span across the same
        windows and reports, per class, the sub-span where it scores highest.

        Two things it is not. It is not a detector — the resolution is the slide
        width, so "at 24-33s" means "somewhere in there", and a second caw in the
        same region is invisible behind the first. And it is not a re-scoring of
        the region: the headline `call_type` and `confidence` still come from
        pooling the whole region, because that is what the ladder in
        experiments/0036/capture_104.py shows is most accurate.

        Returns {} when the region is too short to slide anything wider than
        itself, which is the honest answer rather than a span equal to the region.
        """
        if len(windows) <= LOCALISE_WINDOWS:
            return {}
        offsets = list(range(0, len(windows) - LOCALISE_WINDOWS + 1, LOCALISE_STEP))
        scored = {cls: [] for cls in wanted}
        for i in offsets:
            chunk = windows[i:i + LOCALISE_WINDOWS]
            probs = self.probabilities([w["emb"] for w in chunk])
            for cls in wanted:
                scored[cls].append(probs.get(cls))

        found = {}
        for cls, series in scored.items():
            if not any(p is not None for p in series):
                continue          # a class this head does not have
            peak = max(p for p in series if p is not None)
            best = series.index(peak)
            # Adjacent slides overlap by all but one window, so neighbouring
            # scores are near-ties and the argmax alone is over-precise: on
            # capture 104 the two best sub-spans differ by 0.006. Grow outwards
            # while the score stays close to the peak and report the span they
            # agree on, which is a claim the numbers actually support.
            lo = hi = best
            floor = peak * LOCALISE_TOLERANCE
            while lo > 0 and (series[lo - 1] or 0) >= floor:
                lo -= 1
            while hi < len(series) - 1 and (series[hi + 1] or 0) >= floor:
                hi += 1
            found[cls] = {
                "start": windows[offsets[lo]]["start"],
                "end": windows[offsets[hi] + LOCALISE_WINDOWS - 1]["end"],
                "peak": round(peak, 3),
            }
        return found

    def predict(self, embeddings):
        """(call type, its probability, other classes worth mentioning).

        The third value is the whole reason this changed. A region can hold
        more than one call — capture 104 has an adult cawing over a fledgling's
        begging at 12s and 27s — and the old version took `argmax` and dropped
        everything else on the floor. The runner-up was already computed.

        For a multi-label head the probabilities are independent and do not sum
        to one, so two can be high at once and `alternates` is a real second
        answer. For the legacy softmax heads they compete, so a strong runner-up
        means the head was torn rather than that it heard two things — same
        field, weaker claim, which is why `multi_label` travels with it.
        """
        ranked = sorted(self.probabilities(embeddings).items(),
                        key=lambda pair: -pair[1])
        top, confidence = ranked[0]
        alternates = [{"call_type": c, "confidence": round(p, 3)}
                      for c, p in ranked[1:] if p >= self.ALTERNATE_MIN]
        return top, round(confidence, 3), alternates


class HeadRegistry:
    """Maps a detected species (by common name) to its call-type head, if any."""

    def __init__(self):
        self.heads = {}
        for directory in sorted(p for p in MODELS_DIR.glob("*") if p.is_dir()):
            model = directory / "calltype_clf.joblib"
            if model.exists():
                display = directory.name.replace("-", " ").title()
                self._add(display, model, directory / "metrics.json")

    def _add(self, display, model_path, metrics_path):
        self.heads[display.lower()] = SpeciesHead(display, model_path, metrics_path)

    def for_species(self, common_name):
        return self.heads.get((common_name or "").strip().lower())

    def reliability_payload(self):
        return {h.display: h.reliability for h in self.heads.values()}

    def version(self):
        """What actually ran, in a form a stored analysis can be grouped by.

        Carries three things the old "heads:American Crow+Rook" did not: which
        backbone produced the embeddings, and which *build* of each head read
        them. Free text by design — analysis_results.model_version has no
        schema, so this needs no migration.
        """
        heads = "+".join(f"{h.display.lower().replace(' ', '-')}@{h.fingerprint}"
                         for h in sorted(self.heads.values(), key=lambda h: h.display))
        return (f"{pooling.BACKBONE}/{BIRDNET_VERSION}+{ANALYSIS_FILTER} "
                f"heads:{heads or 'none'}")


print("loading BirdNET + call-type heads…", flush=True)
with contextlib.redirect_stdout(DEVNULL):
    ANALYZER = Analyzer()
HEADS = HeadRegistry()
print(f"ready — heads: {', '.join(sorted(h.display for h in HEADS.heads.values())) or 'none'}",
      flush=True)


class NoAudioTrack(ValueError):
    """The file has no sound in it at all.

    A real state rather than a fault: the field app films *muted* on purpose, so
    the separate WAV stays the pristine signal the model was trained on. A phone
    video handed to the analyzer therefore has nothing to analyze — and the
    caller wants to be told that, not handed ffmpeg's exit status.
    """


def has_audio_track(src: Path) -> bool:
    """Whether the container holds any audio stream at all.

    Only a *successful* probe may answer no. This used to read stdout alone,
    so a corrupt upload — or a box with no ffprobe — was diagnosed as "no
    audio stream": a wrong answer delivered with confidence, about the one
    condition (deliberately muted video) that is not a fault.
    """
    try:
        probe = _guarded(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(src)],
            text=True,
        )
    except FileNotFoundError as missing:
        raise RuntimeError("ffprobe is not installed — the analyzer cannot "
                           "read media containers without it") from missing
    if probe.returncode != 0:
        raise ValueError(
            f"ffprobe could not read {src.name}: "
            f"{probe.stderr.strip()[:200] or f'exit {probe.returncode}'}")
    return "audio" in probe.stdout


def to_wav(src: Path) -> Path:
    """Extract mono 48kHz audio to a temp WAV — robust for mp3/wav/mp4/etc.,
    so BirdNET always gets clean PCM regardless of the container.

    Checks for sound first. Without it a silent file fails as a raw subprocess
    error, which says "the analyzer crashed" when the truth is "there is nothing
    here to listen to".
    """
    if not has_audio_track(src):
        raise NoAudioTrack(f"{src.name} has no audio stream")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    _guarded(
        ["ffmpeg", "-v", "quiet", "-y", "-i", str(src),
         "-ac", "1", "-ar", "48000", tmp.name],
        check=True,
    )
    return Path(tmp.name)


def highpassed(src: Path) -> Path:
    """The analysis rendering: ANALYSIS_FILTER applied, to a temp WAV.

    Two ffmpeg biquads ≈ the 4th-order Butterworth 0031 measured. The caller
    owns the temp file. Quality measurement must NOT be fed this — its low-band
    noise floor is measured over the band this removes.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    _guarded(
        ["ffmpeg", "-v", "quiet", "-y", "-i", str(src),
         "-af", "highpass=f=300,highpass=f=300",
         "-ac", "1", "-ar", "48000", tmp.name],
        check=True,
    )
    return Path(tmp.name)


def waveform_envelope(path: Path):
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "f32le",
           "-ac", "1", "-ar", "4000", "-"]
    raw = _guarded(cmd).stdout
    y = np.abs(np.frombuffer(raw, dtype=np.float32))
    if y.size == 0:
        return [], 0.0
    duration = y.size / 4000.0
    bins = np.array_split(y, min(WAVEFORM_BINS, max(1, y.size)))
    env = np.array([b.max() if b.size else 0.0 for b in bins])
    if env.max() > 0:
        env = env / env.max()
    return [round(float(v), 3) for v in env], round(duration, 2)


def corvid_name(det):
    """The detection's common name if it is a corvid, else None."""
    blob = f"{det.get('common_name','')} {det.get('scientific_name','')}".lower()
    return det.get("common_name") if any(t in blob for t in CROW_TERMS) else None


def analyze(path: Path, lat=None, lon=None, when=None):
    """Corvid call regions in a recording.

    `lat`/`lon`/`when` turn on BirdNET's species-occurrence filter, and they
    matter more than they look. The model is global: without them it will
    happily name a House Crow (South Asia) or a Carrion Crow (Europe) in Utah,
    and because both have trained call-type heads, the wrong species then gets a
    confidently-labelled call type hung off it. A misdetection that stops at
    "some corvid" is recoverable; one that reaches the training manifest as a
    labelled Carrion Crow is not.

    All three are optional because a clip uploaded from a browser has no GPS.
    Without them the filter is off and the species should be read with
    suspicion — `location_filtered` on each call says which it was.
    """
    located = lat is not None and lon is not None
    # The filter lives HERE, not in the worker, so every caller of analyze()
    # gets the same preprocessing that model_version claims — and the worker's
    # separate quality.measure call keeps the unfiltered rendering it needs.
    filtered = highpassed(path)
    try:
        with contextlib.redirect_stdout(DEVNULL):
            rec = Recording(
                ANALYZER, str(filtered), min_conf=0.1,
                **({"lat": float(lat), "lon": float(lon)} if located else {}),
                **({"date": when} if when is not None else {}),
            )
            rec.analyze()
            rec.extract_embeddings()
    finally:
        filtered.unlink(missing_ok=True)
    emb_by_start = {round(s["start_time"], 2): np.array(s["embeddings"])
                    for s in rec.embeddings}

    windows = []
    for det in rec.detections:
        species = corvid_name(det)
        if species is None or det["confidence"] < CANDIDATE_MIN_CONF:
            continue
        emb = emb_by_start.get(round(det["start_time"], 2))
        if emb is None:
            continue
        windows.append({
            "start": round(float(det["start_time"]), 2),
            "end": round(float(det["end_time"]), 2),
            "conf": float(det["confidence"]),
            "species": species,
            "scientific_name": det.get("scientific_name", ""),
            "candidate": det["confidence"] < CROW_MIN_CONF,
            "emb": emb,
        })
    windows.sort(key=lambda w: w["start"])
    return [{**classify_region(r), "location_filtered": located}
            for r in group_regions(windows)]


def group_regions(windows):
    """Fuse same-species windows within REGION_GAP into one call region (pooling
    needs several 3s segments to see temporal spread)."""
    regions = []
    for w in windows:
        last = regions[-1][-1] if regions else None
        # Candidates never fuse with confident windows. A region is one thing or
        # the other, or a single uncertain window would drag a confirmed call
        # into the maybe pile — or worse, borrow its confidence.
        if (last and w["species"] == last["species"]
                and w["candidate"] == last["candidate"]
                and w["start"] - last["end"] <= REGION_GAP):
            regions[-1].append(w)
        else:
            regions.append([w])
    return regions


def classify_region(region):
    species = region[0]["species"]
    head = HEADS.for_species(species)
    call_type, confidence, alternates = None, None, []
    multi_label = False
    if head is not None:
        call_type, confidence, alternates = head.predict([w["emb"] for w in region])
        multi_label = head.multi_label
        # Where each runner-up peaks, added to the alternate it belongs to rather
        # than to a column of its own. `alternates` is already "what else did it
        # hear"; this makes it "what else, and where", which needs no migration
        # and no change in any consumer — the dashboard and the phone read
        # call_type and confidence and ignore keys they do not know.
        #
        # Only the alternates get a span. The top class does not need one: the
        # region already is its span, and that is what it was scored on.
        if alternates:
            where = head.localise(region, [a["call_type"] for a in alternates])
            for alt in alternates:
                found = where.get(alt["call_type"])
                if found:
                    alt.update(found)
    return {
        "start": region[0]["start"],
        "end": region[-1]["end"],
        "species": species,
        "scientific_name": region[0]["scientific_name"],
        "call_type": call_type,
        "confidence": confidence,
        # Other call types the head also heard in this span. Empty for a
        # confident single call; populated when a region holds two, which is
        # what an 18-second "begging" region with a caw in it looks like.
        "alternates": alternates,
        # Whether those alternates are independent probabilities or a softmax's
        # runner-up. Different claims, so the consumer is told which.
        "multi_label": multi_label,
        "crow_conf": round(max(w["conf"] for w in region), 3),
        # The model named a corvid but was not sure. Offered for labelling,
        # counted as nothing until somebody says.
        "candidate": region[0]["candidate"],
    }
