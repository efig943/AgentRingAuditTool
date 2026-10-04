import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.core import config

def get_sqlite_conn():
    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_audit_db():
    """Initialize audit persistence tables and indexes."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            call_id INTEGER PRIMARY KEY,
            call_sid TEXT,
            caller_phone TEXT,
            duration_seconds INTEGER,
            call_created_at TEXT,
            status TEXT NOT NULL,
            has_issues INTEGER NOT NULL DEFAULT 0,
            customer_mad INTEGER NOT NULL DEFAULT 0,
            weird_interaction INTEGER NOT NULL DEFAULT 0,
            db_discrepancy INTEGER NOT NULL DEFAULT 0,
            call_failure INTEGER NOT NULL DEFAULT 0,
            issue_types TEXT,
            summary TEXT,
            customer_sentiment TEXT,
            db_comparison TEXT,
            incident_report TEXT,
            recommended_action TEXT,
            transcript TEXT,
            db_state TEXT,
            email_sent INTEGER NOT NULL DEFAULT 0,
            email_sent_at TEXT,
            audited_at TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0,
            resolved_at TEXT,
            notes TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audits_call_created ON audits(call_created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audits_has_issues ON audits(has_issues);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audits_customer_mad ON audits(customer_mad);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audits_db_discrepancy ON audits(db_discrepancy);")
    conn.commit()
    conn.close()

def save_audit(audit_data: Dict[str, Any]) -> None:
    """Insert or update an audit record."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO audits (
            call_id, call_sid, caller_phone, duration_seconds, call_created_at,
            status, has_issues, customer_mad, weird_interaction, db_discrepancy, call_failure,
            issue_types, summary, customer_sentiment, db_comparison, incident_report, recommended_action,
            transcript, db_state, email_sent, email_sent_at, audited_at, resolved
        ) VALUES (
            :call_id, :call_sid, :caller_phone, :duration_seconds, :call_created_at,
            :status, :has_issues, :customer_mad, :weird_interaction, :db_discrepancy, :call_failure,
            :issue_types, :summary, :customer_sentiment, :db_comparison, :incident_report, :recommended_action,
            :transcript, :db_state, :email_sent, :email_sent_at, :audited_at, :resolved
        )
        ON CONFLICT(call_id) DO UPDATE SET
            status = excluded.status,
            has_issues = excluded.has_issues,
            customer_mad = excluded.customer_mad,
            weird_interaction = excluded.weird_interaction,
            db_discrepancy = excluded.db_discrepancy,
            call_failure = excluded.call_failure,
            issue_types = excluded.issue_types,
            summary = excluded.summary,
            customer_sentiment = excluded.customer_sentiment,
            db_comparison = excluded.db_comparison,
            incident_report = excluded.incident_report,
            recommended_action = excluded.recommended_action,
            transcript = excluded.transcript,
            db_state = excluded.db_state,
            audited_at = excluded.audited_at
    """, {
        "call_id": audit_data["call_id"],
        "call_sid": audit_data.get("call_sid"),
        "caller_phone": audit_data.get("caller_phone"),
        "duration_seconds": audit_data.get("duration_seconds", 0),
        "call_created_at": audit_data.get("call_created_at"),
        "status": audit_data.get("status", "CLEAN"),
        "has_issues": 1 if audit_data.get("has_issues") else 0,
        "customer_mad": 1 if audit_data.get("customer_mad") else 0,
        "weird_interaction": 1 if audit_data.get("weird_interaction") else 0,
        "db_discrepancy": 1 if audit_data.get("db_discrepancy") else 0,
        "call_failure": 1 if audit_data.get("call_failure") else 0,
        "issue_types": json.dumps(audit_data.get("issue_types", [])),
        "summary": audit_data.get("summary", ""),
        "customer_sentiment": audit_data.get("customer_sentiment", "Neutral"),
        "db_comparison": json.dumps(audit_data.get("db_comparison", {})),
        "incident_report": audit_data.get("incident_report", ""),
        "recommended_action": audit_data.get("recommended_action", ""),
        "transcript": json.dumps(audit_data.get("transcript", [])),
        "db_state": json.dumps(audit_data.get("db_state", {})),
        "email_sent": 1 if audit_data.get("email_sent") else 0,
        "email_sent_at": audit_data.get("email_sent_at"),
        "audited_at": audit_data.get("audited_at", datetime.now().isoformat()),
        "resolved": 1 if audit_data.get("resolved") else 0
    })
    conn.commit()
    conn.close()

def mark_email_sent(call_id: int) -> None:
    """Record that an alert email was successfully sent for this call."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE audits 
        SET email_sent = 1, email_sent_at = ? 
        WHERE call_id = ?
    """, (datetime.now().isoformat(), call_id))
    conn.commit()
    conn.close()

def mark_resolved(call_id: int, resolved: bool = True) -> None:
    """Mark an audited call incident as resolved or open."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    now_str = datetime.now().isoformat() if resolved else None
    cur.execute("""
        UPDATE audits 
        SET resolved = ?, resolved_at = ? 
        WHERE call_id = ?
    """, (1 if resolved else 0, now_str, call_id))
    conn.commit()
    conn.close()

