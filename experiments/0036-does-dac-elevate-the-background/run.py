"""Does DAC lift the background, or does EnCodec quietly suppress it?

Ben, mid-sitting on 2026-08-02, unprompted: *"it almost seems like the dac24
elevates footsteps and wind sounds?"*

WHY IT IS PLAUSIBLE RATHER THAN A COINCIDENCE. EnCodec 24 kHz is trained on
speech and music. DAC is trained on environmental audio as well, which is
exactly why 0017 reached for it in the first place. A codec spends its capacity
where its training distribution says the information is, so a broadband
transient (a footstep) and low-frequency rumble (wind) are the kind of content
one would model and the other would treat as noise to be spent away.

WHICH DIRECTION THE ERROR RUNS MATTERS MORE THAN THE EFFECT. "DAC elevates the
background" and "EnCodec attenuates it" sound like the same observation and are
opposite findings:

  - if DAC sits above RAW, DAC is adding something that was not there;
  - if EnCodec sits below RAW and DAC matches it, then EnCodec has been quietly
    denoising every clip this project has produced, and the thing Ben is
    noticing in DAC is fidelity rather than damage.

Raw is the referee and neither arm can be read without it.

WHY IT IS NOT A SIDE QUESTION. CrowGPT is about what crows say AND what was
happening when they said it — the calls x context matrix is the whole point. A
tokenizer that discards ambience is discarding the context half. And every bout
deliberately carries real leading ambience (codec.py's LEAD_FRAMES) so the
causal encoder settles, which means background is in every training sequence
whether or not anyone was measuring it.

IT IS ALSO A POSSIBLE CONFOUND IN THE SITTINGS. If DAC arms carry audibly more
background than raw, a listener can separate them on something other than
quality. 0033 and 0034 both scored DAC near raw, so it did not act as a penalty
there — but "did not penalise" is not "was not audible", and this measures the
size of the cue.

METHOD. Segment each bout with the shipped 12 dB detector to find the call
units, then measure everything that is NOT a unit — the gaps and the leading
ambience. Per-band RMS in dB, so wind (low), the corvid band, and hiss (high)
are separable. The detector runs on the RAW audio only and its regions are
reused for every arm, because letting it re-segment each arm would compare
different stretches of time.
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
from scipy.signal import stft

from crowgpt.codec import Codec, normalise
from crowgpt.dac_codec import DacCodec
from crowgpt.metrics import bootstrap_ci
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
N_BOUTS = 60
MIN_SECONDS = 1.5      # needs room for both call and non-call regions
SR = 24000
BANDS = {"wind_below_500": (20, 500), "corvid_800_4k": (800, 4000), "hiss_above_6k": (6000, 11000)}


def band_rms_db(y, sr, mask_fn):
    """Per-band RMS over the frames mask_fn keeps, in dB."""
    freqs, times, spectrum = stft(y, fs=sr, nperseg=1024, noverlap=768)
    power = np.abs(spectrum) ** 2
    keep = mask_fn(times)
    out = {}
    for name, (lo, hi) in BANDS.items():
        rows = (freqs >= lo) & (freqs <= hi)
        if not keep.any() or not rows.any():
            out[name] = float("nan")
            continue
        value = power[np.ix_(rows, keep)].mean()
        out[name] = float(10 * np.log10(value + 1e-12))
    return out


def main():
    run = Run("0036 — DOES DAC ELEVATE THE BACKGROUND",
              ["choose", "measure", "report"])
    try:
        store = BoutStore(DATA / "bouts")
        segmenter = Segmenter()

        with run.stage("choose") as stage:
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, chosen = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen or store.index[i]["n_samples"] / SR < MIN_SECONDS:
                    continue
                seen.add(recording)
                chosen.append(i)
                if len(chosen) >= N_BOUTS:
                    break
            stage.say(f"{len(chosen)} bouts, one per recording, >= {MIN_SECONDS}s")

        encodec = Codec(bandwidth=24.0)
        dac = DacCodec(n_codebooks=24, model_type="24khz")
        rows = []
        with run.stage("measure") as stage:
            for n, position in enumerate(chosen, 1):
                raw = normalise(store.audio(store.index[position]))
                _, units = segmenter.segment(raw, SR)
                if not units:
                    continue
                # REGIONS COME FROM RAW AND ARE REUSED FOR EVERY ARM. Letting the
                # detector re-run per arm would compare different stretches of
                # time and quietly turn a level question into a detector question.
                def outside(times, units=units):
                    keep = np.ones_like(times, dtype=bool)
                    for start, end in units:
                        keep &= ~((times >= start) & (times <= end))
                    return keep

                def inside(times, units=units):
                    keep = np.zeros_like(times, dtype=bool)
                    for start, end in units:
                        keep |= (times >= start) & (times <= end)
                    return keep

                arms = {
                    "raw": raw,
                    "encodec32": encodec.decode(encodec.encode(raw))[0],
                    "dac24_24": dac.roundtrip(raw)[0],
                }
                entry = {"bout": int(position)}
                for arm, audio in arms.items():
                    audio = np.asarray(audio, dtype=np.float32)[: raw.size]
                    entry[arm] = {"background": band_rms_db(audio, SR, outside),
                                  "calls": band_rms_db(audio, SR, inside)}
                rows.append(entry)
                stage.update(n, len(chosen))

        with run.stage("report") as stage:
            summary = {"n_bouts": len(rows), "bands": BANDS, "deltas_db_vs_raw": {}}
            for region in ("background", "calls"):
                summary["deltas_db_vs_raw"][region] = {}
                for arm in ("encodec32", "dac24_24"):
                    summary["deltas_db_vs_raw"][region][arm] = {}
                    for band in BANDS:
                        diff = np.array([r[arm][region][band] - r["raw"][region][band]
                                         for r in rows if np.isfinite(r[arm][region][band])])
                        lo, hi = bootstrap_ci(diff)
                        summary["deltas_db_vs_raw"][region][arm][band] = {
                            "mean_db": round(float(diff.mean()), 3),
                            "ci": [round(lo, 3), round(hi, 3)],
                            "excludes_zero": bool(lo > 0 or hi < 0),
                        }
            (OUT / "results.json").write_text(json.dumps(
                {"summary": summary, "per_bout": rows}, indent=2))

            for arm in ("encodec32", "dac24_24"):
                bits = " · ".join(
                    f"{b}={summary['deltas_db_vs_raw']['background'][arm][b]['mean_db']:+.2f}dB"
                    for b in BANDS)
                run.note(f"background vs raw — {arm}: {bits}")
            stage.say("wrote results.json")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
