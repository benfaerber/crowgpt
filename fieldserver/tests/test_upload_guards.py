"""What the upload route is allowed to be told to do with a client's bytes.

`Content-Range` decides where bytes land on disk, and it used to be trusted:
split on a dash, `int()` the pieces, seek there. That made a malformed header a
500 and an invented offset an instruction — one byte written at 8 GiB produced
an 8 GiB sparse file, which `finalize` then read back in full to hash it. A
device token was the only thing needed to do it.

These pin the two rules that replaced it: the header has to parse and agree
with the body it came with, and a write may never leave a gap.
"""

import pytest

from fieldserver.app import MAX_UPLOAD_BYTES


@pytest.fixture
def slot(client, recordist):
    """A media slot on a capture, ready to receive bytes."""
    capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                          headers=recordist.headers).get_json()
    return client.post(f"/api/captures/{capture['id']}/media",
                       json={"client_uuid": "med-1"},
                       headers=recordist.headers).get_json()


def put(client, who, slot, data, content_range=None):
    headers = dict(who.headers)
    if content_range:
        headers["Content-Range"] = content_range
    return client.put(f"/api/media/{slot['id']}", data=data, headers=headers)


class TestContentRangeParsing:

    def test_a_whole_body_with_no_range_still_works(self, client, recordist, slot):
        assert put(client, recordist, slot, b"abc").status_code == 200

    def test_a_well_formed_range_is_taken(self, client, recordist, slot):
        answer = put(client, recordist, slot, b"abc", "bytes 0-2/6")
        assert answer.status_code == 200
        assert answer.get_json()["bytes"] == 3

    @pytest.mark.parametrize("header", [
        "bytes abc-def/ghi",
        "bytes -5-10/10",
        "bytes 0-2",
        "chunks 0-2/3",
        "bytes 0-2/0",
        # end past the declared total: the file cannot be shorter than its parts
        "bytes 0-9/3",
        # backwards
        "bytes 5-2/9",
    ])
    def test_a_header_it_cannot_read_is_refused_not_crashed(
            self, client, recordist, slot, header):
        # 400, never 500. The old parser raised ValueError on the first three
        # of these and OSError on the negative seek.
        assert put(client, recordist, slot, b"abc", header).status_code == 400

    def test_an_empty_header_reads_as_no_header_at_all(
            self, client, recordist, slot):
        # Not a malformed range — an absent one. Sending the whole body with no
        # range is a supported call, and this is the same thing said in blanks.
        assert put(client, recordist, slot, b"abc", "").status_code == 200

    def test_a_range_that_disagrees_with_its_body_is_refused(
            self, client, recordist, slot):
        # Claiming ten bytes and sending three is a bug wherever it came from,
        # and taking either number at its word writes the wrong file.
        assert put(client, recordist, slot, b"abc", "bytes 0-9/20").status_code == 400


class TestNoHoles:

    def test_a_far_offset_is_refused(self, client, recordist, slot):
        # The original report: one byte, eight gigabytes of sparse file, and an
        # 8 GiB read at finalize. Nothing is written and nothing is recorded.
        far = 8 * 1024 ** 3
        answer = put(client, recordist, slot, b"x", f"bytes {far}-{far}/{far + 1}")
        assert answer.status_code == 400

    def test_the_slot_is_left_empty_by_the_attempt(self, client, recordist, slot):
        far = 8 * 1024 ** 3
        put(client, recordist, slot, b"x", f"bytes {far}-{far}/{far + 1}")
        capture_id = slot["capture_id"]
        after = client.get(f"/api/captures/{capture_id}/media",
                           headers=recordist.headers).get_json()
        assert after[0]["bytes"] in (None, 0)
        assert after[0]["upload_state"] == "pending"

    def test_even_one_byte_past_the_end_is_refused(self, client, recordist, slot):
        put(client, recordist, slot, b"abc", "bytes 0-2/9")
        assert put(client, recordist, slot, b"z", "bytes 4-4/9").status_code == 400

    def test_resuming_at_the_end_is_the_normal_case(self, client, recordist, slot):
        put(client, recordist, slot, b"abc", "bytes 0-2/6")
        answer = put(client, recordist, slot, b"def", "bytes 3-5/6")
        assert answer.status_code == 200
        assert answer.get_json()["upload_state"] == "complete"

    def test_re_sending_a_chunk_already_stored_is_allowed(
            self, client, recordist, slot):
        # A dropped response is recovered by sending the chunk again, so this
        # has to keep working — overwriting is fine, skipping ahead is not.
        put(client, recordist, slot, b"abcdef", "bytes 0-5/9")
        answer = put(client, recordist, slot, b"abc", "bytes 0-2/9")
        assert answer.status_code == 200