def get_audited_call_ids() -> List[int]:
    """Return all call IDs that have already been audited."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT call_id FROM audits")
    rows = cur.fetchall()
    conn.close()
    return [r["call_id"] for r in rows]

def get_audit(call_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve audit record for a given call_id."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audits WHERE call_id = ?", (call_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    res["issue_types"] = json.loads(res["issue_types"] or "[]")
    res["db_comparison"] = json.loads(res["db_comparison"] or "{}")
    res["transcript"] = json.loads(res["transcript"] or "[]")
    res["db_state"] = json.loads(res["db_state"] or "{}")
    res["has_issues"] = bool(res["has_issues"])
    res["customer_mad"] = bool(res["customer_mad"])
    res["weird_interaction"] = bool(res["weird_interaction"])
    res["db_discrepancy"] = bool(res["db_discrepancy"])
    res["call_failure"] = bool(res["call_failure"])
    res["email_sent"] = bool(res["email_sent"])
    res["resolved"] = bool(res["resolved"])
    return res

def query_audits(
    status: Optional[str] = None,
    filter_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Query audits with comprehensive filtering."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    query = "SELECT * FROM audits WHERE 1=1"
    params = []
    
    if status and status.upper() != "ALL":
        query += " AND status = ?"
        params.append(status.upper())
        
    if filter_type == "issues":
        query += " AND has_issues = 1"
    elif filter_type == "clean":
        query += " AND has_issues = 0"
    elif filter_type == "customer_mad":
        query += " AND customer_mad = 1"
    elif filter_type == "db_discrepancy":
        query += " AND db_discrepancy = 1"
    elif filter_type == "weird_interaction":
        query += " AND weird_interaction = 1"
        
    if start_date:
        query += " AND call_created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND call_created_at <= ?"
        params.append(end_date)
        
    if search:
        search_pattern = f"%{search}%"
        query += " AND (caller_phone LIKE ? OR call_sid LIKE ? OR summary LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])
        
    query += " ORDER BY call_created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        item = dict(row)
        item["issue_types"] = json.loads(item["issue_types"] or "[]")
        item["db_comparison"] = json.loads(item["db_comparison"] or "{}")
        item["transcript"] = json.loads(item["transcript"] or "[]")
        item["db_state"] = json.loads(item["db_state"] or "{}")
        item["has_issues"] = bool(item["has_issues"])
        item["customer_mad"] = bool(item["customer_mad"])
        item["weird_interaction"] = bool(item["weird_interaction"])
        item["db_discrepancy"] = bool(item["db_discrepancy"])
        item["call_failure"] = bool(item["call_failure"])
        item["email_sent"] = bool(item["email_sent"])
        item["resolved"] = bool(item["resolved"])
        results.append(item)
    return results

def get_stats() -> Dict[str, Any]:
    """Get high-level production support audit stats."""
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT count(*) as total FROM audits")
    total_audited = cur.fetchone()["total"]
    
    cur.execute("SELECT count(*) as clean FROM audits WHERE status = 'CLEAN'")
    clean_count = cur.fetchone()["clean"]
    
    cur.execute("SELECT count(*) as warnings FROM audits WHERE status = 'WARNING'")
    warning_count = cur.fetchone()["warnings"]
    
    cur.execute("SELECT count(*) as criticals FROM audits WHERE status = 'CRITICAL'")
    critical_count = cur.fetchone()["criticals"]
    
    cur.execute("SELECT count(*) as mad FROM audits WHERE customer_mad = 1")
    mad_count = cur.fetchone()["mad"]
    
    cur.execute("SELECT count(*) as db_issues FROM audits WHERE db_discrepancy = 1")
    db_issues_count = cur.fetchone()["db_issues"]
    
    cur.execute("SELECT count(*) as weird FROM audits WHERE weird_interaction = 1")
    weird_count = cur.fetchone()["weird"]
    
    cur.execute("SELECT count(*) as unresolved FROM audits WHERE has_issues = 1 AND resolved = 0")
    unresolved_count = cur.fetchone()["unresolved"]
    
    cur.execute("SELECT count(*) as emailed FROM audits WHERE email_sent = 1")
    emailed_count = cur.fetchone()["emailed"]

    cur.execute("SELECT max(audited_at) as last_audit FROM audits")
    last_audit = cur.fetchone()["last_audit"]
    
    conn.close()
    return {
        "total_audited": total_audited,
        "clean_count": clean_count,
        "warning_count": warning_count,
        "critical_count": critical_count,
        "issues_count": warning_count + critical_count,
        "mad_customers_count": mad_count,
        "db_discrepancies_count": db_issues_count,
        "weird_interactions_count": weird_count,
        "unresolved_count": unresolved_count,
        "emailed_count": emailed_count,
        "last_audit_at": last_audit,
        "all_green": (total_audited > 0 and (warning_count + critical_count) == 0)
    }

# Ensure DB is created on import
init_audit_db()
