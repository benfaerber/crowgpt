"""The regions CawScout covers.

Adding a county is adding a Region here — plus the canopy prerequisite: a
tall-trees GeoJSON covering its box (see experiments/0083, which documents
the Meta/WRI tile source). Davis needs the tile north of the current one;
Utah county needs the tiles south and east, and east of the current tile's
edge the Wasatch no longer clips itself for free — mountain forest must be
masked before the trees signal is trustworthy there.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Region:
    slug: str
    name: str
    west: float
    south: float
    east: float
    north: float
    #: repo-root-relative path to a tall-trees GeoJSON (points with `h`)
    trees_geojson: str
    #: (name, lat, lon) — named areas Ben actually drives to that get their
    #: best cell appended if the open ranking leaves them empty
    districts: tuple = field(default_factory=tuple)
    n_targets: int = 20
    #: OSM route classes drawn as reference geometry (regex for Overpass)
    rail_routes: str = "light_rail|tram"
    #: minimum spacing between targets. 700 m suits the home valley's dense
    #: signals; an exploratory county needs more or every pin lands on the
    #: county's one hotspot (Utah Valley's first run put all ten on BYU).
    separation_m: int = 700

    @property
    def bbox(self):
        return self.west, self.south, self.east, self.north

    def contains(self, lat, lon):
        return self.south <= lat <= self.north and self.west <= lon <= self.east


SLC_VALLEY = Region(
    slug="slc-valley",
    name="Salt Lake Valley",
    west=-112.05, south=40.50, east=-111.797, north=40.90,
    trees_geojson="experiments/0083-where-are-the-tall-trees/tall_trees.geojson",
    districts=(
        ("Sugar House", 40.7223, -111.8656),
        ("Millcreek", 40.6869, -111.8636),
        ("East Millcreek", 40.7006, -111.8286),
        ("Holladay", 40.6689, -111.8247),
        ("Cottonwood Heights", 40.6197, -111.8104),
    ),
)

# Both counties: canopy built by experiments/0083's build_region.py, which
# masks stands above 1,650 m — the Wasatch sits inside these boxes, and
# without the mask mountain forest owns the p99 the trees signal
# normalises against. Ten targets each: exploratory ground, not the home
# valley. FrontRunner is the rail reference — neither county has TRAX.
DAVIS = Region(
    slug="davis",
    name="Davis County",
    west=-112.12, south=40.90, east=-111.80, north=41.155,
    trees_geojson="experiments/0083-where-are-the-tall-trees/tall_trees_davis.geojson",
    n_targets=10,
    rail_routes="train",
    separation_m=1500,
)

UTAH_VALLEY = Region(
    slug="utah-valley",
    name="Utah Valley",
    west=-112.06, south=40.06, east=-111.58, north=40.50,
    trees_geojson="experiments/0083-where-are-the-tall-trees/tall_trees_utah_valley.geojson",
    n_targets=10,
    rail_routes="train",
    separation_m=1500,
)

REGIONS = [SLC_VALLEY, DAVIS, UTAH_VALLEY]


def by_slug(slug):
    for region in REGIONS:
        if region.slug == slug:
            return region
    raise KeyError(f"no region '{slug}' — known: {[r.slug for r in REGIONS]}")
