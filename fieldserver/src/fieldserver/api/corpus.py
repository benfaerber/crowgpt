"""The training corpus, browsable: recordings, detections, and the audio.

A window onto the corpus database the collection tooling maintains under
`data/` — read-only by construction (the connection is opened `mode=ro`), the
same stance the Training panel takes toward runs: this server owns none of it
and must work when the corpus is absent, answering an honest nothing.

WHAT A COUNT MEANS HERE. Rows in `recordings` are whatever the tooling
gathered — the `source` column is data, not vocabulary this repo defines.
Rows in `detections` are a model's guesses with timestamps; `candidate` rows
are the model unsure, counted apart and never folded into a confident total.
Nothing on this page is ground truth, and the summary says which column is
which rather than letting a table launder guesses into fact.

NO WIRE_VERSION BUMP. Dashboard surface; the phone neither knows nor cares.
"""

import os
import sqlite3
from pathlib import Path

from flask import abort, jsonify, request, send_file

from ..stores.contributors import FLEET_ROLES

REPO = Path(__file__).resolve().parents[4]

MAX_PAGE = 200

#: Suffix -> mimetype for playback. A wrong type reads as "the file is
#: broken" in a browser rather than "the header is wrong".
AUDIO_TYPES = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".3gp": "audio/3gpp",
    ".webm": "audio/webm", ".opus": "audio/ogg",
}

SORTS = {
    "calls": "calls DESC",
    "caw": "caw_seconds DESC",
    "duration": "duration_seconds DESC",
    "recent": "created_at DESC",
}


def _db_path() -> Path:
    override = os.environ.get("CORPUS_DB")
    if override:
        return Path(override).expanduser()
    data = os.environ.get("DATA_DIR")
    base = Path(data).expanduser() if data else REPO / "data"
    return base / "corvid.db"


def _connect():
    path = _db_path()
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


#: The per-recording rollup every list view joins against. Confident only —
#: candidates are counted in their own column so the split stays visible.
ROLLUP = """
    LEFT JOIN (
        SELECT recording_id,
               SUM(candidate = 0) AS calls,
               SUM(candidate = 1) AS candidates,
               SUM(CASE WHEN candidate = 0 THEN end_seconds - start_seconds
                        ELSE 0 END) AS caw_seconds
        FROM detections GROUP BY recording_id
    ) d ON d.recording_id = r.id
"""


