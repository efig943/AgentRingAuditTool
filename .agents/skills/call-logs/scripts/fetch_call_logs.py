#!/usr/bin/env python3
"""
fetch_call_logs.py - CLI tool to inspect and extract Voice AI call logs and correlated DB records.
Part of the 'call-logs' skill for CallAudit Pro.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
# Find project root by looking for .env or pyproject/git
current_path = Path(__file__).resolve()
PROJECT_ROOT = None
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "audits.db").exists():
        PROJECT_ROOT = parent
        break
if not PROJECT_ROOT:
    PROJECT_ROOT = current_path.parents[4]

sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_DB_PATH = PROJECT_ROOT / "audits.db"

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment or .env file.")
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)

def get_audited_call_ids() -> List[int]:
    """Retrieve already audited call IDs from local SQLite."""
    if not SQLITE_DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT call_id FROM audits")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids
    except Exception:
        return []

def fetch_correlated_records(conn, call_sid: Optional[str], caller_phone: str, call_time: Optional[datetime]) -> Dict[str, Any]:
    """Fetch appointments and leads correlated with this call."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    appts = []
    leads = []

    # 1. Appointments
    if call_sid:
        cur.execute("""
            SELECT id, caller_name, caller_phone, start_time, end_time, duration_minutes, 
                   status, service_address, title, summary, notes, call_sid, metadata_json, created_at
            FROM appointments
            WHERE call_sid = %s
            ORDER BY created_at DESC
        """, (call_sid,))
        appts = [dict(r) for r in cur.fetchall()]

    if not appts and caller_phone and call_time:
        t_start = call_time - timedelta(minutes=15)
        t_end = call_time + timedelta(minutes=15)
        cur.execute("""
            SELECT id, caller_name, caller_phone, start_time, end_time, duration_minutes, 
                   status, service_address, title, summary, notes, call_sid, metadata_json, created_at
            FROM appointments
            WHERE caller_phone = %s AND created_at >= %s AND created_at <= %s
            ORDER BY created_at DESC
        """, (caller_phone, t_start, t_end))
        appts = [dict(r) for r in cur.fetchall()]

    # 2. Leads
    if call_sid:
        cur.execute("""
            SELECT id, caller_phone, parsed_data, created_at
            FROM leads
            WHERE caller_phone = %s AND (
                parsed_data->>'_call_sid' = %s 
                OR (created_at >= %s AND created_at <= %s)
            )
            ORDER BY created_at DESC
        """, (caller_phone, call_sid, (call_time or datetime.now()) - timedelta(minutes=10), (call_time or datetime.now()) + timedelta(minutes=10)))
        leads = [dict(r) for r in cur.fetchall()]
    elif caller_phone and call_time:
        cur.execute("""
            SELECT id, caller_phone, parsed_data, created_at
            FROM leads
            WHERE caller_phone = %s AND created_at >= %s AND created_at <= %s
            ORDER BY created_at DESC
        """, (caller_phone, call_time - timedelta(minutes=15), call_time + timedelta(minutes=15)))
        leads = [dict(r) for r in cur.fetchall()]

    # Format datetimes
    for a in appts:
        for k, v in a.items():
            if isinstance(v, datetime):
                a[k] = v.isoformat()
    for l in leads:
        for k, v in l.items():
            if isinstance(v, datetime):
                l[k] = v.isoformat()

    return {"appointments": appts, "leads": leads}

def parse_transcript(raw_transcript: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_transcript, str):
        try:
            return json.loads(raw_transcript)
        except Exception:
            return []
    elif isinstance(raw_transcript, list):
        return raw_transcript
    return []

