"""Is a contact call lemon-shaped, and does the shape narrow the search?

Ben, 2026-08-09, naming the signature himself this time: contact calls "have
a lemon shaped sound wave" — an envelope that swells in the middle and tapers
at both ends, where an alarm caw slams on and pulses. 0046 turned "modem"
into a stuck codebook and 0059 turned "scream" into duty cycle; this asks the
envelope whether "lemon" is real, because if it is, it becomes the ranking
that narrows 0060's firehose. 0060 proved BirdNET *finds* contact bouts at
the alarm rate — which means it finds everything else at that rate too, and
the trained ear should not have to wade through the alarm-heavy majority to
reach them.

THE UNITS ARE THE SUBJECT, NOT THE BOUTS. A lemon is the shape of one call;
a bout is several calls with gaps, and averaging the gaps in would blur the
one thing being measured. So features are computed per 0013-detector unit on
the in-band linear envelope, then medianed within the bout, on exactly the
bouts 0060 scored — same decode, same segmenter numerics, cross-checked
against 0060's counts so the two experiments are about the same audio.

FEATURES, each a cheap phrasing of "lemon":

    peak_pos    where the unit's envelope peaks, 0..1 — a lemon peaks near
                the middle, a caw's attack peaks early
    centroid    the envelope's centre of mass, 0..1 — same idea, robust to a
                single spiky frame
    symmetry    1 - |2*centroid - 1| — the folded version, so "tapers both
                ways" is one number
    wiggle      total variation of the envelope over twice its peak — an
                ideal rise-and-fall scores 1.0, every extra pulse adds one
    n_peaks     local maxima above half the unit peak — a lemon has one
    unit_sec    unit duration — contact syllables may simply run longer

plus per-bout context: units in the bout and in-burst duty (0059's axis).

READOUT: per-feature AUC (contact vs alarm) at bout level and, because 381
alarm bouts come from only 28 recordings, at recording level too — bout-level
AUC alone would be flattered by recording identity. Then a recording-grouped
cross-validated logistic combo, and the number Ben actually asked for: at a
threshold keeping ~80% of contact bouts, what fraction of alarm bouts
survives. That fraction is the width of the funnel his ear still has to
drink from.

Same honesty caveat as 0060: ground truth is the recordist's word about the
whole recording, both arms equally, European corvids. And alarm is only the
dominant confuser, not the only one — a ranker validated here still meets
begging and song in the wild unmeasured.

    PYTHONPATH=crowgpt/src crowgpt/.venv/bin/python \
        experiments/0061-is-a-contact-call-lemon-shaped/run.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

import numpy as np

from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.trainer import CORVID_DB, _read_only, cut

OUT = Path(__file__).resolve().parent
RESULTS_0060 = OUT.parent / "0060-can-birdnet-hear-a-contact-call" / "results.json"

SR = 32000
CAP_SECONDS = 120.0        # 0060's cap, kept so the bouts are the same bouts
KEEP_CONTACT = 0.80        # the operating point quoted in the answer
FEATURES = ("peak_pos", "centroid", "symmetry", "wiggle", "n_peaks",
            "unit_sec", "n_units", "duty")


class UnitShape:
    """One unit's envelope, described the ways "lemon" could mean."""

    def __init__(self, envelope):
        self.env = np.asarray(envelope, dtype=np.float64)

    def features(self):
        env = self.env
        if env.size < 3 or env.max() <= 0:
            return None
        peak = env.max()
        t = np.arange(env.size)
        centroid = float((t * env).sum() / env.sum()) / (env.size - 1)
        return {
            "peak_pos": float(np.argmax(env)) / (env.size - 1),
            "centroid": centroid,
            "symmetry": 1.0 - abs(2.0 * centroid - 1.0),
            "wiggle": float(np.abs(np.diff(env)).sum() / (2.0 * peak)),
            "n_peaks": self._peaks(env, peak),
            "unit_sec": None,   # filled by the caller, which knows the fps
        }

    @staticmethod
    def _peaks(env, peak):
        rises = np.diff(env) > 0
        maxima = np.flatnonzero(rises[:-1] & ~rises[1:]) + 1
        return int(sum(1 for i in maxima if env[i] >= 0.5 * peak))


def bout_features(env, fps, bout, units):
    """Median unit shape inside one bout, plus the bout's own context."""
    lo, hi = bout
    inside = [(s, e) for s, e in units if s >= lo and e <= hi]
    rows = []
    for start, end in inside:
        s, e = int(start * fps), int(end * fps)
        shaped = UnitShape(env[s:e]).features()
        if shaped is None:
            continue
        shaped["unit_sec"] = end - start
        rows.append(shaped)
    if not rows:
        return None
    out = {name: float(np.median([r[name] for r in rows]))
           for name in rows[0]}
    out["n_units"] = len(rows)
    burst = sum(e - s for s, e in inside)
    out["duty"] = burst / max(hi - lo, 1e-9)
    return out


