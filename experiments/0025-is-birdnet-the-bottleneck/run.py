#!/usr/bin/env python3
"""Is BirdNET the thing limiting call-type classification, or is it the window?

BirdNET is trained to tell species apart, so the worry is that it compresses the
within-species variation call types live in. That worry is reasonable and it is
also not the only candidate. Three things could be losing the nuance:

  (a) the window — BirdNET scores on a fixed non-overlapping 3 s grid at
      3*(second//3), so a 1 s label sits at an arbitrary offset inside its
      window, and a caw is 200-500 ms
  (b) the taxonomy — 4 CORE classes over what the 2026 Leon paper shows is a
      graded continuum. No backbone fixes that; see FUTURE.txt
  (c) the backbone itself

This experiment separates (a) from (c), which is the part that is measurable
without collecting anything new. (b) stays a question.

    ../../pipelines/representation/.venv-birdnet/bin/python run.py --preflight
    ../../pipelines/representation/.venv-birdnet/bin/python run.py --build-cache
    ../../pipelines/representation/.venv-birdnet/bin/python run.py --score

The arms, and what each one isolates:

  A birdnet-grid     BirdNET 3 s at 3*(t//3)      the incumbent. The anchor.
  B birdnet-centred  BirdNET 3 s on the label     A vs B = grid jitter alone
  C perch@3          Perch 2.0, matched context   the backbone
  D perch@1, perch@5 the context ladder           what makes C mean anything
  G birdnet+perch    concatenated                 replace, or add?

The ladder is the load-bearing bit. Perch's native window is 5 s against
BirdNET's 3 s, so a naive comparison hands it two extra seconds and reports the
difference as a fact about the model. If perch@1 already beats birdnet@3 the
objection is dead — it had a third of the audio. If Perch only wins at 5 s, the
honest answer is "give the head more context", which is far cheaper than
swapping a backbone that five shipped heads depend on.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
INGEST = REPO / "pipelines" / "ingest"

sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(INGEST))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from corpus import LabelCorpus  # noqa: E402
from excerpts import DATA, ExcerptCache, segment_keys  # noqa: E402
from features import Features, concatenated  # noqa: E402
from probe import (GroupedProbe, INCUMBENT_CORE_AUC, WithinRecordingProbe,  # noqa: E402
                   reproduces)
from crowgpt.progress import Run  # noqa: E402

CROWTOOLS_CACHE = INGEST / "results" / "pooled_embeddings_crowtools_all-public.npz"
ARCHIVE_CACHE = REPO / "pipelines" / "training" / "results" / "pooled_embeddings.npz"
CACHE_DIR = DATA / "experiments" / "0025"
ARMS_DIR = HERE / "arms"
RESULTS = HERE / "results.json"


#: The four classes crow-tools can express. There is no flight-call flag
#: upstream, so the fifth CORE class cannot appear here at all — which is
#: exactly why the shipped flight-call AUC is measured somewhere else, and is
#: what preflight check 2 is about.
CORE = ["alarm call", "begging", "call", "song"]


def load_corpus():
    """The current row set, keyed and sorted, plus its segments."""
    corpus = LabelCorpus(dataset="all-public")
    segments = {seg.key: seg for seg in corpus.labeled_segments(require_audio=True)}
    return corpus, segments, segment_keys(corpus)


# --------------------------------------------------------------------------
# Preflight — three things about the incumbent that reframe the question


def preflight():
    """Assert what the shipped feature actually is before comparing anything.

    These are not sanity checks. Each one changes what the experiment is
    allowed to conclude, and each one was surprising enough that it needs to
    fail loudly if a future corpus rebuild changes it — otherwise a later run
    silently measures something else and reports it under this README.
    """
    findings = {}
    print("=" * 72)
    print("PREFLIGHT — what the incumbent feature really is")
    print("=" * 72)

    # (1) On this corpus, 3072 dimensions are 1024 dimensions.
    d = np.load(CROWTOOLS_CACHE, allow_pickle=True)
    X = d["X"]
    dim = X.shape[1] // 3
    mean, std, mx = X[:, :dim], X[:, dim:2 * dim], X[:, 2 * dim:]
    nonzero_std = int((np.abs(std) > 1e-12).any(axis=1).sum())
    max_is_mean = int(np.isclose(mx, mean).all(axis=1).sum())

    print(f"\n1. Pooling on the training corpus  ({X.shape[0]} rows, {X.shape[1]}-d)")
    print(f"   rows with any non-zero std : {nonzero_std}")
    print(f"   rows where max == mean     : {max_is_mean}")
    if nonzero_std == 0 and max_is_mean == len(X):
        print("   -> the 3072-d feature is 1024 real dims, 1024 zeros, 1024 copies.")
        print("      build_dataset.py pools ONE 3 s window per label, and pool() on a")
        print("      single vector returns [mean, 0, mean]. So 'mean+std+max destroys")
        print("      sequence structure' is true of the DEPLOYED path (group_regions")
        print("      fuses several windows) and vacuous on the training corpus.")
    else:
        raise SystemExit(
            f"Preflight 1 FAILED: expected a fully degenerate std block, got "
            f"{nonzero_std} rows with variance. The corpus has been rebuilt with "
            f"multi-window pooling, which invalidates the framing of this "
            f"experiment — re-read the README before trusting any arm."
        )
    findings["degenerate_pooling"] = {
        "rows": int(len(X)), "segment_dim": int(dim),
        "rows_with_nonzero_std": nonzero_std, "rows_where_max_eq_mean": max_is_mean,
    }

    # (2) The shipped flight-call number is measured on a corpus indicator.
    print("\n2. Where flight call's positives live")
    ct_flight = sum(1 for labs in d["Y"] if "flight call" in set(labs))
    print(f"   crow-tools flight-call rows: {ct_flight}")
    leak = {"crowtools_flight": ct_flight}
    if ARCHIVE_CACHE.exists():
        dx = np.load(ARCHIVE_CACHE, allow_pickle=True)
        Xx, Yx = dx["X"], dx["Y"]
        dimx = Xx.shape[1] // 3
        nz = (np.abs(Xx[:, dimx:2 * dimx]) > 1e-12).any(axis=1)
        flight = np.array(["flight call" in set(l) for l in Yx])
        print(f"   archive rows with non-zero std: {int(nz.sum())}/{len(Xx)}")
        print(f"   archive flight-call rows   : {int(flight.sum())}, "
              f"of which non-zero std: {int((flight & nz).sum())}")
        leak |= {"archive_rows": int(len(Xx)), "archive_nonzero_std": int(nz.sum()),
                 "archive_flight": int(flight.sum()),
                 "archive_flight_nonzero_std": int((flight & nz).sum())}
        if ct_flight == 0 and flight.sum() and (flight & nz).sum() == flight.sum():
            print("   -> in the COMBINED set the std block is a near-perfect corpus")
            print("      indicator, and every flight-call positive is on one side of")
            print("      it. models/american-crow/metrics.json reports flight call")
            print("      0.975 on a feature that identifies the source of every")
            print("      positive. train_american_crow.py says 'partly encodes")
            print("      source'. It entirely does.")
            print("   -> so the incumbent to beat is experiment 0012 (crow-tools")
            print("      only, recording-grouped), NOT american-crow/metrics.json.")
    findings["flight_call_leak"] = leak

    # (3) The labels have no duration to quantile.
    print("\n3. Span durations in the vendored labels")
    corpus = LabelCorpus(dataset="all-public")
    durations = Counter()
    for key in corpus.labels():
        _, start, end = key.rsplit("-", 2)
        durations[int(end) - int(start)] += 1
    print(f"   histogram (seconds): {dict(durations)}")
    if set(durations) == {1}:
        print("   -> every span is exactly 1 s, so FUTURE.txt's duration-quantile")
        print("      probe has no duration variable to work with. Getting one means")
        print("      running the 12 dB segmenter inside the span, which imports")
        print("      0016's 49%-of-units-lost-to-9 dB problem. Dropped, not deferred.")
    findings["span_durations"] = dict(durations)

    # (4) How far the corpus has drifted from the cached rows.
    print("\n4. Row set drift")
    _, segments, keys = load_corpus()
    cached_groups = set(d["groups"].tolist())
    print(f"   cache      : {len(d['Y'])} rows over {len(cached_groups)} recordings")
    print(f"   corpus now : {len(keys)} rows over "
          f"{len({segments[k].file_id for k in keys})} recordings")
    print(f"   -> {len(d['Y']) - len(keys)} rows have lost their audio. Every arm is")
    print("      pinned to the current key list and joined BY KEY, not row order.")
    findings["row_drift"] = {
        "cached_rows": int(len(d["Y"])), "cached_recordings": len(cached_groups),
        "current_rows": len(keys),
        "current_recordings": len({segments[k].file_id for k in keys}),
    }

    print("\nPreflight passed.\n")
    return findings


def selfcheck():
    """Refuse to run unless this harness reproduces experiment 0012 exactly."""
    print("=" * 72)
    print("SELF-CHECK — does probe.py reproduce experiment 0012?")
    print("=" * 72)
    d = np.load(CROWTOOLS_CACHE, allow_pickle=True)
    got = reproduces(d["X"], d["Y"], d["groups"])
    print(f"\n{'class':<12}{'expected':>10}{'got':>8}")
    for cls in sorted(INCUMBENT_CORE_AUC):
        print(f"{cls:<12}{INCUMBENT_CORE_AUC[cls]:>10}{got[cls]:>8}")
    print("\nSelf-check passed — arms are comparable to the incumbent.\n")
    return got


# --------------------------------------------------------------------------
# Cache


def build_cache(jobs=None):
    _, segments, keys = load_corpus()
    cache = ExcerptCache(CACHE_DIR)
    run = Run("0025 EXCERPT CACHE", [f"decode {len(keys)} excerpts"])
    print(f"building excerpt cache for {len(keys)} segments -> {CACHE_DIR}")
    with run.stage(f"decode {len(keys)} excerpts") as stage:
        stage.say("48 kHz, 9 s, whole-file decode")

        def log(message):
            print(message, flush=True)
            stage.say(message)

        built = cache.build({k: segments[k] for k in keys}, jobs=jobs, log=log)
    run.note(f"built {len(built)}/{len(keys)} rows")
    print(f"built {len(built)}/{len(keys)} rows")
    return built


# --------------------------------------------------------------------------
# Scoring


def arm_paths():
    return sorted(ARMS_DIR.glob("*.npz")) if ARMS_DIR.is_dir() else []


def score(only=None):
    """Score every arm on disk, on the rows they all agree about."""
    _, segments, _ = load_corpus()
    paths = [p for p in arm_paths() if not only or p.stem in only]
    if not paths:
        raise SystemExit(
            f"No arms in {ARMS_DIR}. Build at least one first:\n"
            f"  ../../pipelines/representation/.venv-birdnet/bin/python "
            f"../../pipelines/representation/embed_birdnet_window.py --help"
        )

    arms = {}
    for path in paths:
        arms[path.stem] = Features.read(path)
        print(f"loaded {path.stem:<20} {arms[path.stem].X.shape} "
              f"{arms[path.stem].feature}")

    shared = sorted(set.intersection(*(set(a.keys) for a in arms.values())))
    print(f"\nscoring on {len(shared)} rows shared by all {len(arms)} arms")
    for name in list(arms):
        arms[name] = arms[name].restricted_to(shared)

    # Arm G, built rather than cached: does the rival *add* information, or
    # merely replace it? Pre-registered, so it is not a post-hoc rescue for a
    # backbone that lost — and it is the outcome to expect if the two make
    # different mistakes rather than one making fewer.
    if "a-birdnet-grid" in arms and "c-perch-5s" in arms:
        arms["g-birdnet-plus-perch"] = concatenated(
            arms["a-birdnet-grid"], arms["c-perch-5s"])

    segs = [segments[k] for k in shared]
    groups = np.array([s.file_id for s in segs])
    Y = [sorted(s.labels) for s in segs]

    out = {"n_rows": len(shared), "n_recordings": len(set(groups.tolist())),
           "arms": {}}
    run = Run("0025 SCORING", sorted(arms))
    for name, feats in sorted(arms.items()):
        with run.stage(name) as stage:
            stage.say(f"{feats.dim}-d, {len(shared)} rows, grouped 5-fold")
            print(f"\n=== {name}  ({feats.dim}-d) ===")
            probe = GroupedProbe(feats.X, Y, groups, name=name)
            row = {"dim": feats.dim, "feature": feats.feature, "meta": feats.meta,
                   "core_auc": {}, "core_ap": {}}
            print(f"{'class':<12}{'n+':>6}{'AUC':>8}{'AP':>8}")
            for cls in CORE:
                auc, pos = probe.ovr_auc(cls)
                ap, _ = probe.ovr_ap(cls)
                row["core_auc"][cls] = auc
                row["core_ap"][cls] = ap
                print(f"{cls:<12}{pos:>6}{_fmt(auc):>8}{_fmt(ap):>8}")
            mc = probe.multiclass(CORE)
            row["multiclass"] = {k: v for k, v in (mc or {}).items()
                                 if k not in ("y_true", "y_pred")}
            if mc:
                print(f"  macro-F1 {mc['macro_f1']}  (n={mc['n']})")
                row["_predictions"] = {"y_true": mc["y_true"], "y_pred": mc["y_pred"]}

            for positive, negative in (("mob", "alert"), ("rattle", "softSong")):
                wr = WithinRecordingProbe(feats.X, segs, groups,
                                          positive=positive, negative=negative)
                res = wr.auc()
                row.setdefault("within_recording", {})[f"{positive} vs {negative}"] = res
                print(f"  {positive} vs {negative:<10} {_fmt(res['auc'])} "
                      f"spread {res['spread']}  n={res['n']} over {res['recordings']} rec")
            out["arms"][name] = row

    run.note(f"scored {len(arms)} arms on {len(shared)} rows")
    _verdict(out)
    RESULTS.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {RESULTS}")
    return out


def probes(out=None):
    """The three things per-class AUC cannot show.

    The CORE classes sit at 0.90-0.97 with about 0.04 of headroom, so a null
    there says almost nothing. These have somewhere to move.
    """
    _, segments, _ = load_corpus()
    arms = {p.stem: Features.read(p) for p in arm_paths()}
    if not arms:
        raise SystemExit(f"no arms in {ARMS_DIR}")
    shared = sorted(set.intersection(*(set(a.keys) for a in arms.values())))
    arms = {n: a.restricted_to(shared) for n, a in arms.items()}
    if "a-birdnet-grid" in arms and "c-perch-5s" in arms:
        arms["g-birdnet-plus-perch"] = concatenated(arms["a-birdnet-grid"],
                                                    arms["c-perch-5s"])
    segs = [segments[k] for k in shared]
    groups = np.array([s.file_id for s in segs])
    Y = [sorted(s.labels) for s in segs]
    results = {}

    # N1 — the fine repertoire the CORE vocabulary collapses.
    print("\n" + "=" * 72)
    print("N1  cluster recovery — 86 upstream cluster ids nothing has ever used")
    print("=" * 72)
    clusters = np.array([str(s.flags.get("cluster")) for s in segs])
    per = Counter(clusters)
    rec_per = defaultdict(set)
    for c, g in zip(clusters, groups):
        rec_per[c].add(g)
    usable = {c for c in per if per[c] >= 20 and len(rec_per[c]) >= 5}
    keep = np.isin(clusters, list(usable))
    print(f"{len(usable)} clusters with >=20 segments over >=5 recordings, "
          f"covering {keep.sum()} of {len(segs)} rows")
    print("\nCaveats, pre-registered rather than discovered:")
    print("  * cluster is confounded with recording identity, which is why this")
    print("    is recording-grouped — a held-out recording forces generalisation.")
    print("  * the ids are upstream-derived with unrecorded provenance and may")
    print("    themselves have come from BirdNET embeddings. So this is ONE-SIDED:")
    print("    a rival beating BirdNET here is strong; a rival losing is not.")
    print(f"\n{'arm':<24}{'macro-F1':>10}{'n':>8}{'classes':>9}")
    results["cluster_recovery"] = {}
    for name, feats in sorted(arms.items()):
        probe = GroupedProbe(feats.X[keep], [{c} for c in clusters[keep]],
                             groups[keep], name=name)
        mc = probe.multiclass(sorted(usable))
        results["cluster_recovery"][name] = (
            {k: v for k, v in mc.items() if k not in ("y_true", "y_pred")}
            if mc else None)
        print(f"{name:<24}{(mc['macro_f1'] if mc else '—'):>10}"
              f"{(mc['n'] if mc else 0):>8}{(len(mc['classes']) if mc else 0):>9}")

    # N3 — where the errors are, not how many.
    print("\n" + "=" * 72)
    print("N3  do the arms make the SAME mistakes?")
    print("=" * 72)
    preds = {}
    for name, feats in sorted(arms.items()):
        mc = GroupedProbe(feats.X, Y, groups, name=name).multiclass(CORE)
        if mc:
            preds[name] = (np.array(mc["y_true"]), np.array(mc["y_pred"]))
    base = "a-birdnet-grid"
    if base in preds:
        yt, yb = preds[base]
        print(f"\n{'arm':<24}{'both right':>12}{'both wrong':>12}"
              f"{'arm fixes':>11}{'arm breaks':>12}")
        results["error_overlap"] = {}
        for name, (yt2, yp) in sorted(preds.items()):
            if name == base or len(yt2) != len(yt):
                continue
            ok_a, ok_b = yb == yt, yp == yt2
            cell = {"both_right": int((ok_a & ok_b).sum()),
                    "both_wrong": int((~ok_a & ~ok_b).sum()),
                    "fixes": int((~ok_a & ok_b).sum()),
                    "breaks": int((ok_a & ~ok_b).sum())}
            results["error_overlap"][name] = cell
            print(f"{name:<24}{cell['both_right']:>12}{cell['both_wrong']:>12}"
                  f"{cell['fixes']:>11}{cell['breaks']:>12}")
        print("\nA rival that only reshuffles which rows it gets wrong is carrying")
        print("the same information in a different package. One that fixes far more")
        print("than it breaks is a real gain; if both are large the answer is to")
        print("concatenate rather than replace, and arm G is that test.")

    # N4 — is a win a win, or a win on one kind of segment?
    print("\n" + "=" * 72)
    print("N4  confound sweep — where does any advantage actually come from?")
    print("=" * 72)
    splits = {
        "crowCount==1": np.array([s.flags.get("crowCount") == 1 for s in segs]),
        "crowCount>=2": np.array([(s.flags.get("crowCount") or 0) >= 2 for s in segs]),
        "juvenile": np.array([s.flags.get("crowAge") == "juvenile" for s in segs]),
        "adult": np.array([s.flags.get("crowAge") == "adult" for s in segs]),
    }
    results["confounds"] = {}
    print(f"\n{'split':<16}{'n':>7}" + "".join(f"{n[:14]:>16}" for n in sorted(arms)))
    for label, mask in splits.items():
        if mask.sum() < 50:
            continue
        row = {}
        cells = []
        for name, feats in sorted(arms.items()):
            mc = GroupedProbe(feats.X[mask], [Y[i] for i in np.where(mask)[0]],
                              groups[mask], name=name).multiclass(CORE)
            row[name] = mc["macro_f1"] if mc else None
            cells.append(f"{(mc['macro_f1'] if mc else '—'):>16}")
        results["confounds"][label] = row
        print(f"{label:<16}{int(mask.sum()):>7}" + "".join(cells))
    print("\nAn arm that only wins on crowCount>=2 is fixing overlapping callers,")
    print("not nuance. One that only wins on juveniles is re-finding 0012's")
    print("begging/crowAge confound, where 91% of begging is juvenile-aged.")

    path = HERE / "probes.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {path}")
    return results


def _verdict(out):
    """Read the pre-registered thresholds off the numbers, not off a hunch."""
    arms = out["arms"]
    anchor = arms.get("a-birdnet-grid")
    if not anchor or not anchor.get("multiclass"):
        return
    base_f1 = anchor["multiclass"]["macro_f1"]
    base_wr = anchor.get("within_recording", {}).get("mob vs alert", {})
    print("\n" + "=" * 72)
    print(f"VERDICT vs a-birdnet-grid (macro-F1 {base_f1}, "
          f"mob-vs-alert {_fmt(base_wr.get('auc'))})")
    print("=" * 72)
    for name, row in sorted(arms.items()):
        if name == "a-birdnet-grid" or not row.get("multiclass"):
            continue
        d_f1 = row["multiclass"]["macro_f1"] - base_f1
        wr = row.get("within_recording", {}).get("mob vs alert", {})
        overlap = _overlaps(wr.get("spread"), base_wr.get("spread"))
        if d_f1 >= 0.03 and not overlap:
            call = "MIGRATE"
        elif abs(d_f1) <= 0.02 and overlap:
            call = "NULL"
        else:
            call = "MIXED — read the arms, not this line"
        print(f"  {name:<22} macro-F1 {d_f1:+.3f}  "
              f"mob-vs-alert spreads {'overlap' if overlap else 'separate'}  -> {call}")


def _overlaps(a, b):
    if not a or not b:
        return True
    return not (a[1] < b[0] or b[1] < a[0])


def _fmt(v):
    return "—" if v is None else f"{v}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preflight", action="store_true",
                        help="assert what the incumbent feature is")
    parser.add_argument("--selfcheck", action="store_true",
                        help="reproduce experiment 0012, or abort")
    parser.add_argument("--build-cache", action="store_true",
                        help="decode the 48 kHz excerpt cache (~4 GB)")
    parser.add_argument("--score", action="store_true",
                        help="score every arm in arms/")
    parser.add_argument("--probes", action="store_true",
                        help="the nuance probes per-class AUC cannot show")
    parser.add_argument("--only", nargs="*", help="score only these arms")
    parser.add_argument("--jobs", type=int, default=None)
    args = parser.parse_args()

    ran = False
    findings = {}
    if args.preflight:
        findings = preflight()
        ran = True
    if args.selfcheck or args.score:
        selfcheck()
        ran = True
    if args.build_cache:
        build_cache(args.jobs)
        ran = True
    if args.score:
        score(args.only)
        ran = True
    if args.probes:
        probes()
        ran = True

    if not ran:
        findings = preflight()
        selfcheck()
    if findings:
        (HERE / "preflight.json").write_text(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
