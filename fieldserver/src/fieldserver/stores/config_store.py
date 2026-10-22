"""The command-and-control config the operator pushes to the whole fleet.

The vocabularies used to be hardcoded in the app; this is the versioned,
localized, DB-backed document that replaced them. The operator edits label_defs / instructions /
translations / taxonomy; bumping the version means the whole fleet picks up the
change on its next fetch — no app-store update. `label_defs.core_mapping` mirrors
pipelines/ingest/corpus.py FLAG_TO_CORE: a rich field label (e.g. "mobbing") is a
distinct human label that still trains into a CORE class.
"""

from .db_base import Database, utc_now
# Re-exported so the tests and any tooling keep one import path for the
# vocabulary; the seed data itself lives with its rationale in config_seed.py.
from .config_seed import (  # noqa: F401
    CORE_CLASSES,
    CORE_COLORS,
    NON_TRAINING_LABELS,
    SEED_CALLER_ROLES,
    SEED_CONTEXTS,
    SEED_GUIDE,
    SEED_INSTRUCTIONS,
    SEED_LABELS,
    SEED_OBSERVER_ROLES,
    SEED_TAXONOMY,
    SEED_TRANSLATIONS,
)


class ConfigStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)
        self._seed_and_reconcile()
        self._seed_if_empty()
        self._resync_core_labels()

    def _seed_and_reconcile(self) -> None:
        """Bring the served vocabularies up to what the code expects.

        Not schema — the tables and columns come from the migrations. This is
        the part that cannot: which labels, contexts and observer roles the
        fleet should be offered is decided by constants in this file, and they
        change more often than the shape does.

        Reconciles rather than seeds once. `_seed_if_empty` only fires on a
        brand-new database, and a vocabulary added afterwards would otherwise
        never reach a running server. Publishing a new config version is what
        makes the phones re-fetch, so a change nobody publishes never arrives.
        """
        with self._connect() as conn:
            # Added after the first fleets shipped, so they have to be inserted
            # into existing databases and published, or nobody is offered them.
            for key, en, de in NON_TRAINING_LABELS:
                if conn.execute("SELECT 1 FROM label_defs WHERE key=?",
                                (key,)).fetchone():
                    continue
                order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM label_defs"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO label_defs (key, core_mapping, sort_order, trains) "
                    "VALUES (?, ?, ?, 0)", (key, key, order))
                for locale, text in (("en", en), ("de", de)):
                    conn.execute(
                        "INSERT OR IGNORE INTO translations "
                        "(namespace, key, locale, text) VALUES ('label', ?, ?, ?)",
                        (key, locale, text))
                if conn.execute(
                        "SELECT COUNT(*) FROM config_versions").fetchone()[0]:
                    # version_introduced, not its default of 1. This path exists
                    # *because* these labels arrived after the first fleets, so
                    # letting them claim version 1 states the opposite of the
                    # reason they are here — and that column is what says whether
                    # a word was on the menu when somebody chose a different one.
                    # An `alarm call` label from before `mobbing` existed carries
                    # no opinion about mobbing; one from after carries a weak one.
                    # Get the provenance wrong and a coarse answer reads as a
                    # considered rejection of a word nobody was offered.
                    version = self._publish(conn, f"add label {key}")
                    conn.execute(
                        "UPDATE label_defs SET version_introduced = ? WHERE key = ?",
                        (version, key))
                # A brand-new database has no versions yet and `_seed_if_empty`
                # is about to publish 1, which is genuinely when this label
                # appeared there. The default is right in that case only.
            self._heal_version_introduced(conn)
            # The context vocabulary arrived after the first fleets did, and
            # _seed_if_empty only fires on a brand-new database — so seed it
            # here too, or an existing server serves an empty list forever.
            # Reconcile rather than seed-once. The vocabulary is expected to
            # change — categories were regrouped and tags added after the first
            # fleets were running — and a phone only re-fetches when the config
            # version moves, so a change nobody publishes never arrives.
            existing = {r["key"]: r["category"]
                        for r in conn.execute("SELECT key, category FROM context_defs")}
            changed = False
            for i, (key, category) in enumerate(SEED_CONTEXTS):
                if key not in existing:
                    conn.execute(
                        "INSERT INTO context_defs (key, category, sort_order) "
                        "VALUES (?, ?, ?)", (key, category, i))
                    changed = True
                elif existing[key] != category:
                    conn.execute(
                        "UPDATE context_defs SET category = ?, sort_order = ? WHERE key = ?",
                        (category, i, key))
                    changed = True
                else:
                    # Order alone still moves, silently, exactly as it does for the
                    # guide sections below. Inserting a tag mid-list should slide
                    # the ones after it on every phone, and nothing else records
                    # that. Without this branch sort_order is written only when a
                    # key is new or changes category, which is how six of them came
                    # to share three values.
                    conn.execute(
                        "UPDATE context_defs SET sort_order = ? WHERE key = ?", (i, key))
            # Retired keys stay in the table, deactivated: rows already tagged
            # with one are evidence, and deleting the definition would leave
            # them pointing at nothing.
            retired = set(existing) - {key for key, _ in SEED_CONTEXTS}
            for key in retired:
                # Stamped only on the way out, so re-running this does not keep
                # moving the version a tag was retired at.
                conn.execute(
                    "UPDATE context_defs SET active = 0, version_retired = "
                    "COALESCE(version_retired, "
                    "  (SELECT COALESCE(MAX(version), 0) + 1 FROM config_versions)) "
                    "WHERE key = ? AND active = 1",
                    (key,))
                changed = True
            held = {r["key"]: r["part"]
                    for r in conn.execute("SELECT key, part FROM guide_sections")}
            for i, (key, part) in enumerate(SEED_GUIDE):
                if key not in held:
                    conn.execute(
                        "INSERT INTO guide_sections (key, part, sort_order) "
                        "VALUES (?, ?, ?)", (key, part, i))
                    changed = True
                elif held[key] != part:
                    conn.execute(
                        "UPDATE guide_sections SET part = ?, sort_order = ? WHERE key = ?",
                        (part, i, key))
                    changed = True
                else:
                    # Order alone still moves, silently: a section reordered here
                    # should reorder on every phone, and nothing else records it.
                    conn.execute(
                        "UPDATE guide_sections SET sort_order = ? WHERE key = ?", (i, key))
            for key in set(held) - {key for key, _ in SEED_GUIDE}:
                conn.execute(
                    "UPDATE guide_sections SET active = 0 WHERE key = ? AND active = 1",
                    (key,))
                changed = True
            for namespace in ("guide_title", "guide_body"):
                for key, by_locale in SEED_TRANSLATIONS[namespace].items():
                    for locale, text in by_locale.items():
                        # Upsert rather than insert-or-ignore: the whole point of
                        # serving this is that better wording reaches the fleet.
                        before = conn.execute(
                            "SELECT text FROM translations WHERE namespace=? AND key=? "
                            "AND locale=?", (namespace, key, locale)).fetchone()
                        if before is None or before["text"] != text:
                            changed = True
                        conn.execute(
                            "INSERT INTO translations (namespace, key, locale, text) "
                            "VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(namespace, key, locale) DO UPDATE SET "
                            "text = excluded.text",
                            (namespace, key, locale, text))

            known = {r["key"] for r in conn.execute("SELECT key FROM caller_roles")}
            for i, key in enumerate(SEED_CALLER_ROLES):
                if key not in known:
                    conn.execute(
                        "INSERT INTO caller_roles (key, sort_order) VALUES (?, ?)",
                        (key, i))
                    changed = True
            for key in known - set(SEED_CALLER_ROLES):
                conn.execute("UPDATE caller_roles SET active = 0 WHERE key = ?", (key,))
                changed = True
            for key, by_locale in SEED_TRANSLATIONS["caller_role"].items():
                for locale, text in by_locale.items():
                    conn.execute(
                        "INSERT INTO translations (namespace, key, locale, text) "
                        "VALUES ('caller_role', ?, ?, ?) "
                        "ON CONFLICT(namespace, key, locale) DO UPDATE SET text = ?",
                        (key, locale, text, text))

            known = {r["key"] for r in conn.execute("SELECT key FROM observer_roles")}
            for i, key in enumerate(SEED_OBSERVER_ROLES):
                if key not in known:
                    conn.execute(
                        "INSERT INTO observer_roles (key, sort_order) VALUES (?, ?)",
                        (key, i))
                    changed = True
            for key in known - set(SEED_OBSERVER_ROLES):
                conn.execute("UPDATE observer_roles SET active = 0 WHERE key = ?", (key,))
                changed = True
            for key, by_locale in SEED_TRANSLATIONS["observer_role"].items():
                for locale, text in by_locale.items():
                    conn.execute(
                        "INSERT INTO translations (namespace, key, locale, text) "
                        "VALUES ('observer_role', ?, ?, ?) "
                        "ON CONFLICT(namespace, key, locale) DO UPDATE SET text = excluded.text",
                        (key, locale, text))
            for key, by_locale in SEED_TRANSLATIONS["context"].items():
                for locale, text in by_locale.items():
                    conn.execute(
                        "INSERT INTO translations (namespace, key, locale, text) "
                        "VALUES ('context', ?, ?, ?) "
                        "ON CONFLICT(namespace, key, locale) DO UPDATE SET text = excluded.text",
                        (key, locale, text))
            if changed and conn.execute(
                    "SELECT COUNT(*) FROM config_versions").fetchone()[0]:
                self._publish(conn, "context vocabulary updated")
            # Existing fleets predate the column; fill the core rows so the
            # colours are served without needing the config reseeded.
            for core, color in CORE_COLORS.items():
                conn.execute(
                    "UPDATE label_defs SET color = ? WHERE key = ? AND color IS NULL",
                    (color, core),
                )

    @staticmethod
    def _heal_version_introduced(conn) -> None:
        """Correct the labels this server already inserted claiming version 1.

        The bug above shipped, so two definitions on every existing fleet say
        they have been there since the seed when they arrived at versions 8 and 9.
        Fixable exactly, and without a guess: publishing wrote its own receipt —
        `config_versions.notes` holds "add label not_a_crow" against the version
        that introduced it. So this reads the answer out of the history rather
        than inferring it from a timestamp.

        Only ever moves a version_introduced *forward*, and only from the default.
        A definition that already carries a real version is not second-guessed by
        a string match on a note, and a fleet whose history has been trimmed keeps
        the 1 it cannot improve on.
        """
        for row in conn.execute(
                "SELECT version, notes FROM config_versions "
                "WHERE notes LIKE 'add label %'").fetchall():
            key = row["notes"].removeprefix("add label ")
            conn.execute(
                "UPDATE label_defs SET version_introduced = ? "
                "WHERE key = ? AND version_introduced = 1 AND ? > 1",
                (row["version"], key, row["version"]),
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0]:
                return
            conn.execute(
                "INSERT INTO config_versions (version, published_at, notes) VALUES (?, ?, ?)",
                (1, utc_now(), "seed"),
            )
            for i, (key, core) in enumerate(SEED_LABELS):
                conn.execute(
                    "INSERT INTO label_defs (key, core_mapping, color, sort_order) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO NOTHING",
                    (key, core, CORE_COLORS.get(key), i),
                )
            # Contexts are not seeded here: _init_schema already fills them for
            # fresh and existing databases alike, and doing it in both places
            # violates context_defs.key on every brand-new DB.
            for i, key in enumerate(SEED_INSTRUCTIONS):
                conn.execute(
                    "INSERT INTO instructions (key, sort_order) VALUES (?, ?)", (key, i)
                )
            for namespace, entries in SEED_TRANSLATIONS.items():
                for key, by_locale in entries.items():
                    for locale, text in by_locale.items():
                        # OR IGNORE: _init_schema seeds the context namespace
                        # first so that existing fleets get it too, and seed data
                        # written twice should be a no-op rather than a crash.
                        conn.execute(
                            "INSERT OR IGNORE INTO translations "
                            "(namespace, key, locale, text) VALUES (?, ?, ?, ?)",
                            (namespace, key, locale, text),
                        )
            for common, sci, slug in SEED_TAXONOMY:
                conn.execute(
                    "INSERT INTO taxonomy (common_name, scientific_name, slug) "
                    "VALUES (?, ?, ?)",
                    (common, sci, slug),
                )

    def _resync_core_labels(self) -> None:
        """Make an already-seeded fleet agree with the current CORE set.

        Promoting a class (begging, which used to map down to "call") only
        changes seeding, and seeding runs once — so every existing fleet would
        keep serving the old mapping forever. Reconcile instead of reseeding: a
        label whose key *is* a core maps to itself and carries its own colour,
        and the seed order is reapplied so a migrated DB and a fresh one serve
        the same document. Bumping the version is what makes the phones refetch;
        skip it when nothing moved, or every restart would look like a change.
        """
        with self._connect() as conn:
            if not conn.execute("SELECT COUNT(*) FROM label_defs").fetchone()[0]:
                return
            changed = False
            for core in CORE_CLASSES:
                cur = conn.execute(
                    "UPDATE label_defs SET core_mapping = ?, color = ? "
                    "WHERE key = ? AND (core_mapping != ? OR color IS NOT ?)",
                    (core, CORE_COLORS[core], core, core, CORE_COLORS[core]),
                )
                changed = changed or cur.rowcount > 0
            for i, (key, _) in enumerate(SEED_LABELS):
                conn.execute(
                    "UPDATE label_defs SET sort_order = ? WHERE key = ? AND sort_order != ?",
                    (i, key, i),
                )
            if changed:
                version = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM config_versions").fetchone()[0]
                conn.execute(
                    "INSERT INTO config_versions (version, published_at, notes) "
                    "VALUES (?, ?, ?)",
                    (version, utc_now(), "resync core classes"),
                )

    def current_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(version) FROM config_versions").fetchone()
            return int(row[0] or 0)

    def _translate(self, conn, namespace: str, key: str, locale: str) -> str:
        """Localized text with en fallback, then the raw key as last resort."""
        for loc in (locale, "en"):
            row = conn.execute(
                "SELECT text FROM translations WHERE namespace=? AND key=? AND locale=?",
                (namespace, key, loc),
            ).fetchone()
            if row:
                return row["text"]
        return key

    def get_config(self, locale: str = "en") -> dict:
        with self._connect() as conn:
            labels = [
                {"key": r["key"], "core": r["core_mapping"],
                 # False for judgements about the detection — "not a crow",
                 # "can't tell". Clients show them apart from the call types,
                 # and the training export skips them.
                 "trains": bool(r["trains"]),
                 "text": self._translate(conn, "label", r["key"], locale)}
                for r in conn.execute(
                    "SELECT key, core_mapping, trains FROM label_defs WHERE active=1 "
                    "ORDER BY trains DESC, sort_order")
            ]
            core_colors = {
                r["core_mapping"]: r["color"]
                for r in conn.execute(
                    "SELECT core_mapping, color FROM label_defs "
                    "WHERE active=1 AND trains=1 AND color IS NOT NULL "
                    "ORDER BY sort_order")
            }
            contexts = [
                {"key": r["key"], "category": r["category"],
                 "text": self._translate(conn, "context", r["key"], locale)}
                for r in conn.execute(
                    "SELECT key, category FROM context_defs WHERE active=1 "
                    "ORDER BY sort_order")
            ]
            caller_roles = [
                {"key": r["key"],
                 "text": self._translate(conn, "caller_role", r["key"], locale)}
                for r in conn.execute(
                    "SELECT key FROM caller_roles WHERE active=1 ORDER BY sort_order")
            ]
            observer_roles = [
                {"key": r["key"],
                 "text": self._translate(conn, "observer_role", r["key"], locale)}
                for r in conn.execute(
                    "SELECT key FROM observer_roles WHERE active=1 ORDER BY sort_order")
            ]
            instructions = [
                {"key": r["key"],
                 "text": self._translate(conn, "instruction", r["key"], locale)}
                for r in conn.execute(
                    "SELECT key FROM instructions WHERE active=1 ORDER BY sort_order")
            ]
            guide = [
                {
                    "key": r["key"],
                    "part": r["part"],
                    "title": self._translate(conn, "guide_title", r["key"], locale),
                    "body": self._translate(conn, "guide_body", r["key"], locale),
                }
                for r in conn.execute(
                    "SELECT key, part FROM guide_sections WHERE active=1 "
                    "ORDER BY sort_order")
            ]
            ui = {
                r["key"]: r["text"]
                for r in conn.execute(
                    "SELECT key, text FROM translations WHERE namespace='ui' AND locale=?",
                    (locale,))
            }
            taxonomy = [
                {"common_name": r["common_name"],
                 "name": self._translate(conn, "species", r["common_name"], locale),
                 "scientific_name": r["scientific_name"],
                 "slug": r["slug"], "has_head": bool(r["has_head"])}
                for r in conn.execute(
                    "SELECT * FROM taxonomy WHERE active=1 ORDER BY common_name")
            ]
        return {
            "version": self.current_version(),
            "locale": locale,
            "core_classes": CORE_CLASSES,
            # One colour per core class, and every label inherits its core's.
            # Both clients resolve a call type through this rather than each
            # hardcoding a palette — a rattle that is amber on the phone and blue
            # in the dashboard is a real bug in a labelling tool. Colouring the
            # core rather than the key also means a new label ("mobbing") reads
            # as the alarm it maps to without anyone choosing a colour for it.
            "core_colors": core_colors,
            "labels": labels,
            # What a human witnessed, as opposed to what the bird said. The
            # pairing of the two is the only thing that can turn "this is an
            # alarm call" into "this is what a crow says about a dog".
            "contexts": contexts,
            # What the recordist was to the birds. Served like every other
            # vocabulary so it can be changed in the field without a rebuild.
            "caller_roles": caller_roles,
            "observer_roles": observer_roles,
            "instructions": instructions,
            # The field guide: what to record, and how to read the birds. Served
            # rather than shipped because the answer to "should I record this?"
            # has already changed twice, and a phone cannot be told to update.
            "guide": guide,
            "ui": ui,
            "taxonomy": taxonomy,
        }

    @staticmethod
    def _publish(conn, notes: str) -> int:
        """Bump the served version so the fleet picks the change up.

        Phones ask with `since=<version>` and are answered 304 when it has not
        moved, so a vocabulary change that does not publish is a change no
        recordist ever sees.
        """
        version = (conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM config_versions").fetchone()[0])
        conn.execute(
            "INSERT INTO config_versions (version, published_at, notes) VALUES (?, ?, ?)",
            (version, utc_now(), notes))
        return version

    def add_context(self, key: str, category: str, text: str,
                    translations: dict[str, str] | None = None) -> int:
        """Add a situation to the vocabulary at runtime, and publish it.

        The point of a served vocabulary: noticing in the field that a situation
        recurs should be a config change, not an app release. The phone picks it
        up on its next config fetch.
        """
        key = key.strip()
        if not key:
            raise ValueError("context key cannot be empty")
        with self._connect() as conn:
            order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM context_defs").fetchone()[0]
            version = self._publish(conn, f"add context {key}")
            conn.execute(
                "INSERT INTO context_defs (key, category, sort_order, version_introduced) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "category = excluded.category, active = 1",
                (key, category.strip(), order, version))
            for locale, value in {"en": text, **(translations or {})}.items():
                conn.execute(
                    "INSERT INTO translations (namespace, key, locale, text) "
                    "VALUES ('context', ?, ?, ?) "
                    "ON CONFLICT(namespace, key, locale) DO UPDATE SET text = excluded.text",
                    (key, locale, value))
            return version

    def retire_context(self, key: str) -> int:
        """Stop offering a situation without erasing what was tagged with it."""
        with self._connect() as conn:
            version = self._publish(conn, f"retire context {key}")
            # When it left, beside `version_introduced` which says when it
            # arrived. A relabel queue needs both ends: an event is worth
            # revisiting when its tag was retired after it was recorded.
            conn.execute(
                "UPDATE context_defs SET active = 0, version_retired = ? WHERE key = ?",
                (version, key))
            return version

    def context_exists(self, key: str | None) -> bool:
        """Whether a context key is in the active vocabulary.

        Gated for the same reason call types are: accepting anything would let a
        stale app write situations nothing can group or count, and the value of
        this axis is entirely in the grouping.
        """
        if not key:
            return False
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM context_defs WHERE key=? AND active=1", (key,)
            ).fetchone() is not None

    def caller_role_exists(self, key: str | None) -> bool:
        """Whether a caller role is in the active vocabulary.

        Gated for the same reason as the others: "which kind of bird called" is
        only worth recording if you can group by it later, and prose does not
        group. Absent is not a value — a label with no caller role means nobody
        looked, and the API must not turn that into a claim.
        """
        if not key:
            return False
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM caller_roles WHERE key=? AND active=1", (key,)
            ).fetchone() is not None

    def observer_role_exists(self, key: str | None) -> bool:
        """Whether an observer role is in the active vocabulary.

        Gated like the others. An ungated free-text field here would be worse
        than useless: the whole point is to be able to hold this variable
        constant when comparing recordings, and you cannot group by prose.
        """
        if not key:
            return False
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM observer_roles WHERE key=? AND active=1", (key,)
            ).fetchone() is not None

    def label_exists(self, key: str | None) -> bool:
        """Whether a call type is in the active vocabulary.

        Distinct from having a core class: "not a crow" is a real, storable
        judgement that maps to no training class at all, so existence and
        trainability are different questions.
        """
        if not key:
            return False
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM label_defs WHERE key=? AND active=1", (key,)
            ).fetchone() is not None

    def core_for_label(self, key: str) -> str | None:
        """The CORE class this label trains into, or None if it trains nothing.

        "Not a crow" is a real, storable judgement that maps to no training
        class at all, so this returning None is an answer rather than a
        rejection — see `label_exists`.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT core_mapping, trains FROM label_defs WHERE key=? AND active=1",
                (key,)).fetchone()
            return row["core_mapping"] if row and row["trains"] else None
