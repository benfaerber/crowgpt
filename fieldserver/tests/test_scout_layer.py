"""The scout layer builder: scoring, target selection, assembly, validation.

Synthetic geography throughout — a small box with signal clusters placed on
purpose. No network: the builder takes stub clients.
"""

import json
import math

import pytest

from fieldserver.scout.builder import ScoutLayerBuilder, validate
from fieldserver.scout.regions import Region
from fieldserver.scout.scoring import HOME_EXCLUDE_M, M_PER_LAT, RegionScorer
from fieldserver.scout.sources import Observation

BOX = Region(slug="box", name="Test Box", west=-112.00, south=40.50,
             east=-111.94, north=40.55, trees_geojson="unused.geojson",
             n_targets=5)
RICH = (40.54, -111.95)
POOR = (40.51, -111.99)


def cluster(lat, lon, n=6, name=""):
    return [(lat + 0.0004 * i, lon + 0.0004 * i, name) for i in range(n)]


def points(lat, lon, n=6):
    return [(lat + 0.0004 * i, lon + 0.0004 * i) for i in range(n)]


def scorer(**overrides):
    signals = dict(inat=points(*RICH), trees=[], green=cluster(*RICH),
                   water=[], food=[], owls=[], hawks=[], effort=[])
    signals.update(overrides)
    return RegionScorer(BOX, **signals)


def meters_apart(a, b):
    return math.hypot((a["lat"] - b["lat"]) * M_PER_LAT,
                      (a["lon"] - b["lon"]) * M_PER_LAT)


class TestScoring:
    def test_signal_cluster_outranks_empty_ground(self):
        top = scorer().targets()[0]
        assert meters_apart(top, {"lat": RICH[0], "lon": RICH[1]}) < 1000

    def test_targets_keep_their_separation(self):
        targets = scorer().targets()
        assert len(targets) > 1
        for i, a in enumerate(targets):
            for b in targets[i + 1:]:
                assert meters_apart(a, b) >= BOX.separation_m - 250

    def test_owls_sink_a_cell(self):
        clean = scorer().targets()[0]
        hushed = scorer(owls=points(*RICH, n=12)).targets()[0]
        assert hushed["score"] < clean["score"]

    def test_birding_effort_softens_the_owl_penalty(self):
        watched = scorer(owls=points(*RICH),
                         effort=points(*RICH, n=20)).targets()[0]
        unwatched = scorer(owls=points(*RICH)).targets()[0]
        assert watched["score"] > unwatched["score"]

    def test_home_territory_is_excluded(self):
        away = scorer().targets()[0]
        homed = RegionScorer(BOX, inat=points(*RICH), trees=[],
                             green=cluster(*RICH), water=[], food=[],
                             owls=[], hawks=[], effort=[], home=RICH).targets()
        assert all(
            meters_apart(t, {"lat": RICH[0], "lon": RICH[1]}) > HOME_EXCLUDE_M - 250
            for t in homed)
        assert meters_apart(away, {"lat": RICH[0], "lon": RICH[1]}) < 1000

    def test_taller_stands_score_higher(self):
        short = scorer(green=[], inat=[], trees=[(*RICH, 18)]).targets()
        tall = scorer(green=[], inat=[], trees=[(*RICH, 30)]).targets()
        assert tall[0]["score"] >= short[0]["score"]

    def test_empty_district_gets_a_floor_pin(self):
        district = Region(
            slug=BOX.slug, name=BOX.name, west=BOX.west, south=BOX.south,
            east=BOX.east, north=BOX.north, trees_geojson=BOX.trees_geojson,
            n_targets=1, districts=(("Poorville", *POOR),))
        targets = RegionScorer(
            district, inat=points(*RICH), trees=[], green=cluster(*RICH),
            water=[], food=[], owls=[], hawks=[],
            effort=[], home=None).targets()
        floors = [t for t in targets if t.get("district") == "Poorville"]
        assert len(floors) == 1
        assert floors[0]["rank"] == len(targets)

    def test_near_names_the_closest_named_green(self):
        top = scorer(green=cluster(*RICH, name="Test Park")).targets()[0]
        assert top["near"] == "Test Park"


