"""Do BirdNET's embeddings rank contact against alarm where shape could not?

0061's verdict: Ben's lemon is half real — contact units are smooth,
single-peaked and short — but an envelope-shape combo reaches only 0.637
grouped, which leaves his ear hearing three alarms per contact call. Before
anything new gets built, the feature space the project already ships deserves
its turn: BirdNET's 1024-d embeddings drove every Phase-4 head (flight call
hit 0.91 AUC on them), and 0060's arms are a labeled contact-vs-alarm
training set nobody has used yet.

SAME WINDOWS AS 0060, literally: the stored window starts are re-sliced from
the same capped decode, so this probes the exact audio 0060 scored — not a
re-segmentation, not a fresh draw. A logistic over the embeddings,
recording-grouped 5-fold CV exactly as 0061 grouped its combo, so recording
identity cannot leak into the number.

READOUT: grouped-CV AUC against 0061's 0.637, and the same operating point —
keep 80% of contact bouts, how much alarm survives. That surviving fraction
is the funnel's width; 0061 left it at 59.5%.

Same honesty caveats as the pair before it: recordist-asserted at recording
level, European corvids, and alarm is the dominant confuser rather than the
only one. A probe validated here still meets begging, song and non-corvid
noise unmeasured — its job is candidate ranking for a trained ear, never
labeling.

    PYTHONPATH=crowgpt/src crowgpt/.venv/bin/python \
        experiments/0062-do-embeddings-rank-contact-calls/run.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

import numpy as np

from crowgpt.birdnet import BirdNet
from crowgpt.progress import Run
from crowgpt.trainer import CORVID_DB, _read_only, cut

OUT = Path(__file__).resolve().parent
RESULTS_0060 = OUT.parent / "0060-can-birdnet-hear-a-contact-call" / "results.json"

SR = 32000
CAP_SECONDS = 120.0
WINDOW = 3.0
KEEP_CONTACT = 0.80
BATCH = 100
SEED = 0


def auc(scores, labels):
    scores, labels = np.asarray(scores, float), np.asarray(labels, bool)
    pos, neg = scores[labels], scores[~labels]
    combined = np.concatenate([pos, neg])
    order = np.argsort(combined, kind="mergesort")
    ranks = np.empty(order.size)
    ranks[order] = np.arange(1, order.size + 1)
    for value in np.unique(combined):
        tied = combined == value
        ranks[tied] = ranks[tied].mean()
    return float((ranks[:pos.size].sum() - pos.size * (pos.size + 1) / 2)
                 / (pos.size * neg.size))


def main():
    bouts = json.loads(RESULTS_0060.read_text())["bouts"]
    recording_ids = sorted({row["recording"] for row in bouts})
    with _read_only(CORVID_DB) as db:
        rows = db.execute(
            f"select id, file_path, recordist from recordings where id in "
            f"({','.join('?' * len(recording_ids))})", recording_ids).fetchall()
    paths = {rec_id: path for rec_id, path, _ in rows}
    recordist_of = {rec_id: recordist for rec_id, _, recordist in rows}

    run = Run("0062 embedding probe for contact calls",
              ["slice", "embed", "probe"])
    birdnet = BirdNet(sample_rate=SR)

    clips = []
    with run.stage("slice") as stage:
        decoded = {}
        for done, rec_id in enumerate(recording_ids, 1):
            decoded[rec_id], _ = cut(paths[rec_id], 0.0, CAP_SECONDS, sr=SR)
            stage.update(done, len(recording_ids))
        for row in bouts:
            samples = decoded[row["recording"]]
            lo = int(row["start"] * SR)
            clips.append(samples[lo:lo + int(WINDOW * SR)])

    vectors = np.zeros((len(clips), 1024))
    have = np.zeros(len(clips), dtype=bool)
    with run.stage("embed") as stage:
        for lo in range(0, len(clips), BATCH):
            found, index = birdnet.embed_indexed(clips[lo:lo + BATCH])
            for vector, i in zip(found, index):
                vectors[lo + i] = vector
                have[lo + i] = True
            stage.update(min(lo + BATCH, len(clips)), len(clips),
                         f"{int(have.sum())} embedded")

    with run.stage("probe") as stage:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
        from sklearn.preprocessing import StandardScaler

        kept = [row for row, ok in zip(bouts, have) if ok]
        matrix = vectors[have]
        labels = np.array([row["arm"] == "contact" for row in kept])
        groups = np.array([row["recording"] for row in kept])

        scores = np.zeros(len(kept))
        for train, test in GroupKFold(n_splits=5).split(matrix, labels, groups):
            scaler = StandardScaler().fit(matrix[train])
            probe = LogisticRegression(max_iter=2000, C=0.1).fit(
                scaler.transform(matrix[train]), labels[train])
            scores[test] = probe.predict_proba(
                scaler.transform(matrix[test]))[:, 1]

        overall = auc(scores, labels)
        contact_sorted = np.sort(scores[labels])
        threshold = float(contact_sorted[int((1 - KEEP_CONTACT)
                                             * len(contact_sorted))])
        kept_contact = float((scores[labels] >= threshold).mean())
        kept_alarm = float((scores[~labels] >= threshold).mean())

        by_species = {}
        for species in sorted({row["species"] for row in kept}):
            mine = np.array([row["species"] == species for row in kept])
            by_species[species] = round(auc(scores[mine], labels[mine]), 3)

        # THE RECORDIST CONFOUND, controlled rather than hoped away. Every
        # Hooded Crow contact recording is one recordist's series, so a high
        # AUC could be his microphone wearing a call-type costume. Where a
        # species' whole contact arm is one recordist AND that recordist also
        # has alarm recordings in the sample, the AUC over his recordings
        # alone compares the call with the gear and habits held constant.
        recordist_control = {}
        for species in by_species:
            mine = [i for i, row in enumerate(kept)
                    if row["species"] == species]
            contact_recordists = {recordist_of[kept[i]["recording"]]
                                  for i in mine if kept[i]["arm"] == "contact"}
            if len(contact_recordists) != 1:
                continue
            (sole,) = contact_recordists
            subset = np.array([i for i in mine
                               if recordist_of[kept[i]["recording"]] == sole])
            labs = labels[subset]
            if labs.all() or not labs.any():
                continue
            recordist_control[species] = {
                "recordist": sole,
                "auc": round(auc(scores[subset], labs), 3),
                "contact_bouts": int(labs.sum()),
                "alarm_bouts": int((~labs).sum()),
            }

        payload = {
            "windows": len(bouts), "embedded": int(have.sum()),
            "auc_grouped_cv": round(overall, 3),
            "auc_by_species": by_species,
            "recordist_control": recordist_control,
            "operating_point": {"keep_contact": round(kept_contact, 3),
                                "alarm_survives": round(kept_alarm, 3),
                                "threshold": round(threshold, 4)},
            "shape_combo_0061": 0.637,
            "rows": [{**row, "score": round(float(s), 4)}
                     for row, s in zip(kept, scores)],
        }
        (OUT / "results.json").write_text(json.dumps(payload, indent=1))
        run.note(f"embedding probe AUC {overall:.3f} (0061 shape: 0.637) · "
                 f"keep {kept_contact:.0%} contact -> {kept_alarm:.0%} alarm "
                 f"survives")

    print(json.dumps({k: v for k, v in payload.items() if k != "rows"},
                     indent=2))


if __name__ == "__main__":
    main()
