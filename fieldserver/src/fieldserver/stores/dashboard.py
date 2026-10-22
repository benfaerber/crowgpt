"""Read-only cross-table queries behind the operator dashboard.

The per-table stores answer "what does this device own?" — the questions the
mobile client asks. The operator asks fleet-shaped questions instead ("what came
in today, from whom, and what still needs labelling?"), which cut across every
table at once. Those joins live here rather than being smeared across the stores,
and nothing in this module writes.
"""

from .db_base import Database
from .merges import not_a_part


def _mask_coords(row: dict) -> dict:
    """Blank the exact fix when the recordist asked for it to stay hidden.

    `censor_coords` means "recorded, never shown". The phone honours it, but the
    fleet read endpoints were handing the raw latitude/longitude to the client
    and trusting it to do the hiding — so a plain curl with an operator token
    read the coordinate a contributor asked to mask, usually their home. Nulled
    here, at the one place every fleet view passes through, the promise the UI
    makes is kept by the API that answers it. The flag rides along so the client
    can still say *why* the point is blank rather than that it is missing.
    """
    if row.get("censor_coords"):
        row = {**row, "latitude": None, "longitude": None}
    return row


def latest_analysis_calls(*, candidate: int) -> str:
    """Count detections from each capture's most recent analysis only.

    A capture can hold several analyses — re-running happens whenever the model
    or the thresholds change, and that has happened repeatedly — so a plain
    COUNT(*) over `detected_calls` reports one capture's calls once per pass.
    The capture list has always scoped to MAX(id); the fleet summary and the
    family panel did not, so the three disagreed with each other.
    """
    return f"""
        SELECT COUNT(*) FROM detected_calls dc
          JOIN analysis_results ar ON ar.id = dc.analysis_id
         WHERE dc.candidate = {int(candidate)}
           AND ar.id = (SELECT MAX(id) FROM analysis_results
                         WHERE capture_id = ar.capture_id)
    """


