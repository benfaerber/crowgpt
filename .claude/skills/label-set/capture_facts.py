"""Everything known about a capture, in one readable dump.

Written for the `label-set` skill, which proposes a call type and a set of
context chips per span. The proposal is only as good as its inputs, and the
inputs are scattered: the recordist's own words live in `observations`, the
model's guesses in `detected_calls` behind the *latest* `analysis_results` row,
the audio measurements in `capture_quality`, and the vocabulary on the running
server. Reading four of those and forgetting the fifth is how a proposal ends
up quietly ignoring what the recordist already wrote down.

Captures are named by server id, because that is how they are discussed
("capture 113") and how the dashboard shows them. Paths come from
experiments/lib/media.py so this honours FIELD_DB like everything else.
"""

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from experiments.lib.media import field_db  # noqa: E402

CONFIG_URL = "http://localhost:5100/api/config?locale=en"


def _conf(value):
    """A confidence, or '?' when the analyzer did not give one.

    A detection can arrive with no call type and no confidence — the segment
    was flagged as worth an ear without the classifier committing to what it
    was. Those are exactly the candidates this dump exists to surface, so a
    missing number must print rather than take the whole capture down with it.
    """
    return "  ?  " if value is None else f"{value:.2f}"


def _sec(value):
    return "     ?" if value is None else f"{value:6.1f}"


class Vocabulary:
    """The call types and context keys a label may use.

    Preferred from the running server, because that is what the phone was
    served and therefore what the recordist can actually tap. Falls back to the
    database, which is the same truth one restart earlier, and says which it
    used — a proposal built on a retired key wastes a field session.
    """

    def __init__(self, calls, contexts, source, caller_roles=()):
        self.calls = calls
        self.contexts = contexts
        self.source = source
        self.caller_roles = list(caller_roles)

    @classmethod
    def load(cls, conn):
        try:
            with urllib.request.urlopen(CONFIG_URL, timeout=3) as response:
                served = json.load(response)
            calls = [c["key"] for c in served["labels"]]
            contexts = [(c["category"], c["key"], c["text"]) for c in served["contexts"]]
            callers = [(c["key"], c["text"]) for c in served.get("caller_roles", [])]
            return cls(calls, contexts, "the running server", callers)
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError):
            calls = [r[0] for r in conn.execute(
                "SELECT key FROM label_defs WHERE active=1 ORDER BY sort_order")]
            contexts = [(r[0], r[1], r[1]) for r in conn.execute(
                "SELECT category, key FROM context_defs WHERE active=1 ORDER BY sort_order")]
            try:
                callers = [(r[0], r[0]) for r in conn.execute(
                    "SELECT key FROM caller_roles WHERE active=1 ORDER BY sort_order")]
            except sqlite3.OperationalError:
                callers = []  # a database older than 0020
            return cls(calls, contexts, "the database (server unreachable)", callers)

    def render(self):
        lines = [f"VOCABULARY (from {self.source} — never propose a key absent here)",
                 "  call types: " + ", ".join(self.calls), "  context:"]
        seen = None
        for category, key, text in self.contexts:
            if category != seen:
                lines.append(f"    [{category}]")
                seen = category
            lines.append(f"      {key:24} {text}")
        if self.caller_roles:
            lines.append("  caller roles (which bird made the call):")
            for key, text in self.caller_roles:
                lines.append(f"      {key:24} {text}")
        return "\n".join(lines)


