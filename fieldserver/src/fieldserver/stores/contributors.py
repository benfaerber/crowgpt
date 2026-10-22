"""People. A contributor is *who* collected something; a device is *what* they
collected it on.

Until now identity was the device row, which meant a reinstall minted a new
contributor and stranded everything the old one owned. That is survivable at one
recordist and untenable at a thousand, and it is expensive to change late:
`device_id` is the owner column in every table and every query, so the migration
gets harder with every capture. Hence this layer now, while the corpus is small.

What is deliberately *not* here: passwords, sessions, email. Device bearer tokens
remain the credential — they are scoped, revocable, and work offline, which is
what a field app in a wood needs. Adding a password credential later is additive
(a new table, a new route); moving ownership is not, which is why only the second
one is done here.

Roles
    contributor  sees its own captures
    operator     + reads the whole fleet (the dashboard)
    admin        + changes other contributors' role/status

`admin` is granted by `tools/admin.py`, not by any endpoint. An HTTP route that
mints administrators, on a server with no TLS, would hand out the fleet to
whoever reached it.
"""

import hashlib
import secrets

from .db_base import Database, utc_now

ROLES = ("contributor", "operator", "admin")
FLEET_ROLES = ("operator", "admin")

# How precisely a contributor is willing to say where they were.
#
#   exact   coordinates stored as recorded
#   fuzzed  coordinates snapped to a `fuzz_miles`-wide grid on the phone before
#           they are sent — territory-level truth with no street in it
#   region  no coordinates at all, on the phone or here
#
# Enforced on the phone, which is the only place it can actually be enforced:
# a privacy setting the server applies is a promise, one the phone applies is a
# fact. This end refuses coordinates from a `region` contributor anyway, and
# re-snaps a `fuzzed` contributor's, because a promise kept in two places is
# worth more than one kept in either.
# What gets *recorded*. Whether it is *shown* is `censor_coords`, a separate
# question that used to be folded in here as a middle value.
LOCATION_PRECISIONS = ("exact", "fuzzed", "region")

# The radius has to mean something and has to stay a radius: zero would be
# exact wearing fuzzed's name, and a thousand would be region with extra steps.
FUZZ_MILES_RANGE = (1, 50)

