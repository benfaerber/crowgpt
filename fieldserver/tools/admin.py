#!/usr/bin/env python3
"""Contributor administration, on the box, over the database directly.

The operations here — promoting an admin, merging two people into one — are the
ones that should never be reachable over the network. There is no TLS, the
secrets are shared strings, and a route that mints administrators is a route that
gives the fleet away. Being on the machine with the file *is* the authorization.

    uv run python tools/admin.py list
    uv run python tools/admin.py devices
    uv run python tools/admin.py rename 3 "Ben"
    uv run python tools/admin.py name-device 4 "Pixel 10"
    uv run python tools/admin.py grant 3 admin
    uv run python tools/admin.py merge 3 --absorb 1,4,8,9,10 [--apply]
    uv run python tools/admin.py contexts
    uv run python tools/admin.py add-context feeder_refilled people "Feeder refilled"
    uv run python tools/admin.py retire-context squirrel

`merge` prints what it would do and changes nothing until you pass --apply.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fieldserver.app import DEFAULT_DB  # noqa: E402
from fieldserver.stores.contributors import ROLES, ContributorStore  # noqa: E402
from fieldserver.stores.devices import DeviceStore  # noqa: E402

# The dry run must count exactly what merge() will move, so the list is the
# store's rather than a copy. Three hand-maintained copies of it disagreed,
# and the two tables missing from this one were the two whose foreign keys
# made every real merge fail.
MERGE_TABLES = ContributorStore.REFERENCING_TABLES


def db_path() -> Path:
    return Path(os.environ.get("FIELD_DB") or DEFAULT_DB)


def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(args) -> int:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ct.id, ct.display_name, ct.role, ct.status,
                   (SELECT COUNT(*) FROM devices d WHERE d.contributor_id = ct.id)
                       AS devices,
                   (SELECT COUNT(*) FROM captures c WHERE c.contributor_id = ct.id)
                       AS captures
            FROM contributors ct ORDER BY captures DESC, ct.id
            """).fetchall()
    if not rows:
        print("no contributors — start the server once to run the migration")
        return 1
    print(f"{'id':>4}  {'name':<24} {'role':<12} {'status':<10} {'devices':>7} {'captures':>8}")
    for r in rows:
        print(f"{r['id']:>4}  {r['display_name']:<24} {r['role']:<12} "
              f"{r['status']:<10} {r['devices']:>7} {r['captures']:>8}")
    return 0


def cmd_devices(args) -> int:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.label, d.platform, d.contributor_id, d.revoked_at,
                   ct.display_name,
                   (SELECT COUNT(*) FROM captures c WHERE c.device_id = d.id) AS captures
            FROM devices d LEFT JOIN contributors ct ON ct.id = d.contributor_id
            ORDER BY d.contributor_id, d.id
            """).fetchall()
    print(f"{'id':>4}  {'label':<22} {'platform':<9} {'owner':<22} {'captures':>8}")
    for r in rows:
        label = r["label"] or "—"
        if r["revoked_at"]:
            label += " (revoked)"
        print(f"{r['id']:>4}  {label:<22} {(r['platform'] or '—'):<9} "
              f"{(r['display_name'] or '?'):<22} {r['captures']:>8}")
    return 0


def cmd_rename(args) -> int:
    store = ContributorStore(db_path())
    if not store.get(args.contributor_id):
        print(f"no contributor {args.contributor_id}", file=sys.stderr)
        return 1
    print(store.rename(args.contributor_id, args.name))
    return 0


def cmd_name_device(args) -> int:
    store = DeviceStore(db_path())
    if not store.get(args.device_id):
        print(f"no device {args.device_id}", file=sys.stderr)
        return 1
    device = store.rename(args.device_id, args.label)
    print(f"device {device['id']} is now {device['label']!r}")
    return 0


def cmd_grant(args) -> int:
    store = ContributorStore(db_path())
    if not store.get(args.contributor_id):
        print(f"no contributor {args.contributor_id}", file=sys.stderr)
        return 1
    try:
        print(store.set_role(args.contributor_id, args.role))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def cmd_contexts(args) -> int:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT cd.key, cd.category, cd.active,
                   (SELECT text FROM translations t WHERE t.namespace='context'
                     AND t.key=cd.key AND t.locale='en') AS text,
                   (SELECT COUNT(*) FROM context_events ce WHERE ce.key=cd.key) AS used
            FROM context_defs cd ORDER BY cd.category, cd.sort_order
            """).fetchall()
        version = conn.execute("SELECT MAX(version) FROM config_versions").fetchone()[0]
    print(f"config v{version}")
    print(f"{'category':<10} {'key':<20} {'shown as':<28} {'used':>5}")
    for r in rows:
        flag = "" if r["active"] else "  (retired)"
        print(f"{r['category']:<10} {r['key']:<20} {str(r['text']):<28} {r['used']:>5}{flag}")
    return 0


