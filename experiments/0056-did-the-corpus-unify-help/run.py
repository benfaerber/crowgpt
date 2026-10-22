"""Does the corpus unification change anything a training run would notice?

Ben, 2026-08-06: *"I made some changes to the corpus, I guess there were some
misorganized files... I think it may have had species in wrong folders and
stuff."*

`data/corvid.db` was rewritten today with a `.pre-unify` backup beside it. The
recordings table went from 11,689 rows to 25,000 and gained six columns —
`slug`, `core_type`, `content_sha256`, `bytes`, `group_key`, `group_basis`. This
asks the only question that decides whether to spend 35 minutes re-extracting and
two hours re-tokenising: **how much of the extracted corpus would actually
change?**

THE BOUTS PREDATE THE FIX. `data/crowgpt/bouts` was written 5 Aug and the unify
landed 6 Aug, so nothing any model reads has seen it. That is not a problem to
solve, it is the reason the question is answerable — the old labels are still on
disk to diff against.

THREE THINGS THE UNIFY COULD HAVE CHANGED, and they are worth separating because
they have very different consequences:

    species     a bout filed under the wrong species trains the wrong prefix
                token and pollutes the shard it sits in.
    grouping    `group_key` decides the train/val/test split. A key that is too
                fine puts the same bird on both sides, and validation loss comes
                out optimistic. This is the one that can quietly flatter a result.
    new audio   the big archive's 13,311 assets entering the DB looks like growth, but
                the bouts store already holds 56,164 of its bouts. Metadata
                arriving is not audio arriving.

WHAT COUNTS AS A LEAK, precisely: two recordings the OLD key treated as separate
groups, which the NEW key says are the same recordist on the same day, that the
split then put on opposite sides. Under the new key they are one bird on one
morning, so a model trained on one has effectively seen the other.
"""
import collections
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

OUT = Path(__file__).resolve().parent
DB = REPO / "data" / "corvid.db"
OLD_DB = REPO / "data" / "corvid.db.pre-unify"
BOUTS = REPO / "data" / "crowgpt" / "bouts"


def recordings(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(recordings)")}
    wanted = [c for c in ("source_ref", "source", "species", "slug",
                          "group_key", "group_basis") if c in cols]
    return {str(r["source_ref"]): dict(r)
            for r in conn.execute(f"SELECT {', '.join(wanted)} FROM recordings")}


def main():
    from crowgpt.tokens import BoutStore

    new = recordings(DB)
    old = recordings(OLD_DB) if OLD_DB.exists() else {}
    store = BoutStore(BOUTS)
    splits = store.split(seed=0)
    where = {i: name for name, idxs in splits.items() for i in idxs}

    report = {"recordings_new": len(new), "recordings_old": len(old),
              "bouts": len(store.index)}

    # --- 1. does any bout's species disagree with the unified slug? ---
    relabel = collections.Counter()
    unresolved = 0
    by_source = collections.Counter()
    for row in store.index:
        record = new.get(str(row["recording_id"]))
        if record is None:
            unresolved += 1
            continue
        by_source[record["source"]] += 1
        if record.get("slug") and record["slug"] != row["species"]:
            relabel[(row["species"], record["slug"])] += 1
    report["unresolved_bouts"] = unresolved
    report["bouts_by_source"] = dict(by_source)
    report["relabelled"] = {f"{a} -> {b}": n for (a, b), n in relabel.items()}
    report["relabelled_total"] = sum(relabel.values())

    # --- 2. how much does the grouping collapse, per species? ---
    old_groups, new_groups, recs = (collections.defaultdict(set),
                                    collections.defaultdict(set),
                                    collections.defaultdict(set))
    for row in store.index:
        record = new.get(str(row["recording_id"]))
        if record is None or not record.get("group_key"):
            continue
        sp = row["species"]
        old_groups[sp].add(row.get("group_key"))
        new_groups[sp].add(record["group_key"])
        recs[sp].add(str(row["recording_id"]))
    report["grouping"] = {
        sp: {"recordings": len(recs[sp]), "old_groups": len(old_groups[sp]),
             "new_groups": len(new_groups[sp]),
             "collapse_pct": round(100 * (len(old_groups[sp]) - len(new_groups[sp]))
                                   / max(len(old_groups[sp]), 1), 1)}
        for sp in sorted(recs, key=lambda s: -len(recs[s]))}

    # --- 3. the number that matters: leakage in the split actually used ---
    spans = collections.defaultdict(set)
    species_of = collections.defaultdict(set)
    for i, row in enumerate(store.index):
        record = new.get(str(row["recording_id"]))
        if record is None or not record.get("group_key") or i not in where:
            continue
        spans[record["group_key"]].add(where[i])
        species_of[record["group_key"]].add(row["species"])
    leaking = {g for g, sides in spans.items() if len(sides) > 1}

    held = [i for i in range(len(store.index)) if where.get(i) in ("val", "test")]
    def leak_share(species=None):
        rows = [i for i in held
                if species is None or store.index[i]["species"] == species]
        hit = sum(1 for i in rows
                  if new.get(str(store.index[i]["recording_id"]), {}).get("group_key")
                  in leaking)
        return hit, len(rows)

    hit, total = leak_share()
    ac_hit, ac_total = leak_share("american-crow")
    report["leakage"] = {
        "groups_spanning_splits": len(leaking), "groups_total": len(spans),
        "held_out_in_leaking_group": hit, "held_out_total": total,
        "held_out_pct": round(100 * hit / max(total, 1), 1),
        "american_crow_hit": ac_hit, "american_crow_total": ac_total,
        "american_crow_pct": round(100 * ac_hit / max(ac_total, 1), 1),
        "by_species": dict(collections.Counter(
            sp for g in leaking for sp in species_of[g]).most_common())}

    (OUT / "audit.json").write_text(json.dumps(report, indent=2))

    print(f"recordings {len(old)} -> {len(new)} | bouts {len(store.index)}")
    print(f"bouts by source: {dict(by_source)}  (unresolved {unresolved})\n")
    print(f"SPECIES relabelled by the unify: {report['relabelled_total']} bouts "
          f"({100 * report['relabelled_total'] / len(store.index):.2f}%)")
    for k, n in report["relabelled"].items():
        print(f"   {k}: {n}")
    print(f"\nGROUPING collapse, top species:")
    print(f"{'species':24}{'recs':>7}{'old':>8}{'new':>8}{'collapse':>10}")
    for sp, g in list(report["grouping"].items())[:8]:
        print(f"{sp:24}{g['recordings']:>7}{g['old_groups']:>8}"
              f"{g['new_groups']:>8}{g['collapse_pct']:>9.1f}%")
    lk = report["leakage"]
    print(f"\nLEAKAGE in the split actually used (seed 0)")
    print(f"  groups spanning >1 split: {lk['groups_spanning_splits']} "
          f"of {lk['groups_total']}")
    print(f"  held-out bouts in a leaking group: {lk['held_out_in_leaking_group']}"
          f" of {lk['held_out_total']} ({lk['held_out_pct']}%)")
    print(f"  american crow only: {lk['american_crow_hit']} of "
          f"{lk['american_crow_total']} ({lk['american_crow_pct']}%)")
    print(f"\n-> {OUT / 'audit.json'}")


if __name__ == "__main__":
    main()
