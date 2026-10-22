"""What was happening in the world when the bird called.

The other half of the semantics problem. `labels` records what the crow said —
a class an acoustic model can learn. This records what a human witnessed. A
corpus of calls with no context is a phonetics dataset; a corpus of contexts
with no calls is a diary. Only the pairing can turn "this is an alarm call" into
"this is what a crow says about a dog".
"""

import sqlite3

import pytest


def labelled_capture(client, recordist, uuid="cap-1", call_type="alarm call"):
    """A capture with uploaded audio and one confirmed call to hang context on."""
    # keep=True: these stand for real observations. The semantics matrix
    # filters to kept captures by default, because the corpus is mostly seeded
    # and uploaded test material.
    capture = client.post("/api/captures", json={"client_uuid": uuid, "keep": True},
                          headers=recordist.headers).get_json()
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": f"med-{uuid}"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
    label = client.post(f"/api/captures/{capture['id']}/labels",
                        json={"client_uuid": f"lab-{uuid}", "call_type": call_type,
                              "start_sec": 1.0, "end_sec": 2.0},
                        headers=recordist.headers).get_json()
    return capture, label


@pytest.fixture
def capture_and_label(client, recordist):
    return labelled_capture(client, recordist)


@pytest.fixture
def capture(capture_and_label):
    return capture_and_label[0]


def tag(client, recordist, capture, key="dog_visible", label=None, **body):
    payload = {"client_uuid": f"ctx-{key}", "key": key, **body}
    if label is not None:
        payload["label_id"] = label["id"]
    return client.post(f"/api/captures/{capture['id']}/context",
                       json=payload, headers=recordist.headers)


class TestVocabulary:
    def test_the_config_serves_situations(self, client):
        config = client.get("/api/config?locale=en").get_json()
        keys = {c["key"] for c in config["contexts"]}
        assert {"dog_visible", "human_gives_food", "stranger_passing"} <= keys

    def test_they_are_grouped(self, client):
        """The field UI shows a handful of chips at a time, not twenty."""
        config = client.get("/api/config?locale=en").get_json()
        categories = {c["category"] for c in config["contexts"]}
        assert categories == {"people", "animals", "food", "crows", "quiet"}

    def test_there_is_a_way_to_say_nothing_happened(self, client):
        # Without it the corpus only ever contains eventful recordings, and
        # every call looks like a response to something.
        config = client.get("/api/config?locale=en").get_json()
        assert any(c["key"] == "nothing_obvious" for c in config["contexts"])

    def test_situations_are_localized(self, client):
        german = client.get("/api/config?locale=de").get_json()
        dog = next(c for c in german["contexts"] if c["key"] == "dog_visible")
        assert dog["text"] == "Hund sichtbar"


