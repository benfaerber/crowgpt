"""Everything a route section is allowed to reach for.

A dataclass rather than module globals or `current_app.extensions`: the routes
used to close over names in one factory, and this keeps that property — what a
section can touch is written down in one place and passed in, so a new route
cannot quietly acquire a dependency nobody agreed to.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Deps:
    config: Any
    contributors: Any
    devices: Any
    families: Any
    crows: Any
    captures: Any
    media: Any
    analysis: Any
    #: Measured audio quality, one row per capture.
    quality: Any
    labels: Any
    observations: Any
    #: Spoken field notes and their machine transcripts. NOT bird audio and never
    #: a media row — see stores/dictations.py for why the separation is structural.
    dictations: Any
    context: Any
    sightings: Any
    #: Machine-written prose about a recording or one span of it. Read-only to
    #: every route: it is written by tooling, never by the phone.
    ai_descriptions: Any
    #: Which captures were folded into which, so nothing counts them twice.
    merges: Any
    logs: Any
    #: Listening pools graded a dose at a time. Withholds its own results until
    #: the pre-committed trial count is answered — see stores/listening.py.
    listening: Any
    #: Crow Chat exchanges: a request for a call type and the generated clip
    #: that answers it. Worked off by the generation worker, never this process.
    generations: Any
    #: Read-only joins across all of the above, for the dashboard.
    board: Any
    #: The instance directory, for published reference artifacts the app
    #: reads (the tall-trees layer today). Not a store: nothing here has a
    #: table, and the file's absence is a served 404, not an error.
    instance_dir: Path
    #: Where somebody actually scouted, and what they found — the labels
    #: that grade the 0084 prior. See stores/scout_visits.py.
    scout_visits: Any

    #: The calling device and the person it belongs to, or 401.
    current_actor: Callable[[], tuple]
    #: A capture this contributor may touch, or 403/404.
    owned_capture: Callable[..., dict]
    #: The three head counts, refusing anything that is not one.
    counts: Callable[[dict], dict]
