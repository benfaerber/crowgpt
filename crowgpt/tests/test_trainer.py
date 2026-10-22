"""The trainer's Python half: pools, vocabulary, windows, and refusals.

The page is a measuring instrument for a person, so what matters is what every
listening page already learned the hard way: nothing identifying a clip may be
visible before the answer, a repeat measures memory rather than the ear, and a
clip too short to grade decides its trial before anyone listens. The gathering
side has its own failure mode — a quiz drawing from the wrong rows of a
database is wrong silently — so the SQL paths run here against tiny databases
with exactly the rows that must be excluded.
"""

import json
import re
import shutil
import sqlite3
import subprocess

import numpy as np
import pytest

from crowgpt.trainer import (ASSERTED, FIELD, HUMAN, UNTYPED, TrainerPage,
                             Vocabulary, clip_window, contact_exemplars,
                             field_exemplars, merge_adjacent, spectrogram)

SR = 24000


def _clip(key, seed, clip_id=None, seconds=2.0, provenance=HUMAN,
          species="American Crow", note=""):
    rng = np.random.default_rng(seed)
    return {"clip_id": clip_id or f"{key}-{seed}",
            "key": key, "sr": SR,
            "audio": rng.normal(0, 0.1, int(seconds * SR)).astype(np.float32),
            "provenance": provenance, "species": species, "note": note}


MENU = [{"key": "alarm call", "core": "alarm call", "color": "#f27070"},
        {"key": "call", "core": "call", "color": "#6ea8fe"},
        {"key": "contact call", "core": "call", "color": "#6ea8fe"}]


@pytest.fixture
def clips():
    out = []
    for i in range(4):
        out.append(_clip("alarm call", i))
        out.append(_clip("call", 100 + i))
        out.append(_clip("contact call", 200 + i, provenance=ASSERTED,
                         species="Hooded Crow"))
    return out


class TestVocabulary:
    ROWS = [("alarm call", "alarm call", "#f27070", 0, 1),
            ("call", "call", "#6ea8fe", 2, 1),
            ("contact call", "call", None, 7, 1),
            ("not_a_crow", "not_a_crow", None, 9, 0)]

    def test_a_def_keeps_its_own_color(self):
        assert Vocabulary(self.ROWS).color_for("alarm call") == "#f27070"

    def test_a_colorless_def_borrows_its_core_color(self):
        """The app's colorForCall: contact call reads as the call it maps to."""
        assert Vocabulary(self.ROWS).color_for("contact call") == "#6ea8fe"

    def test_an_unknown_key_stays_grey(self):
        """Grey rather than borrowing a colour and implying a classification."""
        assert Vocabulary(self.ROWS).color_for("kraa") == UNTYPED

    def test_menu_keeps_the_phone_order(self):
        menu = Vocabulary(self.ROWS).menu(["contact call", "alarm call"])
        assert [m["key"] for m in menu] == ["alarm call", "contact call"]

    def test_menu_refuses_a_key_the_phone_cannot_show(self):
        with pytest.raises(ValueError, match="not in the field vocabulary"):
            Vocabulary(self.ROWS).menu(["alarm call", "kraa"])

    def test_load_reads_only_active_defs(self, tmp_path):
        db_path = tmp_path / "field.db"
        with sqlite3.connect(db_path) as db:
            db.execute("create table label_defs (key text, core_mapping text, "
                       "color text, sort_order int, active int, trains int)")
            db.executemany("insert into label_defs values (?,?,?,?,?,?)",
                           [("call", "call", "#6ea8fe", 0, 1, 1),
                            ("retired", "call", None, 1, 0, 1)])
        vocabulary = Vocabulary.load(db_path)
        assert "call" in vocabulary.defs and "retired" not in vocabulary.defs


class TestWindows:
    def test_touching_windows_merge(self):
        assert merge_adjacent([(5, 6), (0, 1), (1, 2)]) == [(0, 2), (5, 6)]

    def test_a_gap_keeps_windows_apart(self):
        assert merge_adjacent([(0, 3), (4, 7)]) == [(0, 3), (4, 7)]
        assert merge_adjacent([(0, 3), (4, 7)], gap=1) == [(0, 7)]

    def test_clip_window_pads_both_sides(self):
        lo, hi = clip_window(2.0, 3.0, pad=0.25, cap=4.0)
        assert (lo, hi) == (1.75, 3.25)

    def test_clip_window_never_starts_before_zero(self):
        lo, _ = clip_window(0.0, 1.0, pad=0.25)
        assert lo == 0.0

    def test_a_long_span_keeps_its_middle(self):
        """The middle of a 30 s song bout is the least likely part to be
        something else — and a 30 s trial is not a quiz question."""
        lo, hi = clip_window(30.0, 60.0, pad=0.25, cap=4.0)
        assert hi - lo == pytest.approx(4.5)
        assert (lo + hi) / 2 == pytest.approx(45.0)