class TestTagging:
    def test_a_situation_is_recorded_against_a_call(
            self, client, recordist, capture_and_label):
        capture, label = capture_and_label
        event = tag(client, recordist, capture, label=label).get_json()
        assert event["key"] == "dog_visible"
        assert event["label_id"] == label["id"]

    def test_it_takes_the_call_span(self, client, recordist, capture_and_label):
        # The situation happened when the call did; restating it would let the
        # two drift.
        capture, label = capture_and_label
        event = tag(client, recordist, capture, label=label).get_json()
        assert (event["start_sec"], event["end_sec"]) == (1.0, 2.0)

    def test_context_without_a_call_is_refused(
            self, client, recordist, capture_and_label):
        """Context has to say which call it is about.

        Tagging the capture would credit every situation to every call in it —
        one dog and one song would report that crows sing at dogs, which is the
        false conclusion this whole axis exists to avoid.
        """
        capture, _ = capture_and_label
        assert tag(client, recordist, capture).status_code == 400

    def test_a_call_from_another_capture_is_refused(self, client, recordist):
        mine, _ = labelled_capture(client, recordist, "c1")
        _, theirs = labelled_capture(client, recordist, "c2")
        assert tag(client, recordist, mine, label=theirs).status_code == 400

    def test_an_unknown_situation_is_refused(self, client, recordist, capture):
        # The value of this axis is entirely in the grouping, so free text would
        # defeat it.
        assert tag(client, recordist, capture, key="dragon").status_code == 400

    def test_a_replay_does_not_duplicate(self, client, recordist, capture_and_label):
        capture, label = capture_and_label
        first = tag(client, recordist, capture, label=label).get_json()
        again = tag(client, recordist, capture, label=label).get_json()
        assert first["id"] == again["id"]

    def test_several_situations_can_apply_to_one_call(
            self, client, recordist, capture_and_label):
        capture, label = capture_and_label
        tag(client, recordist, capture, key="dog_visible", label=label)
        tag(client, recordist, capture, key="stranger_passing", label=label)
        listed = client.get(f"/api/captures/{capture['id']}/context",
                            headers=recordist.headers).get_json()
        assert {e["key"] for e in listed} == {"dog_visible", "stranger_passing"}

    def test_it_can_be_retracted(self, client, recordist, capture_and_label):
        capture, label = capture_and_label
        event = tag(client, recordist, capture, label=label).get_json()
        assert client.delete(f"/api/context/{event['id']}",
                             headers=recordist.headers).status_code == 204

    def test_retracting_the_call_takes_its_context_with_it(
            self, client, recordist, capture_and_label):
        # A situation attached to a call nobody stands behind is not evidence.
        capture, label = capture_and_label
        tag(client, recordist, capture, label=label)
        client.delete(f"/api/labels/{label['id']}", headers=recordist.headers)
        listed = client.get(f"/api/captures/{capture['id']}/context",
                            headers=recordist.headers).get_json()
        assert listed == []

    def test_another_persons_tag_cannot_be_retracted(
            self, client, recordist, stranger, capture_and_label):
        capture, label = capture_and_label
        event = tag(client, recordist, capture, label=label).get_json()
        assert client.delete(f"/api/context/{event['id']}",
                             headers=stranger.headers).status_code == 403

    def test_it_appears_on_the_fleet_capture(
            self, client, recordist, operator, capture_and_label):
        capture, label = capture_and_label
        tag(client, recordist, capture, label=label)
        detail = client.get(f"/api/fleet/captures/{capture['id']}",
                            headers=operator.headers).get_json()
        assert [e["key"] for e in detail["context"]] == ["dog_visible"]


