"""One rate limit per host, shared across processes through a file."""

import json

from corvidcrawler.politeness import DEFAULT_POLICY, POLICIES, Bucket, policy_for


class Sleeps:
    def __init__(self):
        self.slept = []

    def __call__(self, seconds):
        self.slept.append(seconds)


def bucket(root, sleeper=None):
    return Bucket(root=root, sleeper=sleeper or (lambda _s: None))


def test_every_policy_says_why_its_number_is_what_it_is():
    for host, policy in POLICIES.items():
        assert policy["note"], host


def test_an_unknown_host_gets_the_slowest_setting():
    assert policy_for("https://example.invalid/x")["per_minute"] == DEFAULT_POLICY["per_minute"]


def test_a_subdomain_inherits_its_parent_policy():
    assert policy_for("https://www.xeno-canto.org/x")["host"] == "www.xeno-canto.org"
    assert policy_for("https://www.xeno-canto.org/x")["per_minute"] == POLICIES["xeno-canto.org"]["per_minute"]


def test_requests_under_the_limit_never_wait(tmp_path):
    assert [bucket(tmp_path).wait("https://xeno-canto.org/x") for _ in range(5)] == [0.0] * 5


def test_the_limit_is_shared_between_two_processes(tmp_path):
    allowed = policy_for("https://xeno-canto.org/x")["per_minute"]
    first = bucket(tmp_path)
    for _ in range(allowed):
        first.wait("https://xeno-canto.org/x")
    sleeps = Sleeps()

    waited = bucket(tmp_path, sleeps).wait("https://xeno-canto.org/x")

    assert sleeps.slept and waited > 0


def test_one_host_does_not_spend_anothers_budget(tmp_path):
    allowed = policy_for("https://xeno-canto.org/x")["per_minute"]
    first = bucket(tmp_path)
    for _ in range(allowed):
        first.wait("https://xeno-canto.org/x")
    sleeps = Sleeps()

    bucket(tmp_path, sleeps).wait("https://search.macaulaylibrary.org/x")

    assert not sleeps.slept


def test_a_corrupt_file_does_not_stop_a_crawl(tmp_path):
    path = tmp_path / "cache" / "limits" / "xeno-canto.org.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json at all")

    assert bucket(tmp_path).wait("https://xeno-canto.org/x") == 0.0


def test_the_file_does_not_grow_without_bound(tmp_path):
    b = bucket(tmp_path)
    for _ in range(400):
        b.wait("https://xeno-canto.org/x")

    stored = json.loads((tmp_path / "cache" / "limits" / "xeno-canto.org.json").read_text())
    assert len(stored["times"]) <= POLICIES["xeno-canto.org"]["per_minute"] * 2


def test_the_default_root_is_the_data_dir(isolated_data_dir):
    b = Bucket(sleeper=lambda _s: None)
    b.wait("https://xeno-canto.org/x")

    assert (isolated_data_dir / "cache" / "limits" / "xeno-canto.org.json").exists()