def fetch_single_call(call_id: Optional[int] = None, call_sid: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if call_id:
            cur.execute("""
                SELECT id, tenant_id, caller_phone, status, duration_seconds, created_at, call_sid, recording_url, transcript
                FROM call_logs WHERE id = %s
            """, (call_id,))
        elif call_sid:
            cur.execute("""
                SELECT id, tenant_id, caller_phone, status, duration_seconds, created_at, call_sid, recording_url, transcript
                FROM call_logs WHERE call_sid = %s
            """, (call_sid,))
        else:
            return None

        r = cur.fetchone()
        if not r:
            return None

        transcript = parse_transcript(r["transcript"])
        created_at = r["created_at"]
        correlated = fetch_correlated_records(conn, r["call_sid"], r["caller_phone"] or "", created_at)

        return {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "caller_phone": r["caller_phone"],
            "status": r["status"] or "completed",
            "duration_seconds": r["duration_seconds"] or 0,
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
            "call_sid": r["call_sid"],
            "recording_url": r["recording_url"],
            "transcript_turns_count": len(transcript),
            "transcript": transcript,
            "correlated_database_records": correlated
        }
    finally:
        conn.close()

def fetch_calls_list(
    limit: int = 50,
    unaudited_only: bool = False,
    since_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = """
            SELECT id, tenant_id, caller_phone, status, duration_seconds, created_at, call_sid, recording_url, transcript
            FROM call_logs WHERE 1=1
        """
        params = []
        if since_date:
            query += " AND created_at >= %s"
            params.append(since_date)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit * 2 if unaudited_only else limit)

        cur.execute(query, params)
        rows = cur.fetchall()

        audited_ids = set(get_audited_call_ids()) if unaudited_only else set()

        calls = []
        for r in rows:
            if unaudited_only and r["id"] in audited_ids:
                continue

            transcript = parse_transcript(r["transcript"])
            created_at = r["created_at"]
            calls.append({
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "caller_phone": r["caller_phone"],
                "status": r["status"] or "completed",
                "duration_seconds": r["duration_seconds"] or 0,
                "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
                "call_sid": r["call_sid"],
                "transcript_turns_count": len(transcript),
                "audited": r["id"] in audited_ids if not unaudited_only else False
            })

            if unaudited_only and len(calls) >= limit:
                break

        return calls
    finally:
        conn.close()

def format_summary_text(call_data: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"=== CALL #{call_data['id']} (SID: {call_data['call_sid']}) ===")
    lines.append(f"Caller Phone: {call_data.get('caller_phone')} | Duration: {call_data.get('duration_seconds')}s | Status: {call_data.get('status')}")
    lines.append(f"Timestamp:    {call_data.get('created_at')}")
    lines.append("")
    lines.append("--- CORRELATED DATABASE RECORDS ---")
    corr = call_data.get("correlated_database_records", {})
    appts = corr.get("appointments", [])
    leads = corr.get("leads", [])
    lines.append(f"Appointments ({len(appts)}):")
    for a in appts:
        lines.append(f"  - ID {a.get('id')}: {a.get('caller_name')} on {a.get('start_time')} (Status: {a.get('status')}, Addr: {a.get('service_address')})")
    if not appts:
        lines.append("  (None recorded)")
    lines.append(f"Leads ({len(leads)}):")
    for l in leads:
        lines.append(f"  - ID {l.get('id')}: {json.dumps(l.get('parsed_data'))}")
    if not leads:
        lines.append("  (None recorded)")

    lines.append("")
    lines.append("--- TRANSCRIPT ---")
    transcript = call_data.get("transcript", [])
    for idx, turn in enumerate(transcript, 1):
        role = turn.get("role", "unknown").upper()
        text = turn.get("text") or turn.get("message") or turn.get("content") or ""
        lines.append(f"[{idx}] {role}: {text}")

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Call Logs Inspector Tool")
    parser.add_argument("--call-id", type=int, help="Fetch details for a specific call ID")
    parser.add_argument("--call-sid", type=str, help="Fetch details for a specific Call SID")
    parser.add_argument("--limit", type=int, default=10, help="Max calls to return (default: 10)")
    parser.add_argument("--unaudited", action="store_true", help="Filter only unaudited calls")
    parser.add_argument("--since", type=str, help="ISO 8601 start date (e.g. 2026-10-01T00:00:00Z)")
    parser.add_argument("--format", choices=["json", "summary", "list"], default="json", help="Output format")

    args = parser.parse_args()

    try:
        if args.call_id or args.call_sid:
            call = fetch_single_call(call_id=args.call_id, call_sid=args.call_sid)
            if not call:
                print(json.dumps({"error": f"Call not found for ID={args.call_id} SID={args.call_sid}"}, indent=2), file=sys.stderr)
                sys.exit(1)
            
            if args.format == "summary":
                print(format_summary_text(call))
            else:
                print(json.dumps(call, indent=2))
        else:
            calls = fetch_calls_list(limit=args.limit, unaudited_only=args.unaudited, since_date=args.since)
            if args.format == "list":
                print(f"Retrieved {len(calls)} calls:")
                for c in calls:
                    print(f"ID: {c['id']:<4} | SID: {c['call_sid']} | Phone: {c['caller_phone']:<15} | Dur: {c['duration_seconds']:>3}s | Turns: {c['transcript_turns_count']:>2} | Time: {c['created_at']}")
            else:
                print(json.dumps({"total": len(calls), "calls": calls}, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
