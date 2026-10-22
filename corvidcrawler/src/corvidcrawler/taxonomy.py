"""One name for one bird, whatever the archive called it.

Xeno-canto sends English names ("Northern Raven"), Macaulay sends eBird codes
("comrav") and its own English ("Common Raven"), and the corpus directories
are slugs ("common-raven"). Those are all the same bird, and a corpus that
files them apart lets one individual sit in a training slug and a test slug
at once — the failure the whole grouping exercise exists to prevent.

RESOLUTION NEVER GUESSES A CORVID. An unknown name slugifies to itself and
`is_known` stays False so a caller can report it. A wrong slug merges two
birds silently; a missing one shows up as a species nobody has adjudicated.
"""

import re
import unicodedata

#: slug -> (English name as Xeno-canto spells it, binomial, eBird code).
SPECIES = {
    "american-crow": ("American Crow", "Corvus brachyrhynchos", "amecro"),
    "carrion-crow": ("Carrion Crow", "Corvus corone", "carcro1"),
    "hooded-crow": ("Hooded Crow", "Corvus cornix", "hoocro1"),
    "common-raven": ("Northern Raven", "Corvus corax", "comrav"),
    "rook": ("Rook", "Corvus frugilegus", "rook1"),
    "eurasian-jackdaw": ("Western Jackdaw", "Coloeus monedula", "eurjac"),
    "daurian-jackdaw": ("Daurian Jackdaw", "Coloeus dauuricus", "daujac"),
    "fish-crow": ("Fish Crow", "Corvus ossifragus", "fiscro"),
    "large-billed-crow": ("Large-billed Crow", "Corvus macrorhynchos", "labcro"),
    "house-crow": ("House Crow", "Corvus splendens", "houcro1"),
    "pied-crow": ("Pied Crow", "Corvus albus", "piecro1"),
    "cape-crow": ("Cape Crow", "Corvus capensis", "capcro1"),
    "brown-necked-raven": ("Brown-necked Raven", "Corvus ruficollis", "brnrav1"),
    "fan-tailed-raven": ("Fan-tailed Raven", "Corvus rhipidurus", "fatrav1"),
    "white-necked-raven": ("White-necked Raven", "Corvus albicollis", "whnrav1"),
    "cuban-crow": ("Cuban Crow", "Corvus nasicus", "cubcro1"),
    "torresian-crow": ("Torresian Crow", "Corvus orru", "torcro1"),
    "australian-raven": ("Australian Raven", "Corvus coronoides", "ausrav1"),
    "little-crow": ("Little Crow", "Corvus bennetti", "litcro1"),
    "little-raven": ("Little Raven", "Corvus mellori", "litrav1"),
    "forest-raven": ("Forest Raven", "Corvus tasmanicus", "forrav1"),
    "eurasian-jay": ("Eurasian Jay", "Garrulus glandarius", "eurjay1"),
    "black-headed-jay": ("Black-headed Jay", "Garrulus lanceolatus", "blhjay1"),
    "eurasian-magpie": ("Eurasian Magpie", "Pica pica", "eurmag1"),
    "spotted-nutcracker": ("Spotted Nutcracker", "Nucifraga caryocatactes", "sponut1"),
    "red-billed-chough": ("Red-billed Chough", "Pyrrhocorax pyrrhocorax", "rebcho1"),
    "alpine-chough": ("Alpine Chough", "Pyrrhocorax graculus", "yebcho1"),
    "azure-winged-magpie": ("Azure-winged Magpie", "Cyanopica cyanus", "azwmag1"),
    "iberian-magpie": ("Iberian Magpie", "Cyanopica cooki", "ibemag1"),
    "blue-jay": ("Blue Jay", "Cyanocitta cristata", "blujay"),
    "stellers-jay": ("Steller's Jay", "Cyanocitta stelleri", "stejay"),
    "siberian-jay": ("Siberian Jay", "Perisoreus infaustus", "sibjay1"),
    "hendersons-ground-jay": ("Henderson's Ground Jay", "Podoces hendersoni", "mongro1"),
    "transvolcanic-jay": ("Transvolcanic Jay", "Aphelocoma ultramarina", "trajay1"),
}

#: Names an archive uses that are not the one in SPECIES.
ALIASES = {
    "common raven": "common-raven",
    "eurasian jackdaw": "eurasian-jackdaw",
    "jackdaw": "eurasian-jackdaw",
    "corvus monedula": "eurasian-jackdaw",
    "eurasian nutcracker": "spotted-nutcracker",
    "jungle crow": "large-billed-crow",
    "indian jungle crow": "large-billed-crow",
    "corvus levaillantii": "large-billed-crow",
    "yellow-billed chough": "alpine-chough",
}

#: Values that name no bird. They must not become a slug.
NOT_A_SPECIES = {"", "spec.", "sp.", "unknown", "corvus spec.", "corvus sp."}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return _SLUG_STRIP.sub("-", text).strip("-")


def ebird_code(slug) -> str | None:
    names = SPECIES.get(slug)
    return names[2] if names else None


def _index() -> dict:
    lookup = {}
    for slug, names in SPECIES.items():
        lookup[slug] = slug
        for name in names:
            lookup[name.strip().lower()] = slug
            lookup[slugify(name)] = slug
    for name, slug in ALIASES.items():
        lookup[name.strip().lower()] = slug
        lookup[slugify(name)] = slug
    return lookup


_LOOKUP = _index()


class Resolution:
    __slots__ = ("slug", "is_known", "given")

    def __init__(self, slug, is_known, given):
        self.slug, self.is_known, self.given = slug, is_known, given

    def __repr__(self):
        return f"<{self.slug}{'' if self.is_known else ' (unknown)'}>"


def resolve(name) -> Resolution:
    given = str(name or "").strip()
    if given.lower() in NOT_A_SPECIES:
        return Resolution(None, False, given)
    hit = _LOOKUP.get(given.lower()) or _LOOKUP.get(slugify(given))
    if hit:
        return Resolution(hit, True, given)
    return Resolution(slugify(given) or None, False, given)


def slug_for(name) -> str | None:
    return resolve(name).slug