class TestCallContextMatrix:
    """The question the project exists to answer."""

    def test_it_pairs_calls_with_situations(self, client, recordist, operator):
        capture, label = labelled_capture(client, recordist, "c1", "alarm call")
        tag(client, recordist, capture, key="dog_visible", label=label)

        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        pair = next(p for p in matrix["pairs"] if p["context_key"] == "dog_visible")
        assert pair["call_type"] == "alarm call"
        assert pair["n"] == 1

    def test_it_counts_a_situation_across_captures(self, client, recordist, operator):
        for uuid in ("c1", "c2"):
            capture, label = labelled_capture(client, recordist, uuid, "alarm call")
            tag(client, recordist, capture, key="dog_visible", label=label)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        dog = next(c for c in matrix["contexts"] if c["key"] == "dog_visible")
        assert dog["captures"] == 2

    def test_a_call_with_no_context_is_flagged(
            self, client, recordist, operator, capture_and_label):
        # The sound is read, the meaning is not — the work queue.
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        assert matrix["contexts_awaiting_labels"] == 1
        assert matrix["pairs"] == []

    def test_one_situation_does_not_taint_every_call_in_the_capture(
            self, client, recordist, operator):
        """The reason context hangs off a call rather than a recording.

        A dog appears, the crow alarms, and later it sings. Crediting the whole
        capture would report that crows sing at dogs.
        """
        capture, alarm = labelled_capture(client, recordist, "c1", "alarm call")
        song = client.post(f"/api/captures/{capture['id']}/labels",
                           json={"client_uuid": "lab-song", "call_type": "song",
                                 "start_sec": 40.0, "end_sec": 42.0},
                           headers=recordist.headers).get_json()
        tag(client, recordist, capture, key="dog_visible", label=alarm)
        tag(client, recordist, capture, key="nothing_obvious", label=song)

        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        paired = {(p["context_key"], p["call_type"]) for p in matrix["pairs"]}
        assert paired == {("dog_visible", "alarm call"),
                          ("nothing_obvious", "song")}

    def test_model_detections_do_not_count(self, client, recordist, operator, db_path):
        """Human labels only.

        Counting the model's own guesses would let its bias decide what a
        context sounds like, which is circular in exactly the direction that
        matters.
        """
        capture, label = labelled_capture(client, recordist, "c1")
        tag(client, recordist, capture, key="dog_visible", label=label)
        with sqlite3.connect(db_path) as conn:
            job = conn.execute(
                "INSERT INTO analysis_jobs (capture_id, media_id, state, created_at) "
                "VALUES (?, 1, 'done', '2026-07-01T00:00:00Z')", (capture["id"],))
            result = conn.execute(
                "INSERT INTO analysis_results (job_id, capture_id, model_version, "
                "created_at) VALUES (?, ?, 'test', '2026-07-01T00:00:00Z')",
                (job.lastrowid, capture["id"]))
            conn.execute(
                "INSERT INTO detected_calls (analysis_id, start_sec, end_sec, species, "
                "call_type, confidence) VALUES (?, 0, 1, 'American Crow', 'song', 0.9)",
                (result.lastrowid,))

        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        # Only the human label pairs; the model's own guess contributes nothing.
        assert {p["call_type"] for p in matrix["pairs"]} == {"alarm call"}

    def test_test_material_is_excluded_by_default(
            self, client, recordist, operator):
        """The corpus is mostly seeded clips and repeated test uploads.

        A matrix over all of it describes the pipeline, not any crow. Only
        captures the recordist marked real are counted unless asked otherwise.
        """
        capture, label = labelled_capture(client, recordist, "c1", "song")
        client.patch(f"/api/captures/{capture['id']}", json={"keep": False},
                     headers=recordist.headers)
        tag(client, recordist, capture, key="dog_visible", label=label)

        default = client.get("/api/fleet/semantics",
                             headers=operator.headers).get_json()
        assert default["pairs"] == []
        assert default["kept_only"] is True

        everything = client.get("/api/fleet/semantics?all=1",
                                headers=operator.headers).get_json()
        assert len(everything["pairs"]) == 1
        assert everything["kept_only"] is False

    def test_a_contributor_cannot_read_it(self, client, recordist):
        assert client.get("/api/fleet/semantics",
                          headers=recordist.headers).status_code == 403