class DashboardQueries(Database):
    def fleet_summary(self) -> dict:
        with self._connect() as conn:
            def scalar(sql, args=()):
                return conn.execute(sql, args).fetchone()[0] or 0

            statuses = {
                r["status"]: r["n"] for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM captures GROUP BY status")
            }
            jobs = {
                r["state"]: r["n"] for r in conn.execute(
                    "SELECT state, COUNT(*) AS n FROM analysis_jobs GROUP BY state")
            }
            return {
                "contributors": scalar(
                    "SELECT COUNT(*) FROM contributors WHERE status = 'active'"),
                "devices": scalar("SELECT COUNT(*) FROM devices WHERE revoked_at IS NULL"),
                "captures": scalar(
                    f"SELECT COUNT(*) FROM captures WHERE {not_a_part()}"),
                "capture_statuses": statuses,
                "jobs": jobs,
                "media_bytes": scalar("SELECT SUM(bytes) FROM media"),
                "media_complete": scalar(
                    "SELECT COUNT(*) FROM media WHERE upload_state = 'complete'"),
                # Confirmed only. A candidate is a question the model asked, and
                # counting questions as findings is how a corpus
                # starts describing itself instead of any crow.
                #
                # Latest analysis per capture, too. These were raw COUNT(*) over
                # the whole table, so every re-analysis added another full set
                # of rows to the fleet total — and re-analysis happens whenever
                # the model or the thresholds change.
                "detected_calls": scalar(latest_analysis_calls(candidate=0)),
                "candidate_calls": scalar(latest_analysis_calls(candidate=1)),
                "labels": scalar("SELECT COUNT(*) FROM labels"),
                "observations": scalar("SELECT COUNT(*) FROM observations"),
                # The corpus is mostly seeded and uploaded test material. This
                # is the only count that is about crows rather than about the
                # pipeline.
                # Kept is the count this project leans on hardest — it is what
                # separates real field audio from seeded clips — so counting a
                # merged-away part alongside its replacement overstates exactly
                # the number that must not be overstated.
                "kept_captures": scalar(
                    f"SELECT COUNT(*) FROM captures WHERE keep = 1 AND {not_a_part()}"),
                # The gap that matters: analyzed audio nobody has confirmed yet.
                "unlabelled_captures": scalar(
                    "SELECT COUNT(*) FROM captures c WHERE c.status = 'analyzed' "
                    "AND NOT EXISTS (SELECT 1 FROM labels l WHERE l.capture_id = c.id)"),
            }

    def devices(self) -> list[dict]:
        """Every handset, with the person it belongs to.

        `label` is what its owner calls it and `display_name` is who they are.
        """
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                """
                SELECT d.id, d.label, d.contributor_id,
                       d.locale, d.platform, d.created_at, d.last_seen_at,
                       d.revoked_at, d.app_version, d.app_commit,
                       ct.display_name, ct.role, ct.status,
                       (SELECT COUNT(*) FROM captures c WHERE c.device_id = d.id)
                           AS capture_count,
                       (SELECT COUNT(*) FROM labels l WHERE l.device_id = d.id)
                           AS label_count
                FROM devices d
                LEFT JOIN contributors ct ON ct.id = d.contributor_id
                ORDER BY ct.display_name, d.created_at
                """)]

    def contributors(self) -> list[dict]:
        """People, with their fleet and their output — the view that replaces
        counting device rows and hoping they are different humans."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                """
                SELECT ct.id, ct.public_uuid, ct.display_name, ct.role, ct.status,
                       ct.created_at, ct.location_precision, ct.region,
                       (SELECT COUNT(*) FROM devices d
                         WHERE d.contributor_id = ct.id AND d.revoked_at IS NULL)
                           AS device_count,
                       (SELECT GROUP_CONCAT(d.label, ', ') FROM devices d
                         WHERE d.contributor_id = ct.id AND d.revoked_at IS NULL
                           AND d.label IS NOT NULL) AS device_labels,
                       (SELECT COUNT(*) FROM captures c WHERE c.contributor_id = ct.id)
                           AS capture_count,
                       (SELECT COUNT(*) FROM labels l WHERE l.contributor_id = ct.id)
                           AS label_count,
                       (SELECT MAX(d.last_seen_at) FROM devices d
                         WHERE d.contributor_id = ct.id) AS last_seen_at
                FROM contributors ct
                ORDER BY capture_count DESC, ct.created_at
                """)]

    def relabel_queue(self, limit=200) -> list[dict]:
        """Labels whose vocabulary has moved under them.

        Two ways that happens, and the second is the one worth catching:

          - the call type was **retired** after the label was made, so the
            label names something the fleet no longer offers;
          - the key was retired and later **reintroduced**, which is how a tag
            comes back meaning something else. A label made before that has the
            old meaning and reads as though it had the new one.

        Both are found by comparing what the labeller was shown
        (`labels.config_version`) with when the definition last changed. Labels
        with no version predate the stamp and are excluded rather than guessed
        at — inferring one from `created_at` is exactly the arithmetic that does
        not work, because phones label offline against a cached vocabulary.
        """
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                """
                SELECT l.id, l.capture_id, l.call_type, l.species, l.created_at,
                       l.config_version,
                       d.active AS call_type_active,
                       d.version_introduced, d.version_retired,
                       ct.display_name AS contributor_name,
                       CASE
                         WHEN d.key IS NULL THEN 'the call type no longer exists'
                         WHEN d.active = 0 THEN 'the call type was retired'
                         ELSE 'the call type was reintroduced with a new meaning'
                       END AS why
                  FROM labels l
                  LEFT JOIN label_defs d ON d.key = l.call_type
                  LEFT JOIN contributors ct ON ct.id = l.contributor_id
                 WHERE l.config_version IS NOT NULL
                   AND (
                     d.key IS NULL
                     OR (d.active = 0 AND d.version_retired > l.config_version)
                     OR d.version_introduced > l.config_version
                   )
                 ORDER BY l.created_at DESC
                 LIMIT ?
                """, (limit,))]

    def captures(self, limit=200) -> list[dict]:
        with self._connect() as conn:
            return [_mask_coords(dict(r)) for r in conn.execute(
                f"""
                SELECT c.*, ct.display_name AS contributor_name,
                       -- Their choice travels with every row that shows a
                       -- place. Masking decided per query rather than carried
                       -- here is how one view ends up honouring it and the next
                       -- one does not.
                       ct.location_precision,
                       -- Shown-or-not, separate from recorded-or-not since
                       -- wire 17. describePlace needs both or it publishes
                       -- rows the old exact_private used to hide.
                       ct.censor_coords,
                       d.label AS device_label,
                       -- One row per capture by construction (capture_id is the
                       -- PK), so a join rather than the MAX(id) dance calls need.
                       -- measured_at rides along because a flat NULL in
                       -- band_snr_db is two different facts: never measured,
                       -- or measured and unmeasurable (a merged capture's
                       -- silence gaps). The gauge renders them differently.
                       q.band_snr_db, q.measured_at AS quality_measured_at,
                       (SELECT COUNT(*) FROM labels l WHERE l.capture_id = c.id)
                           AS label_count,
                       (SELECT COUNT(*) FROM observations o WHERE o.capture_id = c.id)
                           AS observation_count,
                       (SELECT SUM(m.bytes) FROM media m WHERE m.capture_id = c.id)
                           AS media_bytes,
                       (SELECT COUNT(*) FROM detected_calls dc
                          JOIN analysis_results ar ON ar.id = dc.analysis_id
                         WHERE ar.capture_id = c.id AND dc.candidate = 0
                           AND ar.id = (SELECT MAX(id) FROM analysis_results
                                         WHERE capture_id = c.id)) AS call_count
                FROM captures c
                LEFT JOIN devices d ON d.id = c.device_id
                LEFT JOIN contributors ct ON ct.id = c.contributor_id
                LEFT JOIN capture_quality q ON q.capture_id = c.id
                -- A capture folded into a merge is the same audio as the one
                -- that replaced it, so listing both shows one morning's work
                -- as two mornings'. The rows are kept so a merge stays
                -- reversible; this is where they stop being counted twice.
                WHERE {not_a_part("c.id")}
                ORDER BY c.created_at DESC
                LIMIT ?
                """, (limit,))]

    def capture(self, capture_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT c.*, ct.display_name AS contributor_name, "
                "ct.location_precision, ct.censor_coords, d.label AS device_label "
                "FROM captures c "
                "LEFT JOIN devices d ON d.id = c.device_id "
                "LEFT JOIN contributors ct ON ct.id = c.contributor_id "
                "WHERE c.id = ?",
                (capture_id,)).fetchone()
            return _mask_coords(dict(row)) if row else None

    def media_for_capture(self, capture_id) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT id, kind, format, sample_rate, channels, input_device, "
                "input_honoured, pre_roll_sec, bytes, sha256, upload_state, uploaded_at "
                "FROM media WHERE capture_id = ? ORDER BY id",
                (capture_id,))]

    def families(self) -> list[dict]:
        """Every family, with where and when it has been heard.

        A family is the unit that makes a corpus more than a pile of clips: the
        same birds, the same territory, across months. Aggregating here rather
        than in the app is the point — the phone only knows the families *it*
        created, and the interesting questions ("which family do we have most
        of?", "which has gone quiet?") are fleet-shaped.

        The centroid is the average of its captures' coordinates, which is what
        turns a family into a place — the "in SLC" half of "family A in SLC".
        """
        with self._connect() as conn:
            return [_mask_coords(dict(r)) for r in conn.execute(
                """
                SELECT f.id, f.name, f.color, f.notes, f.created_at,
                       ct.display_name AS contributor_name,
                       -- The centroid is an average of exact fixes, so a family
                       -- of one capture has a centroid equal to that capture's
                       -- coordinate. It masks on the family owner's setting like
                       -- every other coordinate the fleet hands out.
                       ct.censor_coords,
                       COUNT(c.id) AS capture_count,
                       MIN(c.recorded_at) AS first_heard,
                       MAX(c.recorded_at) AS last_heard,
                       AVG(c.latitude) AS latitude,
                       AVG(c.longitude) AS longitude,
                       -- Latest analysis only, confirmed only — the same two
                       -- conditions the capture list applies. Without them a
                       -- capture analysed twice counted twice, and every
                       -- candidate counted as a finding, in the one panel
                       -- labelled "Calls". Analysis is re-run whenever the
                       -- model or the thresholds move, which has happened
                       -- repeatedly, so this drifted further with each pass.
                       (SELECT COUNT(*) FROM detected_calls dc
                          JOIN analysis_results ar ON ar.id = dc.analysis_id
                          JOIN captures c2 ON c2.id = ar.capture_id
                         WHERE c2.family_id = f.id AND dc.candidate = 0
                           AND ar.id = (SELECT MAX(id) FROM analysis_results
                                         WHERE capture_id = c2.id)) AS call_count,
                       (SELECT COUNT(*) FROM observations o
                          JOIN captures c3 ON c3.id = o.capture_id
                         WHERE c3.family_id = f.id) AS observation_count
                FROM families f
                LEFT JOIN contributors ct ON ct.id = f.contributor_id
                LEFT JOIN captures c ON c.family_id = f.id
                GROUP BY f.id
                ORDER BY capture_count DESC, f.name
                """)]

    def family(self, family_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT f.*, ct.display_name AS contributor_name FROM families f "
                "LEFT JOIN contributors ct ON ct.id = f.contributor_id WHERE f.id = ?",
                (family_id,)).fetchone()
            return dict(row) if row else None

    def family_captures(self, family_id, limit=200) -> list[dict]:
        with self._connect() as conn:
            return [_mask_coords(dict(r)) for r in conn.execute(
                """
                SELECT c.id, c.recorded_at, c.created_at, c.status, c.duration_sec,
                       c.latitude, c.longitude, c.location_name, c.notes,
                       -- Selected because this row is passed to describePlace,
                       -- which without them defaults to "exact" and prints the
                       -- coordinates whatever the recordist asked for. The panel
                       -- that quietly does not honour the setting, found while
                       -- adding censor_coords.
                       ct.location_precision, ct.censor_coords,
                       (SELECT COUNT(*) FROM detected_calls dc
                          JOIN analysis_results ar ON ar.id = dc.analysis_id
                         WHERE ar.capture_id = c.id AND dc.candidate = 0
                           AND ar.id = (SELECT MAX(id) FROM analysis_results
                                         WHERE capture_id = c.id)) AS call_count
                FROM captures c
                LEFT JOIN contributors ct ON ct.id = c.contributor_id
                WHERE c.family_id = ?
                ORDER BY c.recorded_at DESC LIMIT ?
                """, (family_id, limit))]

    def family_call_types(self, family_id) -> list[dict]:
        """What this family is heard saying — its vocal profile.

        Only the latest analysis per capture counts. A capture re-analyzed after
        a model update otherwise contributes twice, which would quietly make
        whichever clips were reprocessed look like the family's favourite call.
        """
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                """
                SELECT dc.species, dc.call_type, COUNT(*) AS n,
                       AVG(dc.confidence) AS mean_confidence
                FROM detected_calls dc
                JOIN analysis_results ar ON ar.id = dc.analysis_id
                JOIN captures c ON c.id = ar.capture_id
                WHERE c.family_id = ?
                  -- Confirmed only: a family's vocal profile built from the
                  -- model's uncertain guesses is a profile of the street.
                  AND dc.candidate = 0
                  AND ar.id = (SELECT MAX(id) FROM analysis_results
                                WHERE capture_id = c.id)
                GROUP BY dc.species, dc.call_type
                ORDER BY n DESC
                """, (family_id,))]

    def call_context_matrix(self, kept_only=False) -> dict:
        """Which call types co-occur with which witnessed situations.

        The question the project exists to answer, in its bluntest form: count
        the confirmed calls in captures tagged with each context. Co-occurrence,
        not inference — a crow calling while a dog is present is not necessarily
        calling *about* the dog, and nothing here claims otherwise.

        Human labels only, deliberately. Model detections would let the model's
        own bias decide what a context sounds like, which is circular in exactly
        the direction that matters.

        `kept_only` filters to captures the recordist marked as real
        observations. The corpus is mostly seeded archive audio and repeated
        test uploads, so the unfiltered matrix describes the pipeline rather
        than any crow.
        """
        kept = "AND c.keep = 1" if kept_only else ""
        with self._connect() as conn:
            # Joined on label_id, not capture_id. Joining on the capture would
            # pair every situation in a recording with every call in it, so one
            # dog and one song would report that crows sing at dogs.
            pairs = [dict(r) for r in conn.execute(
                """
                SELECT ce.key AS context_key, l.call_type, l.species, COUNT(*) AS n,
                       COUNT(DISTINCT l.capture_id) AS captures
                FROM context_events ce
                JOIN labels l ON l.id = ce.label_id
                JOIN captures c ON c.id = l.capture_id
                WHERE 1=1 {kept}
                -- Species is part of the key, not a detail. "Alarm call" means
                -- a different vocalisation in Corvus brachyrhynchos and Corvus
                -- cornix, and a contributor in Germany recording hooded crows
                -- would otherwise have their calls averaged into the American
                -- Crow result — producing a finding about neither bird.
                GROUP BY ce.key, l.call_type, l.species
                ORDER BY n DESC
                """.format(kept=kept))]
            contexts = [dict(r) for r in conn.execute(
                """
                SELECT key, COUNT(DISTINCT capture_id) AS captures,
                       COUNT(DISTINCT label_id) AS labelled_calls
                FROM context_events
                WHERE label_id IS NOT NULL
                GROUP BY key ORDER BY captures DESC
                """)]
            # The denominator: situations a human watched happen on a recording
            # confirmed to contain no crow calls at all.
            #
            # Without this the matrix can only say what was going on when a crow
            # called. It cannot say how often the same thing happened and the
            # crow said nothing — and until it can, "crows alarm at dogs" is not
            # a finding, it is a count of the times somebody pressed record.
            #
            # Kept a separate key, never merged into `pairs`. These rows have no
            # call to pair with, and inventing one would be the exact confusion
            # the label_id rule exists to prevent.
            silent = [dict(r) for r in conn.execute(
                """
                SELECT ce.key, COUNT(DISTINCT ce.capture_id) AS captures
                FROM context_events ce
                JOIN captures c ON c.id = ce.capture_id
                WHERE ce.label_id IS NULL
                  AND c.silent_confirmed_at IS NOT NULL {kept}
                GROUP BY ce.key ORDER BY captures DESC
                """.format(kept=kept))]
            silent_captures = conn.execute(
                "SELECT COUNT(*) FROM captures c "
                "WHERE c.silent_confirmed_at IS NOT NULL {kept}".format(kept=kept)
            ).fetchone()[0]
            # Confirmed calls nobody has said anything about are the gap worth
            # showing: the sound is read, the meaning is not, and they are what
            # to work on next.
            unlabelled = conn.execute(
                """
                SELECT COUNT(*) FROM labels l
                WHERE NOT EXISTS (SELECT 1 FROM context_events ce WHERE ce.label_id = l.id)
                """).fetchone()[0]
        return {"pairs": pairs, "contexts": contexts,
                "silent_contexts": silent, "silent_captures": silent_captures,
                "contexts_awaiting_labels": unlabelled, "kept_only": kept_only}

    def label_totals(self) -> list[dict]:
        """What the corpus actually contains, by call type — the retrain view."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT call_type, species, COUNT(*) AS n FROM labels "
                "GROUP BY call_type, species ORDER BY n DESC")]
