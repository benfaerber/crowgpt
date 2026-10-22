#!/usr/bin/env python3
"""Refresh the numbers on the promo page from where they are actually measured.

`promo/stats.json` is the one place a figure on the page is written down. The
page prints the `text` of each entry — the HTML and the chart carry `{{key}}`
tokens, substituted at build time — so nothing on the site restates a number in
its own words, and there is no second copy to forget.

    python3 promo/tools/build_stats.py            # refresh, rewrite stats.json
    python3 promo/tools/build_stats.py --check     # exit 1 if anything is stale

Entries marked `"auto": true` are recomputed here. The rest are typed by hand
from an experiment that cannot be re-run in a second — this script never invents
a value for one, it only lists them so a stale AUC is a thing you are told about
rather than a thing you notice on the live site.

A source that is missing is not a source that says zero. When the field server's
database or the corpus is not on this machine, the rules that need it are
reported as unchecked and their existing values are left exactly as they are.

Still hardcoded at build time, deliberately. The bundle reads no store and takes
no token, so a visitor never touches the corpus; this script moves the update
from "edit five places in index.html" to "run one command", without wiring the
page to a live database that would silently restate itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATS = REPO / "promo" / "stats.json"

FIELD_DB = Path(os.environ.get("FIELD_DB") or REPO / "fieldserver" / "instance" / "field.db")
CREDITS = REPO / "promo" / "public" / "credits.json"
HEADS = REPO / "pipelines" / "training" / "models"
CROWTOOLS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"

HUMAN = "label_source = 'human'"


class Unavailable(Exception):
    """A source this machine does not have. Leaves the existing value alone."""


class Sources:
    """The measured places a promo number comes from, opened once each."""

    def __init__(self) -> None:
        self._field: sqlite3.Connection | None = None
        self._credits: dict | None = None

    @property
    def field(self) -> sqlite3.Connection:
        if self._field is None:
            if not FIELD_DB.exists():
                raise Unavailable(f"no field server database at {FIELD_DB}")
            # Read-only: this is the live server's file, and the promo page has
            # no business being the process that checkpoints its WAL.
            self._field = sqlite3.connect(f"file:{FIELD_DB}?mode=ro", uri=True)
            self._field.row_factory = sqlite3.Row
        return self._field

    def one(self, sql: str):
        return self.field.execute(sql).fetchone()[0]

    def rows(self, sql: str) -> list[sqlite3.Row]:
        return self.field.execute(sql).fetchall()

    @property
    def credits(self) -> dict:
        if self._credits is None:
            if not CREDITS.exists():
                raise Unavailable("no credits.json — run promo/tools/build_credits.py first")
            self._credits = json.loads(CREDITS.read_text())
        return self._credits

    def json_at(self, path: Path) -> dict:
        if not path.exists():
            raise Unavailable(f"missing {path.relative_to(REPO)}")
        return json.loads(path.read_text())

    def close(self) -> None:
        if self._field is not None:
            self._field.close()


def grouped(n: int) -> str:
    return f"{n:,}"


class Rules:
    """One method per auto figure, named for its key with dots as underscores.

    Each returns (value, text). `value` is the raw measurement, `text` is what
    the page prints — kept apart so the JSON says plainly what a visitor reads,
    and so grouping and rounding live here rather than in the bundle.
    """

    def __init__(self, sources: Sources) -> None:
        self.s = sources

    def labels_count(self):
        n = self.s.one(f"SELECT COUNT(*) FROM labels WHERE {HUMAN}")
        return n, grouped(n)

    def labels_captures(self):
        n = self.s.one(f"SELECT COUNT(DISTINCT capture_id) FROM labels WHERE {HUMAN}")
        return n, grouped(n)

    def labels_seconds(self):
        total = self.s.one(
            f"SELECT COALESCE(SUM(end_sec - start_sec), 0) FROM labels "
            f"WHERE {HUMAN} AND start_sec IS NOT NULL AND end_sec IS NOT NULL"
        )
        return round(total, 1), grouped(round(total))

    def labels_minutes(self):
        seconds, _ = self.labels_seconds()
        minutes = round(seconds / 60, 1)
        return minutes, f"{minutes:.1f}"

    def context_events(self):
        n = self.s.one("SELECT COUNT(*) FROM context_events")
        return n, grouped(n)

    def context_tags(self):
        n = self.s.one("SELECT COUNT(*) FROM context_defs WHERE active = 1")
        return n, grouped(n)

    def context_categories(self):
        n = self.s.one("SELECT COUNT(DISTINCT category) FROM context_defs WHERE active = 1")
        return n, grouped(n)

    def context_tags_used(self):
        n = self.s.one("SELECT COUNT(DISTINCT key) FROM context_events")
        return n, grouped(n)

    def context_tags_witnessed(self):
        """Active chips that have actually come up — the honest companion to
        context.tags, which is only what the phone offers."""
        n = self.s.one(
            "SELECT COUNT(*) FROM context_defs d WHERE d.active = 1 AND EXISTS "
            "(SELECT 1 FROM context_events e WHERE e.key = d.key)"
        )
        return n, grouped(n)

    def context_vocabulary(self):
        """The chips a recordist can actually put on a call, in the app's order.

        Display text comes from the translations table rather than the seed
        constants in config_store.py, so an edited chip reads on the page the
        way it reads on the phone. A tag with no English row falls back to its
        key rather than vanishing — a missing translation should look wrong, not
        shrink the vocabulary.

        `used` counts events, which is honest in a way most counts here are not:
        context is typed by a person watching, so nothing seeded contributes.
        Retired keys still hold their old events and are excluded here, which is
        why the total can exceed the sum of these.
        """
        rows = self.s.rows(
            "SELECT d.category, d.key, t.text AS label, "
            "  (SELECT COUNT(*) FROM context_events e WHERE e.key = d.key) AS used "
            "FROM context_defs d "
            "LEFT JOIN translations t "
            "  ON t.namespace = 'context' AND t.key = d.key AND t.locale = 'en' "
            "WHERE d.active = 1 ORDER BY d.category, d.sort_order, d.key"
        )
        tags = [
            {
                "key": row["key"],
                "category": row["category"],
                "label": row["label"] or row["key"].replace("_", " ").capitalize(),
                "used": row["used"],
            }
            for row in rows
        ]
        # Joined on · rather than a comma: "Crows still, not moving" has one of
        # its own, and a comma-joined list of chips reads as a longer list than
        # it is.
        return tags, " · ".join(tag["label"] for tag in tags)

    def captures_kept(self):
        n = self.s.one("SELECT COUNT(*) FROM captures WHERE keep = 1")
        return n, grouped(n)

    def captures_total(self):
        n = self.s.one("SELECT COUNT(*) FROM captures")
        return n, grouped(n)

    def species_heads(self):
        if not HEADS.exists():
            raise Unavailable(f"missing {HEADS.relative_to(REPO)}")
        # A directory only counts once it has metrics, so a half-finished
        # training run cannot quietly add a species to the front page.
        n = sum(1 for d in HEADS.iterdir() if d.is_dir() and (d / "metrics.json").exists())
        return n, grouped(n)

    def crowtools_segments(self):
        labels = self.s.json_at(CROWTOOLS)["labels"]
        n = sum(1 for entry in labels.values() if entry.get("reviewed"))
        return n, grouped(n)

    def credits_recordings(self):
        n = self.s.credits["counts"]["recordings"]
        return n, grouped(n)

    def credits_recordists(self):
        n = self.s.credits["counts"]["recordists"]
        return n, grouped(n)

    def credits_species(self):
        n = self.s.credits["counts"]["species"]
        return n, grouped(n)


class Refresh:
    """Walks stats.json, recomputes what it can, and reports the rest."""

    def __init__(self, document: dict, rules: Rules) -> None:
        self.document = document
        self.rules = rules
        self.changed: list[str] = []
        self.unchecked: list[tuple[str, str]] = []
        self.manual: list[str] = []

    def run(self) -> None:
        for key, figure in self.document["figures"].items():
            if not figure.get("auto"):
                self.manual.append(key)
                continue
            rule = getattr(self.rules, key.replace(".", "_"), None)
            if rule is None:
                self.unchecked.append((key, 'marked "auto" but no rule defines it'))
                continue
            try:
                value, text = rule()
            except Unavailable as missing:
                self.unchecked.append((key, str(missing)))
                continue
            if (value, text) != (figure.get("value"), figure.get("text")):
                self.changed.append(f"{key}: {figure.get('text')} -> {text}")
                figure["value"], figure["text"] = value, text

    def report(self) -> None:
        for line in self.changed:
            print(f"  changed  {line}")
        for key, why in self.unchecked:
            print(f"  unchecked {key} — {why}")
        if self.manual:
            print(f"  by hand  {len(self.manual)} figure(s) this script cannot check:")
            for key in self.manual:
                print(f"             {key} — {self.document['figures'][key]['source']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report without writing, and exit 1 if any auto figure is stale",
    )
    args = parser.parse_args()

    document = json.loads(STATS.read_text())
    sources = Sources()
    refresh = Refresh(document, Rules(sources))
    try:
        refresh.run()
    finally:
        sources.close()

    refresh.report()

    if args.check:
        if refresh.changed:
            print(f"\n{len(refresh.changed)} figure(s) stale — run build_stats.py")
            return 1
        print("\nEvery checkable figure on the promo page is current.")
        return 0

    if not refresh.changed:
        print("\nNothing changed; stats.json left alone.")
        return 0

    # Stamped only on a real write, so the date means "these numbers were true
    # then" rather than "somebody ran the script".
    document["refreshed_at"] = today()
    # ensure_ascii off: this file is read and edited by hand, and a source note
    # full of — escapes is not.
    STATS.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{len(refresh.changed)} figure(s) updated in {STATS.relative_to(REPO)}")
    print("Rebuild the page for them to reach it: make -C promo build")
    return 0


def today() -> str:
    from datetime import date

    return date.today().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