def cmd_add_context(args) -> int:
    """Publishing is the point: phones only re-fetch when the version moves."""
    from fieldserver.stores.config_store import ConfigStore

    version = ConfigStore(db_path()).add_context(args.key, args.category, args.text)
    print(f"added '{args.key}' to {args.category} — published as config v{version}")
    print("phones pick it up on their next config fetch (app start).")
    return 0


def cmd_retire_context(args) -> int:
    from fieldserver.stores.config_store import ConfigStore

    version = ConfigStore(db_path()).retire_context(args.key)
    print(f"retired '{args.key}' — published as config v{version}")
    print("already-tagged rows keep it; it is just no longer offered.")
    return 0


def cmd_merge(args) -> int:
    absorb = [int(x) for x in args.absorb.split(",") if x.strip()]
    store = ContributorStore(db_path())
    keeper = store.get(args.keep)
    if not keeper:
        print(f"no contributor {args.keep} to merge into", file=sys.stderr)
        return 1

    with connect() as conn:
        placeholders = ",".join("?" * len(absorb))
        totals = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE contributor_id IN ({placeholders})",
                absorb).fetchone()[0]
            for table in MERGE_TABLES
        }
        # Idempotency keys are scoped per contributor, so merging can collide
        # where the separate owners could not. Refusing here beats a half-applied
        # merge that dies partway through the UPDATE.
        clashes = conn.execute(
            f"""
            SELECT client_uuid, COUNT(*) AS n FROM captures
             WHERE contributor_id IN ({placeholders},?) AND client_uuid IS NOT NULL
             GROUP BY client_uuid HAVING n > 1
            """, (*absorb, args.keep)).fetchall()

    print(f"merge into #{args.keep} ({keeper['display_name']}) from {absorb}:")
    for table, n in totals.items():
        print(f"  {table:<14} {n:>5}")

    if clashes and not args.dedupe:
        print(f"\nrefusing: {len(clashes)} capture client_uuid(s) appear on both sides.",
              file=sys.stderr)
        print("Those are the same recording synced twice under two identities — the "
              "very thing\nthis merge exists to undo. Re-run with --dedupe to keep the "
              "first copy of each\nand release the uuid on the rest (no rows are "
              "deleted).", file=sys.stderr)
        return 1

    superseded = _superseded_captures(absorb, args.keep) if clashes else []
    if superseded:
        print(f"\n--dedupe will release client_uuid on {len(superseded)} superseded "
              f"capture(s): {superseded}")
        print("  (rows and media are left intact — delete them yourself once happy)")

    if not args.apply:
        print("\ndry run — pass --apply to write")
        return 0

    if superseded:
        placeholders = ",".join("?" * len(superseded))
        with connect() as conn:
            conn.execute(
                f"UPDATE captures SET client_uuid = NULL WHERE id IN ({placeholders})",
                superseded)

    result = store.merge(args.keep, absorb)
    print(f"\nmoved {result['moved']}; deleted contributors {result['absorbed']}")
    return 0


