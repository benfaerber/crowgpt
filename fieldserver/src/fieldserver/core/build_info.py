"""What code this server is running, resolved from git.

Same scheme as the phone's Settings screen: the first commit is v1, the
hundredth is v100. A number that counts is worth more than a hash alone when the
question is "is this newer than what's on the phone" — you can compare two
integers at a glance and you cannot compare two hashes at all.

Resolved once at import. The process cannot change commit while it runs, and
shelling out to git on every /api/health would be a subprocess per poll.
"""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# What this server can store, as opposed to what commit it happens to be on.
#
# Bumped only when the request or response contract changes — a new field a
# client might send, a new route, a new rule about an existing one. Most commits
# do not touch it, and that is the point: comparing commit counts flagged a
# server three tooling commits behind as incompatible, and a warning that fires
# on unrelated work is one people learn to click past.
#
#   1  baseline: captures, media, labels, context, families, observations
#   2  media.pre_roll_sec
#   3  captures.app_version/app_commit, X-App-Version header on every request
#   4  captures.observer_role, observer_roles in the served config
#   5  /api/captures/<id>/sightings
#   6  captures.silent_confirmed_at, and capture-level context on a silent one
#   7  captures.behavior_guess
#   8  captures.crop_start_sec/crop_end_sec — which span of the recording the
#      uploaded audio actually is
#   9  detected_calls.candidate — sub-threshold detections offered for labelling
#  10  captures.distance_band — roughly how far away the bird was
#  11  captures.adult_count/juvenile_count/unaged_count — who was there
#  12  POST /api/logs — the phone's own diagnostic log, pushed on demand
#  13  captures.region, contributors.location_precision and
#      /api/me/location-precision — how precisely a recordist says where
#  14  audio stored as FLAC, and /api/media/<id>/raw?format=wav to render one
#      back for the phone, which parses RIFF directly
#  15  labels.config_version and context_events.config_version — which
#      vocabulary a decision was made from, sent by the client because it
#      labels offline against a cached one
#  16  POST/GET /api/captures/<id>/merge — which captures were folded into
#      this one, and where each landed on its timeline. The joined audio
#      arrives as an ordinary capture; this is the record that stops the
#      parts and the whole being counted as different birds
#  17  contributors.censor_coords — whether recorded coordinates may be shown,
#      split out of location_precision's old `exact_private` middle value
#  18  label_revisions — re-answering a label keeps what it used to say, and its
#      config_version moves with the new answer. Not required of a client, and
#      deliberately so: the phone sends nothing new and loses nothing against a
#      v17 server, which overwrites the old answer exactly as every server did
#      until now. What it costs is history nobody had yet, not fieldwork.
#  19  crows — a roster of individual birds per family, and labels.crow_id
#      naming which one was watched making a call. REQUIRED of a client, unlike
#      18: a phone that sends crow_id to a v18 server has it silently dropped,
#      and the attribution cannot be recovered afterwards. Experiment 0017
#      showed the audio does not carry the caller — five crows produce the
#      cluster structure one crow produces — so a lost attribution is lost for
#      good, not merely delayed. That asymmetry is what makes this one a floor
#      rather than a nicety.
#  20  captures.nothing_to_label_at — "this recording is not worth labelling",
#      which is what lets the label queue empty. NOT required of a client: a
#      phone sending it to a v19 server has the flag dropped, and the cost is
#      that one recording keeps appearing in a queue on that phone. Nothing is
#      observed of a bird in it and nothing is unrecoverable, which is exactly
#      the asymmetry 19 had and this does not.
#  21  dictations — a spoken field note attached to a capture, its transcript,
#      and the queue that makes one. NOT required of a client, and for a reason
#      worth stating: a v20 server has no /dictations route at all, so the push
#      404s, the phone keeps the note and says so in the log. That is a refusal,
#      not the accept-and-drop this number exists to catch — nothing is lost, and
#      the note goes up whenever the server catches up.
#  22  location_precision gains `fuzzed` — coordinates snapped to an N-mile grid
#      on the phone — with contributors.fuzz_miles carrying the radius and
#      captures.coord_fuzz_miles saying how coarse each row's coordinates are.
#      REQUIRED of a client, the same asymmetry as 19: a v21 server accepts the
#      snapped coordinates but drops the radius beside them, storing fixes a few
#      miles wide that are forever indistinguishable from exact ones.
#  23  captures.trigger — "auto" when the phone's idle-mode trigger started the
#      recording rather than a person. REQUIRED of a client, same asymmetry as
#      19 and 22: a v22 server accepts the capture and drops the flag, and an
#      unattended recording then masquerades forever as a deliberate one — in a
#      corpus whose discipline is knowing what is real, that mislabelling is
#      unrecoverable.
WIRE_VERSION = 23


def _git(args: str, fallback: str = "") -> str:
    try:
        return subprocess.run(
            ["git", *args.split()], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # A deployment without git, or without the repo. A version that admits
        # it doesn't know beats one that invents a number.
        return fallback


def resolve() -> dict:
    return {
        "version": int(_git("rev-list --count HEAD", "0") or 0),
        "commit": _git("rev-parse --short HEAD", "unknown") or "unknown",
        "committed_at": _git("log -1 --format=%cI") or None,
        # Loud on purpose: a server running uncommitted edits cannot be
        # reproduced from its hash, so a bug reported against it is a bug
        # reported against nothing.
        "dirty": bool(_git("status --porcelain")),
        "branch": _git("rev-parse --abbrev-ref HEAD") or None,
        # Deliberately not derived from git: this is a promise about behaviour,
        # and a promise that moves on its own is not one.
        "wire": WIRE_VERSION,
    }


BUILD = resolve()
