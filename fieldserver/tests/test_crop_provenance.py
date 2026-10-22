"""Which span of the recording the stored audio actually is.

The phone uploads only the selected span but reports `duration_sec` for the
whole recording. Without the crop bounds the server holds twelve seconds of
audio labelled ninety, and nothing on the row says why — so every duration
downstream was quietly wrong for any trimmed capture.
"""

import pytest


def make(client, recordist, **body):
    return client.post("/api/captures",
                       json={"client_uuid": "cap-1", "duration_sec": 90.0, **body},
                       headers=recordist.headers).get_json()


class TestCropBounds:

    def test_a_trimmed_capture_says_which_span_it_is(self, client, recordist):
        capture = make(client, recordist, crop_start_sec=12.0, crop_end_sec=24.0)
        assert capture["crop_start_sec"] == 12.0
        assert capture["crop_end_sec"] == 24.0

    def test_duration_still_describes_the_whole_recording(self, client, recordist):
        # Not rewritten to the trimmed length: what was recorded and what was
        # uploaded are different facts, and both are worth keeping.
        capture = make(client, recordist, crop_start_sec=12.0, crop_end_sec=24.0)
        assert capture["duration_sec"] == 90.0

    def test_the_stored_audio_length_is_derivable(self, client, recordist):
        capture = make(client, recordist, crop_start_sec=12.0, crop_end_sec=24.0)
        assert capture["crop_end_sec"] - capture["crop_start_sec"] == 12.0

    def test_an_untrimmed_capture_is_null_not_zero(self, client, recordist):
        # Zero would claim a trim starting at the beginning, which is a
        # different statement from "the file is the whole recording".
        capture = make(client, recordist)
        assert capture["crop_start_sec"] is None
        assert capture["crop_end_sec"] is None

    def test_a_trim_from_the_start_is_recorded_as_zero(self, client, recordist):
        capture = make(client, recordist, crop_start_sec=0.0, crop_end_sec=30.0)
        assert capture["crop_start_sec"] == 0.0

    def test_it_is_not_editable_afterwards(self, client, recordist):
        # Moving the bounds without re-uploading the audio would leave metadata
        # describing bytes that are not there. The whole value is that these
        # describe the file the server holds.
        capture = make(client, recordist, crop_start_sec=12.0, crop_end_sec=24.0)
        client.patch(f"/api/captures/{capture['id']}",
                     json={"crop_start_sec": 0.0, "crop_end_sec": 90.0},
                     headers=recordist.headers)
        after = client.get("/api/captures", headers=recordist.headers).get_json()[0]
        assert after["crop_start_sec"] == 12.0