def register(app, deps) -> None:
    current_actor = deps.current_actor

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    @app.get("/api/corpus/summary")
    def corpus_summary():
        """The corpus by source and by heard species, or an honest nothing."""
        current_operator()
        conn = _connect()
        if conn is None:
            return jsonify({"available": False, "path": str(_db_path()),
                            "sources": [], "species": [], "totals": None})
        with conn:
            sources = [dict(r) for r in conn.execute(
                """
                SELECT r.source,
                       COUNT(*) AS recordings,
                       SUM(r.downloaded) AS downloaded,
                       ROUND(SUM(r.duration_seconds) / 3600.0, 1) AS hours,
                       SUM(r.analyzed_at IS NOT NULL) AS analyzed,
                       COALESCE(SUM(d.calls), 0) AS calls,
                       ROUND(COALESCE(SUM(d.caw_seconds), 0) / 3600.0, 2) AS caw_hours
                FROM recordings r
                """ + ROLLUP + """
                GROUP BY r.source ORDER BY calls DESC
                """)]
            species = [dict(r) for r in conn.execute(
                """
                SELECT species,
                       COUNT(*) AS calls,
                       COUNT(DISTINCT recording_id) AS recordings,
                       ROUND(SUM(end_seconds - start_seconds) / 60.0, 1) AS caw_minutes
                FROM detections WHERE candidate = 0
                GROUP BY species ORDER BY calls DESC
                """)]
            totals = dict(conn.execute(
                """
                SELECT COUNT(*) AS recordings,
                       SUM(r.downloaded) AS downloaded,
                       ROUND(SUM(r.duration_seconds) / 3600.0, 1) AS hours,
                       SUM(r.analyzed_at IS NOT NULL) AS analyzed,
                       COALESCE(SUM(d.calls), 0) AS calls,
                       COALESCE(SUM(d.candidates), 0) AS candidates,
                       ROUND(COALESCE(SUM(d.caw_seconds), 0) / 3600.0, 1) AS caw_hours
                FROM recordings r
                """ + ROLLUP).fetchone())
        conn.close()
        return jsonify({"available": True, "path": str(_db_path()),
                        "sources": sources, "species": species,
                        "totals": totals})

    @app.get("/api/corpus/recordings")
    def corpus_recordings():
        """A page of recordings, filterable by what the detector heard."""
        current_operator()
        conn = _connect()
        if conn is None:
            return jsonify({"recordings": [], "total": 0})

        clauses, params = ["1=1"], []
        if request.args.get("source"):
            clauses.append("r.source = ?")
            params.append(request.args["source"])
        if request.args.get("species"):
            clauses.append(
                "r.id IN (SELECT recording_id FROM detections "
                "         WHERE candidate = 0 AND species = ?)")
            params.append(request.args["species"])
        if request.args.get("with_calls") == "1":
            clauses.append("COALESCE(d.calls, 0) > 0")
        if request.args.get("q"):
            like = f"%{request.args['q']}%"
            clauses.append("(r.recordist LIKE ? OR r.species LIKE ? OR r.source_ref LIKE ?)")
            params += [like, like, like]

        order = SORTS.get(request.args.get("sort", "caw"), SORTS["caw"])
        limit = min(int(request.args.get("limit", 50)), MAX_PAGE)
        offset = max(int(request.args.get("offset", 0)), 0)
        where = " AND ".join(clauses)

        with conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM recordings r {ROLLUP} WHERE {where}",
                params).fetchone()[0]
            rows = [dict(r) for r in conn.execute(
                f"""
                SELECT r.id, r.source, r.source_ref, r.species, r.recordist,
                       r.date, r.duration_seconds, r.license, r.downloaded,
                       r.page_url, r.created_at,
                       COALESCE(d.calls, 0) AS calls,
                       COALESCE(d.candidates, 0) AS candidates,
                       ROUND(COALESCE(d.caw_seconds, 0), 1) AS caw_seconds
                FROM recordings r {ROLLUP}
                WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?
                """, params + [limit, offset])]
        conn.close()
        return jsonify({"recordings": rows, "total": total})

    @app.get("/api/corpus/recordings/<int:recording_id>")
    def corpus_recording(recording_id):
        """One recording with every detection, timestamps and all."""
        current_operator()
        conn = _connect()
        if conn is None:
            abort(404, "no corpus database")
        try:
            row = conn.execute(
                "SELECT id, source, source_ref, species, recordist, date, "
                "       duration_seconds, license, downloaded, file_path, "
                "       page_url, location, lat, lng, quality "
                "FROM recordings WHERE id = ?", (recording_id,)).fetchone()
            if row is None:
                abort(404, "no such recording")
            detections = [dict(r) for r in conn.execute(
                "SELECT start_seconds, end_seconds, species, confidence, "
                "       candidate, call_type, call_type_confidence "
                "FROM detections WHERE recording_id = ? ORDER BY start_seconds",
                (recording_id,))]
        finally:
            conn.close()
        body = dict(row)
        playable = bool(body.get("file_path")) and Path(body["file_path"]).exists()
        body.pop("file_path", None)  # a server path is not the dashboard's business
        body["playable"] = playable
        body["detections"] = detections
        return jsonify(body)

    @app.get("/api/corpus/recordings/<int:recording_id>/audio")
    def corpus_audio(recording_id):
        """The stored bytes, ranged so a player can seek a two-hour file.

        The path comes from the corpus row and nowhere else — no client
        input names a file.
        """
        current_operator()
        conn = _connect()
        if conn is None:
            abort(404, "no corpus database")
        row = conn.execute(
            "SELECT file_path FROM recordings WHERE id = ? AND downloaded = 1",
            (recording_id,)).fetchone()
        conn.close()
        if row is None or not row["file_path"]:
            abort(404, "no audio for this recording")
        path = Path(row["file_path"])
        if not path.exists():
            abort(404, "audio file missing on disk")
        mimetype = AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return send_file(path, mimetype=mimetype, conditional=True,
                         download_name=path.name)
