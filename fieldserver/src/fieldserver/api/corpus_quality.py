"""How well documented a corpus recording is, read from what its source said.

The detector's guesses say what is *in* the audio; this says how much the
person who uploaded it told us — a remark, a grade, a call type, the other
species audible, timed annotations. None of it is ground truth either, but a
recording with a remark and an A grade is a different kind of row from a bare
file, and the corpus page should let the difference be seen and filtered on.

Sources disagree on shape, so the signals are read by key and by value shape,
never by source name: a grade is a letter (A best), a number (5 best) or a
review state, and a remark is whichever text field the row happens to carry.
"""

import html
import json
import re
from dataclasses import dataclass, field


def _json(path: str) -> str:
    return f"(CASE WHEN json_valid(r.raw) THEN json_extract(r.raw, '{path}') END)"


def _text(path: str) -> str:
    return f"NULLIF(trim(CAST({_json(path)} AS TEXT)), '')"


class QualitySignals:
    """The SQL that turns a raw source row into comparable quality columns."""

    #: Free-text fields, most descriptive first. A short tag field is last so
    #: it only stands in when nothing better was written.
    REMARK_KEYS = ("rmk", "mediaNotes", "description", "caption", "comments",
                   "remarks", "title", "description_en")

    TIERS = ("high", "mid", "low", "unrated")

    @classmethod
    def remark(cls) -> str:
        return "COALESCE(" + ", ".join(_text(f"$.{key}") for key in cls.REMARK_KEYS) + ")"

    @staticmethod
    def tier() -> str:
        number = "CAST(r.quality AS REAL)"
        is_number = "(r.quality GLOB '[0-9]*')"
        return f"""
            CASE
              WHEN r.quality IS NULL OR trim(r.quality) = '' THEN 'unrated'
              WHEN upper(r.quality) = 'A' OR r.quality = 'research'
                   OR ({is_number} AND {number} >= 4) THEN 'high'
              WHEN upper(r.quality) IN ('B', 'C') OR r.quality = 'needs_id'
                   OR ({is_number} AND {number} >= 2.5) THEN 'mid'
              WHEN upper(r.quality) IN ('D', 'E') OR r.quality = 'casual'
                   OR ({is_number} AND {number} > 0) THEN 'low'
              ELSE 'unrated'
            END"""

    @staticmethod
    def labelled() -> str:
        return ("(r.call_type IS NOT NULL AND trim(r.call_type) NOT IN ('', 'uncertain'))")

    @staticmethod
    def background() -> str:
        also = _json("$.also")
        return f"""
            (CASE
               WHEN json_valid(r.raw) AND json_type(r.raw, '$.also') = 'array'
                    THEN json_array_length({also}) > 0
               WHEN {_text('$.background_species')} IS NOT NULL THEN 1
               ELSE 0
             END)"""

    @staticmethod
    def annotated() -> str:
        return """
            (CASE
               WHEN json_valid(r.raw) AND json_type(r.raw, '$.events') = 'array'
                    THEN json_array_length(r.raw, '$.events') > 0
               WHEN json_valid(r.raw) AND json_type(r.raw, '$.events') = 'object'
                    THEN json_extract(r.raw, '$.events') != '{}'
               ELSE 0
             END)"""

    @classmethod
    def cte(cls) -> str:
        """`rq`: every recording with its quality columns, computed once."""
        return f"""
            WITH rq AS (
              SELECT r.*,
                     {cls.remark()} AS remark,
                     {cls.tier()} AS tier,
                     {cls.labelled()} AS labelled,
                     {cls.background()} AS background,
                     {cls.annotated()} AS annotated
              FROM recordings r
            )
        """

    @staticmethod
    def richness() -> str:
        """A sort key, not a score to report: grade, then each extra signal."""
        return ("(CASE r.tier WHEN 'high' THEN 2 WHEN 'mid' THEN 1 ELSE 0 END)"
                " + (r.remark IS NOT NULL) + r.labelled + r.annotated")

    @classmethod
    def coverage_columns(cls) -> str:
        """Per-group counts of each signal, for the summary's quality table."""
        tiers = ", ".join(f"SUM(r.tier = '{t}') AS tier_{t}" for t in cls.TIERS)
        return f"""
            COUNT(*) AS recordings,
            SUM(r.remark IS NOT NULL) AS with_remark,
            {tiers},
            SUM(r.labelled) AS labelled,
            SUM(r.annotated) AS annotated,
            SUM(r.background) AS background,
            SUM(r.lat IS NOT NULL) AS geo,
            SUM(r.date IS NOT NULL AND r.date != '') AS dated,
            SUM(r.analyzed_at IS NOT NULL) AS analyzed,
            SUM(COALESCE(d.calls, 0) > 0) AS with_calls
        """


