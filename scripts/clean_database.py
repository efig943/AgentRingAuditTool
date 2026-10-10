"""
Database Cleanup Script for Production Supabase PostgreSQL.
Preserves ONLY the two active accounts and their active phone numbers:
  1. Ethan Figueredo (ethan.figueredo943@gmail.com, Tenant ID: 1, Phone: +19498768809)
  2. Jim Lahey (randy@yahoo.com, Tenant ID: 184, Phone: +16267799551)

Performs Option 2 cleanup:
1. Backs up all records to scripts/backups/ before deletion.
2. Purges the 11 inactive test tenants and their dummy profiles & users.
3. Purges the 5 mock development calls (IDs: 30, 31, 32, 82, 83 with invalid phone numbers/durations).
4. Links the 3 candidate leads to their corresponding appointments (IDs: 35->61, 80->66, 99->67).
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
MOCK_CALL_IDS = (30, 31, 32, 82, 83)

def default_json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

def run_cleanup(dry_run=True):
    print("=" * 65)
    print(f"DATABASE CLEANUP (OPTION 2) - {'DRY RUN' if dry_run else 'EXECUTING LIVE'}")
    print(f"Target retained tenants: {RETAINED_TENANT_IDS}")
    print("=" * 65)

    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = False  # Explicit transaction
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        # Step 1: Gather backup data
        backup_data = {}

        # A. Test tenant accounts and children
        for table in ["users", "tenant_profiles", "agent_configs", "tenants"]:
            id_col = "id" if table == "tenants" else "tenant_id"
            cur.execute(f"SELECT * FROM \"{table}\" WHERE \"{id_col}\" NOT IN %s;", (RETAINED_TENANT_IDS,))
            rows = [dict(r) for r in cur.fetchall()]
            backup_data[table] = rows
            print(f"Identified {len(rows)} records in '{table}' to be deleted.")

        # B. Mock calls
        cur.execute("SELECT * FROM call_logs WHERE id IN %s;", (MOCK_CALL_IDS,))
        mock_calls = [dict(r) for r in cur.fetchall()]
        backup_data["call_logs_mock"] = mock_calls
        print(f"Identified {len(mock_calls)} mock development calls to be deleted: {MOCK_CALL_IDS}")

        # Verification of retained data
        for table in ["leads", "appointments", "phone_numbers", "tenant_integrations"]:
            cur.execute(f"SELECT count(*) FROM \"{table}\" WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            count = cur.fetchone()[0]
            print(f"Verification: '{table}' has {count} rows outside retained tenants (expected 0).")

        total_rows_to_delete = sum(len(v) for v in backup_data.values())

        if not dry_run:
            # Step 2: Save complete backup to scripts/backups/
            backup_dir = Path(__file__).resolve().parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = backup_dir / f"backup_deleted_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, default=default_json_serializer, indent=2)
            print(f"\n[BACKUP] Saved backup of all {total_rows_to_delete} records to: {backup_file}")

            # Step 3: Delete child records first
            print("\n[PURGING] Deleting orphan child records...")
            cur.execute("DELETE FROM agent_configs WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            print(f" - Deleted {cur.rowcount} rows from agent_configs")

            cur.execute("DELETE FROM tenant_profiles WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            print(f" - Deleted {cur.rowcount} rows from tenant_profiles")

            cur.execute("DELETE FROM users WHERE tenant_id NOT IN %s;", (RETAINED_TENANT_IDS,))
            print(f" - Deleted {cur.rowcount} rows from users")

            # Step 4: Delete mock calls
            cur.execute("DELETE FROM call_logs WHERE id IN %s;", (MOCK_CALL_IDS,))
            print(f" - Deleted {cur.rowcount} mock calls from call_logs")

            # Step 5: Delete parent test tenants
            cur.execute("DELETE FROM tenants WHERE id NOT IN %s;", (RETAINED_TENANT_IDS,))
            print(f" - Deleted {cur.rowcount} test tenants from tenants")

            # Step 6: Link candidate leads to appointments
            print("\n[LINKING] Reconciling unlinked candidate appointments...")
            cur.execute("UPDATE appointments SET lead_id = 61 WHERE id = 35 AND lead_id IS NULL;")
            print(f" - Linked Appointment #35 -> Lead #61 (rows: {cur.rowcount})")
            cur.execute("UPDATE appointments SET lead_id = 66 WHERE id = 80 AND lead_id IS NULL;")
            print(f" - Linked Appointment #80 -> Lead #66 (rows: {cur.rowcount})")
            cur.execute("UPDATE appointments SET lead_id = 67 WHERE id = 99 AND lead_id IS NULL;")
            print(f" - Linked Appointment #99 -> Lead #67 (rows: {cur.rowcount})")

            # Commit transaction
            conn.commit()
            print("\n[SUCCESS] Transaction committed successfully! Production database cleaned and reconciled.")

        else:
            print(f"\n[DRY RUN COMPLETE] Total records identified for deletion: {total_rows_to_delete}. Zero records modified.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Transaction rolled back due to error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    run_cleanup(dry_run=not is_live)
