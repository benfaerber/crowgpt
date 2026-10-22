"""Can BirdNET hear a contact call as a crow at all?

Ben, 2026-08-09, after the trainer shipped and he had learned the sound: if
species detection already fires on contact calls, the existing corpus scan
becomes the contact-bout finder and his trained ear the filter — the calls the
call-type head cannot see (FUTURE's contact entry) could be *found* without a
head existing yet.

THE TRAP THIS DESIGN AVOIDS. The trainer's contact clips were cut FROM
BirdNET detection windows, so scoring those would measure BirdNET on exactly
the audio BirdNET already liked. Here every recording is segmented by 0013's
energy detector instead — corvid-band bursts against the recording's own
floor, at the 12 dB threshold 0013 validated, no BirdNET anywhere in it — and
every bout gets a 3 s window (BirdNET's own unit) scored for corvid
confidence.

ARMS, MATCHED BY SPECIES, because the question is about the call type and
species is the obvious confound:

    contact   every downloaded recording whose recordist metadata says
              contact (Hooded Crow, Northern Raven — the corpus has 28)
    alarm     recordings by the same two species asserting alarm, the call
              type BirdNET is known to find, sampled to the same recording
              count per species with a seeded rng

Both arms are recordist-asserted European corvids, so the recording-level
label is one person's word covering the whole file — same grade of truth on
both sides, which is what makes the comparison fair. Nothing here speaks to
American Crow contact calls directly; if contact detects here, the next
question is whether it detects at the window.

READOUT: detection rate over energy bouts at the corpus's own crow_min
threshold, per arm and per species, plus confidence quantiles. Contact at or
near the alarm rate means BirdNET can find contact bouts and the funnel has a
finder. Contact far below means finding them needs the embedding route
(FUTURE's active-learning assist) instead.

    PYTHONPATH=crowgpt/src crowgpt/.venv/bin/python \
        experiments/0060-can-birdnet-hear-a-contact-call/run.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

import numpy as np

from crowgpt.birdnet import BirdNet
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.trainer import CORVID_DB, _read_only, cut

OUT = Path(__file__).resolve().parent

SR = 32000            # the segmenter's analysis rate; BirdNET resamples itself
WINDOW = 3.0          # BirdNET's unit, and the segmenter's bout cap
CAP_SECONDS = 120.0   # one 269 s raven session must not become half an arm
SPECIES = ("Hooded Crow", "Northern Raven")
SEED = 0
BATCH = 100           # bouts per worker call, so progress ticks between them
STRONG = 0.5          # reported alongside crow_min: the "comfortably heard" bar


class Arm:
    """One arm's recordings, resolved by id through the database."""

    def __init__(self, name, rows):
        self.name = name
        self.rows = rows   # (id, species, file_path, duration_seconds)

    @classmethod
    def contact(cls, db):
        return cls("contact", db.execute(
            "select id, species, file_path, duration_seconds from recordings "
            "where downloaded = 1 and lower(call_type) like '%contact%' "
            "  and species in (?, ?) order by id", SPECIES).fetchall())

    @classmethod
    def alarm_matched(cls, db, contact, rng):
        """Alarm recordings, the same count per species as the contact arm."""
        wanted = defaultdict(int)
        for _, species, _, _ in contact.rows:
            wanted[species] += 1
        rows = []
        for species, count in sorted(wanted.items()):
            pool = db.execute(
                "select id, species, file_path, duration_seconds from recordings "
                "where downloaded = 1 and lower(call_type) like '%alarm%' "
                "  and species = ? order by id", (species,)).fetchall()
            picked = rng.choice(len(pool), size=min(count, len(pool)),
                                replace=False)
            rows.extend(pool[i] for i in sorted(picked))
        return cls("alarm", rows)


def bout_clips(samples, sr, segmenter):
    """A 3 s window centred on every energy bout, clamped to the recording."""
    bouts, _ = segmenter.segment(samples, sr)
    length = len(samples) / sr
    clips = []
    for start, end in bouts:
        middle = (start + end) / 2
        lo = min(max(0.0, middle - WINDOW / 2), max(0.0, length - WINDOW))
        hi = min(length, lo + WINDOW)
        clips.append((round(lo, 3), samples[int(lo * sr):int(hi * sr)]))
    return clips


def main():
    segmenter = Segmenter()
    birdnet = BirdNet(sample_rate=SR)
    rng = np.random.default_rng(SEED)

    with _read_only(CORVID_DB) as db:
        contact = Arm.contact(db)
        alarm = Arm.alarm_matched(db, contact, rng)

    run = Run("0060 contact-call detectability",
              ["segment", "birdnet", "report"])

    bouts = []   # one row per energy bout, both arms interleaved by build order
    audio = []
    with run.stage("segment") as stage:
        arms = [(arm, row) for arm in (contact, alarm) for row in arm.rows]
        for done, (arm, (rec_id, species, file_path, duration)) in enumerate(arms, 1):
            seconds = min(float(duration or CAP_SECONDS), CAP_SECONDS)
            samples, sr = cut(file_path, 0.0, seconds, sr=SR)
            for start, clip in bout_clips(samples, sr, segmenter):
                bouts.append({"arm": arm.name, "recording": rec_id,
                              "species": species, "start": start})
                audio.append(clip)
            stage.update(done, len(arms),
                         f"{len(bouts)} bouts · {arm.name} {rec_id}")

    crow_min = None
    with run.stage("birdnet") as stage:
        for lo in range(0, len(audio), BATCH):
            confidences, crow_min = birdnet.confidence(audio[lo:lo + BATCH])
            for row, confidence in zip(bouts[lo:], confidences):
                row["confidence"] = confidence
            stage.update(min(lo + BATCH, len(audio)), len(audio))

    with run.stage("report"):
        summary = {}
        for arm in ("contact", "alarm"):
            rows = [b for b in bouts if b["arm"] == arm]
            found = [b["confidence"] for b in rows
                     if b["confidence"] is not None]
            hits = [c for c in found if c >= crow_min]
            summary[arm] = {
                "recordings": len({b["recording"] for b in rows}),
                "bouts": len(rows),
                "detected": len(hits),
                "rate": round(len(hits) / len(rows), 3) if rows else None,
                "strong_rate": round(sum(1 for c in found if c >= STRONG)
                                     / len(rows), 3) if rows else None,
                "confidence_quartiles": [round(float(q), 3) for q in
                                         np.percentile(found, [25, 50, 75])]
                                        if found else None,
                "by_species": {},
            }
            for species in SPECIES:
                mine = [b for b in rows if b["species"] == species]
                mine_hits = [b for b in mine if (b["confidence"] or 0) >= crow_min]
                if mine:
                    summary[arm]["by_species"][species] = {
                        "bouts": len(mine), "detected": len(mine_hits),
                        "rate": round(len(mine_hits) / len(mine), 3)}

        payload = {"seed": SEED, "crow_min": crow_min, "strong": STRONG,
                   "cap_seconds": CAP_SECONDS, "window": WINDOW,
                   "summary": summary, "bouts": bouts}
        (OUT / "results.json").write_text(json.dumps(payload, indent=1))

        for arm, s in summary.items():
            run.note(f"{arm}: {s['detected']}/{s['bouts']} bouts >= crow_min "
                     f"({s['rate']:.0%}), strong {s['strong_rate']:.0%}")

    print(json.dumps(summary, indent=2))
    print(f"\ncrow_min {crow_min} · results in {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