# The old middle value, still accepted from a phone that has not been updated.
# It meant "record them, never show them", which is exactly exact + censor, so
# it maps rather than erroring — refusing it would make a stale client's privacy
# setting fail closed into something *less* private on its next write.
def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class ContributorStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def create(self, display_name, role="contributor"):
        """Create a contributor. Returns (public row, raw claim code)."""
        if role not in ROLES:
            raise ValueError(f"unknown role '{role}'")
        claim_code = secrets.token_urlsafe(9)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO contributors (public_uuid, display_name, role, "
                "claim_code_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (secrets.token_hex(16), (display_name or "").strip() or "Unnamed recordist",
                 role, _hash(claim_code), utc_now()),
            )
            return self._public(conn, cur.lastrowid), claim_code

    def get(self, contributor_id):
        with self._connect() as conn:
            return self._public(conn, contributor_id)

    def by_claim_code(self, claim_code):
        """The contributor a claim code joins, or None. Suspended people can't
        recruit new devices."""
        if not claim_code:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM contributors WHERE claim_code_hash = ? AND status = 'active'",
                (_hash(claim_code),)).fetchone()
            return self._public(conn, row["id"]) if row else None

    def rotate_claim_code(self, contributor_id):
        claim_code = secrets.token_urlsafe(9)
        with self._connect() as conn:
            conn.execute("UPDATE contributors SET claim_code_hash = ? WHERE id = ?",
                         (_hash(claim_code), contributor_id))
        return claim_code

    def rename(self, contributor_id, display_name):
        name = (display_name or "").strip()
        if not name:
            raise ValueError("display name cannot be empty")
        with self._connect() as conn:
            conn.execute("UPDATE contributors SET display_name = ? WHERE id = ?",
                         (name, contributor_id))
            return self._public(conn, contributor_id)

    def set_role(self, contributor_id, role):
        if role not in ROLES:
            raise ValueError(f"unknown role '{role}' — one of {', '.join(ROLES)}")
        with self._connect() as conn:
            conn.execute("UPDATE contributors SET role = ? WHERE id = ?",
                         (role, contributor_id))
            return self._public(conn, contributor_id)

    def set_location_precision(self, contributor_id, precision, region=None,
                               censor_coords=None, fuzz_miles=None):
        """How precisely this person is willing to say where they were.

        Theirs to set, from their own phone — not an operator's to set for them,
        which is why this sits beside rename rather than beside set_role.

        The region comes along because the two are only meaningful together: at
        `region` precision it is the *only* thing said about place, and a phone
        that tightens the setting without providing one would quietly stop
        saying anything at all.
        """
        # The pre-split `exact_private` stopped being accepted 2026-08-09:
        # revision 0013 rewrote every stored row into exact + censor, and no
        # build still on a phone can send it — so tolerance here would only
        # hide a client that has genuinely gone wrong.
        censor = None
        if precision not in LOCATION_PRECISIONS:
            raise ValueError(
                f"unknown location precision '{precision}' — one of "
                f"{', '.join(LOCATION_PRECISIONS)}")
        if censor_coords is not None:
            censor = 1 if censor_coords else 0
        if fuzz_miles is not None:
            low, high = FUZZ_MILES_RANGE
            try:
                fuzz_miles = float(fuzz_miles)
            except (TypeError, ValueError):
                raise ValueError(f"fuzz_miles must be a number, {low}-{high}")
            if not low <= fuzz_miles <= high:
                raise ValueError(f"fuzz_miles must be between {low} and {high}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE contributors SET location_precision = ?, "
                "censor_coords = COALESCE(?, censor_coords), "
                "fuzz_miles = COALESCE(?, fuzz_miles), "
                "region = COALESCE(?, region) WHERE id = ?",
                (precision, censor, fuzz_miles,
                 (region or "").strip() or None, contributor_id))
            return self._public(conn, contributor_id)

    def set_status(self, contributor_id, status):
        if status not in ("active", "suspended"):
            raise ValueError(f"unknown status '{status}'")
        with self._connect() as conn:
            conn.execute("UPDATE contributors SET status = ? WHERE id = ?",
                         (status, contributor_id))
            return self._public(conn, contributor_id)

    def list_all(self):
        with self._connect() as conn:
            return [self._public(conn, r["id"]) for r in
                    conn.execute("SELECT id FROM contributors ORDER BY created_at")]

    OWNED_TABLES = ("captures", "families", "labels", "observations",
                    "context_events", "sightings")

    # Every table with a contributor_id — what merge() must move before the
    # absorbed row can be deleted. OWNED_TABLES plus the two that ownership
    # transfer has no business touching: devices (kept on purpose, see merge())
    # and device_logs, where the column is NOT NULL. With foreign keys
    # enforced, a table missing from this list does not orphan rows — it
    # aborts the DELETE and rolls the whole merge back, which is how merging
    # anyone who had ever tagged a context, logged a sighting or synced a log
    # line failed outright.
    REFERENCING_TABLES = ("devices", "device_logs", *OWNED_TABLES)

    def merge(self, keep_id, absorb_ids) -> dict:
        """Move everything owned by `absorb_ids` onto `keep_id` and delete them.

        The devices survive — that is the point. A merged contributor keeps every
        phone it ever recorded on, and each capture still records which one took
        it, so provenance is not what merging costs you.
        """
        absorb = [i for i in absorb_ids if i != keep_id]
        if not absorb:
            return {"kept": keep_id, "absorbed": [], "moved": {}}
        placeholders = ",".join("?" * len(absorb))
        moved = {}
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM contributors WHERE id = ?",
                                (keep_id,)).fetchone():
                raise ValueError(f"no contributor {keep_id} to merge into")
            for table in self.REFERENCING_TABLES:
                cur = conn.execute(
                    f"UPDATE {table} SET contributor_id = ? "
                    f"WHERE contributor_id IN ({placeholders})",
                    (keep_id, *absorb))
                moved[table] = cur.rowcount
            conn.execute(f"DELETE FROM contributors WHERE id IN ({placeholders})", absorb)
        return {"kept": keep_id, "absorbed": absorb, "moved": moved}

    @staticmethod
    def _public(conn, contributor_id):
        """Never includes claim_code_hash — nothing outside this module needs it."""
        row = conn.execute(
            "SELECT id, public_uuid, display_name, role, status, created_at, "
            "location_precision, censor_coords, fuzz_miles, region "
            "FROM contributors WHERE id = ?", (contributor_id,)).fetchone()
        return dict(row) if row else None
