"""Media store — the lossless originals. Uploads are written byte-for-byte with
**no transcode** (the hard-won YouTube lesson: lossy ingest discards training
signal). Resumable via Content-Range so a dropped cellular upload resumes instead
of re-sending a large WAV. The storage/storage_ref columns are the seam that lets
the prototype write to apartment disk and the fleet phase write to R2 unchanged.
"""

import hashlib
import logging
import re
import secrets
import sqlite3
from pathlib import Path

from ..core import transcode
from .db_base import Database, utc_now

log = logging.getLogger(__name__)

#: What a media row is allowed to call its format.
#:
#: A format is a filename suffix and half a media type, so it has to be safe as
#: both — and it arrives from the client, which for the dashboard means whatever
#: extension an operator's file happened to have.
#:
#: A shape rather than a list of known codecs: refusing an unusual-but-real
#: recording would cost a capture, and the corpus is the point. `../` is never a
#: recording, and this is what makes the storage ref a single path component
#: rather than a path.
MEDIA_FORMAT = re.compile(r"^[a-z0-9]{1,8}$")
MEDIA_KINDS = ("audio", "video")

#: Kinds the analyzer may be pointed at.
#:
#: An allow-list rather than the absence of a filter, which is what this was.
#: `complete_audio_for` only ever *sorted* by kind, so anything complete on the
#: capture was a candidate and among non-audio kinds the newest won — a rule that
#: happened to be right only because 'audio' and 'video' were the only kinds
#: there had ever been. A future kind now has to opt in rather than be swept in,
#: which is the difference between a guarantee and a coincidence.
ANALYSABLE_KINDS = ("audio", "video")