class TestDashboardUpload:
    """The browser's upload path.

    Deliberately the same create/slot/chunk endpoints the phone uses, so test
    material exercises real ingest rather than a convenience back door — which
    means this test is also a test of the phone's path.
    """

    def test_a_multi_chunk_upload_completes(self, client, operator):
        capture = client.post("/api/captures",
                              json={"client_uuid": "up-1", "name": "test clip",
                                    "notes": "uploaded from the dashboard"},
                              headers=operator.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "up-1-media", "kind": "audio",
                                  "format": "wav"},
                            headers=operator.headers).get_json()

        payload = bytes(range(256)) * 40  # 10240 bytes
        chunk = 4096
        for offset in range(0, len(payload), chunk):
            end = min(offset + chunk, len(payload))
            result = client.put(
                f"/api/media/{media['id']}", data=payload[offset:end],
                headers={**operator.headers,
                         "Content-Range": f"bytes {offset}-{end - 1}/{len(payload)}"},
            ).get_json()
        assert result["upload_state"] == "complete"
        assert result["bytes"] == len(payload)

    def test_uploads_land_under_the_uploader(self, client, operator, recordist):
        # Dashboard test material must stay separable from field recordings
        # rather than quietly joining someone's corpus.
        client.post("/api/captures", json={"client_uuid": "up-1", "name": "test"},
                    headers=operator.headers)
        mine = client.get("/api/captures", headers=recordist.headers).get_json()
        assert [c["client_uuid"] for c in mine] == []

    def test_a_video_upload_is_stored_as_video(self, client, operator):
        capture = client.post("/api/captures", json={"client_uuid": "up-2"},
                              headers=operator.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "up-2-media", "kind": "video",
                                  "format": "mp4"},
                            headers=operator.headers).get_json()
        assert media["kind"] == "video"

    def test_a_video_only_capture_can_still_be_analyzed(self, client, operator):
        """The analyzer decodes with ffmpeg, so an mp4's audio track is readable.

        This asserted a 409 at first, pinning the assumption that video carries
        nothing to analyze. That is true of *phone* video — the camera films
        muted so the separate WAV stays pristine — and false of a clip dropped
        in from anywhere else, which is exactly what this upload path is for. A
        dropped video sat at "uploaded" forever with nothing to say why.
        """
        capture = client.post("/api/captures", json={"client_uuid": "up-3"},
                              headers=operator.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "up-3-media", "kind": "video",
                                  "format": "mp4"},
                            headers=operator.headers).get_json()
        client.put(f"/api/media/{media['id']}", data=b"xyz",
                   headers={**operator.headers, "Content-Range": "bytes 0-2/3"})
        response = client.post(f"/api/captures/{capture['id']}/analyze",
                               headers=operator.headers)
        assert response.status_code == 202

    def test_audio_still_wins_when_a_capture_has_both(self, client, operator):
        # A phone capture carries both, and the WAV is the pristine signal the
        # model was trained on — the video's compressed track must never be
        # picked over it.
        capture = client.post("/api/captures", json={"client_uuid": "up-4"},
                              headers=operator.headers).get_json()
        for kind, fmt in (("audio", "wav"), ("video", "mp4")):
            media = client.post(f"/api/captures/{capture['id']}/media",
                                json={"client_uuid": f"up-4-{kind}", "kind": kind,
                                      "format": fmt},
                                headers=operator.headers).get_json()
            client.put(f"/api/media/{media['id']}", data=b"xyz",
                       headers={**operator.headers, "Content-Range": "bytes 0-2/3"})
            if kind == "audio":
                audio_id = media["id"]
        job = client.post(f"/api/captures/{capture['id']}/analyze",
                          headers=operator.headers).get_json()
        assert job["media_id"] == audio_id


class TestVideoPlayback:
    """A video-only capture has to be playable, not just analyzable.

    The dashboard showed "No fully-uploaded audio" for one — the analysis had
    run and found calls, but nothing rendered, which reads as a failed upload
    rather than a display bug.
    """

    def uploaded(self, client, operator, kind="video", fmt="mp4"):
        capture = client.post("/api/captures", json={"client_uuid": f"vid-{kind}"},
                              headers=operator.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": f"vid-{kind}-m", "kind": kind,
                                  "format": fmt},
                            headers=operator.headers).get_json()
        client.put(f"/api/media/{media['id']}", data=b"xyz",
                   headers={**operator.headers, "Content-Range": "bytes 0-2/3"})
        return capture, media

    def test_video_is_served_as_video(self, client, operator):
        # Serving an mp4 as audio/mp4 makes the browser refuse to render it.
        _, media = self.uploaded(client, operator)
        response = client.get(f"/api/media/{media['id']}/raw", headers=operator.headers)
        assert response.mimetype == "video/mp4"

    def test_audio_is_still_served_as_audio(self, client, operator):
        _, media = self.uploaded(client, operator, kind="audio", fmt="wav")
        response = client.get(f"/api/media/{media['id']}/raw", headers=operator.headers)
        assert response.mimetype == "audio/wav"


