"""
Rebuild the analytical mirror from the spine.

The mirror is derived. SQLite is the source of truth, ClickHouse is a copy kept
for the questions a column store answers well, and nothing is lost by throwing
the copy away and making it again. That is the property this script rests on,
and it is worth stating because it is what makes wiping safe.

Why it exists rather than being done by hand once: the mirror has already drifted
twice in one day. It held 5355 rows of test fixtures, because a suite run with
CLICKHOUSE_HOST set wrote into the same database a demo reads from -- fixed since,
by pointing tests at `cinespine_test`. And it held 84 rows under a slate nobody
wrote, from a parser defect corrected after those rows were already mirrored. A
mirror that cannot be rebuilt on demand accumulates both kinds of wrong.

    python scripts/rebuild_mirror.py            # show what would change
    python scripts/rebuild_mirror.py --apply    # wipe and rebuild

Reads CLICKHOUSE_HOST / PORT / USER / PASSWORD / SECURE / DATABASE from the
environment, the same as the app.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.spine import clickhouse as ch  # noqa: E402
from backend.app.spine.schema import schema_ddl  # noqa: E402
from backend.app.spine.writer import _clickhouse_datetime  # noqa: E402

# Tables with a durable SQLite source, and the query that reproduces them.
# takes_meta and audit_discrepancies are not here: they are indexes written as
# documents are ingested and discrepancies computed, so they refill through use
# rather than from a table.
SOURCES = {
    "production_events": {
        "sql": """
            SELECT event_id, production_id, shoot_day, axis, department, doc_type,
                   entity_type, payload, metadata, timestamp
            FROM spine_events ORDER BY seq
        """,
        "columns": ["event_id", "production_id", "shoot_day", "axis", "department",
                    "doc_type", "entity_type", "payload_json", "metadata_json", "created_at"],
        "uuid_first": True,
    },
    "editorial_tag_events": {
        "sql": """
            SELECT event_id, production_id, target_type, target_id, action,
                   coalesce(status,''), coalesce(needs,'[]'), coalesce(descriptors,'[]'),
                   coalesce(note,''), coalesce(actor,''), created_at
            FROM editorial_tag_events ORDER BY rowid
        """,
        "columns": ["event_id", "production_id", "target_type", "target_id", "action",
                    "status", "needs_json", "descriptors_json", "note", "actor", "created_at"],
        "uuid_first": False,
    },
    "requirement_events": {
        "sql": """
            SELECT event_id, requirement_id, production_id, action,
                   coalesce(status,''), coalesce(priority,''), coalesce(assigned_to,''),
                   coalesce(changes,'{}'), coalesce(note,''), coalesce(actor,''), created_at
            FROM requirement_events ORDER BY rowid
        """,
        "columns": ["event_id", "requirement_id", "production_id", "action", "status",
                    "priority", "assigned_to", "changes_json", "note", "actor", "created_at"],
        "uuid_first": False,
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually wipe and rebuild; without it nothing is written")
    ap.add_argument("--db-path", default=os.environ.get("CINESPINE_DB_PATH", "spine.db"))
    args = ap.parse_args()

    client = ch.connect()
    if client is None:
        print("No ClickHouse connection. Set CLICKHOUSE_HOST (and CLICKHOUSE_PASSWORD).")
        return 1

    db = ch.database()
    print(f"mirror   : {db} on {os.environ.get('CLICKHOUSE_HOST')}")
    print(f"spine    : {args.db_path}")

    if db != ch.DEFAULT_DATABASE:
        # Rebuilding `cinespine_test` from the real spine would put production
        # rows into the database the suite treats as disposable. Almost
        # certainly a mistake, so say so rather than doing it.
        print(f"\nRefusing: CLICKHOUSE_DATABASE is {db!r}, not {ch.DEFAULT_DATABASE!r}.")
        print("Unset it to rebuild the mirror the app reads from.")
        return 1

    sqlite_conn = sqlite3.connect(args.db_path)

    plan = []
    for table, spec in SOURCES.items():
        rows = sqlite_conn.execute(spec["sql"]).fetchall()
        before = client.query(f"SELECT count() FROM {db}.{table}").result_rows[0][0]
        plan.append((table, before, len(rows), rows, spec))
        print(f"  {table:22s} {before:6d} in mirror  ->  {len(rows):6d} from the spine")

    for table in ("takes_meta", "audit_discrepancies"):
        before = client.query(f"SELECT count() FROM {db}.{table}").result_rows[0][0]
        print(f"  {table:22s} {before:6d} in mirror  ->  emptied; refills through use")

    if not args.apply:
        print("\nNothing written. Re-run with --apply.")
        return 0

    for statement in schema_ddl(db).split(";"):
        if statement.strip():
            client.command(statement)

    for table in list(SOURCES) + ["takes_meta", "audit_discrepancies"]:
        client.command(f"TRUNCATE TABLE IF EXISTS {db}.{table}")

    for table, _, _, rows, spec in plan:
        if not rows:
            continue
        payload = []
        for row in rows:
            values = list(row)
            if spec["uuid_first"]:
                # production_events keys on a UUID; SQLite holds it as text.
                values[0] = str(values[0])
            # SQLite keeps timestamps as ISO strings and the driver wants a
            # datetime. `_clickhouse_datetime` is the app's own conversion, and
            # using it rather than a second one here means the rebuilt rows
            # carry exactly the times the live path would have written -- it
            # already carries the fix for naive datetimes landing an hour out.
            values[-1] = _clickhouse_datetime(values[-1])
            payload.append(values)
        client.insert(f"{db}.{table}", payload, column_names=spec["columns"])
        print(f"  wrote {len(payload):6d} into {table}")

    print("\nRebuilt. Counts now:")
    for table in list(SOURCES) + ["takes_meta", "audit_discrepancies"]:
        n = client.query(f"SELECT count() FROM {db}.{table}").result_rows[0][0]
        print(f"  {table:22s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
