"""Raptor co-detections and American Crow `rattle` labels round-trip cleanly."""

from fieldserver.stores.analysis import AnalysisStore


def _make_capture(client, recordist, uuid="cap-raptor"):
    capture = client.post(
        "/api/captures",
        json={"client_uuid": uuid, "keep": True},
        headers=recordist.headers,
    ).get_json()
    media = client.post(
        f"/api/captures/{capture['id']}/media",
        json={"client_uuid": f"med-{uuid}"},
        headers=recordist.headers,
    ).get_json()
    client.put(
        f"/api/media/{media['id']}",
        data=b"xyz",
        headers={**recordist.headers, "Content-Range": "bytes 0-2/3"},
    )
    return capture, media


def test_co_detections_and_rattle_round_trip(client, operator, recordist, db_path):
    capture, media = _make_capture(client, recordist)
    store = AnalysisStore(db_path)
    job = store.enqueue(capture["id"], media["id"])
    store.complete(
        job["id"],
        capture_id=capture["id"],
        duration=21.0,
        waveform=[0.2, 0.8],
        reliability={"American Crow": {"rattle": {"label": "reliable", "level": "good", "auc": 0.97}}},
        model_version="birdnet/2.4+hp300 heads:american-crow@test",
        calls=[
            {
                "start": 3.0,
                "end": 6.0,
                "species": "American Crow",
                "scientific_name": "Corvus brachyrhynchos",
                "call_type": "rattle",
                "confidence": 0.91,
                "crow_conf": 0.96,
                "candidate": False,
                "multi_label": True,
                "alternates": [],
            },
        ],
        co_detections=[
            {
                "species": "Cooper's Hawk",
                "scientific_name": "Accipiter cooperii",
                "confidence": 0.742,
                "start": 9.0,
                "end": 12.0,
            },
        ],
    )

    latest = store.latest_calls_for_capture(capture["id"])
    assert latest["calls"][0]["call_type"] == "rattle"
    assert latest["co_detections"] == [
        {
            "species": "Cooper's Hawk",
            "scientific_name": "Accipiter cooperii",
            "confidence": 0.742,
            "start": 9.0,
            "end": 12.0,
        },
    ]

    # Operator capture detail also receives co_detections via latest_calls_for_capture.
    detail = client.get(
        f"/api/fleet/captures/{capture['id']}",
        headers=operator.headers,
    ).get_json()
    assert detail["analysis"]["co_detections"][0]["species"] == "Cooper's Hawk"


def test_legacy_rows_without_co_detections_decode_to_empty_list(client, recordist, db_path):
    capture, media = _make_capture(client, recordist, uuid="cap-legacy")
    store = AnalysisStore(db_path)
    job = store.enqueue(capture["id"], media["id"])
    store.complete(
        job["id"],
        capture_id=capture["id"],
        duration=6.0,
        waveform=[],
        reliability={},
        model_version="legacy",
        calls=[],
    )
    assert store.latest_calls_for_capture(capture["id"])["co_detections"] == []
