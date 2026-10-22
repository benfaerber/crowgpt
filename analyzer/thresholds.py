"""The analyzer's tuning constants, importable without loading a model.

Importing `analyzer.birdnet` builds an Analyzer and every call-type head at
module level — several seconds and a lot of resident memory. Three modules
were paying that (behind a subprocess and a redirected stdout) just to read
the numbers below, which is what this file exists to stop: the constants and
the essays that justify them, at zero import cost. `birdnet.py` re-exports
them, so either import path answers.
"""

#: Which BirdNET the embeddings come from. Part of model_version, so a stored
#: analysis records the detector as well as the heads.
BIRDNET_VERSION = "2.4"

#: The preprocessing every analysis input passes through, and part of
#: model_version for the same reason as the detector: stored analyses made
#: before and after it must stay distinguishable. hp300 = a 4th-order 300 Hz
#: high-pass (two ffmpeg biquads), measured in 0008 and re-measured in 0031
#: (confidence up on 4 of 4 mower captures, spurious short regions merged,
#: beat a 19M-parameter denoiser). ANALYSIS ONLY: quality.measure keeps the
#: unfiltered audio, because noise_floor_low_dbfs reads 0-300 Hz — exactly
#: the band this removes — and it is the windshield question's instrument.
ANALYSIS_FILTER = "hp300"

CROW_TERMS = ("crow", "raven", "corvus", "jackdaw", "rook", "magpie")
CROW_MIN_CONF = 0.25
# Below the gate but worth a human's three seconds.
#
# The gate exists because BirdNET names a corvid in a lot of street noise, and a
# corpus of its uncertain guesses is a corpus of traffic. But it also closes a
# loop: the analyzer proposes, the recordist confirms, confirmations become
# training data — so the corpus can only ever hold calls the model already scores
# well, and the faint ones it most needs to learn are filtered out before anyone
# sees them. A real alarm call in capture 88 scored 0.183 and was discarded
# silently; a begging fledgling scored 0.06.
#
# So windows in this band are kept as *candidates*: offered for labelling,
# visibly uncertain, and inert — never exported for training and never in the
# calls x context matrix — until a human rules on them. Saying "not a crow" is
# just as useful an answer, and that is a negative example nothing else produces.
CANDIDATE_MIN_CONF = 0.10
# BirdNET scores on a fixed 3-second grid, so the gap between two detections is
# always a multiple of this. That makes the threshold a choice between exactly
# two behaviours rather than a dial: below 3s merges only *contiguous* windows;
# 3s or above also merges across a silent one, which chains a whole recording
# into a single region as long as something is detected every other window.
DETECTION_WINDOW_SEC = 3.0

#: The old name. It means the *detection* grid and always has — the comment
#: above argues entirely from detector behaviour — but "window" alone stops
#: being unambiguous the moment a second model with a different window supplies
#: the embeddings. Two consumers read it as the detection grid and would keep
#: working while meaning something else: crowgpt/extract.py bins detections with
#: `start_time // WINDOW_SEC`, and experiments/0013 converts window counts into
#: the corpus's reported hours. Renaming while it is still only a rename.
WINDOW_SEC = DETECTION_WINDOW_SEC

# Contiguous only. It was 3.5, and a 39-second recording came back as one region
# labelled `call` — the alarm call at 12s and the song at 36s had been absorbed
# into it. A span that long is mostly not-call as a training example, and the two
# call types it swallowed were the interesting part.
REGION_GAP = DETECTION_WINDOW_SEC / 2
WAVEFORM_BINS = 700

#: How wide a sub-span must be before its pooled vector is worth believing, in
#: 3s windows, and how far the slide moves each step.
#:
#: ONE window is excluded on measurement, not taste: it pools to std=0 and
#: max=mean, leaving a third of the 3072-d feature empty and a third redundant.
#: Experiment 0036 found that degeneracy collapsing predictions toward the
#: dominant class — 41 of 52 field spans called `alarm call` when pooled one
#: window at a time against 25 of 52 pooled over the whole span — and capture
#: 104 shows it producing a *confident* wrong answer: window 12-15s scored alone
#: reads `alarm call` 0.991, which no wider span agrees with.
#:
#: TWO (6s) over three (9s) is tuned on capture 104, the only region in the
#: corpus with a human account of what is inside it. Sliding 6s separates the
#: caw cleanly — call 0.094 at 9-15s against 0.998 at 18-24s — while 9s already
#: reads 0.826 in its first sub-span and 12s saturates at 0.98+ everywhere.
#: One capture is a thin basis for a constant. It is set here because the
#: alternative was an arbitrary choice, and it should be revisited the moment a
#: second region has ground truth to check it against.
LOCALISE_WINDOWS = 2
LOCALISE_STEP = 1

#: How close to the peak a neighbouring sub-span must score to be folded into
#: the reported span. Adjacent slides share all but one window, so their scores
#: are near-ties by construction — capture 104's two best differ by 0.006, and
#: picking one of them would dress a coin-flip as a measurement.
LOCALISE_TOLERANCE = 0.9
