"""Individual birds, so a label can say which one called.

Experiment 0017 established that the audio cannot answer this: five crows in one
recording produce the cluster structure one crow produces, and what structure
exists tracks where the bird was standing rather than who it was. So attribution
is not something a model recovers later — it is something a person sees, once,
while the bird is calling in front of them, or it is lost.

The roster CRUD surface (routes and store methods for adding, renaming and
removing birds) was built ahead of any client and removed as dead code on
2026-08-16; git history has it whole if the roster feature returns. What
survives is the one check the label write path actually makes: whether a
`crow_id` on an incoming label belongs to the contributor writing it.
"""

from .db_base import Database


class CrowStore(Database):
    """The attribution of a label to a bird on the recordist's roster."""

    def owned_by(self, crow_id, contributor_id) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT f.contributor_id FROM crows c "
                "JOIN families f ON f.id = c.family_id WHERE c.id = ?",
                (crow_id,)).fetchone()
            return bool(row) and row["contributor_id"] == contributor_id