class Capture:
    """One capture, and everything recorded about it.

    Found by name, because the name is what the app shows and therefore the only
    handle the recordist has. The id still exists and still appears in the
    output — it is what the dashboard and every verification query speak — but
    nobody should have to look it up to ask a question about a recording.
    """

    def __init__(self, conn, row):
        self.conn = conn
        self.row = row
        self.id = row["id"]

    @classmethod
    def find(cls, conn, needle):
        """Resolve a capture id, or a fragment of a name, to one capture."""
        if needle.isdigit():
            found = conn.execute(
                "SELECT * FROM captures WHERE id = ?", (int(needle),)).fetchall()
        else:
            found = conn.execute(
                "SELECT * FROM captures WHERE name LIKE ? ORDER BY recorded_at",
                (f"%{needle}%",)).fetchall()
        if len(found) == 1:
            return cls(conn, found[0])
        if not found:
            raise SystemExit(
                f"nothing matching {needle!r} in {field_db()}\n\n"
                "Recent captures:\n" + cls._listing(conn))
        raise SystemExit(
            f"{needle!r} matches {len(found)} captures — be more specific:\n"
            + "\n".join(f"  {r['recorded_at'][:10]}  {r['name']}" for r in found))

    @staticmethod
    def _listing(conn):
        rows = conn.execute(
            "SELECT recorded_at, name, keep FROM captures "
            "WHERE name IS NOT NULL AND name != '' "
            "ORDER BY recorded_at DESC LIMIT 15").fetchall()
        return "\n".join(
            f"  {r['recorded_at'][:10]}  {'*' if r['keep'] else ' '} {r['name']}"
            for r in rows)

    def _description(self):
        """What the recordist wrote, and how — typed, or spoken and confirmed.

        `source` is selected rather than ignored because a confirmed transcript
        lands here as an ordinary observation, and a year from now nothing else
        distinguishes it from something typed at a desk. The words are his
        either way; how they arrived is worth keeping.
        """
        rows = self.conn.execute(
            "SELECT body, source FROM observations WHERE capture_id = ? ORDER BY id",
            (self.id,)).fetchall()
        parts = []
        for r in rows:
            parts.append(r["body"] + ("  [spoken in the field, confirmed]"
                                      if r["source"] == "voice" else ""))
        return "\n".join(parts)

    def _dictations(self):
        """Spoken notes whose transcript nobody has stood behind yet.

        Confirmed ones are deliberately excluded: they are already an
        `observations` row and would otherwise print twice — once as testimony
        and once as a transcript — which reads as two independent accounts
        agreeing with each other.
        """
        return self.conn.execute(
            "SELECT transcript, transcript_model, mean_logprob, duration_sec "
            "FROM dictations WHERE capture_id = ? AND transcript IS NOT NULL "
            "AND confirmed_at IS NULL ORDER BY id",
            (self.id,)).fetchall()

    def _quality(self):
        return self.conn.execute(
            "SELECT * FROM capture_quality WHERE capture_id = ?", (self.id,)).fetchone()

    def _detections(self):
        """The latest analysis only. An older run's rows are not a second opinion."""
        return self.conn.execute(
            "SELECT dc.start_sec, dc.end_sec, dc.call_type, dc.confidence, "
            "       dc.crow_conf, dc.candidate "
            "FROM detected_calls dc JOIN analysis_results ar ON ar.id = dc.analysis_id "
            "WHERE ar.capture_id = ? AND ar.id = "
            "      (SELECT MAX(id) FROM analysis_results WHERE capture_id = ?) "
            "ORDER BY dc.start_sec", (self.id, self.id)).fetchall()

    def _ai_descriptions(self):
        """Machine-written prose, whole-capture row first then spans in time order."""
        return self.conn.execute(
            "SELECT start_sec, end_sec, description, model, written_at "
            "FROM ai_descriptions WHERE capture_id = ? "
            "ORDER BY start_sec IS NOT NULL, start_sec, end_sec",
            (self.id,)).fetchall()

    def _labels(self):
        return self.conn.execute(
            "SELECT l.id, l.start_sec, l.end_sec, l.call_type, l.caller_role, "
            "       (SELECT name FROM crows WHERE id = l.crow_id) AS crow_name, "
            "       (SELECT group_concat(key, ' + ') FROM context_events "
            "        WHERE label_id = l.id) AS context "
            "FROM labels l WHERE l.capture_id = ? ORDER BY l.start_sec",
            (self.id,)).fetchall()

    def render(self):
        row, out = self.row, []
        out.append(f"{row['name'] or '(unnamed)'}")
        out.append(f"  recorded {row['recorded_at']}  {row['duration_sec']}s  "
                   f"{'* kept' if row['keep'] else 'not kept'}  status={row['status']}")
        out.append(f"  (capture {self.id} on the server — for queries, not for the app)")
        out.append(f"  observer_role={row['observer_role'] or '-'}  "
                   f"distance={row['distance_band'] or '-'}  "
                   f"adults={row['adult_count'] or '-'} "
                   f"juveniles={row['juvenile_count'] or '-'}")

        description = self._description()
        if description:
            out.append("\nWHAT THE RECORDIST WROTE (weigh this above the model):")
            out += [f"  {line}" for line in description.splitlines()]
        else:
            out.append("\nWHAT THE RECORDIST WROTE: nothing — ask before proposing.")
        if row["notes"]:
            out.append("\nNOTES:")
            out += [f"  {line}" for line in row["notes"].splitlines()]
        spoken = self._dictations()
        if spoken:
            out.append(
                "\nWHAT THE RECORDIST SAID OUT LOUD (transcribed by machine — his"
                "\nwords, a machine's spelling, and NOBODY HAS CHECKED IT. Speech"
                "\nrecognition gets proper nouns, digits and species names wrong and"
                "\ngives no sign that it did, which is exactly what you are about to"
                "\nask him about. Quote a name, a number or a species back to him"
                "\nbefore you rely on it):")
            for n, note in enumerate(spoken, start=1):
                length = f"{note['duration_sec']:.0f}s" if note["duration_sec"] else "?"
                confidence = ("" if note["mean_logprob"] is None
                              else f", mean logprob {note['mean_logprob']:.2f}")
                out.append(f"  note {n} ({length}{confidence}):")
                out += [f"    {line}"
                        for line in (note["transcript"] or "").splitlines()]

        if row["behavior_guess"]:
            out.append(f"\nBEHAVIOUR GUESS (an interpretation, not an observation):"
                       f"\n  {row['behavior_guess']}")

        quality = self._quality()
        if quality is not None:
            out.append(f"\nAUDIO: band SNR {quality['band_snr_db']:.1f} dB  "
                       f"peak {quality['peak_dbfs']:.1f} dBFS  "
                       f"clipped {quality['clipped_samples']}")

        out.append("\nMODEL DETECTIONS (guesses — a low crow_conf is a candidate,")
        out.append("the faint awkward calls most needing an ear; not_a_crow is a")
        out.append("useful answer nothing else produces):")
        for d in self._detections():
            flag = "  <- candidate" if d["candidate"] else ""
            out.append(f"  {_sec(d['start_sec'])}-{_sec(d['end_sec'])}s  "
                       f"{d['call_type'] or '?':12} conf={_conf(d['confidence'])} "
                       f"crow={_conf(d['crow_conf'])}{flag}")

        written = self._ai_descriptions()
        if written:
            # Below the detections on purpose. This is prose a model wrote from
            # the same audio the detections came from, so it is a second reading
            # of the evidence and not a second witness — treating it as one is
            # how the model ends up marking its own homework.
            out.append("\nWHAT A MODEL WROTE (a guess, like the detections above —")
            out.append("never weigh it against the recordist, and never let it stand")
            out.append("in for an answer nobody gave):")
            for row_ in written:
                where = ("whole recording" if row_["start_sec"] is None
                         else f"{_sec(row_['start_sec'])}-{_sec(row_['end_sec'])}s")
                stamp = (row_["written_at"] or "")[:10]
                out.append(f"  [{where}] {row_['model'] or 'unknown model'}, {stamp}")
                out += [f"    {line}" for line in row_["description"].splitlines()]

        labels = self._labels()
        out.append("\nHUMAN LABELS SO FAR:" if labels else "\nHUMAN LABELS SO FAR: none.")
        for label in labels:
            # Caller shown as "-" rather than omitted. An absent caller means
            # nobody looked, and that is a fact worth seeing while quizzing —
            # it is the only field on a label that cannot be filled in later.
            caller = label["crow_name"] or label["caller_role"] or "-"
            out.append(f"  [{label['id']}] {label['start_sec']:6.1f}-"
                       f"{label['end_sec']:6.1f}s  {label['call_type']:12} "
                       f"caller={caller:14} {label['context'] or '(no context)'}")
        return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        with sqlite3.connect(f"file:{field_db()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            raise SystemExit(
                'usage: capture_facts.py "<part of the capture name>"\n\n'
                "Recent captures:\n" + Capture._listing(conn))
    needle = " ".join(sys.argv[1:])
    with sqlite3.connect(f"file:{field_db()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        print(Capture.find(conn, needle).render())
        print()
        print(Vocabulary.load(conn).render())


if __name__ == "__main__":
    main()