class Remark:
    """Uploader text as a reader should see it: some sources store HTML."""

    TAG = re.compile(r"<[^>]+>")
    BREAK = re.compile(r"<\s*(br|/p|/div|/li)\s*/?>", re.IGNORECASE)
    BLANK_LINES = re.compile(r"\n\s*\n+")

    @classmethod
    def clean(cls, text: str | None) -> str | None:
        if not text:
            return None
        plain = cls.TAG.sub("", cls.BREAK.sub("\n", text))
        plain = cls.BLANK_LINES.sub("\n\n", html.unescape(plain)).strip()
        return plain or None

    @classmethod
    def preview(cls, text: str | None, limit: int = 140) -> str | None:
        plain = cls.clean(text)
        if plain is None:
            return None
        flat = " ".join(plain.split())
        return flat if len(flat) <= limit else flat[:limit - 1] + "…"


@dataclass
class Annotation:
    label: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    seconds: float | None = None


@dataclass
class RecordingNotes:
    """What one source row says about itself, for the detail view."""

    remark: str | None = None
    background: list[str] = field(default_factory=list)
    flags: dict[str, str] = field(default_factory=dict)
    rating_count: int | None = None
    annotations: list[Annotation] = field(default_factory=list)

    FLAG_KEYS = {"animal-seen": "animal seen", "playback-used": "playback used",
                 "method": "method", "sex": "sex", "stage": "stage",
                 "dvc": "device", "mic": "mic", "recording_equipment": "equipment",
                 "habitat": "habitat", "weather": "weather"}

    @classmethod
    def from_raw(cls, raw: str | None) -> "RecordingNotes":
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            return cls()
        if not isinstance(body, dict):
            return cls()
        return cls(
            remark=cls._remark(body),
            background=cls._background(body),
            flags={label: str(body[key]).strip() for key, label in cls.FLAG_KEYS.items()
                   if isinstance(body.get(key), (str, int, float))
                   and str(body[key]).strip()},
            rating_count=body.get("ratingCount") if isinstance(body.get("ratingCount"), int) else None,
            annotations=cls._annotations(body.get("events")),
        )

    @staticmethod
    def _remark(body: dict) -> str | None:
        for key in QualitySignals.REMARK_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return Remark.clean(value)
        return None

    @staticmethod
    def _background(body: dict) -> list[str]:
        also = body.get("also")
        if isinstance(also, list):
            return [str(s) for s in also if str(s).strip()]
        named = body.get("background_species")
        if isinstance(named, str) and named.strip():
            return [s.strip() for s in named.split(",") if s.strip()]
        return []

    @staticmethod
    def _annotations(events) -> list[Annotation]:
        if isinstance(events, list):
            return sorted((Annotation(
                label=", ".join(e.get("tags") or []) or "event",
                start_seconds=e.get("start_time_seconds"),
                end_seconds=e.get("end_time_seconds"),
            ) for e in events if isinstance(e, dict)),
                key=lambda a: a.start_seconds or 0)
        if isinstance(events, dict):
            return sorted((Annotation(label=str(k), seconds=round(float(v), 1))
                           for k, v in events.items() if isinstance(v, (int, float))),
                          key=lambda a: -(a.seconds or 0))
        return []
