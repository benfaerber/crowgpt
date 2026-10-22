"""A capture is a recording session — a sighting with audio attached.

It carries what a sighting carried (lat/lng/location_name/notes/family_id) plus
an owner and a status, so the note and the recording arrive together instead of
being reconciled afterwards, and map/list code works on it unchanged.
"""

import sqlite3

from .db_base import Database, utc_now


# How far away the bird was, coarsely.
#
# A fixed list rather than a served vocabulary, unlike labels and contexts.
# Those change as you learn what recurs; distance bands are physical and are
# bounded by what a person can estimate looking at a bird. "About twenty metres"
# is a real answer; metres to a decimal place would be invented precision.
#
# Per capture rather than per call: it describes where you stood, and asking it
# again for every caw would be a tap nobody takes.
DISTANCE_BANDS = ("under_5m", "5_20m", "20_50m", "over_50m")


def _count(value):
    """A head count, or None for "nobody counted".

    Nullable throughout, because not counting is the normal case and has to stay
    distinguishable from counting zero — zero adults is a real observation about
    a group of fledglings.
    """
    if value is None:
        return None
    number = int(value)
    if number < 0:
        raise ValueError("a count cannot be negative")
    return number


class CaptureStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, contributor_id, device_id, latitude=None, longitude=None,
            coord_fuzz_miles=None,
            location_name=None, recorded_at=None, duration_sec=None, notes=None,
            family_id=None, client_uuid=None, name=None, keep=False,
            app_version=None, app_commit=None, trigger=None, observer_role=None,
            behavior_guess=None, crop_start_sec=None, crop_end_sec=None,
            distance_band=None, adult_count=None, juvenile_count=None,
            unaged_count=None, region=None):
        """Create a capture, or return the existing one for this `client_uuid`.

        The field app records offline and syncs on demand, so a retry after a
        lost response is routine rather than exceptional. Keying on the device's
        own uuid makes the create idempotent — without it a dropped response
        leaves a duplicate capture (and a duplicate media slot) on the server
        with no way to tell it from the real one. Scoped per contributor so one
        person can't address another's rows by guessing a uuid.

        `device_id` is still recorded: it is which phone took the recording,
        which stays worth knowing once it is no longer who owns it.
        """
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, contributor_id, client_uuid)
                if existing:
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO captures (contributor_id, device_id, client_uuid, "
                    "name, keep, latitude, longitude, coord_fuzz_miles, "
                    "location_name, recorded_at, "
                    "duration_sec, notes, family_id, app_version, app_commit, "
                    "trigger, "
                    "observer_role, behavior_guess, crop_start_sec, crop_end_sec, "
                    "distance_band, adult_count, juvenile_count, unaged_count, "
                    "region, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, 'recording', ?)",
                    (contributor_id, device_id, client_uuid, name, int(bool(keep)),
                     latitude, longitude, coord_fuzz_miles,
                     location_name, recorded_at, duration_sec,
                     notes, family_id,
                     None if app_version is None else int(app_version), app_commit,
                     trigger,
                     observer_role, (behavior_guess or "").strip() or None,
                     None if crop_start_sec is None else float(crop_start_sec),
                     None if crop_end_sec is None else float(crop_end_sec),
                     distance_band,
                     _count(adult_count), _count(juvenile_count), _count(unaged_count),
                     (region or "").strip() or None,
                     utc_now()),
                )
            except sqlite3.IntegrityError:
                # Two syncs raced on the same uuid; the loser reads the winner's row.
                return self._by_client_uuid(conn, contributor_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    @staticmethod
    def _by_client_uuid(conn, contributor_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM captures WHERE contributor_id = ? AND client_uuid = ?",
            (contributor_id, client_uuid)).fetchone()
        return dict(row) if row else None

    def get(self, capture_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM captures WHERE id = ?",
                               (capture_id,)).fetchone()
            return dict(row) if row else None

    def for_contributor(self, contributor_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM captures WHERE contributor_id = ? ORDER BY created_at DESC",
                (contributor_id,))]

    # What a recordist can still change after the audio has landed. Deliberately
    # not `recorded_at` or `duration_sec`: those describe the recording itself,
    # and a client that could rewrite them could rewrite history.
    MUTABLE = ("name", "keep", "family_id", "notes", "location_name",
               "latitude", "longitude", "coord_fuzz_miles",
               "observer_role", "behavior_guess",
               "distance_band", "adult_count", "juvenile_count", "unaged_count",
               # Editable because tightening the setting must be able to reach
               # back: a recordist who switches to region-only expects the
               # captures already up here to stop carrying coordinates too.
               "region")

    def update(self, capture_id, **fields):
        """Apply an edit made after the capture was first uploaded.

        Assigning a family to a capture already on the server used to be
        impossible: the family was only ever sent while *creating* the row, so a
        capture tagged afterwards kept syncing and silently stayed unassigned.
        """
        changes = {k: v for k, v in fields.items() if k in self.MUTABLE and v is not None}
        if not changes:
            return self.get(capture_id)
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._connect() as conn:
            conn.execute(f"UPDATE captures SET {assignments} WHERE id = ?",
                         (*changes.values(), capture_id))
            return self._row(conn, capture_id)

    def confirm_silent(self, capture_id, silent=True):
        """Mark, or unmark, that this recording holds no crow calls."""
        with self._connect() as conn:
            conn.execute("UPDATE captures SET silent_confirmed_at = ? WHERE id = ?",
                         (utc_now() if silent else None, capture_id))
            return self._row(conn, capture_id)

    def mark_nothing_to_label(self, capture_id, nothing=True):
        """Mark, or unmark, that this recording is not worth labelling.

        A different claim from confirm_silent, which says a human listened and
        heard no crow calls — that is an observation about crows and belongs in
        the denominator. This says the recording is not field material at all: a
        test upload, a seeded clip, a walk that caught only traffic. Its only job
        is to let the label queue empty, and conflating the two would put test
        uploads into the "listened to, genuinely quiet" count.
        """
        with self._connect() as conn:
            conn.execute("UPDATE captures SET nothing_to_label_at = ? WHERE id = ?",
                         (utc_now() if nothing else None, capture_id))
            return self._row(conn, capture_id)

    def clear_nothing_to_label_if_set(self, capture_id) -> None:
        """A label contradicts the dismissal, so the dismissal goes.

        Same rule as clear_silent_if_set below and for the same reason: labelling
        something you had waved past is a correction, not an error, and nobody
        should have to undo a flag to record it.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE captures SET nothing_to_label_at = NULL "
                "WHERE id = ? AND nothing_to_label_at IS NOT NULL", (capture_id,))

    def clear_silent_if_set(self, capture_id) -> None:
        """A labelled call contradicts the claim, so the claim goes.

        Called when a label lands. Cleared rather than refused: finding a call
        in something you thought was silent is a correction, not an error, and
        the recordist should not have to undo a checkbox to record it.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE captures SET silent_confirmed_at = NULL "
                "WHERE id = ? AND silent_confirmed_at IS NOT NULL", (capture_id,))

    def set_status(self, capture_id, status):
        with self._connect() as conn:
            conn.execute("UPDATE captures SET status = ? WHERE id = ?",
                         (status, capture_id))

    @staticmethod
    def _row(conn, capture_id):
        return dict(conn.execute("SELECT * FROM captures WHERE id = ?",
                                 (capture_id,)).fetchone())
