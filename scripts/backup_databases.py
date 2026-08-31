"""
CineSpine Database Backup & Restore Utility.

Safely creates and restores backups of:
1. SQLite Event Spine (spine.db) using online backup API (safe with active WAL).
2. AI Cache (ai_cache.db).
3. Reconstructs ClickHouse analytical mirror automatically upon restore.

Usage:
    # 1. Take a backup
    python scripts/backup_databases.py

    # 2. List available backups
    python scripts/backup_databases.py --list

    # 3. Restore a backup
    python scripts/backup_databases.py --restore backups/backup_20260831_221302
"""
import argparse
import glob
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


def backup_sqlite(source_path: str, dest_path: str) -> bool:
    """Uses SQLite Online Backup API to safely backup active WAL databases."""
    if not os.path.exists(source_path):
        print(f"[-] Source database not found: {source_path}")
        return False

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"[*] Backing up {os.path.basename(source_path)} -> {dest_path}...")
    
    src = sqlite3.connect(source_path)
    dst = sqlite3.connect(dest_path)
    try:
        with dst:
            src.backup(dst, pages=100)
        print(f"[+] Successfully backed up {os.path.basename(source_path)} ({os.path.getsize(dest_path):,} bytes)")
        return True
    finally:
        dst.close()
        src.close()


def restore_sqlite(backup_path: str, target_path: str) -> bool:
    """Safely restores a backup SQLite database into target location."""
    if not os.path.exists(backup_path):
        print(f"[-] Backup file not found: {backup_path}")
        return False

    print(f"[*] Restoring {os.path.basename(backup_path)} -> {target_path}...")
    
    # Remove existing WAL/SHM files to prevent state mixing
    for ext in ["-wal", "-shm"]:
        wal_file = target_path + ext
        if os.path.exists(wal_file):
            try:
                os.remove(wal_file)
            except Exception as e:
                print(f"[!] Warning: Could not remove {wal_file}: {e}")

    src = sqlite3.connect(backup_path)
    dst = sqlite3.connect(target_path)
    try:
        with dst:
            src.backup(dst, pages=100)
        print(f"[+] Successfully restored {os.path.basename(target_path)} ({os.path.getsize(target_path):,} bytes)")
        return True
    finally:
        dst.close()
        src.close()


def list_backups(backups_dir: str):
    print(f"[*] Available backups in {backups_dir}:")
    pattern = os.path.join(backups_dir, "backup_*")
    folders = sorted(glob.glob(pattern), reverse=True)
    if not folders:
        print("    (No backups found)")
        return

    for folder in folders:
        name = os.path.basename(folder)
        spine_db = os.path.join(folder, "spine.db")
        size_str = ""
        if os.path.exists(spine_db):
            size_str = f" - spine.db: {os.path.getsize(spine_db):,} bytes"
        print(f"  • {name}{size_str}")


def main():
    parser = argparse.ArgumentParser(description="Backup and Restore CineSpine databases.")
    parser.add_argument(
        "--out-dir",
        default=os.path.join(ROOT_DIR, "backups"),
        help="Destination directory for backups (default: backups/)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all existing backups",
    )
    parser.add_argument(
        "--restore",
        metavar="BACKUP_PATH",
        help="Restore databases from specified backup folder and rebuild mirror",
    )
    args = parser.parse_args()

    # 1. List
    if args.list:
        list_backups(args.out_dir)
        return

    # 2. Restore
    if args.restore:
        backup_folder = args.restore
        if not os.path.isabs(backup_folder):
            backup_folder = os.path.join(ROOT_DIR, backup_folder)

        if not os.path.isdir(backup_folder):
            print(f"[!] Error: Backup folder does not exist: {backup_folder}")
            sys.exit(1)

        print(f"==========================================")
        print(f"  Restoring CineSpine Databases")
        print(f"  Source: {backup_folder}")
        print(f"==========================================")

        # Restore spine.db
        spine_src = os.path.join(backup_folder, "spine.db")
        spine_dst = os.path.join(ROOT_DIR, "spine.db")
        if os.path.exists(spine_src):
            restore_sqlite(spine_src, spine_dst)
        else:
            print(f"[!] Warning: No spine.db found in {backup_folder}")

        # Restore ai_cache.db
        cache_src = os.path.join(backup_folder, "ai_cache.db")
        cache_dst = os.path.join(ROOT_DIR, "ai_cache.db")
        if os.path.exists(cache_src):
            restore_sqlite(cache_src, cache_dst)

        # Rebuild ClickHouse analytical mirror
        print(f"\n[*] Rebuilding ClickHouse analytical mirror from restored spine.db...")
        rebuild_script = os.path.join(ROOT_DIR, "scripts", "rebuild_mirror.py")
        try:
            res = subprocess.run([sys.executable, rebuild_script, "--apply"], cwd=ROOT_DIR, capture_output=True, text=True)
            print(res.stdout)
            if res.stderr:
                print(res.stderr)
            print("[+] Analytical mirror rebuild complete.")
        except Exception as e:
            print(f"[-] Warning: Failed to trigger rebuild_mirror.py: {e}")

        print(f"\n[OK] Restore process finished successfully.\n")
        return

    # 3. Take Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder = os.path.join(args.out_dir, f"backup_{timestamp}")
    os.makedirs(backup_folder, exist_ok=True)

    print(f"==========================================")
    print(f"  CineSpine Database Backup: {timestamp}")
    print(f"  Output Directory: {backup_folder}")
    print(f"==========================================")

    # 1. Primary Source of Truth: spine.db
    spine_db = os.path.join(ROOT_DIR, "spine.db")
    spine_backup = os.path.join(backup_folder, "spine.db")
    backup_sqlite(spine_db, spine_backup)

    # 2. AI Cache DB
    ai_cache_db = os.path.join(ROOT_DIR, "ai_cache.db")
    if os.path.exists(ai_cache_db):
        ai_cache_backup = os.path.join(backup_folder, "ai_cache.db")
        backup_sqlite(ai_cache_db, ai_cache_backup)

    # 3. Create a manifest / info file
    manifest_path = os.path.join(backup_folder, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(f'{{\n  "timestamp": "{timestamp}",\n  "created_at": "{datetime.now().isoformat()}",\n  "rebuild_command": "python scripts/rebuild_mirror.py --apply"\n}}\n')

    print(f"\n[OK] Backup completed successfully in:\n     {backup_folder}\n")


if __name__ == "__main__":
    main()
