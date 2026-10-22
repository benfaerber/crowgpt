"""The species-tree crawl: the manifest `make train` reads, written as the
crawl runs, with each archive replacing only its own records."""

import json

import pytest

from corvidcrawler.species import MACAULAY_STAMP, XENO_STAMP, SpeciesCrawl, load_manifest_module


class FakeSource:
    def __init__(self, recs, total=None):
        self.recs = recs
        self.total = len(recs) if total is None else total

    def count(self, query):
        return self.total

    def fetch(self, query, max_recordings, should_stop=None, refresh=False, **_):
        yield from self.recs[:max_recordings]


class FakeDownloader:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def fetch(self, url, dest, on_bytes=None):
        self.calls.append(url)
        if url in self.fail:
            return False
        dest.write_bytes(b"ID3 audio")
        if on_bytes:
            on_bytes(9, 9)
        return True


class QuietReport:
    def __init__(self):
        self.updates, self.notes = [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, fetched, downloaded, total=None, detail=""):
        self.updates.append((fetched, downloaded, total))

    def in_flight(self, done, total):
        pass

    def note(self, line):
        self.notes.append(line)


def xc(rid, **overrides):
    return {"source": "xeno_canto", "source_ref": str(rid), "species": "Carrion Crow",
            "call_type": "call", "quality": "A", "recordist": "A Recordist",
            "date": "2020-05-01", "location": "Somewhere",
            "audio_url": f"https://x/{rid}.mp3", **overrides}


@pytest.fixture
def manifest():
    return load_manifest_module()


def crawl(tmp_path, manifest, recs, source_id="xeno_canto", **kwargs):
    return SpeciesCrawl(
        source_id, gen="Corvus", sp="corone", slug="carrion-crow", data=tmp_path,
        manifest=manifest, downloader=FakeDownloader(kwargs.pop("fail", ())),
        source=FakeSource(recs), report=QuietReport(), **kwargs)


def test_it_writes_audio_and_a_manifest_make_train_can_read(tmp_path, manifest):
    job = crawl(tmp_path, manifest, [xc(1), xc(2)])

    summary = job.run()

    assert summary["downloaded"] == 2
    written = json.loads((tmp_path / "species" / "carrion-crow" / "manifest.json").read_text())
    assert written["slug"] == "carrion-crow"
    assert [r["id"] for r in written["recordings"]] == ["1", "2"]
    assert all(r["source"] == XENO_STAMP for r in written["recordings"])
    assert (tmp_path / "species" / "carrion-crow" / "audio" / "1.mp3").exists()


def test_a_record_carries_what_a_grouped_split_needs(tmp_path, manifest):
    crawl(tmp_path, manifest, [xc(1)]).run()

    row = json.loads((tmp_path / "species" / "carrion-crow" / "manifest.json").read_text())["recordings"][0]
    assert (row["recordist"], row["date"], row["locality"]) == ("A Recordist", "2020-05-01", "Somewhere")


def test_a_file_already_on_disk_is_not_refetched(tmp_path, manifest):
    crawl(tmp_path, manifest, [xc(1)]).run()

    summary = crawl(tmp_path, manifest, [xc(1)]).run()

    assert summary == {**summary, "downloaded": 0, "on_disk": 1}


def test_a_failed_download_is_counted_and_left_out_of_the_manifest(tmp_path, manifest):
    summary = crawl(tmp_path, manifest, [xc(1), xc(2)], fail={"https://x/2.mp3"}).run()

    assert summary["failed"] == 1
    written = json.loads((tmp_path / "species" / "carrion-crow" / "manifest.json").read_text())
    assert [r["id"] for r in written["recordings"]] == ["1"]


def test_the_manifest_is_flushed_as_the_crawl_runs(tmp_path, manifest):
    seen = []
    job = crawl(tmp_path, manifest, [xc(i) for i in range(1, 6)], flush_every=2)
    original = job._flush

    def spy(records):
        seen.append(len(records))
        return original(records)

    job._flush = spy
    job.run()

    assert seen == [2, 4, 5]


def test_one_archive_leaves_the_others_records_alone(tmp_path, manifest):
    crawl(tmp_path, manifest, [xc(1)]).run()
    ml = [{**xc("ML9", species="Carrion Crow"), "source": "macaulay",
           "audio_url": "https://ml/ML9/mp3"}]

    crawl(tmp_path, manifest, ml, source_id="macaulay", taxon="carcro1").run()
    again = crawl(tmp_path, manifest, [xc(2)]).run()

    written = json.loads((tmp_path / "species" / "carrion-crow" / "manifest.json").read_text())
    by_source = {r["source"] for r in written["recordings"]}
    assert by_source == {XENO_STAMP, MACAULAY_STAMP}
    assert sorted(r["id"] for r in written["recordings"]) == ["2", "ML9"]
    assert again["from_other_sources"] == 1


def test_field_records_survive_a_recrawl(tmp_path, manifest):
    path = tmp_path / "species" / "carrion-crow" / "manifest.json"
    manifest.write(path, [manifest.record("field-1", "/media/field/abc.wav", manifest.FIELD)])

    crawl(tmp_path, manifest, [xc(1)]).run()

    assert "field-1" in {r["id"] for r in json.loads(path.read_text())["recordings"]}


def test_macaulay_needs_a_taxon_it_can_resolve(tmp_path, manifest):
    from corvidcrawler.macaulay import MacaulayError

    with pytest.raises(MacaulayError, match="--taxon"):
        SpeciesCrawl("macaulay", slug="mystery-bird", data=tmp_path, manifest=manifest,
                     source=FakeSource([]), report=QuietReport())


def test_the_progress_file_lands_in_the_shared_directory(tmp_path, manifest, monkeypatch):
    progress = tmp_path / "progress"
    monkeypatch.setenv("PROGRESS_DIR", str(progress))
    job = SpeciesCrawl("xeno_canto", gen="Corvus", sp="corone", data=tmp_path, manifest=manifest,
                       downloader=FakeDownloader(), source=FakeSource([xc(1)]))
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    job.run()

    payload = json.loads((progress / "corvidcrawler-carrion-crow-from-xeno-canto.json").read_text())
    assert payload["finished"] and not payload["failed"]
    assert payload["stages"][0]["done"] == 1