class TestACompletedUploadIsSealed:
    """Bytes stop being writable the moment finalize() has hashed them.

    Otherwise a second PUT rewrites the file while sha256 keeps describing the
    old one — and because owned_capture hands operators every capture, that is
    how one operator silently overwrites another recordist's field recording.
    A genuine resume never reaches here: a completed upload has nothing left to
    resume.
    """

    def completed(self, client, recordist, slot):
        answer = put(client, recordist, slot, b"ORIGINALAUDIO")
        assert answer.get_json()["upload_state"] == "complete"
        return client.get(f"/api/captures/{slot['capture_id']}/media",
                          headers=recordist.headers).get_json()[0]

    def test_appending_to_a_complete_upload_is_refused(self, client, recordist, slot):
        self.completed(client, recordist, slot)
        assert put(client, recordist, slot, b"XXXX", "bytes 0-3/13").status_code == 400

    def test_the_bytes_and_hash_are_untouched_by_the_attempt(
            self, client, recordist, slot):
        before = self.completed(client, recordist, slot)
        put(client, recordist, slot, b"XXXX", "bytes 0-3/13")
        after = client.get(f"/api/captures/{slot['capture_id']}/media",
                           headers=recordist.headers).get_json()[0]
        assert after["sha256"] == before["sha256"]
        assert after["bytes"] == before["bytes"]
        assert after["upload_state"] == "complete"


class TestBodySize:

    def test_a_ceiling_is_set(self, app):
        # `request.get_data()` buffers whatever arrives, so without this one
        # POST is a memory-exhaustion switch for anything holding a token.
        assert app.config["MAX_CONTENT_LENGTH"] == MAX_UPLOAD_BYTES

    def test_it_clears_the_largest_chunk_either_client_sends(self):
        # The dashboard uploads in 4 MiB chunks, the phone in 256 KiB ones. A
        # cap under either would break syncing rather than protect anything.
        assert MAX_UPLOAD_BYTES > 4 * 1024 * 1024

    def test_a_body_over_it_is_refused(self, client, recordist, slot):
        answer = put(client, recordist, slot, b"x" * (MAX_UPLOAD_BYTES + 1))
        assert answer.status_code == 413


class TestMediaFormat:
    """`format` becomes a filename and half a media type, so it has to be safe
    as both. The dashboard takes it from whatever extension an operator's file
    had, which is why it is validated here rather than trusted."""

    @pytest.fixture
    def capture(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "cap-2"},
                           headers=recordist.headers).get_json()

    def slot_with(self, client, recordist, capture, **body):
        return client.post(f"/api/captures/{capture['id']}/media",
                           json=body, headers=recordist.headers)

    @pytest.mark.parametrize("fmt", ["wav", "flac", "mp4", "m4a", "ogg", "opus"])
    def test_a_real_extension_is_accepted(self, client, recordist, capture, fmt):
        # An unusual-but-real recording must still land: refusing one costs a
        # capture, and the corpus is the point.
        answer = self.slot_with(client, recordist, capture, format=fmt,
                                client_uuid=f"med-{fmt}")
        assert answer.status_code == 201
        assert answer.get_json()["format"] == fmt

    @pytest.mark.parametrize("fmt", [
        "../../../../tmp/pwn",
        "wav/../../../tmp/pwn",
        "/tmp/pwn",
        "wav\x00.txt",
        "a" * 40,
        "",
    ])
    def test_anything_that_is_not_one_is_refused(
            self, client, recordist, capture, fmt):
        answer = self.slot_with(client, recordist, capture, format=fmt,
                                client_uuid="med-bad")
        assert answer.status_code == 400

    def test_the_storage_ref_stays_a_single_path_component(
            self, client, recordist, capture):
        row = self.slot_with(client, recordist, capture, format="WAV",
                             client_uuid="med-case").get_json()
        assert "/" not in row["storage_ref"]
        assert ".." not in row["storage_ref"]
        assert row["format"] == "wav"

    def test_an_unknown_kind_is_refused(self, client, recordist, capture):
        # It picks the media type the raw route serves, so it is the other half
        # of the same header.
        answer = self.slot_with(client, recordist, capture, kind="text",
                                client_uuid="med-kind")
        assert answer.status_code == 400
