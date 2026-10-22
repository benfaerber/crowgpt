# 0083 — where are the tall trees?

**2026-08-20** · build: one CHM tile + ~2 m of numpy · **answer: a map**

## The question

Ben wants to find new crows, and crows nest and roost high. So: every stand
of canopy ≥ 18 m in the Salt Lake valley, as a map a phone can open in the
field.

## Build

Meta/WRI 1 m global canopy height model, tile 023100000 (the tile edge at
-111.797 conveniently clips the Wasatch forests that would drown the map).
Heights max-pooled to ~10 m cells, stands labelled by connected components,
top 2,500 ranked by height × log(area). `run.py` needs a venv with
rasterio/scipy and a downloaded `chm.tif` (226 MB, not committed):

    curl -o chm.tif https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm/023100000.tif
    python run.py chm.tif

Outputs `tall_trees.geojson` and `tall-trees-map.html` (Leaflet + OSM tiles;
needs internet to draw the basemap, which a phone in the field has). Each dot
links straight to Google Maps navigation.

## Revised 2026-08-20 — every stand, no ranking

Ben's field check caught the cut: South Temple's giant street trees were in
the data (879 cells ≥ 18 m along the corridor, peaking 26 m) and the
top-2,500 height×log(area) rank dropped them — the formula loved contiguous
groves and starved street rows, which stand as small separated blobs at 10 m
pooling. All 19,601 stands publish now; the app's canvas rendering and
zoom-gated icons carry the density. A second honest limit remains: a
continuous street row merges into ONE stand with one centroid, so a block of
elms is a single marker, not a marker per tree.

## Revised 2026-08-20 (later) — the floor drops, then OSM trunks fill the streets

Ben kept grading against streets he knows and the corridor kept losing. Two
causes, measured on the South Temple corridor:

1. **The 18 m floor was too high for street trees.** The CHM systematically
   compresses street giants (the Cathedral of the Madeleine block maxes at
   19 m in the model; the corridor has 3,636 cells ≥ 15 m but only 879 ≥ 18 m).
   `MIN_HEIGHT` dropped to 15 → 45,046 stands, 40 on the corridor.
2. **One blob per row is still one marker per row**, and rows the model reads
   short vanish entirely. The city's per-tree Urban Forestry inventory would
   fix this, but it lives in TreeKeeper with no fetchable open endpoint (four
   ArcGIS/DCAT probes, all empty). OpenStreetMap has it instead: 47,848
   individually-mapped trees in the valley, 810 on the corridor alone.

`merge_osm_trees.py` marries the two sources: OSM supplies verified trunk
positions, the CHM supplies each one's height (max within ~6 m of the trunk —
a 3×3 window missed crown peaks on the ~1.2 m raster and found only 26
corridor trees; ±5 px finds 54). Trunks reading ≥ 12 m join the layer (a
verified trunk earns a lower floor than an anonymous blob), deduped within
15 m of existing stands. Result: **47,854 features (2,808 OSM trunks); the
corridor went 40 → 94 markers**. Ben's verdict from the field: looking good.

## What the map says

19,601 stands ≥ 18 m in the scouting box; the kept 2,500 break down 18–20 m:
~1,100 · 21–24 m: ~1,000 · 25–29 m: ~340 · 30 m+: ~100. The 30 m+ giants
cluster at the canyon mouths and the northeast bench (conifers at the tile
edge); the urban scouting meat is the 20–29 m band — cemetery rows, the old
parks, and the mature-neighborhood cottonwoods.

## What it changed

Field scouting has a target list instead of a drive-around: sort by the
purple and red dots nearest home, listen at dawn. If a new murder turns up,
the capture GPS lands next to a dot and the map has paid for itself.

## Revised 2026-08-22 — Davis and Utah county, and the mask the tile edge was

CawScout left the valley, and both accidents of the original build broke at
once: the new counties span 2-3 Meta/WRI tiles each, and around Provo the
Wasatch sits *inside* the box instead of past the tile edge. `build_region.py`
replaces run.py for anything beyond the valley: it takes a region slug from
`fieldserver.scout.regions` (one source of truth for every box), mosaics all
intersecting CHM tiles strip-wise (a county window is ~6 GB read whole),
and masks every stand and OSM trunk above **1,650 m** using Copernicus
GLO-30 elevation read straight off S3 — benches stay, mountainsides go.
The mask is not cosmetic: 12,396 of Davis's 28,654 stands and 23,195 of
Utah Valley's 50,315 were mountainside forest that would have owned the
p99 the scout score normalises against. Canyon-mouth riparian below the
line survives on purpose — cottonwoods at 1,540 m are crow habitat.

Tiles now live in `DATA_DIR/experiments/0083-chm/` (five: 021322222,
023100000-023100003; ~1.9 GB, same curl pattern as above) so future
regions don't re-download. Outputs: `tall_trees_davis.geojson` (16,520
features) and `tall_trees_utah_valley.geojson` (27,693). The original
`tall_trees.geojson` is untouched — re-running the valley through the
mask would reshuffle CawScout's validated targets, a separate decision.
