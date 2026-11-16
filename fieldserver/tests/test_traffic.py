"""crowgpt.org traffic: the classifier, the daily summary, the worker's
schedule of what is final, and the operator-only route. Cloudflare is faked."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from fieldserver.core.traffic import BEACON, Classifier, Kind, Request, Summary
from fieldserver.stores.traffic import TrafficStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
import traffic_worker  # noqa: E402

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0"


def req(path, ip="203.0.113.7", kind=Kind.BROWSER, count=1, status=200, country="United States", agent=BROWSER_UA):
    return Request(count, BROWSER_UA, path, country, status, ip, kind, agent)


class TestClassifier:
    classify = staticmethod(Classifier().classify)

    def test_a_claimed_assistant_hunting_files_is_a_probe(self):
        assert self.classify("Mozilla/5.0 ChatGPT-User/1.0", "/docker-compose.dev.yml", 404)[0] is Kind.PROBE

    def test_a_refused_assistant_is_a_probe_whatever_the_path(self):
        assert self.classify("Mozilla/5.0 Claude-User/1.0", "/nothing-here", 404)[0] is Kind.PROBE

    def test_a_redirected_assistant_is_a_probe(self):
        assert self.classify("Mozilla/5.0 ChatGPT-User/1.0", "/z9x8c7v6b5-debug-trigger", 301)[0] is Kind.PROBE

    def test_an_assistant_reading_a_page_is_an_assistant(self):
        assert self.classify("Mozilla/5.0 ChatGPT-User/1.0", "/crowgpt", 200) == (Kind.ASSISTANT, "ChatGPT")

    def test_a_browser_reading_a_page_is_a_browser(self):
        assert self.classify(BROWSER_UA, "/scan", 200)[0] is Kind.BROWSER

    def test_secret_hunting_is_a_probe(self):
        assert self.classify(BROWSER_UA, "/.env", 404)[0] is Kind.PROBE


class TestSummary:
    def test_views_and_visitors_come_from_the_beacon_and_no_ip_survives(self):
        summary = Summary([
            req(BEACON, count=3), req(BEACON, ip="198.51.100.2", country="Sri Lanka"),
            req("/", count=5), req("/assets/app.js", count=9),
            req("/.env", kind=Kind.PROBE, status=404),
        ]).as_dict()
        assert summary["views"] == 4
        assert summary["visitors"] == 2
        assert summary["countries"] == {"United States": 1, "Sri Lanka": 1}
        assert summary["pages"] == {"/": 5}
        assert summary["probes"] == {"/.env": 1}
        assert "203.0.113.7" not in repr(summary)


class FakeCloudflare:
    asked: list = []

    def __init__(self, token):
        pass

    def summary(self, day):
        FakeCloudflare.asked.append(day)
        return {"views": day.day}


class FakeToken:
    def read(self):
        return "token"


class TestWorker:
    @pytest.fixture
    def collector(self, db_path, monkeypatch):
        FakeCloudflare.asked = []
        monkeypatch.setattr(traffic_worker, "Cloudflare", FakeCloudflare)
        return traffic_worker.TrafficCollector(TrafficStore(db_path), FakeToken())

    def test_the_window_is_pulled_and_only_settled_days_are_final(self, collector):
        collector.collect(datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc))
        days = {row["day"]: row["final"] for row in collector.store.since(date(2026, 11, 1))}
        assert len(days) == 8
        assert days["2026-11-14"] is True
        assert days["2026-11-15"] is False
        assert days["2026-11-16"] is False

    def test_a_final_day_is_not_pulled_again(self, collector):
        collector.collect(datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc))
        FakeCloudflare.asked = []
        collector.collect(datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc))
        assert FakeCloudflare.asked == [date(2026, 11, 16)]


class TestRoute:
    def test_operators_read_the_days(self, client, operator, db_path):
        today = datetime.now(timezone.utc).date()
        TrafficStore(db_path).save(today, {"views": 7}, final=False)
        body = client.get("/api/traffic?days=7", headers=operator.headers).get_json()
        assert [d["summary"] for d in body["days"]] == [{"views": 7}]
        assert body["last_fetched"]

    def test_a_phone_cannot(self, client, recordist):
        assert client.get("/api/traffic", headers=recordist.headers).status_code == 403
