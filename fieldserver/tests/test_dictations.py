"""Spoken field notes: the queue, and the two separations that justify the table.

A dictation is the recordist talking, not the birds. Most of what is worth
testing here is what it must NOT touch — the media directory, the analyzer's idea
of what a capture's audio is, and the capture's own status — because every one of
those failures is silent and only shows up as a number that is quietly wrong.
"""

import pytest

from fieldserver.stores.captures import CaptureStore
from fieldserver.stores.contributors import ContributorStore
from fieldserver.stores.devices import DeviceStore
from fieldserver.stores.dictations import DictationStore
from fieldserver.stores.media import MediaStore


@pytest.fixture
def captures(db_path):
    return CaptureStore(db_path)


@pytest.fixture
def owner(db_path):
    """A contributor with a phone — `captures.device_id` is NOT NULL."""
    who, _claim = ContributorStore(db_path).create(display_name="Ben")
    device, _token = DeviceStore(db_path).register(who["id"], label="Pixel 8")
    return who["id"], device["id"]


@pytest.fixture
def capture(captures, owner):
    contributor_id, device_id = owner
    return captures.add(contributor_id=contributor_id, device_id=device_id,
                        notes="Two crows on the wire.")


@pytest.fixture
def media_dir(tmp_path):
    return tmp_path / "media"


@pytest.fixture
def media(db_path, media_dir):
    return MediaStore(db_path, media_dir)


@pytest.fixture
def store(db_path, tmp_path):
    return DictationStore(db_path, tmp_path / "dictations")


def spoken(store, capture, data=b"RIFFxxxxWAVEfmt spoken words", **kw):
    row = store.create(capture_id=capture["id"], **kw)
    store.append(row["id"], data, 0)
    return store.finalize(row["id"])


class TestUpload:
    def test_a_memo_resumes_where_it_stopped(self, store, capture):
        row = store.create(capture_id=capture["id"])
        store.append(row["id"], b"first half ", 0)
        # The client resumes from the byte count it was handed back, exactly as
        # a media upload does.
        partial = store.get(row["id"])
        store.append(row["id"], b"second half", partial["bytes"])

        done = store.finalize(row["id"])
        assert done["upload_state"] == "complete"
        assert store.path(done).read_bytes() == b"first half second half"

    def test_it_refuses_to_leave_a_hole(self, store, capture):
        """A sparse file's length is whatever the client claimed, and finalize
        reads the whole of it back to hash it."""
        row = store.create(capture_id=capture["id"])
        with pytest.raises(ValueError, match="gap"):
            store.append(row["id"], b"late", 4096)

    def test_the_same_client_uuid_resumes_rather_than_duplicating(self, store, capture):
        first = store.create(capture_id=capture["id"], client_uuid="memo-1")
        again = store.create(capture_id=capture["id"], client_uuid="memo-1")
        assert again["id"] == first["id"]

    def test_it_defaults_to_sixteen_kilohertz(self, store, capture):
        """What the transcriber wants, a third of the bytes, and it makes 'not
        bird audio' a property of the file rather than of a column."""
        assert store.create(capture_id=capture["id"])["sample_rate"] == 16000


class TestItIsNotBirdAudio:
    def test_the_bytes_never_land_in_the_media_directory(
        self, store, capture, media_dir, tmp_path
    ):
        """`instance/media/` means 'somebody's recording of birds'. Everything
        that walks it — the compressor, the experiments, any export — relies on
        that being literally true."""
        done = spoken(store, capture)

        assert store.path(done).exists()
        assert not media_dir.exists() or list(media_dir.iterdir()) == []
        assert not (tmp_path / "media-originals").exists()

    def test_the_analyzer_is_never_handed_one(self, store, media, capture):
        """The sharp edge: `complete_audio_for` used only to SORT by kind, so any
        complete row was a candidate and the newest non-audio kind won. A memo is
        not in `media` at all, and the allow-list is what keeps that a rule
        rather than a coincidence."""
        spoken(store, capture)

        assert media.complete_audio_for(capture["id"]) is None

    def test_a_real_recording_is_still_found(self, store, media, capture):
        slot = media.create(capture["id"], kind="audio")
        media.append(slot["id"], b"RIFFxxxxWAVEfmt bird audio", 0)
        media.finalize(slot["id"])
        spoken(store, capture)

        found = media.complete_audio_for(capture["id"])
        assert found is not None and found["id"] == slot["id"]


