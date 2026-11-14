"""The photo classifier's logic, without its models.

BioCLIP and the bird detector are downloads measured in hundreds of megabytes,
so nothing here builds one: the detector and embedder are stand-ins, and what
is tested is everything between them — the atlas, the crop, how the two terms
combine, and what happens with no coordinates or no bird.

    make photo-test
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from analyzer.photo.atlas import FLOOR, Atlas, Occurrences, slugify  # noqa: E402
from analyzer.photo.identify import (  # noqa: E402
    ModelMissing,
    PhotoIdentifier,
    SpeciesHead,
    exif_coordinates,
)
from analyzer.photo.vision import (  # noqa: E402
    MAX_SIDE, BirdBox, Look, PhotoFeatures, PhotoTooLarge, open_photo, square_crop,
)

SALT_LAKE = (40.76, -111.89)
MIAMI = (25.76, -80.19)
NAMES = {
    "american-crow": {"common": "American Crow", "scientific": "Corvus brachyrhynchos"},
    "fish-crow": {"common": "Fish Crow", "scientific": "Corvus ossifragus"},
}


def atlas():
    return Atlas(
        {
            "american-crow": Occurrences.from_degrees([SALT_LAKE] * 3 + [MIAMI]),
            "fish-crow": Occurrences.from_degrees([MIAMI] * 4),
        },
        NAMES,
    )


class StubDetector:
    def __init__(self, box, instead=None):
        self.found = Look(box, instead)

    def look(self, image):
        return self.found


class StubEmbedder:
    """Embeds an image as its mean colour, so a test picks the answer by
    painting the photo."""

    def embed(self, images):
        return np.array([np.asarray(i.resize((1, 1))).reshape(3) / 255.0 for i in images])


def identifier(box=None):
    reds, blues = np.tile([1.0, 0, 0, 1.0, 0, 0], (5, 1)), np.tile([0, 0, 1.0, 0, 0, 1.0], (5, 1))
    classifier = LogisticRegression().fit(np.vstack([reds, blues]), [0] * 5 + [1] * 5)
    head = SpeciesHead(classifier, ["american-crow", "fish-crow"])
    return PhotoIdentifier(PhotoFeatures(StubDetector(box), StubEmbedder()), head, atlas())


def photo(tmp_path, colour):
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 48), colour).save(path)
    return path


def test_subspecies_groups_fold_into_the_species():
    assert slugify("Carrion Crow (Eastern)") == "carrion-crow"


def test_share_counts_records_within_the_radius():
    crow = atlas().species["american-crow"]
    assert crow.share_within(*SALT_LAKE) == pytest.approx(0.75)
    assert crow.share_within(*MIAMI) == pytest.approx(0.25)


def test_a_recordist_cannot_vouch_for_their_own_photo():
    crow = Occurrences.from_degrees([SALT_LAKE, SALT_LAKE, MIAMI], np.array(["ann", "bob", "bob"]))
    assert crow.share_within(*SALT_LAKE, excluding_recordist="ann") == pytest.approx(0.5)


def test_a_species_never_recorded_nearby_is_unlikely_not_impossible():
    likelihoods = atlas().log_likelihoods(["american-crow", "fish-crow"], *SALT_LAKE)
    assert likelihoods[1] == pytest.approx(np.log(FLOOR))
    assert likelihoods[0] > likelihoods[1]


def test_the_atlas_survives_a_save_without_its_recordists(tmp_path):
    original = Atlas.from_exports(write_export(tmp_path))
    original.save(tmp_path / "atlas.npz")
    loaded = Atlas.load(tmp_path / "atlas.npz")
    assert loaded.names == original.names
    assert loaded.species["carrion-crow"].recordists is None
    assert loaded.shares(["carrion-crow"], 51.5, 0.7) == pytest.approx(original.shares(["carrion-crow"], 51.5, 0.7))


def write_export(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    header = "ML Catalog Number,Format,Common Name,Scientific Name,Recordist,Latitude,Longitude,Parent Species\n"
    rows = (
        "1,Photo,Carrion Crow,Corvus corone,Ann,51.52,0.78,Corvus corone\n"
        "2,Audio,Carrion Crow (Eastern),Corvus corone orientalis,Bob,43.1,131.9,Corvus corone\n"
        "3,Photo,Carrion Crow,Corvus corone,Cy,,,Corvus corone\n"
    )
    (exports / "ML_carcro1.csv").write_text("﻿" + header + rows, encoding="utf-8")
    return exports


def test_an_export_gives_one_species_and_skips_unlocated_rows(tmp_path):
    built = Atlas.from_exports(write_export(tmp_path))
    assert list(built.species) == ["carrion-crow"]
    assert len(built.species["carrion-crow"].positions) == 2
    assert built.names["carrion-crow"] == {"common": "Carrion Crow", "scientific": "Corvus corone"}


def test_crop_is_a_square_with_a_margin_around_the_bird():
    image = Image.new("RGB", (1200, 800))
    crop = square_crop(image, BirdBox(500, 300, 600, 500, 0.9, 1))
    assert crop.size == (240, 240)


def test_crop_stays_inside_the_frame_for_a_bird_at_the_edge():
    image = Image.new("RGB", (1200, 800))
    assert square_crop(image, BirdBox(0, 0, 100, 200, 0.9, 1)).size == (240, 240)
    assert square_crop(image, BirdBox(100, 0, 300, 790, 0.9, 1)).size == (800, 800)


def test_no_bird_means_the_whole_frame():
    image = Image.new("RGB", (1200, 800))
    assert square_crop(image, None) is image


def test_pixels_alone_decide_without_coordinates(tmp_path):
    result = identifier().identify(photo(tmp_path, "red"))
    assert result.best.slug == "american-crow"
    assert result.best.common_name == "American Crow"
    assert not result.used_location
    assert result.bird_box is None
    assert sum(score.probability for score in result.ranking) == pytest.approx(1.0)


def test_location_overrules_ambiguous_pixels(tmp_path):
    grey = photo(tmp_path, (128, 0, 128))
    assert identifier().identify(grey, *SALT_LAKE).best.slug == "american-crow"
    assert identifier().identify(grey, *MIAMI).best.slug == "fish-crow"


def test_a_place_with_no_records_is_ignored(tmp_path):
    result = identifier().identify(photo(tmp_path, "blue"), -33.87, 151.21)
    assert not result.used_location
    assert result.best.slug == "fish-crow"


def test_the_bird_box_and_its_frame_are_reported(tmp_path):
    box = BirdBox(10, 10, 30, 30, 0.9, 1)
    result = identifier(box).identify(photo(tmp_path, "red"), *SALT_LAKE)
    assert result.bird_box == box
    assert (result.width, result.height) == (64, 48)
    assert result.to_dict()["bird_box"]["left"] == 10
    assert (result.latitude, result.longitude) == SALT_LAKE


def test_a_judged_bird_is_a_corvid_verdict(tmp_path):
    result = identifier(BirdBox(10, 10, 50, 50, 0.9, 1)).identify(photo(tmp_path, (255, 0, 0)))
    assert (result.verdict, result.instead) == ("corvid", None)
    assert result.to_dict()["verdict"] == "corvid"


def test_no_bird_is_said_so_and_still_ranked(tmp_path):
    result = identifier().identify(photo(tmp_path, (255, 0, 0)))
    assert result.verdict == "no_bird"
    assert result.ranking


def test_a_photo_of_something_else_names_it(tmp_path):
    features = PhotoFeatures(StubDetector(None, "cat"), StubEmbedder())
    result = PhotoIdentifier(features, identifier().head, atlas()).identify(photo(tmp_path, (255, 0, 0)))
    assert (result.verdict, result.instead) == ("other", "cat")
    assert result.to_dict()["instead"] == "cat"


def test_coordinates_come_from_exif_when_not_given(tmp_path):
    path = tmp_path / "geotagged.jpg"
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (25.0, 45.0, 36.0), 3: "W", 4: (80.0, 11.0, 24.0)}
    Image.new("RGB", (64, 48), (128, 0, 128)).save(path, exif=exif)
    assert exif_coordinates(path) == pytest.approx((25.76, -80.19))
    result = identifier().identify(path)
    assert result.used_location
    assert result.best.slug == "fish-crow"


def geotagged_in_miami(tmp_path):
    path = tmp_path / "geotagged.jpg"
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (25.0, 45.0, 36.0), 3: "W", 4: (80.0, 11.0, 24.0)}
    Image.new("RGB", (64, 48), (128, 0, 128)).save(path, exif=exif)
    return path


def test_given_coordinates_overrule_the_photos_own_by_default(tmp_path):
    result = identifier().identify(geotagged_in_miami(tmp_path), *SALT_LAKE)
    assert result.location_source == "given"
    assert result.best.slug == "american-crow"


def test_a_guessed_location_gives_way_to_the_photos_gps_tags(tmp_path):
    result = identifier().identify(geotagged_in_miami(tmp_path), *SALT_LAKE, prefer_exif=True)
    assert result.location_source == "exif"
    assert (result.latitude, result.longitude) == pytest.approx((25.76, -80.19))
    assert result.best.slug == "fish-crow"


def test_a_guessed_location_is_used_when_the_photo_has_none(tmp_path):
    result = identifier().identify(photo(tmp_path, (128, 0, 128)), *SALT_LAKE, prefer_exif=True)
    assert result.location_source == "given"
    assert result.best.slug == "american-crow"


def test_no_coordinates_anywhere_has_no_source(tmp_path):
    result = identifier().identify(photo(tmp_path, "red"))
    assert result.location_source is None
    assert result.latitude is None


def test_a_photo_without_gps_has_no_coordinates(tmp_path):
    assert exif_coordinates(photo(tmp_path, "red")) is None


def test_loading_without_a_trained_model_says_how_to_build_one(tmp_path):
    with pytest.raises(ModelMissing, match="make photo-train"):
        PhotoIdentifier.load(tmp_path)


def test_a_file_that_is_not_a_photo_format_is_refused_whatever_it_is_called(tmp_path):
    path = tmp_path / "crow.jpg"
    Image.new("RGB", (8, 8)).save(path, "BMP")
    with pytest.raises(Exception, match="cannot identify image file"):
        open_photo(path)


def test_a_frame_larger_than_any_camera_is_refused_before_it_is_decoded(tmp_path):
    path = tmp_path / "bomb.png"
    Image.new("1", (9000, 9000)).save(path)
    assert path.stat().st_size < 100_000
    with pytest.raises(PhotoTooLarge):
        open_photo(path)


def test_a_large_photo_is_handed_on_no_longer_than_the_models_need(tmp_path):
    path = tmp_path / "big.jpg"
    Image.new("RGB", (6000, 3000)).save(path)
    assert open_photo(path).size == (MAX_SIDE, MAX_SIDE // 2)
