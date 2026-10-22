"""Machine-written descriptions, and the two things that make them worth having.

The first is durability. The whole reason this is keyed on a span rather than on
a label is that re-answering a call type deletes the label row, and a description
that died with it would be worth less than the minute it cost to write. So the
tests that matter most are the ones where a label comes and goes underneath.

The second is that it stays distinguishable from what the recordist wrote. That
one is mostly enforced by the schema — separate table, separate verb — but the
tests pin that a capture's own `notes` are never touched by writing one.
"""

import pytest

from fieldserver.stores.ai_descriptions import AiDescriptionStore
from fieldserver.stores.captures import CaptureStore
from fieldserver.stores.contributors import ContributorStore
from fieldserver.stores.devices import DeviceStore
from fieldserver.stores.labels import LabelStore
from fieldserver.stores.media import MediaStore


@pytest.fixture
def descriptions(db_path):
    return AiDescriptionStore(db_path)


@pytest.fixture
def captures(db_path):
    return CaptureStore(db_path)


@pytest.fixture
def owner(db_path):
    """A contributor with a phone. `captures.device_id` is NOT NULL.

    Named `owner` rather than `recordist` so it does not shadow conftest's
    fixture of that name, which is an enrolled API client and a different thing.
    """
    who, _claim_code = ContributorStore(db_path).create(display_name="Ben")
    device, _token = DeviceStore(db_path).register(who["id"], label="Pixel 8")
    return who["id"], device["id"]


@pytest.fixture
def capture(captures, owner):
    contributor_id, device_id = owner
    return captures.add(contributor_id=contributor_id, device_id=device_id,
                        notes="Two crows on the wire, mobbing something.")


@pytest.fixture
def media(db_path, tmp_path, capture):
    """A media slot, because `labels.media_id` is NOT NULL."""
    return MediaStore(db_path, tmp_path / "media").create(capture["id"])


def label_on(labels, capture, media, call_type, start_sec, end_sec):
    return labels.add(capture_id=capture["id"], media_id=media["id"],
                      contributor_id=capture["contributor_id"],
                      device_id=capture["device_id"],
                      species="American Crow", call_type=call_type,
                      start_sec=start_sec, end_sec=end_sec)


class TestWholeCapture:
    def test_a_description_of_the_recording_is_stored_and_read_back(
        self, descriptions, capture
    ):
        descriptions.set(capture["id"], "A long account of the whole recording.",
                         model="fable-5")

        found = descriptions.whole_capture(capture["id"])
        assert found["description"] == "A long account of the whole recording."
        assert found["model"] == "fable-5"
        assert found["start_sec"] is None

    def test_writing_again_replaces_rather_than_accumulates(self, descriptions, capture):
        """A re-run model is the same reading done again, not a change of mind."""
        descriptions.set(capture["id"], "First attempt.")
        descriptions.set(capture["id"], "Second, better attempt.")

        assert descriptions.whole_capture(capture["id"])["description"] == (
            "Second, better attempt.")
        assert len(descriptions.for_capture(capture["id"])) == 1

    def test_it_does_not_touch_what_the_recordist_wrote(
        self, descriptions, captures, capture
    ):
        descriptions.set(capture["id"], "The model's account.")

        assert captures.get(capture["id"])["notes"] == (
            "Two crows on the wire, mobbing something.")

    def test_none_written_is_none_rather_than_empty(self, descriptions, capture):
        assert descriptions.whole_capture(capture["id"]) is None
        assert descriptions.for_capture(capture["id"]) == []


class TestSpans:
    def test_a_span_is_stored_against_its_seconds(self, descriptions, capture):
        descriptions.set(capture["id"], "A harsh doubled caw.", 3.0, 5.5)

        span = descriptions.spans(capture["id"])[0]
        assert (span["start_sec"], span["end_sec"]) == (3.0, 5.5)

    def test_spans_come_back_in_time_order(self, descriptions, capture):
        descriptions.set(capture["id"], "third", 9.0, 10.0)
        descriptions.set(capture["id"], "first", 1.0, 2.0)
        descriptions.set(capture["id"], "second", 4.0, 5.0)

        assert [s["description"] for s in descriptions.spans(capture["id"])] == [
            "first", "second", "third"]

    def test_the_whole_capture_row_is_not_one_of_the_spans(self, descriptions, capture):
        """Or every per-span reader would have to filter it out by hand."""
        descriptions.set(capture["id"], "the whole thing")
        descriptions.set(capture["id"], "one call", 1.0, 2.0)

        assert len(descriptions.spans(capture["id"])) == 1
        assert len(descriptions.for_capture(capture["id"])) == 2

    def test_the_whole_capture_row_comes_first(self, descriptions, capture):
        descriptions.set(capture["id"], "one call", 1.0, 2.0)
        descriptions.set(capture["id"], "the whole thing")

        assert descriptions.for_capture(capture["id"])[0]["start_sec"] is None

    def test_two_captures_do_not_share_a_span(self, descriptions, captures, capture):
        other = captures.add(contributor_id=capture["contributor_id"],
                             device_id=capture["device_id"])
        descriptions.set(capture["id"], "mine", 1.0, 2.0)
        descriptions.set(other["id"], "theirs", 1.0, 2.0)

        assert descriptions.spans(capture["id"])[0]["description"] == "mine"
        assert descriptions.spans(other["id"])[0]["description"] == "theirs"