class TestTheQueue:
    def test_a_finished_upload_can_be_claimed_once(self, store, capture):
        done = spoken(store, capture)
        store.enqueue(done["id"], capture["id"])

        claimed = store.claim_next()
        assert claimed["state"] == "running"
        assert store.claim_next() is None

    def test_enqueueing_twice_makes_one_job(self, store, capture):
        """Re-sending a final chunk is routine on a bad link; transcribing the
        same memo twice is not."""
        done = spoken(store, capture)
        first = store.enqueue(done["id"], capture["id"])
        again = store.enqueue(done["id"], capture["id"])

        assert again["id"] == first["id"]

    def test_a_failed_job_may_be_superseded(self, store, capture):
        done = spoken(store, capture)
        first = store.enqueue(done["id"], capture["id"])
        store.fail(first["id"], "the model fell over")

        assert store.enqueue(done["id"], capture["id"])["id"] != first["id"]

    def test_a_worker_restart_hands_back_what_it_was_holding(self, store, capture):
        done = spoken(store, capture)
        store.enqueue(done["id"], capture["id"])
        store.claim_next()

        requeued, abandoned = store.reclaim_running()
        assert (requeued, abandoned) == (1, 0)
        assert store.claim_next() is not None

    def test_a_job_that_keeps_killing_the_worker_is_abandoned(self, store, capture):
        """Otherwise the restart it caused requeues it forever."""
        done = spoken(store, capture)
        store.enqueue(done["id"], capture["id"])
        for _ in range(3):
            store.claim_next()
            store.reclaim_running()

        assert store.claim_next() is None
        assert store.get(done["id"])["transcribed_at"] is None

    def test_completing_writes_the_transcript_and_the_state_together(
        self, store, capture
    ):
        """Done-with-no-transcript must be unreachable: the transcript is this
        job's product, not a decoration like quality is on an analysis job."""
        done = spoken(store, capture)
        job = store.enqueue(done["id"], capture["id"])
        store.claim_next()

        finished = store.complete(job["id"], done["id"], "two of them were mobbing",
                                  model="whisper-large-v3-turbo", language="en",
                                  mean_logprob=-0.21)
        assert finished["state"] == "done"
        row = store.get(done["id"])
        assert row["transcript"] == "two of them were mobbing"
        assert row["transcript_model"] == "whisper-large-v3-turbo"
        assert row["mean_logprob"] == pytest.approx(-0.21)

    def test_failing_a_transcription_leaves_the_capture_alone(
        self, store, captures, capture
    ):
        """The easiest copy-paste mistake in the store. `AnalysisStore.fail` ends
        by handing the capture back from 'analyzing' to 'uploaded'; doing that
        here would make an analysed recording reappear in the dashboard's
        needs-work count because speech-to-text fell over."""
        captures.set_status(capture["id"], "analyzed")
        done = spoken(store, capture)
        job = store.enqueue(done["id"], capture["id"])
        store.claim_next()

        store.fail(job["id"], "no speech found")

        assert captures.get(capture["id"])["status"] == "analyzed"


class TestTheAudit:
    def test_purge_takes_the_audio_with_the_row(self, store, capture):
        """The privacy note needs a verb. A memo is speech and may name people."""
        done = spoken(store, capture)
        path = store.path(done)
        assert path.exists()

        removed = store.purge_before("2999-01-01T00:00:00Z")

        assert removed == 1
        assert not path.exists()
        assert store.for_capture(capture["id"]) == []