class TestSpectrogram:
    def test_shape_and_range(self):
        rng = np.random.default_rng(0)
        spec = spectrogram(rng.normal(0, 0.1, SR).astype(np.float32), SR)
        raw = __import__("base64").b64decode(spec["b64"])
        assert len(raw) == spec["w"] * spec["h"]

    def test_a_tone_outshines_the_silence_around_it(self):
        t = np.arange(SR) / SR
        tone = np.sin(2 * np.pi * 2000 * t).astype(np.float32)
        clip = np.concatenate([np.zeros(SR, dtype=np.float32), tone])
        spec = spectrogram(clip, SR)
        raw = np.frombuffer(__import__("base64").b64decode(spec["b64"]),
                            dtype=np.uint8).reshape(spec["h"], spec["w"])
        halves = np.array_split(raw, 2, axis=1)
        assert halves[1].max() > halves[0].max()


class TestTrainerPage:
    def test_pools_group_by_class_and_keep_every_clip(self, clips):
        page = TrainerPage(clips, MENU, {}, seed=0)
        assert {k: len(v) for k, v in page.pools.items()} == {
            "alarm call": 4, "call": 4, "contact call": 4}

    def test_a_repeated_clip_id_is_refused(self, clips):
        """A repeat inside a session tests memory, not the ear."""
        with pytest.raises(ValueError, match="repeated clip_id"):
            TrainerPage(clips + [_clip("call", 100)], MENU, {}, seed=0)

    def test_a_short_clip_is_refused(self, clips):
        """0044's rule, enforced here exactly as the other pages enforce it."""
        with pytest.raises(ValueError, match="ungradeable"):
            TrainerPage(clips + [_clip("call", 999, seconds=0.4)], MENU, {})

    def test_a_class_missing_from_the_menu_is_refused(self, clips):
        with pytest.raises(ValueError, match="missing from the menu"):
            TrainerPage(clips + [_clip("kraa", 1)], MENU, {}, seed=0)

    def test_the_menu_drops_classes_with_no_clips(self, clips):
        menu = MENU + [{"key": "song", "core": "song", "color": "#c58af9"}]
        page = TrainerPage(clips, menu, {}, seed=0)
        assert {m["key"] for m in page.menu} == {"alarm call", "call",
                                                "contact call"}

    def test_the_page_is_deterministic_for_a_seed(self, clips):
        first = TrainerPage(clips, MENU, {}, seed=7)
        second = TrainerPage(clips, MENU, {}, seed=7)
        assert first.rotation == second.rotation
        assert ({k: [c["clip_id"] for c in v] for k, v in first.pools.items()}
                == {k: [c["clip_id"] for c in v] for k, v in second.pools.items()})

    def test_embedded_json_parses(self, clips):
        html = TrainerPage(clips, MENU, {"Clips": 12}, seed=0).render()
        pools = re.search(r"const POOLS = (\{.*?\});\n", html, re.S).group(1)
        assert sum(len(v) for v in json.loads(pools).values()) == 12

    def test_nothing_identifying_a_clip_is_visible_before_the_answer(self):
        """Species and provenance would leak the class — every contact
        exemplar is European. They may exist in the payload; they must not be
        rendered markup, exactly as PairPage hides its arms."""
        clips = [_clip("alarm call", i, note=f"secret-note-{i}",
                       species="Corvus-secretus") for i in range(4)]
        clips += [_clip("call", 50 + i) for i in range(4)]
        html = TrainerPage(clips, MENU, {}, seed=0).render()
        body = html[: html.index("<script>")]
        assert "secret-note" not in body and "Corvus-secretus" not in body

    def test_every_clip_carries_audio_waveform_and_spectrogram(self, clips):
        page = TrainerPage(clips, MENU, {}, seed=0)
        for pool in page.pools.values():
            for clip in pool:
                assert clip["audio"].startswith("data:audio/wav;base64,")
                assert len(clip["peaks"]) == 160
                assert clip["spec"]["w"] * clip["spec"]["h"] > 0
                assert clip["seconds"] >= 1.0