def cmd_prune(args) -> int:
    """Delete contributors that hold nothing.

    Test probes, abandoned enrollments and the dashboard rows that the old
    sign-in minted one-per-visit. Deliberately refuses to touch anyone with a
    capture or a label to their name: emptiness is the safety property, so
    "prune" can never mean "lose a recording".
    """
    # A capture that never received a byte and carries no note is a smoke-test
    # artifact, not a recording. `--shells` widens "holds nothing" to include
    # them, because api.rest leaves a few behind every time it is run.
    holds_a_capture = (
        """EXISTS (SELECT 1 FROM captures c WHERE c.contributor_id = ct.id
                    AND (c.notes IS NOT NULL
                         OR (SELECT COALESCE(SUM(m.bytes), 0) FROM media m
                              WHERE m.capture_id = c.id) > 0))"""
        if args.shells else
        "EXISTS (SELECT 1 FROM captures c WHERE c.contributor_id = ct.id)"
    )
    with connect() as conn:
        empty = conn.execute(
            f"""
            SELECT ct.id, ct.display_name, ct.role,
                   (SELECT COUNT(*) FROM devices d WHERE d.contributor_id = ct.id) devices,
                   (SELECT COUNT(*) FROM captures c WHERE c.contributor_id = ct.id) captures
            FROM contributors ct
            WHERE NOT {holds_a_capture}
              AND NOT EXISTS (SELECT 1 FROM labels l WHERE l.contributor_id = ct.id)
              AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.contributor_id = ct.id)
              AND ct.role != 'admin'
            ORDER BY ct.id
            """).fetchall()

    if not empty:
        print("nothing to prune — every contributor holds something")
        return 0

    print(f"{'id':>4}  {'name':<24} {'role':<12} {'devices':>7} {'empty caps':>10}")
    for r in empty:
        print(f"{r['id']:>4}  {r['display_name']:<24} {r['role']:<12} "
              f"{r['devices']:>7} {r['captures']:>10}")

    if not args.apply:
        print(f"\ndry run — {len(empty)} contributor(s) and their devices; "
              "pass --apply to delete")
        return 0

    ids = [r["id"] for r in empty]
    placeholders = ",".join("?" * len(ids))
    with connect() as conn:
        # Order matters: captures cascade from devices, so the devices have to
        # go before the contributor row they hang off.
        conn.execute(f"DELETE FROM devices WHERE contributor_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM captures WHERE contributor_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM contributors WHERE id IN ({placeholders})", ids)
    print(f"\ndeleted {len(ids)} contributor(s) and their devices")
    return 0


def _superseded_captures(absorb, keep) -> list[int]:
    """The duplicate copies to release, keeping the earliest row for each uuid.

    Earliest wins because it is the one that has been on the server longest, so
    anything already pointing at a capture id — an analysis result, a label —
    points at that one.
    """
    placeholders = ",".join("?" * len(absorb))
    losers = []
    with connect() as conn:
        duplicated = conn.execute(
            f"""
            SELECT client_uuid FROM captures
             WHERE contributor_id IN ({placeholders},?) AND client_uuid IS NOT NULL
             GROUP BY client_uuid HAVING COUNT(*) > 1
            """, (*absorb, keep)).fetchall()
        for (uuid,) in duplicated:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM captures WHERE client_uuid = ? ORDER BY id", (uuid,))]
            losers.extend(ids[1:])
    return sorted(losers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="contributors and their counts").set_defaults(fn=cmd_list)
    sub.add_parser("devices", help="devices and their owners").set_defaults(fn=cmd_devices)

    p = sub.add_parser("rename", help="rename a contributor")
    p.add_argument("contributor_id", type=int)
    p.add_argument("name")
    p.set_defaults(fn=cmd_rename)

    p = sub.add_parser("name-device", help="give a device a human name")
    p.add_argument("device_id", type=int)
    p.add_argument("label")
    p.set_defaults(fn=cmd_name_device)

    p = sub.add_parser("grant", help="set a contributor's role")
    p.add_argument("contributor_id", type=int)
    p.add_argument("role", choices=ROLES)
    p.set_defaults(fn=cmd_grant)

    sub.add_parser("contexts", help="the situation vocabulary").set_defaults(fn=cmd_contexts)

    p = sub.add_parser("add-context", help="add a situation and publish it to the fleet")
    p.add_argument("key", help="stable key, e.g. feeder_refilled")
    p.add_argument("category", help="people | animals | food | crows | quiet")
    p.add_argument("text", help="what the app shows, e.g. \"Feeder refilled\"")
    p.set_defaults(fn=cmd_add_context)

    p = sub.add_parser("retire-context", help="stop offering a situation")
    p.add_argument("key")
    p.set_defaults(fn=cmd_retire_context)

    p = sub.add_parser("prune", help="delete contributors that hold nothing")
    p.add_argument("--shells", action="store_true",
                   help="also drop those whose only captures never received audio")
    p.add_argument("--apply", action="store_true", help="actually delete")
    p.set_defaults(fn=cmd_prune)

    p = sub.add_parser("merge", help="fold contributors into one person")
    p.add_argument("keep", type=int, help="the contributor to keep")
    p.add_argument("--absorb", required=True, help="comma-separated ids to fold in")
    p.add_argument("--dedupe", action="store_true",
                   help="release client_uuid on re-synced duplicate captures")
    p.add_argument("--apply", action="store_true", help="actually write")
    p.set_defaults(fn=cmd_merge)

    args = parser.parse_args()
    if not db_path().exists():
        print(f"no database at {db_path()}", file=sys.stderr)
        return 1
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