class TestVocabularyIsServerDriven:
    """Noticing a recurring situation in the field must not need an app release.

    The whole reason the vocabulary is served rather than shipped. A phone asks
    with `since=<version>`, so a change that does not publish a new version is a
    change no recordist ever sees — which is the failure mode worth pinning.
    """

    def test_a_situation_can_be_added_at_runtime(self, client, db_path):
        from fieldserver.stores.config_store import ConfigStore

        before = client.get("/api/config?locale=en").get_json()
        ConfigStore(db_path).add_context("feeder_refilled", "people", "Feeder refilled")

        after = client.get("/api/config?locale=en").get_json()
        added = next(c for c in after["contexts"] if c["key"] == "feeder_refilled")
        assert added["text"] == "Feeder refilled"
        assert added["category"] == "people"
        assert after["version"] > before["version"]

    def test_a_phone_holding_the_old_version_is_told_to_refetch(self, client, db_path):
        from fieldserver.stores.config_store import ConfigStore

        held = client.get("/api/config?locale=en").get_json()["version"]
        # Nothing changed yet: the phone's copy is current.
        assert client.get(f"/api/config?since={held}").status_code == 304

        ConfigStore(db_path).add_context("feeder_refilled", "people", "Feeder refilled")
        assert client.get(f"/api/config?since={held}").status_code == 200

    def test_the_new_situation_can_be_tagged_immediately(
            self, client, db_path, recordist):
        from fieldserver.stores.config_store import ConfigStore

        ConfigStore(db_path).add_context("feeder_refilled", "people", "Feeder refilled")
        capture, label = labelled_capture(client, recordist, "c1")
        response = tag(client, recordist, capture, key="feeder_refilled", label=label)
        assert response.status_code == 201

    def test_retiring_keeps_what_was_already_tagged(self, client, db_path, recordist):
        """A situation nobody offers any more is still evidence about the past."""
        from fieldserver.stores.config_store import ConfigStore

        capture, label = labelled_capture(client, recordist, "c1")
        tag(client, recordist, capture, key="dog_visible", label=label)
        ConfigStore(db_path).retire_context("dog_visible")

        offered = {c["key"] for c in client.get("/api/config").get_json()["contexts"]}
        assert "dog_visible" not in offered
        still_there = client.get(f"/api/captures/{capture['id']}/context",
                                 headers=recordist.headers).get_json()
        assert [e["key"] for e in still_there] == ["dog_visible"]

    def test_categories_describe_rather_than_interpret(self, client):
        """"Human walks through" under `threat` answered the question the corpus
        exists to ask — and got it wrong for a recordist the birds know."""
        config = client.get("/api/config?locale=en").get_json()
        categories = {c["category"] for c in config["contexts"]}
        assert categories == {"people", "animals", "food", "crows", "quiet"}
        assert "threat" not in categories

    def test_what_the_world_did_and_what_the_birds_did_are_separable(self, client):
        # "nothing obvious" meant "nothing happened" in one recording and "the
        # crows didn't move" in the next, because there was only one slot.
        config = client.get("/api/config?locale=en").get_json()
        by_key = {c["key"]: c["category"] for c in config["contexts"]}
        assert by_key["crows_still"] == "crows"
        assert by_key["nothing_obvious"] == "quiet"


class TestMobbingIsNotAContextTag:
    """`mobbing_together` went for the rule the vocabulary states for itself.

    It named the conclusion. `raptor_overhead` + `group_gathers` +
    `crows_agitated` record the event it was drawn from, and recording those lets
    the co-occurrence say it was mobbing — which is the whole reason the two axes
    exist. Recording "mobbing" instead answers the question the corpus is asking,
    the same way "human walks through" under `threat` did.

    Retired while nothing had been tagged with it, so unlike `several_birds`
    there is no evidence to preserve. The distinction worth protecting is that
    `mobbing` survives as a *call type*: experiments/0012 measured it as a real
    acoustic class (0.838 one-vs-rest, holding at 0.726 against alert with the
    recording held constant), so it is a claim about a sound and belongs on that
    axis.
    """

    def test_the_served_vocabulary_does_not_offer_it(self, client):
        served = client.get("/api/config?locale=en").get_json()
        assert "mobbing_together" not in {c["key"] for c in served["contexts"]}

    def test_tagging_a_call_with_it_is_refused(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-m"},
                              headers=recordist.headers).get_json()
        answer = client.post(f"/api/captures/{capture['id']}/context",
                             json={"key": "mobbing_together", "start_sec": 1},
                             headers=recordist.headers)
        assert answer.status_code == 400

    def test_the_descriptive_pieces_it_was_drawn_from_are_all_still_offered(
            self, client):
        # Retiring the conclusion only works if the observations survive. If one
        # of these ever goes, mobbing stops being recordable at all rather than
        # being recordable in parts.
        served = {c["key"] for c in client.get(
            "/api/config?locale=en").get_json()["contexts"]}
        assert {"raptor_overhead", "group_gathers", "crows_agitated"} <= served

    def test_mobbing_is_still_offered_as_a_call_type(self, client):
        # The other axis, and a real acoustic class. Retiring the context tag
        # must not take the call type with it — it is the only route by which mob
        # ground truth can ever reach the corpus.
        served = client.get("/api/config?locale=en").get_json()
        by_key = {label["key"]: label for label in served["labels"]}
        assert by_key["mobbing"]["core"] == "alarm call"
        assert by_key["mobbing"]["trains"] is True


