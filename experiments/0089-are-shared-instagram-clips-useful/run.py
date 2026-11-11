"""Are clips shared by crow enthusiasts on Instagram worth asking for?

Reads the field database only (FIELD_DB, default the local instance; run it on
the box, or against a copy, for the hosted data). Compares the shared batch
with the recordist's own kept field captures on four things the pipeline
already measures: signal-to-noise, how much context each capture carries, how
often BirdNET hears a crow, and whether the call-type head agrees with the
recordist's label.

    FIELD_DB=path/to/field.db python experiments/0089-are-shared-instagram-clips-useful/run.py [batch]
"""

import os
import sqlite3
import sys
from pathlib import Path
from statistics import median

REPO = Path(__file__).resolve().parents[2]
DB = Path(os.environ.get("FIELD_DB") or REPO / "fieldserver" / "instance" / "field.db")
BATCH = sys.argv[1] if len(sys.argv) > 1 else "instagram-2026-11"


class Group:
    def __init__(self, name, conn, capture_ids):
        self.name = name
        self.conn = conn
        self.ids = capture_ids

    def _in(self):
        return f"({','.join(str(i) for i in self.ids)})" if self.ids else "(NULL)"

    def minutes(self):
        return sum(r[0] or 0 for r in self.conn.execute(
            f"select duration_sec from captures where id in {self._in()}")) / 60

    def snr(self):
        values = [r[0] for r in self.conn.execute(
            f"select band_snr_db from capture_quality where capture_id in {self._in()} "
            "and band_snr_db is not null")]
        return median(values) if values else None

    def per_minute(self, table):
        count = self.conn.execute(
            f"select count(*) from {table} where capture_id in {self._in()}").fetchone()[0]
        minutes = self.minutes()
        return count / minutes if minutes else None

    def latest_calls(self):
        return self.conn.execute(
            f"""select a.capture_id, d.species, d.call_type, d.confidence, d.crow_conf
                from detected_calls d join analysis_results a on a.id = d.analysis_id
                where a.capture_id in {self._in()} and a.id = (
                    select max(id) from analysis_results where capture_id = a.capture_id)
            """).fetchall()

    def crow_hit_rate(self):
        hits = {r["capture_id"] for r in self.latest_calls() if r["species"] and "Crow" in r["species"]}
        return len(hits) / len(self.ids) if self.ids else None

    def report(self):
        snr = self.snr()
        print(f"{self.name}: {len(self.ids)} captures, {self.minutes():.1f} min")
        print(f"  median band SNR      {snr:.1f} dB" if snr is not None else "  median band SNR      -")
        for table in ("labels", "context_events"):
            rate = self.per_minute(table)
            print(f"  {table:20} {rate:.1f}/min" if rate is not None else f"  {table:20} -")
        rate = self.crow_hit_rate()
        print(f"  BirdNET hears a crow {rate:.0%} of captures" if rate is not None else "")


class Agreement:
    """The recordist's whole-clip label against the head's per-call guesses."""

    def __init__(self, conn, group):
        self.conn = conn
        self.group = group
        self.core = dict(conn.execute("select key, core_mapping from label_defs"))

    def rows(self):
        labels = {r["capture_id"]: r for r in self.conn.execute(
            f"select capture_id, call_type, notes from labels where capture_id in {self.group._in()}")}
        calls = {}
        for r in self.group.latest_calls():
            calls.setdefault(r["capture_id"], []).append(r)
        for capture_id in self.group.ids:
            label = labels.get(capture_id)
            yield capture_id, label, calls.get(capture_id, [])

    def report(self):
        agree = judged = 0
        print("\nper clip: recordist label (core) | detections | head's call types | species")
        for capture_id, label, calls in self.rows():
            said = label["call_type"] if label else "-"
            core = self.core.get(said)
            heard = sorted({c["call_type"] for c in calls if c["call_type"]})
            species = sorted({c["species"] for c in calls if c["species"]})
            if core and core not in ("unsure", "not_a_crow") and heard:
                judged += 1
                agree += core in {self.core.get(h, h) for h in heard}
            print(f"  {capture_id}: {said} ({core}) | {len(calls)} | {', '.join(heard) or '-'} | {', '.join(species) or '-'}")
        if judged:
            print(f"\nhead names the recordist's core class somewhere in the clip: {agree}/{judged}")


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    shared = [r[0] for r in conn.execute(
        "select c.id from captures c join devices d on d.id = c.device_id "
        "where c.provenance = 'shared' and d.label = ? order by c.id", (BATCH,))]
    if not shared:
        sys.exit(f"no shared captures for batch {BATCH} in {DB}")
    own = [r[0] for r in conn.execute(
        "select id from captures where keep = 1 and provenance = 'app'")]
    pending = conn.execute(
        f"select count(*) from analysis_jobs where capture_id in ({','.join(map(str, shared))}) "
        "and state not in ('done', 'failed')").fetchone()[0]
    if pending:
        print(f"warning: {pending} analysis jobs still pending\n")
    Group(f"shared ({BATCH})", conn, shared).report()
    Group("own kept field captures", conn, own).report()
    Agreement(conn, Group("shared", conn, shared)).report()


if __name__ == "__main__":
    main()
