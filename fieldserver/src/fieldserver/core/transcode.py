"""Storing the audio as FLAC, without ever trusting that it worked.

Measured in experiments/0007: bit-exact on all 77 files in the corpus, and real
field recordings come out at 22.4% of WAV — far better than the published
ratios, because a crow ten metres up peaks around -30 dBFS and quiet audio
carries fewer bits of entropy per sample. Storage is the only cost in this
project that grows, so this is the one lever worth pulling.

The care here is all in one idea: **the encoder is not believed**. Every
transcode is verified by decoding the result back to raw PCM and comparing a
hash of the samples with the same hash taken from the original. Only then is
the WAV allowed to go anywhere. An encoder that quietly mangles one file in ten
thousand would be undetectable afterwards — the WAV is gone, the FLAC decodes
happily, and nothing says the recording is not what the microphone heard.

That verification is also why the hash is of the *samples* rather than the
file. `media.sha256` hashes the stored bytes, which is right for detecting a
corrupted upload and useless for comparing two containers holding identical
audio. Both are worth having and they answer different questions.
"""

import hashlib
import os
import resource
import shutil
import subprocess
from pathlib import Path

# Level 8. Level 12 costs 3.5x the CPU for another half a percentage point —
# measured, in experiments/0007.
COMPRESSION_LEVEL = 8

#: How long one ffmpeg call may run before it is killed.
#:
#: Every call here decodes bytes a phone uploaded, and a malformed container can
#: make a decoder spin rather than fail. Without this the request thread waits
#: forever and `capture_output` accumulates stderr while it does — a wedged
#: worker, reachable by anything holding an enrolment token. Two minutes is far
#: above the longest real capture and far below "never".
#:
#: The offline scripts in pipelines/ have carried a timeout since they were
#: written; the request path was the one place missing it.
FFMPEG_TIMEOUT_SEC = float(os.environ.get("FIELD_FFMPEG_TIMEOUT_SEC", "120"))

#: Address-space ceiling for the child, or 0 to leave it alone.
#:
#: Bounds what a decoder can allocate while parsing an untrusted file. Generous
#: on purpose — ffmpeg reserves address space for thread stacks and mapped
#: libraries that it never touches, and a limit tight enough to be interesting
#: is tight enough to refuse a legitimate long recording.
FFMPEG_MEMORY_MB = int(os.environ.get("FIELD_FFMPEG_MEMORY_MB", "4096"))

#: Global flags every invocation carries.
#:
#: `-nostdin` because ffmpeg reads stdin for interactive keypresses, and a
#: child inheriting the terminal a worker was started from can swallow input
#: meant for its parent.
BASE_FLAGS = ("-nostdin", "-v", "error")

# Built once, at import. `_cap_memory` runs after fork and before exec, where
# the less it does the better: Flask serves threaded, and CPython documents
# preexec_fn as unsafe in the presence of threads because the child inherits
# whatever locks were held at fork. An attribute lookup and one syscall is
# about as close to nothing as this can get. FIELD_FFMPEG_MEMORY_MB=0 turns it
# off without a code change if it ever does misbehave.
_LIMIT = (FFMPEG_MEMORY_MB * 1024 * 1024,) * 2


def _cap_memory() -> None:
    resource.setrlimit(resource.RLIMIT_AS, _LIMIT)


class TranscodeError(RuntimeError):
    """The audio did not survive, so nothing is deleted and nothing is changed."""


def run_ffmpeg(args: list[str], failed: str, *, capture: bool = True):
    """Run ffmpeg under a timeout and a memory ceiling, or raise TranscodeError.

    Every failure mode arrives as one exception type because every caller's
    correct response is the same: leave the original where it is. A timeout and
    a memory kill are not special — they are just ways the audio did not
    survive, and `failed` is the sentence the caller wants said about it.

    analyzer/birdnet.py carries its own copy of this, deliberately: the analyzer
    is a path in and findings out, and importing the field server to decode a
    file would give it a database, a job queue and two shared secrets. The
    duplication is six lines; the coupling would not be.
    """
    try:
        return subprocess.run(
            ["ffmpeg", *BASE_FLAGS, *args],
            check=True, capture_output=capture,
            timeout=FFMPEG_TIMEOUT_SEC,
            preexec_fn=_cap_memory if FFMPEG_MEMORY_MB else None,
        )
    except subprocess.TimeoutExpired as error:
        raise TranscodeError(
            f"{failed}: still running after {FFMPEG_TIMEOUT_SEC:.0f}s") from error
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise TranscodeError(f"{failed}: {error}") from error


def pcm_sha256(path: Path) -> str:
    """Hash of the samples, with the container taken out of the question.

    Decoded through the same tool on both sides, so a WAV header carrying a
    LIST chunk is not mistaken for a difference in the audio.
    """
    raw = run_ffmpeg(
        ["-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
        f"could not decode {path.name}",
    ).stdout
    if not raw:
        raise TranscodeError(f"{path.name} decoded to no audio at all")
    return hashlib.sha256(raw).hexdigest()


def to_flac(source: Path, target: Path) -> str:
    """Encode, verify the samples survived, and return their hash.

    Raises rather than returning a flag: every caller's correct response to a
    failed transcode is to leave the original exactly where it is, and an
    exception is harder to forget than a return value.
    """
    before = pcm_sha256(source)
    try:
        run_ffmpeg(
            ["-y", "-i", str(source),
             "-compression_level", str(COMPRESSION_LEVEL), str(target)],
            f"could not encode {source.name}",
        )
    except TranscodeError:
        target.unlink(missing_ok=True)
        raise

    after = pcm_sha256(target)
    if after != before:
        target.unlink(missing_ok=True)
        raise TranscodeError(
            f"{source.name} did not survive encoding — samples differ. "
            "The original has been left alone."
        )
    return after


def to_wav(source: Path, target: Path) -> Path:
    """Render back to WAV, for a client that only speaks it.

    The phone parses RIFF headers directly to draw waveforms, to normalise
    playback and to crop before upload, so restoring a capture to a handset
    means handing it something it can read. Cheap and rare: restore is a
    deliberate act, not a background one.
    """
    try:
        run_ffmpeg(
            ["-y", "-i", str(source), "-acodec", "pcm_s16le", str(target)],
            f"could not render {source.name} as WAV",
        )
    except TranscodeError:
        target.unlink(missing_ok=True)
        raise
    return target


def archive(source: Path, backups: Path) -> Path:
    """Put the original somewhere safe rather than deleting it.

    Belt and braces on top of the verification: the check above is strong, but
    it is a check written by the same hand as the thing it checks, and a field
    recording cannot be collected again. These can be deleted by hand, later,
    by somebody who has satisfied themselves — which is a different and better
    decision from one this code makes at three in the morning.

    That somebody decided (Ben, 2026-07-30): keep them. The archive was
    running at roughly the size of the media it backs — the whole FLAC saving
    — and the answer was that the saving is not worth being one bad encoder
    release away from having no original. Disk is cheap; a recording is not.
    Revisit if the archive's size ever becomes a real constraint.
    """
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / source.name
    if not target.exists():
        shutil.move(str(source), str(target))
    else:
        source.unlink(missing_ok=True)
    return target