class TestItOutlivesTheLabel:
    """The reason this is not a column on `labels`."""

    def test_a_description_survives_the_label_being_retracted(
        self, db_path, descriptions, capture, media
    ):
        labels = LabelStore(db_path)
        label = label_on(labels, capture, media, "alarm call", 3.0, 5.5)
        descriptions.set(capture["id"], "A harsh doubled caw.", 3.0, 5.5)

        # Re-answering from the phone is delete-and-recreate, not an edit.
        labels.delete(label["id"])

        assert descriptions.spans(capture["id"])[0]["description"] == "A harsh doubled caw."

    def test_it_is_still_there_for_the_label_that_replaces_it(
        self, db_path, descriptions, capture, media
    ):
        labels = LabelStore(db_path)
        first = label_on(labels, capture, media, "alarm call", 3.0, 5.5)
        descriptions.set(capture["id"], "A harsh doubled caw.", 3.0, 5.5)
        labels.delete(first["id"])
        second = label_on(labels, capture, media, "call", 3.0, 5.5)

        # A different row id, the same seconds, and the description still applies.
        assert second["id"] != first["id"]
        assert descriptions.spans(capture["id"])[0]["start_sec"] == second["start_sec"]

    def test_a_span_can_be_described_before_anything_is_labelled(
        self, descriptions, capture
    ):
        """Which is the useful order: describe first, decide afterwards."""
        descriptions.set(capture["id"], "Something faint at four seconds.", 4.0, 5.0)

        assert len(descriptions.spans(capture["id"])) == 1

    def test_deleting_the_capture_takes_its_descriptions(
        self, db_path, descriptions, capture
    ):
        """They are about that audio and nothing else."""
        descriptions.set(capture["id"], "gone with it", 1.0, 2.0)
        with AiDescriptionStore(db_path)._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM captures WHERE id = ?", (capture["id"],))

        assert descriptions.spans(capture["id"]) == []


class TestRefusals:
    def test_half_a_span_is_refused(self, descriptions, capture):
        """Nothing could tell "from here on" from a forgotten end."""
        with pytest.raises(ValueError, match="both"):
            descriptions.set(capture["id"], "text", start_sec=1.0)
        with pytest.raises(ValueError, match="both"):
            descriptions.set(capture["id"], "text", end_sec=2.0)

    def test_a_backwards_span_is_refused(self, descriptions, capture):
        with pytest.raises(ValueError, match="end after"):
            descriptions.set(capture["id"], "text", 5.0, 3.0)
        with pytest.raises(ValueError, match="end after"):
            descriptions.set(capture["id"], "text", 3.0, 3.0)

    def test_empty_text_is_refused_rather_than_treated_as_deletion(
        self, descriptions, capture
    ):
        """A truncated write must not silently erase a paragraph."""
        descriptions.set(capture["id"], "a real description")
        with pytest.raises(ValueError, match="clear"):
            descriptions.set(capture["id"], "   ")

        assert descriptions.whole_capture(capture["id"])["description"] == (
            "a real description")


class TestTheDashboardSeesIt:
    """The operator dashboard is the only reader today, so the key is a contract."""

    @pytest.fixture
    def served(self, client, recordist, operator, db_path):
        capture = client.post("/api/captures", json={"client_uuid": "cap-ai1"},
                              headers=recordist.headers).get_json()
        AiDescriptionStore(db_path).set(
            capture["id"], "The whole account.", model="fable-5")
        AiDescriptionStore(db_path).set(
            capture["id"], "One doubled caw.", 3.0, 5.5, model="fable-5")
        return client.get(f"/api/fleet/captures/{capture['id']}",
                          headers=operator.headers).get_json()

    def test_the_detail_carries_them_whole_capture_first(self, served):
        written = served["ai_descriptions"]

        assert [w["description"] for w in written] == [
            "The whole account.", "One doubled caw."]
        assert written[0]["start_sec"] is None
        assert written[1]["start_sec"] == 3.0

    def test_the_model_and_the_date_travel_with_the_text(self, served):
        """A guess whose author and date are unknown cannot be judged later."""
        entry = served["ai_descriptions"][0]

        assert entry["model"] == "fable-5"
        assert entry["written_at"]

    def test_it_is_its_own_key_not_folded_into_the_recordists_words(
        self, served
    ):
        """Rendering machine prose as testimony is the one failure that matters."""
        assert served["capture"]["notes"] is None
        assert "ai_descriptions" in served
        assert served["observations"] == []

    def test_a_capture_with_none_says_so_rather_than_omitting_the_key(
        self, client, recordist, operator
    ):
        capture = client.post("/api/captures", json={"client_uuid": "cap-ai2"},
                              headers=recordist.headers).get_json()

        detail = client.get(f"/api/fleet/captures/{capture['id']}",
                            headers=operator.headers).get_json()

        assert detail["ai_descriptions"] == []


class TestClearing:
    def test_clear_removes_the_whole_capture_row(self, descriptions, capture):
        descriptions.set(capture["id"], "written in error")

        assert descriptions.clear(capture["id"]) is True
        assert descriptions.whole_capture(capture["id"]) is None

    def test_clear_removes_one_span_and_leaves_the_others(self, descriptions, capture):
        descriptions.set(capture["id"], "keep", 1.0, 2.0)
        descriptions.set(capture["id"], "drop", 4.0, 5.0)

        assert descriptions.clear(capture["id"], 4.0, 5.0) is True
        assert [s["description"] for s in descriptions.spans(capture["id"])] == ["keep"]

    def test_clearing_the_whole_capture_leaves_the_spans(self, descriptions, capture):
        descriptions.set(capture["id"], "the whole thing")
        descriptions.set(capture["id"], "one call", 1.0, 2.0)

        descriptions.clear(capture["id"])

        assert len(descriptions.spans(capture["id"])) == 1

    def test_clearing_nothing_says_so(self, descriptions, capture):
        assert descriptions.clear(capture["id"]) is False
