"""The CORE label space, and the two things that keep it honest.

`begging` used to be the place this broke: the served config mapped it down to
`call` while both training mappers dropped it, so the same vocalization meant
three different things depending on which side of the repo you asked. It is a
core class now — these tests are the reason it can't quietly stop being one.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from fieldserver.core import schema
from fieldserver.stores.config_store import CORE_CLASSES, CORE_COLORS, SEED_LABELS, ConfigStore

REPO = Path(__file__).resolve().parents[2]


def _load(module_path: Path):
    """Import a pipeline module by path — they are scripts, not a package."""
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheLabelSpaceAgrees:
    """The claim in config_store's docstring, enforced rather than asserted.

    Nothing about a Python import binds the field server to the pipelines, so
    the only thing stopping the two label spaces from drifting is a test that
    reads both. corpus.py is deliberately pure stdlib, which is what makes it
    importable from here without the BirdNET venv.
    """

    def test_every_corpus_flag_maps_to_a_core_class(self):
        corpus = _load(REPO / "pipelines" / "ingest" / "corpus.py")
        unknown = set(corpus.FLAG_TO_CORE.values()) - set(CORE_CLASSES)
        assert not unknown, f"corpus.py maps flags onto non-core classes: {unknown}"

    def test_the_server_and_the_pipelines_name_the_same_classes(self):
        # corpus.CORE_CLASSES is the one written-down list; this side keeps its
        # own only because a server module cannot import a pipeline script at
        # runtime. Equal, or the fleet is serving a vocabulary nothing trains.
        corpus = _load(REPO / "pipelines" / "ingest" / "corpus.py")
        assert sorted(corpus.CORE_CLASSES) == sorted(CORE_CLASSES)

    def test_flight_call_is_the_one_the_vendored_flags_cannot_reach(self):
        # Not a defect to fix — there is no flight-call flag upstream — but it
        # is why crowgpt's vocabulary is four where this one is five, and the
        # gap has to stay named rather than be rediscovered by whoever joins
        # the two. crowgpt asserts the same thing from its own side.
        corpus = _load(REPO / "pipelines" / "ingest" / "corpus.py")
        unreachable = set(CORE_CLASSES) - set(corpus.FLAG_TO_CORE.values())
        assert unreachable == {"flight call"}

    def test_begging_is_a_class_on_both_sides(self):
        corpus = _load(REPO / "pipelines" / "ingest" / "corpus.py")
        assert "begging" in CORE_CLASSES
        assert corpus.FLAG_TO_CORE["begging"] == "begging"

    def test_every_core_class_has_a_colour(self):
        assert set(CORE_COLORS) == set(CORE_CLASSES)

    def test_every_core_class_is_seeded_as_its_own_label(self):
        seeded = dict(SEED_LABELS)
        for core in CORE_CLASSES:
            assert seeded.get(core) == core, f"{core} is not seeded as itself"

    def test_every_seeded_label_maps_into_the_core_space(self):
        for key, core in SEED_LABELS:
            assert core in CORE_CLASSES, f"{key} -> {core}"

    def test_judgements_about_a_detection_train_nothing(self, client):
        """"Not a crow" is storable but must never become a predicted class.

        The model heard a crow and there was not one: that is precision data,
        and retracting the label would throw it away. It is still not a call
        type, so it carries no core class and the training export skips it.
        """
        config = client.get("/api/config?locale=en").get_json()
        by_key = {label["key"]: label for label in config["labels"]}
        assert by_key["not_a_crow"]["trains"] is False
        assert by_key["unsure"]["trains"] is False
        assert all(label["trains"] for label in config["labels"]
                   if label["key"] in {"call", "song", "alarm call"})


class TestPromotingAClassReachesAnExistingFleet:
    """Seeding runs once, so a promoted class has to be migrated in.

    A fleet that seeded before begging was core would otherwise serve the old
    mapping forever — and its phones would never know to ask, because the
    version they cache would never change.
    """

    # The seed order as it shipped, when begging sat among the field labels
    # rather than the cores. Restoring it here is the point: promotion reorders
    # the served list, and a migrated fleet has to end up where a fresh one does.
    OLD_ORDER = ["alarm call", "call", "flight call", "song", "mobbing",
                 "scold", "contact call", "begging", "rattle"]

    @classmethod
    def _seed_pre_begging(cls, db_path) -> int:
        """A DB as it looked when begging still mapped down to `call`."""
        ConfigStore(db_path)
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute(
                "UPDATE label_defs SET core_mapping='call', color=NULL WHERE key='begging'")
            for i, key in enumerate(cls.OLD_ORDER):
                conn.execute("UPDATE label_defs SET sort_order=? WHERE key=?", (i, key))
            version = conn.execute("SELECT MAX(version) FROM config_versions").fetchone()[0]
        conn.close()
        return version

    def test_an_existing_fleet_is_remapped_on_open(self, db_path):
        self._seed_pre_begging(db_path)
        assert ConfigStore(db_path).core_for_label("begging") == "begging"

    def test_the_remap_publishes_a_version_the_phones_will_notice(self, db_path):
        stale = self._seed_pre_begging(db_path)
        assert ConfigStore(db_path).current_version() > stale

    def test_reopening_an_up_to_date_fleet_publishes_nothing(self, db_path):
        version = ConfigStore(db_path).current_version()
        assert ConfigStore(db_path).current_version() == version

    def test_a_migrated_fleet_serves_what_a_fresh_one_serves(self, db_path, tmp_path):
        self._seed_pre_begging(db_path)
        migrated = ConfigStore(db_path).get_config()
        # Migrated explicitly: a store no longer creates its own tables, so a
        # bare path is a database with nothing in it.
        fresh_path = tmp_path / "fresh.db"
        schema.upgrade(fresh_path)
        fresh = ConfigStore(fresh_path).get_config()
        assert migrated["labels"] == fresh["labels"]
        assert migrated["core_colors"] == fresh["core_colors"]


class TestTheServedConfigCarriesBegging:
    def test_begging_is_served_as_its_own_core(self, client):
        config = client.get("/api/config?locale=en").get_json()
        begging = next(l for l in config["labels"] if l["key"] == "begging")
        assert begging["core"] == "begging"
        assert begging["text"] == "Begging"

    def test_begging_no_longer_borrows_the_call_colour(self, client):
        colors = client.get("/api/config?locale=en").get_json()["core_colors"]
        assert colors["begging"] != colors["call"]