class TestSpeciesIsNotAveraged:
    """Two species' calls must never land in the same cell.

    A contributor in Germany records hooded crows; the corpus here is American
    Crows. "Alarm call" is a different vocalisation in each, and pooling them
    produces a finding about neither bird — the same failure as tagging context
    to a capture, arriving through the taxonomy instead.
    """

    def test_the_matrix_keys_on_species(self, client, recordist, operator):
        american, american_label = labelled_capture(client, recordist, uuid="us-1",
                                                    call_type="alarm call")
        hooded, _ = labelled_capture(client, recordist, uuid="de-1",
                                     call_type="alarm call")
        # The German contributor's capture, same call type, different bird.
        with_species = client.post(f"/api/captures/{hooded['id']}/labels",
                                   json={"client_uuid": "lab-de-2",
                                         "call_type": "alarm call",
                                         "species": "Hooded Crow",
                                         "start_sec": 5.0, "end_sec": 6.0},
                                   headers=recordist.headers).get_json()
        client.post(f"/api/captures/{hooded['id']}/context",
                    json={"key": "dog_visible", "label_id": with_species["id"],
                          "client_uuid": "ctx-de"},
                    headers=recordist.headers)
        client.post(f"/api/captures/{american['id']}/context",
                    json={"key": "dog_visible", "label_id": american_label["id"],
                          "client_uuid": "ctx-us"},
                    headers=recordist.headers)

        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        pairs = [p for p in matrix["pairs"] if p["context_key"] == "dog_visible"]
        species = {p["species"] for p in pairs}
        assert species == {"American Crow", "Hooded Crow"}, (
            "one cell per species — pooling them describes neither bird")

    def test_each_species_keeps_its_own_count(self, client, recordist, operator):
        american, label = labelled_capture(client, recordist, uuid="us-2",
                                           call_type="alarm call")
        client.post(f"/api/captures/{american['id']}/context",
                    json={"key": "dog_visible", "label_id": label["id"],
                          "client_uuid": "ctx-1"},
                    headers=recordist.headers)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        row = next(p for p in matrix["pairs"] if p["context_key"] == "dog_visible")
        assert row["n"] == 1
        assert row["species"] == "American Crow"


class TestRetiringATag:
    """`several_birds` went when group composition arrived.

    A head count on the capture says the same thing and says how many, so the
    tag could only ever agree redundantly or disagree. What matters is that
    retiring it does not touch the two events already tagged with it: a human
    watched several crows and wrote it down, and that is evidence rather than a
    mistake to be corrected.
    """

    def test_the_served_vocabulary_does_not_include_it(self, client):
        served = client.get("/api/config?locale=en").get_json()
        assert "several_birds" not in {c["key"] for c in served["contexts"]}

    def test_tagging_a_call_with_it_is_refused(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-r"},
                              headers=recordist.headers).get_json()
        answer = client.post(f"/api/captures/{capture['id']}/context",
                             json={"key": "several_birds", "start_sec": 1},
                             headers=recordist.headers)
        assert answer.status_code == 400

    def test_events_recorded_before_it_went_still_exist(self, client, recordist,
                                                        db_path):
        # Written straight to the table, because the API now refuses the key —
        # which is the situation on the live server: two rows, tagged when the
        # tag was still offered.
        import sqlite3
        capture = client.post("/api/captures", json={"client_uuid": "cap-s"},
                              headers=recordist.headers).get_json()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO context_events (capture_id, contributor_id, key, "
                "start_sec, created_at) VALUES (?, ?, 'several_birds', 2.0, "
                "'2026-07-01T00:00:00Z')",
                (capture["id"], recordist.contributor["id"]))

        rows = client.get(f"/api/captures/{capture['id']}/context",
                          headers=recordist.headers).get_json()

        assert [r["key"] for r in rows] == ["several_birds"]
