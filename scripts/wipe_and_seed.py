"""
CineSpine Database Wipe & Seed Utility.

Performs a clean factory reset across:
1. SQLite (spine.db): completely wipes all domain tables and seeds baseline defaults.
2. ClickHouse: truncates all analytical mirror tables.

Usage:
    python scripts/wipe_and_seed.py           # Wipe and re-seed baseline defaults
    python scripts/wipe_and_seed.py --no-seed # Wipe everything without seeding
"""
import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.app.spine.writer import SpineWriter


def main():
    parser = argparse.ArgumentParser(description="Wipe and seed CineSpine databases.")
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Wipe all tables without re-seeding default demo productions and screenplay",
    )
    args = parser.parse_args()

    print("==========================================")
    print("  CineSpine Database Factory Reset & Seed")
    print("==========================================")

    writer = SpineWriter()
    result = writer.wipe_all(seed=not args.no_seed)

    print(f"[*] Status: {result['status']}")
    print(f"[*] Message: {result['message']}")
    print(f"[*] SQLite Tables Cleared: {', '.join(result['sqlite_tables'])}")
    print(f"[*] ClickHouse Tables Cleared: {', '.join(result['clickhouse_tables'])}")
    if result.get("seeded"):
        print(f"[+] Baseline Seeding:")
        print(f"    - Productions: {result['seeded']['productions']}")
        print(f"    - Team Users: {result['seeded']['users']}")
        print(f"    - Screenplay: {result['seeded']['screenplay']}")
    print("\n[OK] Factory reset finished.\n")


if __name__ == "__main__":
    main()
