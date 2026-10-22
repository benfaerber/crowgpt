"""Which of Ben's own crow recordings are good enough to publish?

Asked for the promo site: "can we pick the creme de la creme of crow calls".
There was no such list anywhere in the repo, so this builds one and writes down
how, because "the best clips" is otherwise a judgement nobody can re-derive.

WHY THE UNIT IS A LABELLED SPAN AND NOT A CAPTURE. The 24 kept captures run 14 s
to 172 s and most of them are mostly ambience — the crow is a few seconds
somewhere inside. Ranking captures by whole-file SNR picks long quiet recordings
that happen to contain one distant caw. The `labels` table already holds 57
human-marked spans on those captures with a call type on each, which is the only
place in this project that says "the crow is *here*". So the candidates are spans.

WHY NOT THE CORPUS, AND WHY NOT THE GENERATOR. Two hard constraints, neither
about quality:

  - The archive corpus is out. Some of those recordings are CC BY-NC-**ND** and the
    corpus's derived units are explicitly not redistributable. A public promo page
    cannot carry them, and generated clips are trained on them.
  - The generator is out for a second reason: 0053 is mid-flight and blinded.
    Publishing "the best generated clips" while Ben is grading channel-000
    against channel-081 would hand him the answer.

Ben's own field recordings have neither problem. All 24 kept captures are from
device 10, his daily phone, and the ★ keep flag is the thing that distinguishes a
real field recording from seeded archive audio and test uploads (CLAUDE.md).

WHAT IS MEASURED, per span rather than per file:

    band_snr_db     energy in the 800-4000 Hz corvid band inside the span,
                    against the quietest tenth of the whole recording. The band
                    is `analyzer`'s, not invented here.
    peak_dbfs       to catch clipping, which whole-capture SNR does not. Three
                    kept captures peak at exactly 0.0 dBFS with clip events
                    recorded, and one of them is the top-ranked capture by SNR.
    dropout         the longest CONTIGUOUS run of digital silence. Measured as a
                    run and not as a fraction, which was the first version's
                    second mistake: quiet audio crosses zero constantly and
                    individual samples fall under any absolute floor, so
                    "fraction of silent samples" flagged captures 69, 88 and 154
                    at 1.4-2.8% when none of them has a run longer than 20 ms.
                    Capture 100 does — three of them, of exactly 3.00 s, at 19.0,
                    45.5 and 63.0 seconds. That is a real fault and its stored
                    `band_snr_db` is 0.0, so the analyzer choked on it too. The
                    first version also took its noise floor inside one of those
                    gaps and reported SNRs of 156-168 dB, putting nine clips from
                    the one glitched recording in the top nine places.
    onset           how quickly the call arrives, so a span that opens with two
                    seconds of nothing can be trimmed rather than published.

NOTHING HERE DECIDES. The output is a ranked shortlist and a folder of excerpts
for Ben to listen to, because "sounds good" is his call and this is the third time
in this project that an automated ranking has ordered arms correctly and located
nothing.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]

OUT = Path(__file__).resolve().parent
CLIPS = OUT / "candidates"
SHORT_DIR = OUT / "shortlist"

#: The corvid band, from analyzer rather than restated. 0031 and 0036 both use it.
BAND = (800, 4000)

#: Call types worth publishing. `unsure` and `not_a_crow` are excluded because the
#: recordist already said he could not vouch for them.
PUBLISHABLE = ("alarm call", "call", "begging")

#: A promo clip has to stand alone. Under this and it is a fragment; over it and
#: nobody listens to the end.
MIN_SECONDS, MAX_SECONDS = 1.2, 12.0

#: Room either side of the label, so a call does not start on sample zero.
PAD_SECONDS = 0.35

#: How many clips go in front of Ben. Small on purpose: he is the instrument and
#: 34 clean candidates is a sitting, not a shortlist.
SHORTLIST = 8

#: Lead-in kept ahead of the call after trimming.
TRIM_LEAD_SECONDS = 0.25

#: Below this a sample is a hardware dropout, not quiet ambience. Real room noise
#: on a phone mic never reaches exact zero.
SILENCE_FLOOR = 1e-7

#: The shortest silent run that is a fault rather than a zero-crossing. A phone
#: mic's room noise never holds exact zero for this long.
MAX_DROPOUT_SECONDS = 0.05


def band_energy(samples, rate, low=BAND[0], high=BAND[1]):
    """RMS in the corvid band, via a plain FFT — no scipy dependency needed."""
    if samples.size < 256:
        return 0.0
    spectrum = np.fft.rfft(samples * np.hanning(samples.size))
    freqs = np.fft.rfftfreq(samples.size, 1.0 / rate)
    keep = (freqs >= low) & (freqs <= high)
    if not keep.any():
        return 0.0
    return float(np.sqrt((np.abs(spectrum[keep]) ** 2).sum()) / samples.size)


def db(value, floor=1e-12):
    return 20.0 * np.log10(max(value, floor))


def frame_band_db(samples, rate, hop=0.05, drop_silent=False):
    """Band energy per 50 ms frame, in dB — the noise floor comes from this.

    `drop_silent` throws away frames that are digitally silent. A floor taken
    across them is a floor measured inside a dropout, which is how the first
    version of this script produced 168 dB SNRs out of a glitched recording.
    """
    step = max(1, int(rate * hop))
    frames, values = [], []
    for i in range(0, max(1, samples.size - step), step):
        chunk = samples[i:i + step]
        if drop_silent and np.max(np.abs(chunk)) < SILENCE_FLOOR:
            continue
        values.append(db(band_energy(chunk, rate)))
    return np.array(values) if values else np.array([db(0.0)])


def longest_dropout(samples, rate):
    """The longest contiguous run of digital silence, in seconds.

    A RUN, NOT A FRACTION. Quiet audio crosses zero on almost every cycle and
    those samples fall below any absolute floor, so counting silent samples
    reports 1-3% on perfectly good recordings. What a listener hears as a fault
    is a *gap*, and only a run measures one.
    """
    if samples.size == 0:
        return 0.0
    silent = np.abs(samples) < SILENCE_FLOOR
    if not silent.any():
        return 0.0
    # Run lengths via the boundaries of the silent mask.
    padded = np.concatenate(([False], silent, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    runs = edges[1::2] - edges[0::2]
    return float(runs.max() / rate) if runs.size else 0.0


def onset_seconds(samples, rate):
    """How far into the span the call actually starts."""
    frames = frame_band_db(samples, rate)
    if frames.size < 3:
        return 0.0
    ceiling = np.percentile(frames, 95)
    floor = np.percentile(frames, 10)
    if ceiling - floor < 3.0:
        return 0.0
    hot = np.flatnonzero(frames >= floor + 0.5 * (ceiling - floor))
    return float(hot[0] * 0.05) if hot.size else 0.0


def field_db():
    """The served database. Same rule `fieldserver.core.paths` uses.

    Re-derived rather than imported because this runs in crowgpt's venv, which is
    the one carrying numpy and soundfile; fieldserver's has neither. Honouring
    FIELD_DB matters — it is how the server is pointed at a copy.
    """
    import os

    return Path(os.environ.get("FIELD_DB")
                or REPO / "fieldserver" / "instance" / "field.db")


def main():
    import sqlite3

    import soundfile as sf

    db_path = field_db()
    if not db_path.exists():
        raise SystemExit(f"no database at {db_path}; set FIELD_DB")
    media_dir = db_path.parent / "media"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    spans = [dict(r) for r in conn.execute("""
        SELECT l.id AS label_id, l.capture_id, l.start_sec, l.end_sec,
               l.call_type, l.species, l.caller_role,
               c.name AS capture_name, c.duration_sec,
               m.storage_ref, m.sample_rate,
               q.band_snr_db AS capture_snr, q.clip_events, q.peak_dbfs AS capture_peak
        FROM labels l
        JOIN captures c ON c.id = l.capture_id
        JOIN media m ON m.capture_id = c.id AND m.kind = 'audio'
        LEFT JOIN capture_quality q ON q.capture_id = c.id
        WHERE c.keep = 1 AND l.label_source = 'human'
        ORDER BY l.capture_id, l.start_sec""")]

    CLIPS.mkdir(parents=True, exist_ok=True)
    cache = {}
    rows = []
    skipped = {"call_type": 0, "too_short": 0, "too_long": 0, "no_audio": 0}

    for span in spans:
        if span["call_type"] not in PUBLISHABLE:
            skipped["call_type"] += 1
            continue
        length = (span["end_sec"] or 0) - (span["start_sec"] or 0)
        if length < MIN_SECONDS:
            skipped["too_short"] += 1
            continue
        if length > MAX_SECONDS:
            skipped["too_long"] += 1
            continue

        path = media_dir / span["storage_ref"]
        if not path.exists():
            skipped["no_audio"] += 1
            continue
        if path not in cache:
            audio, rate = sf.read(path, dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            cache[path] = (audio, rate)
        audio, rate = cache[path]

        start = max(0, int((span["start_sec"] - PAD_SECONDS) * rate))
        end = min(audio.size, int((span["end_sec"] + PAD_SECONDS) * rate))
        clip = audio[start:end]
        if clip.size < int(MIN_SECONDS * rate):
            skipped["too_short"] += 1
            continue

        # The floor comes from the WHOLE recording, not from inside the span: a
        # span is chosen to be full of crow, so its own quiet frames are the gaps
        # between caws and would flatter every clip equally.
        floor = float(np.percentile(
            frame_band_db(audio, rate, drop_silent=True), 10))
        gap = longest_dropout(clip, rate)
        signal = db(band_energy(clip, rate))
        peak = db(float(np.max(np.abs(clip))) if clip.size else 0.0)

        rows.append({
            "label_id": span["label_id"],
            "capture_id": span["capture_id"],
            "capture_name": span["capture_name"],
            "call_type": span["call_type"],
            "caller_role": span["caller_role"],
            "start_sec": round(span["start_sec"], 2),
            "end_sec": round(span["end_sec"], 2),
            "seconds": round(clip.size / rate, 2),
            "span_snr_db": round(signal - floor, 1),
            "peak_dbfs": round(peak, 1),
            "clipped": bool(span["clip_events"]) or bool(peak > -0.2),
            "dropout_sec": round(gap, 3),
            "dropout": bool(gap > MAX_DROPOUT_SECONDS),
            "onset_sec": round(onset_seconds(clip, rate), 2),
            "capture_snr_db": round(span["capture_snr"] or 0, 1),
            "sample_rate": rate,
            "_clip": clip,
            "_rate": rate,
        })

    # Dropouts and clipping sort last regardless of SNR: both are defects a
    # listener cannot un-hear and a promo page cannot excuse.
    rows.sort(key=lambda r: (r["dropout"], r["clipped"], -r["span_snr_db"]))

    kept_audio = {r["label_id"]: r["_clip"] for r in rows}
    for rank, row in enumerate(rows, 1):
        clip, rate = row.pop("_clip"), row.pop("_rate")
        peak = float(np.max(np.abs(clip))) or 1.0
        name = (f"{rank:02d}-{row['call_type'].replace(' ', '-')}"
                f"-cap{row['capture_id']}-l{row['label_id']}.wav")
        sf.write(CLIPS / name, np.clip(clip / peak * 0.95, -1, 1), rate,
                 format="WAV", subtype="PCM_16")
        row["file"] = name
        row["rank"] = rank

    # --- the shortlist ---
    #
    # ONE PER CAPTURE, AND EVERY CALL TYPE REPRESENTED. Ranking by SNR alone hands
    # back six clips of the same family in the same flower bed: 25 of the 34 clean
    # candidates are alarm calls and capture 100 supplies seven. A promo page wants
    # range, and 0042's finding is the reason to care — timbre varies 6.2x more
    # between recordings than within one, so two clips from one capture are nearly
    # the same clip as far as a listener is concerned.
    clean = [r for r in rows if not r["dropout"] and not r["clipped"]]
    shortlist, seen_captures = [], set()
    for call_type in PUBLISHABLE:                      # a seat for each type first
        for row in clean:
            if row["call_type"] == call_type and row["capture_id"] not in seen_captures:
                shortlist.append(row)
                seen_captures.add(row["capture_id"])
                break
    for row in clean:                                  # then best remaining captures
        if len(shortlist) >= SHORTLIST:
            break
        if row["capture_id"] not in seen_captures:
            shortlist.append(row)
            seen_captures.add(row["capture_id"])
    shortlist.sort(key=lambda r: -r["span_snr_db"])

    SHORT_DIR.mkdir(parents=True, exist_ok=True)
    for seat, row in enumerate(shortlist, 1):
        clip, rate = np.array(kept_audio[row["label_id"]]), row["sample_rate"]
        # Trim the run-up so the call starts promptly. Capture 69's best span does
        # not open for 3.15 s, which on a promo page is three seconds of nothing.
        lead = max(0.0, row["onset_sec"] - TRIM_LEAD_SECONDS)
        if lead > 0.1:
            clip = clip[int(lead * rate):]
        peak = float(np.max(np.abs(clip))) or 1.0
        name = (f"{seat}-{row['call_type'].replace(' ', '-')}"
                f"-cap{row['capture_id']}.wav")
        sf.write(SHORT_DIR / name, np.clip(clip / peak * 0.95, -1, 1), rate,
                 format="WAV", subtype="PCM_16")
        row["shortlist_file"] = name
        row["shortlist_seconds"] = round(clip.size / rate, 2)
        row["trimmed_sec"] = round(lead, 2)

    (OUT / "candidates.json").write_text(json.dumps(
        {"band_hz": BAND, "publishable_call_types": list(PUBLISHABLE),
         "min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS,
         "pad_seconds": PAD_SECONDS, "skipped": skipped,
         "shortlist": [r["shortlist_file"] for r in shortlist],
         "candidates": rows}, indent=2))

    print(f"{len(spans)} human labels on kept captures -> {len(rows)} candidates")
    print(f"skipped: {skipped}\n")
    print(f"{'#':>3}{'type':>12}{'cap':>5}{'secs':>6}{'SNR':>7}"
          f"{'peak':>7}{'onset':>7}{'defect':>8}  capture")
    for row in rows:
        defect = "dropout" if row["dropout"] else ("clipped" if row["clipped"] else "")
        print(f"{row['rank']:>3}{row['call_type']:>12}{row['capture_id']:>5}"
              f"{row['seconds']:>6.1f}{row['span_snr_db']:>7.1f}"
              f"{row['peak_dbfs']:>7.1f}{row['onset_sec']:>7.2f}"
              f"{defect:>8}  {row['capture_name'][:36]}")
    print(f"\nall {len(rows)} candidates -> {CLIPS}")
    print(f"\nshortlist for Ben ({len(shortlist)} clips -> {SHORT_DIR}):")
    print(f"{'':>2}{'type':>12}{'cap':>5}{'secs':>6}{'SNR':>7}{'trim':>6}  capture")
    for row in shortlist:
        print(f"{'':>2}{row['call_type']:>12}{row['capture_id']:>5}"
              f"{row['shortlist_seconds']:>6.1f}{row['span_snr_db']:>7.1f}"
              f"{row['trimmed_sec']:>6.1f}  {row['capture_name'][:38]}")


if __name__ == "__main__":
    main()