class FakeINat:
    def presence_points(self, taxon, region, max_pages=5):
        return points(*RICH)

    def recent(self, taxon, region, cap=150):
        return [Observation(RICH[0], RICH[1], "2026-08-01", "photo.jpg", "obs")]


class FakeEBird:
    def recent(self, species_code, region, back_days=30):
        return [{"lat": POOR[0], "lon": POOR[1],
                 "date": "2026-08-22 07:15", "count": 3}]


class FakeOverpass:
    def habitat(self, region):
        return cluster(*RICH, name="Test Park"), [], []

    def rail(self, region, fallback_color="#5c6bc0"):
        return [{"color": "#ff0000", "coords": [[40.51, -111.99], [40.52, -111.98]]}]


@pytest.fixture
def repo(tmp_path):
    trees = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [RICH[1], RICH[0]]},
         "properties": {"h": 22, "area_m2": 400}}]}
    (tmp_path / "unused.geojson").write_text(json.dumps(trees))
    return tmp_path


def build(repo, regions, previous=None, ebird=FakeEBird()):
    builder = ScoutLayerBuilder(repo_root=repo, db_path=None,
                                inat=FakeINat(), overpass=FakeOverpass(),
                                ebird=ebird, log=lambda *_: None)
    return builder.build(regions, previous=previous)


PREVIOUS_ICONS = {"icons": {name: f"data:image/png;base64,{name}" for name in (
    "owl-icon", "hawk-icon", "peregrine-icon", "coopers-hawk-icon",
    "raven-icon", "magpie-icon", "crow-icon")}}


class TestBuilder:
    def test_layer_carries_every_section(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        assert set(layer) == {"regions", "targets", "owls", "predators",
                              "icons", "rail"}
        validate(layer)

    def test_every_row_carries_its_region(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        assert layer["regions"] == [{"slug": "box", "name": "Test Box"}]
        for section in ("owls", "predators", "rail"):
            assert all(row["region"] == "box" for row in layer[section])

    def test_ranks_continue_across_regions(self, repo):
        east = Region(slug="east-box", name="East Box", west=-111.94,
                      south=40.50, east=-111.88, north=40.55,
                      trees_geojson="unused.geojson", n_targets=5)
        layer = build(repo, [BOX, east], previous=PREVIOUS_ICONS)
        ranks = [t["rank"] for t in layer["targets"]]
        assert ranks == list(range(1, len(ranks) + 1))
        assert {t["region"] for t in layer["targets"]} == {"box", "east-box"}

    def test_coopers_synonyms_collapse_to_one_pin(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        coopers = [p for p in layer["predators"]
                   if p["species"] == "Cooper's Hawk"
                   and p.get("src") != "ebird"]
        assert len(coopers) == 1

    def test_fresh_ebird_rows_ride_along_tagged(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        fresh = [p for p in layer["predators"] if p.get("src") == "ebird"]
        assert fresh and all(p["by"] == "eBird" for p in fresh)
        crows = [p for p in fresh if p["species"] == "American Crow"]
        assert crows and crows[0]["community"] and crows[0]["count"] == 3

    def test_no_ebird_client_still_builds(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS, ebird=None)
        assert not [p for p in layer["predators"] if p.get("src") == "ebird"]
        validate(layer)

    def test_community_crows_are_flagged(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        crows = [p for p in layer["predators"]
                 if p["species"] == "American Crow"]
        assert crows and all(p.get("community") for p in crows)

    def test_icons_carry_forward_from_previous_publish(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        assert layer["icons"]["owl-icon"] == "data:image/png;base64,owl-icon"

    def test_missing_trees_layer_is_a_loud_failure(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="tall-trees"):
            build(tmp_path, [BOX], previous=PREVIOUS_ICONS)


class TestValidate:
    def test_duplicate_ranks_are_rejected(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        layer["targets"][1]["rank"] = layer["targets"][0]["rank"]
        with pytest.raises(ValueError, match="unique"):
            validate(layer)

    def test_predator_without_its_icon_is_rejected(self, repo):
        layer = build(repo, [BOX], previous=PREVIOUS_ICONS)
        del layer["icons"]["owl-icon"]
        with pytest.raises(ValueError, match="owl-icon"):
            validate(layer)

    def test_empty_targets_are_rejected(self):
        with pytest.raises(ValueError, match="no targets"):
            validate({"targets": []})
