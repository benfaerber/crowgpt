"""The on-box admin commands — the only code here that deletes rows for good.

These commands run over the database directly, with being on the machine as
the authorization. They had no tests at all, which meant the two destructive
ones — prune and merge — were also the two least-watched.
"""

import argparse
import importlib.util
from pathlib import Path

import pytest

ADMIN_PY = Path(__file__).resolve().parents[1] / "tools" / "admin.py"
spec = importlib.util.spec_from_file_location("admin_cli", ADMIN_PY)
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


@pytest.fixture(autouse=True)
def admin_env(monkeypatch, db_path):
    """Point the CLI at this test's database, the way FIELD_DB does on the box."""
    monkeypatch.setenv("FIELD_DB", str(db_path))


def args(**kw):
    return argparse.Namespace(**kw)


class TestPrune:
    def test_a_contributor_holding_a_capture_survives(
            self, client, recordist, stranger):
        client.post("/api/captures", json={"client_uuid": "keep-me"},
                    headers=recordist.headers)

        assert admin.cmd_prune(args(apply=True, shells=False)) == 0

        remaining = {c["id"] for c in admin.ContributorStore(admin.db_path()).list_all()}
        assert recordist.contributor["id"] in remaining
        assert stranger.contributor["id"] not in remaining

    def test_a_dry_run_deletes_nobody(self, client, recordist, stranger):
        admin.cmd_prune(args(apply=False, shells=False))
        remaining = {c["id"] for c in admin.ContributorStore(admin.db_path()).list_all()}
        assert stranger.contributor["id"] in remaining


class TestMerge:
    def merge(self, keep, absorb, apply=False, dedupe=False):
        return admin.cmd_merge(args(keep=keep, absorb=str(absorb),
                                    apply=apply, dedupe=dedupe))

    def test_the_dry_run_counts_every_table_the_merge_will_move(
            self, recordist, stranger, capsys):
        # The counts and the merge used to read different lists, so the dry
        # run promised less than --apply did — and both missed the tables
        # whose foreign keys made the merge fail outright.
        assert self.merge(recordist.contributor["id"],
                          stranger.contributor["id"]) == 0
        shown = capsys.readouterr().out
        for table in admin.MERGE_TABLES:
            assert table in shown, table

    def test_the_dry_run_changes_nothing(self, recordist, stranger, capsys):
        self.merge(recordist.contributor["id"], stranger.contributor["id"])
        remaining = {c["id"] for c in admin.ContributorStore(admin.db_path()).list_all()}
        assert stranger.contributor["id"] in remaining

    def test_a_shared_client_uuid_is_refused_without_dedupe(
            self, client, recordist, stranger, capsys):
        # The same recording synced under two identities is the very thing
        # merge exists to undo — silently keeping both would collide the
        # idempotency key the moment they share an owner.
        for who in (recordist, stranger):
            client.post("/api/captures", json={"client_uuid": "same-recording"},
                        headers=who.headers)

        assert self.merge(recordist.contributor["id"],
                          stranger.contributor["id"], apply=True) == 1

        remaining = {c["id"] for c in admin.ContributorStore(admin.db_path()).list_all()}
        assert stranger.contributor["id"] in remaining