class MediaStore(Database):
    def __init__(self, db_path, media_dir):
        super().__init__(db_path)
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        # The WAVs, after they have been re-stored as FLAC. Kept rather than
        # deleted: the transcode is verified sample-for-sample, but a field
        # recording cannot be collected again, and throwing the original away
        # is a decision better made by hand once the new copies have been heard.
        self.backups = self.media_dir.parent / "media-originals"

    def create(self, capture_id, kind="audio", format="wav",
               sample_rate=48000, channels=1, client_uuid=None,
               input_device=None, input_honoured=None, pre_roll_sec=None):
        """Register a slot, or return the existing one for this `client_uuid`.

        Idempotent for the same reason captures are: a retried sync must resume
        the upload it already started, not strand a half-written file behind a
        second slot. Returning the existing row also hands the client back its
        `bytes` count, which is the offset its next Content-Range resumes from.
        """
        format = (format or "").strip().lower().lstrip(".")
        if not MEDIA_FORMAT.match(format):
            raise ValueError(
                "format must be a short plain extension like 'wav' or 'mp4'")
        if kind not in MEDIA_KINDS:
            raise ValueError(f"kind must be one of {MEDIA_KINDS}")
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    return existing
            storage_ref = f"{secrets.token_hex(16)}.{format}"
            try:
                cur = conn.execute(
                    "INSERT INTO media (capture_id, client_uuid, kind, storage, storage_ref, "
                    "format, sample_rate, channels, input_device, input_honoured, "
                    "pre_roll_sec, upload_state, created_at) "
                    "VALUES (?, ?, ?, 'local', ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (capture_id, client_uuid, kind, storage_ref, format,
                     sample_rate, channels, input_device,
                     None if input_honoured is None else int(bool(input_honoured)),
                     None if pre_roll_sec is None else float(pre_roll_sec),
                     utc_now()),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def for_capture(self, capture_id) -> list[dict]:
        """Every media slot on a capture, oldest first.

        Read side of the upload path. A phone restoring a capture it no longer
        has needs to know what to download and how big it should be.
        """
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM media WHERE capture_id = ? ORDER BY id", (capture_id,))]

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM media WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(row) if row else None

    def get(self, media_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
            return dict(row) if row else None

    def path(self, media_row) -> Path:
        return self.media_dir / media_row["storage_ref"]

    def complete_audio_for(self, capture_id):
        """The newest fully-uploaded media analysis can run on.

        Audio first, then video. The analyzer decodes with ffmpeg, so an mp4's
        audio track is as readable as a WAV — and a capture that is *only* video
        is exactly what a dashboard upload of a test clip looks like.

        The fallback never changes what a phone capture analyzes: those always
        carry audio, and the camera records muted precisely so the WAV stays the
        pristine signal the model was trained on.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM media WHERE capture_id = ? AND upload_state = 'complete' "
                f"AND kind IN ({','.join('?' * len(ANALYSABLE_KINDS))}) "
                "ORDER BY CASE kind WHEN 'audio' THEN 0 ELSE 1 END, id DESC LIMIT 1",
                (capture_id, *ANALYSABLE_KINDS)).fetchone()
            return dict(row) if row else None

    def append(self, media_id, data: bytes, offset: int) -> dict:
        """Write `data` at byte `offset` (resumable). No transcode — raw bytes.

        Refuses to leave a hole. Seeking past the end of what has arrived makes
        a sparse file whose recorded length is whatever the client asked for,
        and `finalize` reads the whole of it back to hash it — so one byte
        written at 8 GiB cost 8 GiB of memory the moment the upload completed.

        A resumable upload never needs it: the client resumes from the `bytes`
        this hands back, so it writes at the end of what it has or re-sends
        something already there. Both stay allowed; the hole does not.
        """
        media = self.get(media_id)
        # A completed upload is sealed. finalize() has already hashed the bytes,
        # so a later write would leave sha256 describing a file that no longer
        # exists — and because owned_capture hands operators every capture, that
        # write is how one operator silently rewrites another recordist's field
        # recording. A genuine resume never reaches here: the client resumes from
        # the `bytes` it was handed, and that upload is not yet complete.
        if media["upload_state"] == "complete":
            raise ValueError("this upload is already complete and cannot be appended to")
        dest = self.path(media)
        stored = dest.stat().st_size if dest.exists() else 0
        if offset < 0 or offset > stored:
            raise ValueError(
                f"cannot write at byte {offset}: {stored} bytes have arrived, "
                "so that would leave a gap")
        with open(dest, "r+b" if dest.exists() else "wb") as fh:
            fh.seek(offset)
            fh.write(data)
        size = dest.stat().st_size
        with self._connect() as conn:
            conn.execute(
                "UPDATE media SET bytes = ?, upload_state = 'partial' WHERE id = ?",
                (size, media_id))
            return self._row(conn, media_id)

    def finalize(self, media_id) -> dict:
        """Hash the assembled file, store it as FLAC, and mark it complete."""
        media = self.get(media_id)
        digest = hashlib.sha256(self.path(media).read_bytes()).hexdigest()
        with self._connect() as conn:
            conn.execute(
                "UPDATE media SET sha256 = ?, upload_state = 'complete', uploaded_at = ? "
                "WHERE id = ?", (digest, utc_now(), media_id))
            row = self._row(conn, media_id)
        return self.compress(row["id"]) or row

    def compress(self, media_id):
        """Re-store a WAV as FLAC, keeping the original in the backup directory.

        Lossless and measured — experiments/0007 — and the encoder is verified
        rather than trusted: the samples are hashed before and after, and a
        mismatch leaves everything exactly as it was.

        Returns the updated row, or None when there was nothing to do. A failure
        is deliberately not raised past here: the upload succeeded, the audio is
        on disk and readable, and refusing the whole sync because a compression
        step failed would trade the recording for the saving.
        """
        media = self.get(media_id)
        if not media or media["kind"] != "audio" or media["format"] != "wav":
            return None
        source = self.path(media)
        if not source.exists() or media["upload_state"] != "complete":
            return None

        target = source.with_suffix(".flac")
        try:
            samples = transcode.to_flac(source, target)
        except transcode.TranscodeError as failed:
            # Deliberately swallowed (see the docstring) — but not silently:
            # to the caller a failed compression and "nothing to compress"
            # are the same None, so this line is the only place the failure
            # exists at all.
            log.warning("FLAC compression failed for media %s, keeping WAV: %s",
                        media_id, failed)
            target.unlink(missing_ok=True)
            return None

        transcode.archive(source, self.backups)
        size = target.stat().st_size
        with self._connect() as conn:
            conn.execute(
                "UPDATE media SET storage_ref = ?, format = 'flac', bytes = ?, "
                # The stored bytes changed, so the hash of the stored bytes has
                # to change with them or every later integrity check is a lie.
                "sha256 = ?, pcm_sha256 = ? WHERE id = ?",
                (target.name, size,
                 hashlib.sha256(target.read_bytes()).hexdigest(), samples, media_id))
            return self._row(conn, media_id)

    def as_wav(self, media_row) -> Path:
        """The audio as a WAV, rendering one if what is stored is not.

        For the phone, which parses RIFF directly to draw waveforms, normalise
        playback and crop before upload. Rendered into the backup directory
        beside the originals rather than into the media directory, which holds
        only things that are somebody's actual recording.
        """
        stored = self.path(media_row)
        if media_row["format"] != "flac":
            return stored
        self.backups.mkdir(parents=True, exist_ok=True)
        rendered = self.backups / f"{Path(media_row['storage_ref']).stem}.rendered.wav"
        if not rendered.exists():
            transcode.to_wav(stored, rendered)
        return rendered

    @staticmethod
    def _row(conn, media_id):
        return dict(conn.execute("SELECT * FROM media WHERE id = ?",
                                 (media_id,)).fetchone())