def auc(scores, labels):
    """Mann-Whitney AUC: P(random contact scores above random alarm)."""
    scores, labels = np.asarray(scores, float), np.asarray(labels, bool)
    pos, neg = scores[labels], scores[~labels]
    if not pos.size or not neg.size:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(order.size)
    ranks[order] = np.arange(1, order.size + 1)
    # midranks for ties, so a constant feature reads 0.5 rather than lying
    combined = np.concatenate([pos, neg])
    for value in np.unique(combined):
        tied = combined == value
        ranks[tied] = ranks[tied].mean()
    return float((ranks[:pos.size].sum() - pos.size * (pos.size + 1) / 2)
                 / (pos.size * neg.size))


def grouped_combo_auc(matrix, labels, groups):
    """Logistic combo, recording-grouped CV so identity cannot leak."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    matrix, labels = np.asarray(matrix), np.asarray(labels)
    scores = np.zeros(len(labels))
    for train, test in GroupKFold(n_splits=5).split(matrix, labels, groups):
        scaler = StandardScaler().fit(matrix[train])
        model = LogisticRegression(max_iter=1000).fit(
            scaler.transform(matrix[train]), labels[train])
        scores[test] = model.predict_proba(scaler.transform(matrix[test]))[:, 1]
    return scores, auc(scores, labels)


def main():
    reference = json.loads(RESULTS_0060.read_text())
    expected = {arm: reference["summary"][arm]["bouts"]
                for arm in ("contact", "alarm")}
    recordings = {}   # id -> (arm, species)
    for row in reference["bouts"]:
        recordings[row["recording"]] = (row["arm"], row["species"])

    with _read_only(CORVID_DB) as db:
        paths = dict(db.execute(
            f"select id, file_path from recordings where id in "
            f"({','.join('?' * len(recordings))})", list(recordings)).fetchall())

    run = Run("0061 lemon-shaped contact calls",
              ["features", "auc"])
    segmenter = Segmenter()

    rows = []
    with run.stage("features") as stage:
        for done, (rec_id, (arm, species)) in enumerate(sorted(recordings.items()), 1):
            samples, sr = cut(paths[rec_id], 0.0, CAP_SECONDS, sr=SR)
            db_env, fps = segmenter.envelope(samples, sr)
            bouts, units = segmenter.segment(samples, sr)
            env = 10 ** (db_env / 20)
            for bout in bouts:
                shaped = bout_features(env, fps, bout, units)
                if shaped is None:
                    continue
                rows.append({"arm": arm, "recording": rec_id,
                             "species": species, "start": round(bout[0], 3),
                             **shaped})
            stage.update(done, len(recordings), f"{len(rows)} bouts")

    counts = defaultdict(int)
    for row in rows:
        counts[row["arm"]] += 1
    drift = {arm: (counts[arm], expected[arm]) for arm in expected
             if abs(counts[arm] - expected[arm]) > expected[arm] * 0.1}
    if drift:
        raise SystemExit(f"re-segmentation drifted from 0060's bouts: {drift} "
                         f"— the two experiments would not be about the same "
                         f"audio")

    with run.stage("auc"):
        labels = [row["arm"] == "contact" for row in rows]
        groups = [row["recording"] for row in rows]
        per_feature = {}
        for name in FEATURES:
            values = [row[name] for row in rows]
            by_recording = defaultdict(list)
            for row in rows:
                by_recording[row["recording"]].append(row[name])
            rec_values = [float(np.median(v)) for v in by_recording.values()]
            rec_labels = [recordings[r][0] == "contact" for r in by_recording]
            # Within-species too: ravens are 58% of contact bouts but 20% of
            # alarm, so a pooled AUC can be species timbre wearing a call-type
            # costume — or a real effect cancelled by one.
            by_species = {}
            for species in sorted({row["species"] for row in rows}):
                mine = [row for row in rows if row["species"] == species]
                by_species[species] = round(
                    auc([row[name] for row in mine],
                        [row["arm"] == "contact" for row in mine]), 3)
            per_feature[name] = {
                "bout_auc": round(auc(values, labels), 3),
                "recording_auc": round(auc(rec_values, rec_labels), 3),
                "by_species": by_species,
            }

        matrix = [[row[name] for name in FEATURES] for row in rows]
        scores, combo = grouped_combo_auc(matrix, labels, groups)

        contact_scores = np.sort(scores[np.asarray(labels)])
        threshold = float(contact_scores[int((1 - KEEP_CONTACT)
                                             * len(contact_scores))])
        kept_contact = float((scores[np.asarray(labels)] >= threshold).mean())
        kept_alarm = float((scores[~np.asarray(labels)] >= threshold).mean())

        payload = {
            "bouts": counts, "features": per_feature,
            "combo_auc_grouped_cv": round(combo, 3),
            "operating_point": {"keep_contact": round(kept_contact, 3),
                                "alarm_survives": round(kept_alarm, 3),
                                "threshold": round(threshold, 4)},
            "rows": rows,
        }
        (OUT / "results.json").write_text(json.dumps(payload, indent=1))
        run.note(f"combo AUC {combo:.3f} · keep {kept_contact:.0%} contact -> "
                 f"{kept_alarm:.0%} alarm survives")

    print(json.dumps({k: v for k, v in payload.items() if k != "rows"},
                     indent=2))


if __name__ == "__main__":
    main()