class TestContactExemplars:
    """The crawl query, against a database holding exactly the traps."""

    @pytest.fixture
    def corvid_db(self, tmp_path):
        db_path = tmp_path / "corvid.db"
        wav = tmp_path / "clip.wav"
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                            "-i", "sine=frequency=800:duration=12",
                            "-ar", "24000", str(wav)], check=True)
        except FileNotFoundError:
            pytest.skip("ffmpeg not installed")
        with sqlite3.connect(db_path) as db:
            db.execute("create table recordings (id integer primary key, "
                       "species text, call_type text, file_path text, "
                       "downloaded int)")
            db.execute("create table detections (recording_id int, "
                       "start_seconds real, end_seconds real, species text, "
                       "confidence real)")
            db.executemany(
                "insert into recordings values (?,?,?,?,?)",
                [(1, "Hooded Crow", "call, Contact call", str(wav), 1),
                 (2, "Nucifraga caryocatactes", "contact call", str(wav), 1),
                 (3, "Hooded Crow", "alarm call", str(wav), 1),
                 (4, "Common Raven", "contact calls in family", str(wav), 0)])
            db.executemany(
                "insert into detections values (?,?,?,?,?)",
                [(1, 0.0, 3.0, "Hooded Crow", 0.9),
                 (1, 0.0, 3.0, "Carrion Crow", 0.5),   # same window, twice
                 (1, 3.0, 6.0, "Hooded Crow", 0.8),
                 (1, 6.0, 9.0, "Hooded Crow", 0.7),    # third-best, capped away
                 (1, 9.0, 11.0, "Black-crowned Night-Heron", 0.95),
                 (2, 0.0, 3.0, "Hooded Crow", 0.9),
                 (3, 0.0, 3.0, "Hooded Crow", 0.9),
                 (4, 0.0, 3.0, "Common Raven", 0.9)])
        return db_path

    def test_only_corvid_contact_recordings_survive(self, corvid_db):
        """Recording 2 is a nutcracker, 3 never said contact, 4 was never
        downloaded, and the heron detection is not a corvid calling."""
        rng = np.random.default_rng(0)
        out = contact_exemplars(rng, per_class=20, db_path=corvid_db)
        assert out, "the one legitimate recording produced nothing"
        assert {c["clip_id"].split(":")[1] for c in out} == {"1"}

    def test_one_recording_is_capped(self, corvid_db):
        """One long raven session must not become half the class."""
        rng = np.random.default_rng(0)
        out = contact_exemplars(rng, per_class=20, db_path=corvid_db)
        assert len(out) == 2

    def test_clips_carry_the_asserted_tier(self, corvid_db):
        rng = np.random.default_rng(0)
        for clip in contact_exemplars(rng, per_class=20, db_path=corvid_db):
            assert clip["provenance"] == ASSERTED
            assert clip["key"] == "contact call"
            assert len(clip["audio"]) / clip["sr"] >= 1.0


class TestFieldExemplars:
    @pytest.fixture
    def field_db(self, tmp_path):
        db_path = tmp_path / "field.db"
        media = tmp_path / "media"
        media.mkdir()
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                            "-i", "sine=frequency=600:duration=30",
                            "-ar", "24000", str(media / "a.wav")], check=True)
        except FileNotFoundError:
            pytest.skip("ffmpeg not installed")
        with sqlite3.connect(db_path) as db:
            db.execute("create table label_defs (key text, trains int)")
            db.executemany("insert into label_defs values (?,?)",
                           [("alarm call", 1), ("not_a_crow", 0)])
            db.execute("create table media (id integer primary key, "
                       "storage_ref text)")
            db.execute("insert into media values (1, 'a.wav')")
            db.execute("create table labels (id integer primary key, "
                       "media_id int, call_type text, label_source text, "
                       "start_sec real, end_sec real)")
            db.executemany(
                "insert into labels values (?,?,?,?,?,?)",
                [(1, 1, "alarm call", "human", 0.0, 3.0),
                 (2, 1, "alarm call", "birdnet", 3.0, 6.0),   # model guess
                 (3, 1, "not_a_crow", "human", 6.0, 9.0),      # trains = 0
                 (4, 1, "alarm call", "human", 9.0, 9.5)])     # too short
        return db_path, media

    def test_only_human_trainable_spans_survive(self, field_db):
        """detected_calls-grade rows would teach the model's confusions back
        to the ear that is supposed to correct them."""
        db_path, media = field_db
        rng = np.random.default_rng(0)
        out = field_exemplars(rng, per_class=10, db_path=db_path,
                              media_dir=media)
        assert list(out) == ["alarm call"]
        assert [c["clip_id"] for c in out["alarm call"]] == ["field:1"]
        assert out["alarm call"][0]["provenance"] == FIELD
