"""
Read the shoot date out of documents that were ingested before we looked for it.

The date was always written on the paperwork -- the daily production report's
header, the Thumbnail Report's volume stamp, the script report headers. What
was missing was anything reading it, so documents already on the spine carry no
`shoot_date` claim and the department sync matrix has no baseline to measure
from.

This is a backfill, not a repair. It appends the claim each document was always
making; it does not alter a single stored row. Documents that state no date get
nothing, because a document that does not say what day it covers has not said
it.

    python scripts/backfill_shoot_dates.py            # show what would be added
    python scripts/backfill_shoot_dates.py --apply    # append the claims

Run `scripts/rebuild_mirror.py --apply` afterwards to carry them to ClickHouse.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from backend.app.normalizers.shoot_days import extract_shoot_date  # noqa: E402
from backend.app.spine import event_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="append the claims; without it nothing is written")
    ap.add_argument("--db-path", default=os.environ.get("CINESPINE_DB_PATH", "spine.db"))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    # Documents that already produced a claim are left alone. The spine is
    # append-only, so running this twice would otherwise state the same fact
    # twice and every count of it would double.
    already = {
        row["doc_id"] for row in conn.execute(
            "SELECT DISTINCT doc_id FROM spine_events WHERE entity_type = 'shoot_date'"
        ) if row["doc_id"]
    }

    documents = conn.execute(
        "SELECT doc_id, production_id, shoot_day, filename, doc_type, department, content"
        " FROM source_documents ORDER BY filename"
    ).fetchall()

    planned, silent, skipped = [], [], 0
    for doc in documents:
        if doc["doc_id"] in already:
            skipped += 1
            continue
        found = extract_shoot_date(doc["content"] or "", doc["filename"] or "")
        if not found:
            silent.append(doc["filename"])
            continue
        planned.append((doc, found))

    print(f"documents        : {len(documents)}")
    print(f"already claimed  : {skipped}")
    print(f"state no date    : {len(silent)}")
    for name in silent:
        print(f"                   {name}")
    print(f"claims to append : {len(planned)}")
    for doc, found in planned:
        print(f"                   day {doc['shoot_day']:>3}  {found['date']}  "
              f"via {found['source']:<16} {doc['filename'][:44]}")

    if not args.apply:
        print("\nNothing written. Re-run with --apply.")
        return 0

    for doc, found in planned:
        event_store.append_event({
            "event_id": doc["doc_id"],
            "production_id": doc["production_id"],
            "shoot_day": doc["shoot_day"],
            # The axis the document itself is on. A date is a claim by whoever
            # filed the paperwork, not a fact of a separate kind.
            "axis": "intent" if doc["department"] == "office" else "belief",
            "department": doc["department"],
            "doc_type": doc["doc_type"],
            "entity_type": "shoot_date",
            "payload": {
                "date": found["date"],
                "source": found["source"],
                "stated_shoot_day": found.get("shoot_day"),
                "filename": doc["filename"],
            },
            "metadata": {"doc_id": doc["doc_id"], "backfilled": True},
            "doc_id": doc["doc_id"],
        })

    print(f"\nAppended {len(planned)} shoot-date claims.")
    print("Run scripts/rebuild_mirror.py --apply to carry them to ClickHouse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
