"""
Database Cleanup Script for Production Supabase PostgreSQL.
Preserves ONLY the two active accounts and their active phone numbers:
  1. Ethan Figueredo (ethan.figueredo943@gmail.com, Tenant ID: 1, Phone: +19498768809)
  2. Jim Lahey (randy@yahoo.com, Tenant ID: 184, Phone: +16267799551)
Deletes all other test/inactive accounts and their orphan records.
Backs up all data before removal.
"""

import os
import sys
import json
from datetime import datetime, date
from pathlib import Path
import psycopg2
import psycopg2.extras

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core import config

RETAINED_TENANT_IDS = (1, 184)

def default_json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

def run_cleanup(dry_run=True):
    print("=" * 60)
    print(f"DATABASE CLEANUP - {'DRY RUN' if dry_run else 'EXECUTING LIVE'}")
    print(f"Target retained tenants: {RETAINED_TENANT_IDS}")
    print("=" * 60)

    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = False # Use explicit transaction
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        # Step 1: Backup records to be deleted
        backup_data = {}
        tables_to_clean = ["users", "tenant_profiles", "agent_configs", "tenants"]
        
        for table in tables_to_clean:
            id_col = "id" if table == "tenants" else "tenant_id"
            cur.execute(f"SELECT * FROM \"{table}\" WHERE \"{id_col}\" NOT IN %s;", (RETAINED_TENANT_IDS,))
            rows = [dict(r) for r in cur.fetchall()]
            backup_data[table] = rows
            print(f"Identified {len(rows)} records in '{table}' to be deleted.")

        # Also verify other tables have 0 rows outside the retained tenants
        for table in ["leads", "appointments", "call_logs", "phone_numbers", "tenant_integrations"]:
            cur.execute(f"SELECT count(*) FROM \"{table}\" WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            count = cur.fetchone()[0]
            print(f"Verification: '{table}' has {count} rows outside retained tenants (expected 0).")

        if not dry_run:
            # Save backup to scripts/backups/
            backup_dir = Path(__file__).resolve().parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = backup_dir / f"backup_deleted_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, default=default_json_serializer, indent=2)
            print(f"\n[BACKUP] Saved backup of all {sum(len(v) for v in backup_data.values())} rows to {backup_file}")

            # Step 2: Delete child tables first (FK dependency order)
            print("\n[PURGING] Deleting orphan child records...")
            
            cur.execute("DELETE FROM agent_configs WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            deleted_ac = cur.rowcount
            print(f" - Deleted {deleted_ac} rows from agent_configs")

            cur.execute("DELETE FROM tenant_profiles WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            deleted_tp = cur.rowcount
            print(f" - Deleted {deleted_tp} rows from tenant_profiles")

            cur.execute("DELETE FROM users WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            deleted_u = cur.rowcount
            print(f" - Deleted {deleted_u} rows from users")

            # Step 3: Delete parent tenants
            cur.execute("DELETE FROM tenants WHERE id NOT IN %s;", (RETAINED_TENANT_IDS,))
            deleted_t = cur.rowcount
            print(f" - Deleted {deleted_t} rows from tenants")

            # Commit transaction
            conn.commit()
            print("\n[SUCCESS] Transaction committed successfully!")

        else:
            print("\n[DRY RUN COMPLETE] No records were modified.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Transaction rolled back due to error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    run_cleanup(dry_run=not is_live)
