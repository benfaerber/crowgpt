"""The registry: what this crawler can talk to, and what each source means by
`query`. The runner hands each source an opaque string, so the meaning has to
be written down somewhere, and this is somewhere."""

import os

from .errors import SourceError
from .macaulay import MacaulaySource
from .xeno_canto import XenoCantoSource

SOURCES = [
    {
        "id": XenoCantoSource.id,
        "name": "Xeno-canto",
        "needs_key": True,
        "key_env": "XENOCANTO_KEY",
        "query_is": "a v3 search expression, e.g. 'gen:Corvus sp:corone q:A'",
        "counts_up_front": True,
        "gives_duration": True,
        "docs": "https://xeno-canto.org/explore/api",
        "description": "Community bird-sound archive, filterable by call type, and "
                       "the one source that reports a recording length. Needs a free key.",
    },
    {
        "id": MacaulaySource.id,
        "name": "Macaulay Library",
        "needs_key": False,
        "key_env": None,
        "query_is": "a species slug ('rook'), an eBird taxon code ('rook1'), "
                    "or a path to a CSV export",
        # The search API reports no total, so a bar on a Macaulay crawl counts
        # toward --max, never toward the species.
        "counts_up_front": False,
        "gives_duration": False,
        "docs": "https://search.macaulaylibrary.org/catalog?mediaType=audio",
        "description": "Cornell's archive, through the JSON search API the web UI "
                       "calls, with pages cached on disk so a re-run costs nothing. "
                       "Its tags are a controlled vocabulary.",
    },
]

SOURCE_CLASSES = {
    XenoCantoSource.id: XenoCantoSource,
    MacaulaySource.id: MacaulaySource,
}

#: Presets for the query builder — the corvids worth pulling for CrowGPT.
CORVID_SPECIES = [
    {"label": "American Crow", "gen": "Corvus", "sp": "brachyrhynchos"},
    {"label": "Northwestern Crow", "gen": "Corvus", "sp": "caurinus"},
    {"label": "Carrion Crow", "gen": "Corvus", "sp": "corone"},
    {"label": "Hooded Crow", "gen": "Corvus", "sp": "cornix"},
    {"label": "Common Raven", "gen": "Corvus", "sp": "corax"},
    {"label": "Rook", "gen": "Corvus", "sp": "frugilegus"},
    # Jackdaws were split out of Corvus into Coloeus; Xeno-canto follows that.
    {"label": "Eurasian Jackdaw", "gen": "Coloeus", "sp": "monedula"},
    {"label": "Daurian Jackdaw", "gen": "Coloeus", "sp": "dauuricus"},
    {"label": "Fish Crow", "gen": "Corvus", "sp": "ossifragus"},
]


def source_status(source_id=None) -> list[dict]:
    """The registry, annotated with whether each source can run right now —
    which depends on an environment variable static metadata cannot see."""
    rows = [dict(s) for s in SOURCES if source_id in (None, s["id"])]
    for row in rows:
        env = row.get("key_env")
        has_key = bool(os.environ.get(env, "").strip()) if env else True
        row["key_configured"] = has_key
        row["ready"] = has_key
        row["blocked_by"] = None if has_key else f"{env} is not set"
    return rows


def get_source(source_id: str):
    try:
        return SOURCE_CLASSES[source_id]()
    except KeyError:
        raise SourceError(f"Source '{source_id}' is not available.") from None


def build_query_for(source_id: str, params: dict) -> str:
    """The `crawl` subcommand's gen/sp flags, as the source's own query.

    Xeno-canto takes a search expression; Macaulay takes a species slug, so the
    preset whose genus and epithet match is looked up and its slug returned.
    """
    if source_id == MacaulaySource.id:
        wanted = (params.get("gen") or "").lower(), (params.get("sp") or "").lower()
        match = next((s for s in CORVID_SPECIES
                      if (s["gen"].lower(), s["sp"].lower()) == wanted), None)
        if match is None:
            raise SourceError("Macaulay needs --query (a species slug, eBird code or CSV path) "
                              "or a --gen/--sp pair from the presets.")
        return match["label"].lower().replace(" ", "-")
    from .xeno_canto import build_query
    return build_query(params)
