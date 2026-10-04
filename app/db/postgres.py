import psycopg2
import psycopg2.extras
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.core import config

def get_db_connection():
    """Establish connection to PostgreSQL production database."""
    conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=10)
    return conn

def fetch_calls(
    limit: int = 200,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch call logs from PostgreSQL."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = """
            SELECT 
                id, 
                tenant_id, 
                caller_phone, 
                status, 
                duration_seconds, 
                created_at, 
                call_sid, 
                recording_url,
                transcript
            FROM call_logs
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= %s"
            params.append(end_date)
        if min_id:
            query += " AND id > %s"
            params.append(min_id)
            
        if limit:
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
        else:
            query += " ORDER BY created_at DESC"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        calls = []
        for r in rows:
            transcript = r["transcript"]
            if isinstance(transcript, str):
                try:
                    transcript = json.loads(transcript)
                except Exception:
                    transcript = []
            elif transcript is None:
                transcript = []
                
            calls.append({
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "caller_phone": r["caller_phone"],
                "status": r["status"] or "completed",
                "duration_seconds": r["duration_seconds"] or 0,
                "created_at": r["created_at"],
                "call_sid": r["call_sid"],
                "recording_url": r["recording_url"],
                "transcript": transcript,
            })
        return calls
    finally:
        conn.close()

def fetch_call_by_id(call_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single call log by primary key ID."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT 
                id, 
                tenant_id, 
                caller_phone, 
                status, 
                duration_seconds, 
                created_at, 
                call_sid, 
                recording_url,
                transcript
            FROM call_logs
            WHERE id = %s
        """, (call_id,))
        r = cur.fetchone()
        if not r:
            return None
        transcript = r["transcript"]
        if isinstance(transcript, str):
            try:
                transcript = json.loads(transcript)
            except Exception:
                transcript = []
        elif transcript is None:
            transcript = []

        return {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "caller_phone": r["caller_phone"],
            "status": r["status"] or "completed",
            "duration_seconds": r["duration_seconds"] or 0,
            "created_at": r["created_at"],
            "call_sid": r["call_sid"],
            "recording_url": r["recording_url"],
            "transcript": transcript,
        }
    finally:
        conn.close()

def fetch_linked_records(call_sid: Optional[str], caller_phone: str, call_time: datetime) -> Dict[str, Any]:
    """
    Fetch appointments and leads in the database associated with this call.
    Matches either by explicit call_sid or phone number within a time window.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Fetch appointments
        appts = []
        if call_sid:
            cur.execute("""
                SELECT id, caller_name, caller_phone, start_time, end_time, duration_minutes, 
                       status, service_address, title, summary, notes, call_sid, metadata_json, created_at
                FROM appointments
                WHERE call_sid = %s
                ORDER BY created_at DESC
            """, (call_sid,))
            appts = [dict(r) for r in cur.fetchall()]
        
        # If no appointment found by call_sid, search for appointments by caller_phone near call_time
        if not appts and caller_phone and call_time:
            time_window_start = call_time - timedelta(minutes=15)
            time_window_end = call_time + timedelta(minutes=15)
            cur.execute("""
                SELECT id, caller_name, caller_phone, start_time, end_time, duration_minutes, 
                       status, service_address, title, summary, notes, call_sid, metadata_json, created_at
                FROM appointments
                WHERE caller_phone = %s AND created_at >= %s AND created_at <= %s
                ORDER BY created_at DESC
            """, (caller_phone, time_window_start, time_window_end))
            appts = [dict(r) for r in cur.fetchall()]

        # 2. Fetch leads
        leads = []
        if call_sid:
            cur.execute("""
                SELECT id, caller_phone, parsed_data, created_at
                FROM leads
                WHERE caller_phone = %s AND (
                    parsed_data->>'_call_sid' = %s 
                    OR (created_at >= %s AND created_at <= %s)
                )
                ORDER BY created_at DESC
            """, (caller_phone, call_sid, call_time - timedelta(minutes=10), call_time + timedelta(minutes=10)))
            leads = [dict(r) for r in cur.fetchall()]
        elif caller_phone and call_time:
            cur.execute("""
                SELECT id, caller_phone, parsed_data, created_at
                FROM leads
                WHERE caller_phone = %s AND created_at >= %s AND created_at <= %s
                ORDER BY created_at DESC
            """, (caller_phone, call_time - timedelta(minutes=15), call_time + timedelta(minutes=15)))
            leads = [dict(r) for r in cur.fetchall()]

        # Convert datetime objects to string representation for serialization
        for a in appts:
            for k, v in a.items():
                if isinstance(v, datetime):
                    a[k] = v.isoformat()
        for l in leads:
            for k, v in l.items():
                if isinstance(v, datetime):
                    l[k] = v.isoformat()

        return {
            "appointments": appts,
            "leads": leads
        }
    finally:
        conn.close()
