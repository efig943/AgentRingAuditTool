#!/usr/bin/env python3
"""
audit_database.py - Comprehensive PostgreSQL & Relational Integrity Auditor.
Part of the 'db-audit' skill for CallAudit Pro.

Performs full-spectrum audits across all database tables:
1. Table Inventory & Storage Metrics
2. Foreign Key & Referential Integrity (Parent/Child & Reverse Orphans)
3. Cross-Entity Business Flow & Multi-Tenant Isolation
4. Data Hygiene, E.164 Formatting, JSON Schemas & Time Invariants
5. Cross-System Sync with Local SQLite audits.db
"""

import os
import sys
import json
import re
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Locate project root and load environment variables
current_path = Path(__file__).resolve()
PROJECT_ROOT = None
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "audits.db").exists():
        PROJECT_ROOT = parent
        break
if not PROJECT_ROOT:
    PROJECT_ROOT = current_path.parents[4]

sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_DB_PATH = PROJECT_ROOT / "audits.db"

# Strict E.164 regex: + followed by 7-15 digits starting with 1-9
E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")

TABLES_OF_INTEREST = [
    "tenants",
    "tenant_profiles",
    "agent_configs",
    "phone_numbers",
    "tenant_integrations",
    "users",
    "call_logs",
    "leads",
    "appointments",
]


class AuditIssue:
    def __init__(
        self,
        code: str,
        severity: str,  # 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        table: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        remediation_sql: Optional[str] = None,
    ):
        self.code = code
        self.severity = severity.upper()
        self.table = table
        self.message = message
        self.details = self._sanitize_dict(details or {})
        self.remediation_sql = remediation_sql

    def _sanitize_dict(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._sanitize_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_dict(v) for v in obj]
        elif isinstance(obj, (datetime, Path)):
            return str(obj)
        return obj

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "table": self.table,
            "message": self.message,
            "details": self.details,
            "remediation_sql": self.remediation_sql,
        }


class DatabaseAuditor:
    def __init__(self, db_url: str, sqlite_path: Optional[Path] = None):
        if not db_url:
            raise ValueError("DATABASE_URL is not provided or empty.")
        self.db_url = db_url
        self.sqlite_path = sqlite_path
        self.issues: List[AuditIssue] = []
        self.table_stats: Dict[str, Any] = {}
        self.cross_db_stats: Dict[str, Any] = {}

    def get_pg_conn(self):
        return psycopg2.connect(self.db_url, connect_timeout=10)

    def run_full_audit(self, target_table: Optional[str] = None) -> Dict[str, Any]:
        self.issues.clear()
        self.table_stats.clear()

        with self.get_pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Inventory & Statistics
                self._audit_inventory_and_stats(cur, target_table)

                # 2. Referential Integrity & Foreign Keys
                if not target_table or target_table != "none":
                    self._audit_referential_integrity(cur, target_table)

                # 3. Multi-Tenant Leak & Cross-Entity Consistency
                if not target_table or target_table in ["appointments", "leads", "call_logs"]:
                    self._audit_cross_entity_correlation(cur)

                # 4. Data Hygiene (E.164, JSON, Timestamps, Invariants)
                self._audit_data_hygiene(cur, target_table)

        # 5. Cross-Check with Local SQLite audits.db
        if not target_table or target_table == "call_logs":
            self._audit_sqlite_sync()

        return self.compile_report()

    # -------------------------------------------------------------------------
    # 1. Inventory & Table Statistics
    # -------------------------------------------------------------------------
    def _audit_inventory_and_stats(self, cur, target_table: Optional[str]):
        tables = [target_table] if target_table and target_table in TABLES_OF_INTEREST else TABLES_OF_INTEREST
        for table in tables:
            try:
                cur.execute(f"SELECT count(*) FROM {table};")
                count = cur.fetchone()[0]

                # Fetch column count and primary key
                cur.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (table,))
                cols = cur.fetchall()

                self.table_stats[table] = {
                    "row_count": count,
                    "column_count": len(cols),
                    "columns": [c["column_name"] for c in cols],
                }

                if count == 0:
                    self.issues.append(
                        AuditIssue(
                            code="INV-001",
                            severity="WARNING",
                            table=table,
                            message=f"Table '{table}' is completely empty (0 rows).",
                        )
                    )
            except Exception as e:
                self.issues.append(
                    AuditIssue(
                        code="INV-ERR",
                        severity="ERROR",
                        table=table,
                        message=f"Failed to query table metadata: {str(e)}",
                    )
                )

    # -------------------------------------------------------------------------
    # 2. Referential Integrity & Foreign Keys
    # -------------------------------------------------------------------------
    def _audit_referential_integrity(self, cur, target_table: Optional[str]):
        # A. Child records with invalid tenant_id
        child_tables_with_tenant = [
            "tenant_profiles",
            "agent_configs",
            "phone_numbers",
            "tenant_integrations",
            "users",
            "call_logs",
            "leads",
            "appointments",
        ]
        for tbl in child_tables_with_tenant:
            if target_table and tbl != target_table:
                continue
            cur.execute(f"""
                SELECT id, tenant_id FROM {tbl} 
                WHERE tenant_id IS NULL OR tenant_id NOT IN (SELECT id FROM tenants);
            """)
            orphaned = cur.fetchall()
            if orphaned:
                ids = [r["id"] for r in orphaned]
                self.issues.append(
                    AuditIssue(
                        code="FK-001",
                        severity="CRITICAL",
                        table=tbl,
                        message=f"Found {len(orphaned)} orphaned records with nonexistent or null tenant_id.",
                        details={"orphaned_ids": ids[:20], "total_orphaned": len(orphaned)},
                        remediation_sql=f"DELETE FROM {tbl} WHERE tenant_id NOT IN (SELECT id FROM tenants);",
                    )
                )

        # B. Appointments with invalid lead_id
        if not target_table or target_table == "appointments":
            cur.execute("""
                SELECT id, lead_id FROM appointments 
                WHERE lead_id IS NOT NULL AND lead_id NOT IN (SELECT id FROM leads);
            """)
            broken_lead_fks = cur.fetchall()
            if broken_lead_fks:
                ids = [r["id"] for r in broken_lead_fks]
                self.issues.append(
                    AuditIssue(
                        code="FK-002",
                        severity="ERROR",
                        table="appointments",
                        message=f"Found {len(broken_lead_fks)} appointments referencing a nonexistent lead_id.",
                        details={"appointment_ids": ids},
                        remediation_sql="UPDATE appointments SET lead_id = NULL WHERE lead_id NOT IN (SELECT id FROM leads);",
                    )
                )

        # C. Reverse Orphan Checks: Tenants missing essential operational configuration
        if not target_table or target_table == "tenants":
            # 1. Missing profiles
            cur.execute("""
                SELECT id, company_name FROM tenants 
                WHERE id NOT IN (SELECT tenant_id FROM tenant_profiles);
            """)
            missing_profiles = cur.fetchall()
            if missing_profiles:
                self.issues.append(
                    AuditIssue(
                        code="CFG-001",
                        severity="ERROR",
                        table="tenants",
                        message=f"Found {len(missing_profiles)} tenants missing a tenant_profile (onboarding incomplete).",
                        details={"tenants": [{"id": r["id"], "name": r["company_name"]} for r in missing_profiles]},
                    )
                )

            # 2. Missing agent config
            cur.execute("""
                SELECT id, company_name FROM tenants 
                WHERE id NOT IN (SELECT tenant_id FROM agent_configs);
            """)
            missing_configs = cur.fetchall()
            if missing_configs:
                self.issues.append(
                    AuditIssue(
                        code="CFG-002",
                        severity="WARNING",
                        table="tenants",
                        message=f"Found {len(missing_configs)} tenants missing agent_configs (voice agent unconfigured).",
                        details={"tenants": [{"id": r["id"], "name": r["company_name"]} for r in missing_configs[:10]]},
                    )
                )

            # 3. Missing phone numbers
            cur.execute("""
                SELECT id, company_name FROM tenants 
                WHERE id NOT IN (SELECT tenant_id FROM phone_numbers);
            """)
            missing_phones = cur.fetchall()
            if missing_phones:
                self.issues.append(
                    AuditIssue(
                        code="CFG-003",
                        severity="WARNING",
                        table="tenants",
                        message=f"Found {len(missing_phones)} tenants with no inbound phone_numbers provisioned.",
                        details={"tenants": [{"id": r["id"], "name": r["company_name"]} for r in missing_phones[:10]]},
                    )
                )

    # -------------------------------------------------------------------------
    # 3. Multi-Tenant Leak & Cross-Entity Consistency
    # -------------------------------------------------------------------------
    def _audit_cross_entity_correlation(self, cur):
        # A. CRITICAL SECURITY: Appointment tenant vs Lead tenant mismatch
        cur.execute("""
            SELECT a.id AS appt_id, a.tenant_id AS appt_tenant, 
                   l.id AS lead_id, l.tenant_id AS lead_tenant
            FROM appointments a
            JOIN leads l ON a.lead_id = l.id
            WHERE a.tenant_id != l.tenant_id;
        """)
        mismatched_leads = cur.fetchall()
        if mismatched_leads:
            self.issues.append(
                AuditIssue(
                    code="SEC-001",
                    severity="CRITICAL",
                    table="appointments",
                    message=f"CRITICAL MULTI-TENANT LEAK: {len(mismatched_leads)} appointments linked to leads belonging to DIFFERENT tenants!",
                    details={"records": [dict(r) for r in mismatched_leads]},
                )
            )

        # B. CRITICAL SECURITY: Appointment tenant vs Call Log tenant mismatch by call_sid
        cur.execute("""
            SELECT a.id AS appt_id, a.tenant_id AS appt_tenant, a.call_sid,
                   c.id AS call_id, c.tenant_id AS call_tenant
            FROM appointments a
            JOIN call_logs c ON a.call_sid = c.call_sid
            WHERE a.call_sid IS NOT NULL AND a.tenant_id != c.tenant_id;
        """)
        mismatched_calls = cur.fetchall()
        if mismatched_calls:
            self.issues.append(
                AuditIssue(
                    code="SEC-002",
                    severity="CRITICAL",
                    table="appointments",
                    message=f"CRITICAL MULTI-TENANT LEAK: {len(mismatched_calls)} appointments share call_sid with call_logs from a DIFFERENT tenant!",
                    details={"records": [dict(r) for r in mismatched_calls]},
                )
            )

        # C. Appointments referencing a call_sid not present in call_logs
        cur.execute("""
            SELECT id, call_sid, caller_phone, created_at 
            FROM appointments
            WHERE call_sid IS NOT NULL 
              AND call_sid NOT IN (SELECT call_sid FROM call_logs WHERE call_sid IS NOT NULL);
        """)
        orphan_appts = cur.fetchall()
        if orphan_appts:
            self.issues.append(
                AuditIssue(
                    code="COR-001",
                    severity="WARNING",
                    table="appointments",
                    message=f"Found {len(orphan_appts)} appointments referencing a call_sid missing from call_logs.",
                    details={"appointments": [dict(r) for r in orphan_appts]},
                )
            )

        # D. Leads with _call_sid in parsed_data not present in call_logs
        cur.execute("""
            SELECT id, caller_phone, parsed_data->>'_call_sid' AS call_sid
            FROM leads
            WHERE parsed_data->>'_call_sid' IS NOT NULL
              AND parsed_data->>'_call_sid' NOT IN (SELECT call_sid FROM call_logs WHERE call_sid IS NOT NULL);
        """)
        orphan_lead_sids = cur.fetchall()
        if orphan_lead_sids:
            self.issues.append(
                AuditIssue(
                    code="COR-002",
                    severity="WARNING",
                    table="leads",
                    message=f"Found {len(orphan_lead_sids)} leads with '_call_sid' in parsed_data missing from call_logs.",
                    details={"leads": [dict(r) for r in orphan_lead_sids]},
                )
            )

        # E. Unlinked appointments that have candidates in leads (same phone & within 30 mins)
        cur.execute("""
            SELECT a.id AS appt_id, a.caller_phone, a.tenant_id, a.created_at AS appt_time,
                   l.id AS candidate_lead_id, l.created_at AS lead_time
            FROM appointments a
            JOIN leads l ON a.tenant_id = l.tenant_id AND a.caller_phone = l.caller_phone
            WHERE a.lead_id IS NULL
              AND l.created_at BETWEEN a.created_at - INTERVAL '30 minutes' AND a.created_at + INTERVAL '30 minutes';
        """)
        candidate_links = cur.fetchall()
        if candidate_links:
            self.issues.append(
                AuditIssue(
                    code="COR-003",
                    severity="INFO",
                    table="appointments",
                    message=f"Found {len(candidate_links)} unlinked appointments that have candidate leads matching caller_phone and timestamp window.",
                    details={"matches": [dict(r) for r in candidate_links]},
                )
            )

        # F. Appointments and linked Leads with conflicting phone numbers
        cur.execute("""
            SELECT a.id AS appt_id, a.caller_phone AS appt_phone,
                   l.id AS lead_id, l.caller_phone AS lead_phone
            FROM appointments a
            JOIN leads l ON a.lead_id = l.id
            WHERE a.caller_phone != l.caller_phone;
        """)
        phone_mismatch = cur.fetchall()
        if phone_mismatch:
            self.issues.append(
                AuditIssue(
                    code="COR-004",
                    severity="WARNING",
                    table="appointments",
                    message=f"Found {len(phone_mismatch)} linked appointments where caller_phone does not match the linked lead caller_phone.",
                    details={"mismatches": [dict(r) for r in phone_mismatch]},
                )
            )

    # -------------------------------------------------------------------------
    # 4. Data Hygiene (E.164, JSON, Timestamps, Invariants)
    # -------------------------------------------------------------------------
    def _audit_data_hygiene(self, cur, target_table: Optional[str]):
        # A. Phone number format validation (E.164)
        phone_checks = [
            ("call_logs", "caller_phone"),
            ("appointments", "caller_phone"),
            ("leads", "caller_phone"),
            ("phone_numbers", "twilio_number"),
            ("tenant_profiles", "assigned_phone_number"),
            ("tenant_profiles", "forwarding_number"),
            ("agent_configs", "forwarding_number"),
        ]
        for tbl, col in phone_checks:
            if target_table and tbl != target_table:
                continue
            cur.execute(f"SELECT id, {col} FROM {tbl} WHERE {col} IS NOT NULL;")
            rows = cur.fetchall()
            invalid = []
            for r in rows:
                val = r[col]
                if val and not E164_REGEX.match(val):
                    invalid.append({"id": r["id"], col: val})

            if invalid:
                self.issues.append(
                    AuditIssue(
                        code="HYG-001",
                        severity="WARNING",
                        table=tbl,
                        message=f"Found {len(invalid)} records in '{tbl}.{col}' with non-standard E.164 phone formats.",
                        details={"invalid_samples": invalid[:10], "total_invalid": len(invalid)},
                    )
                )

        # B. Call logs transcript validation & anomaly checks
        if not target_table or target_table == "call_logs":
            cur.execute("""
                SELECT id, status, duration_seconds, transcript, created_at
                FROM call_logs;
            """)
            call_rows = cur.fetchall()
            empty_transcripts_completed = []
            malformed_json_transcripts = []
            negative_duration = []

            for r in call_rows:
                call_id = r["id"]
                status = r["status"]
                dur = r["duration_seconds"]
                transcript_raw = r["transcript"]

                if dur is not None and dur < 0:
                    negative_duration.append({"id": call_id, "duration": dur})

                # Validate JSON structure
                transcript_data = None
                if isinstance(transcript_raw, str):
                    try:
                        transcript_data = json.loads(transcript_raw)
                    except Exception:
                        malformed_json_transcripts.append(call_id)
                elif isinstance(transcript_raw, (list, dict)):
                    transcript_data = transcript_raw

                if transcript_data is not None:
                    if not isinstance(transcript_data, list):
                        malformed_json_transcripts.append(call_id)
                    else:
                        # Completed call with duration > 30s but 0 transcript turns
                        if status == "completed" and (dur or 0) > 30 and len(transcript_data) == 0:
                            empty_transcripts_completed.append({
                                "id": call_id,
                                "duration_seconds": dur,
                                "created_at": str(r["created_at"])
                            })

            if malformed_json_transcripts:
                self.issues.append(
                    AuditIssue(
                        code="HYG-002",
                        severity="ERROR",
                        table="call_logs",
                        message=f"Found {len(malformed_json_transcripts)} call_logs with corrupted/non-array transcript JSON.",
                        details={"call_ids": malformed_json_transcripts},
                    )
                )

            if empty_transcripts_completed:
                self.issues.append(
                    AuditIssue(
                        code="HYG-003",
                        severity="WARNING",
                        table="call_logs",
                        message=f"Found {len(empty_transcripts_completed)} 'completed' calls (>30s) with completely empty transcript arrays.",
                        details={"calls": empty_transcripts_completed[:10], "total": len(empty_transcripts_completed)},
                    )
                )

            if negative_duration:
                self.issues.append(
                    AuditIssue(
                        code="HYG-004",
                        severity="ERROR",
                        table="call_logs",
                        message=f"Found {len(negative_duration)} call_logs with negative duration_seconds.",
                        details={"calls": negative_duration},
                    )
                )

        # C. Appointment Temporal Invariants
        if not target_table or target_table == "appointments":
            cur.execute("""
                SELECT id, start_time, end_time, duration_minutes, status
                FROM appointments;
            """)
            appts = cur.fetchall()
            inverted_time = []
            duration_mismatch = []

            for a in appts:
                start = a["start_time"]
                end = a["end_time"]
                dur = a["duration_minutes"]

                if start and end:
                    if start >= end:
                        inverted_time.append({"id": a["id"], "start": str(start), "end": str(end)})
                    diff_mins = int((end - start).total_seconds() / 60)
                    if dur is not None and abs(diff_mins - dur) > 1:
                        duration_mismatch.append({
                            "id": a["id"],
                            "recorded_duration": dur,
                            "calculated_duration": diff_mins
                        })

            if inverted_time:
                self.issues.append(
                    AuditIssue(
                        code="HYG-005",
                        severity="CRITICAL",
                        table="appointments",
                        message=f"Found {len(inverted_time)} appointments where start_time >= end_time.",
                        details={"appointments": inverted_time},
                    )
                )

            if duration_mismatch:
                self.issues.append(
                    AuditIssue(
                        code="HYG-006",
                        severity="WARNING",
                        table="appointments",
                        message=f"Found {len(duration_mismatch)} appointments where duration_minutes does not match (end_time - start_time).",
                        details={"appointments": duration_mismatch},
                    )
                )

        # D. Expired OAuth Tokens in tenant_integrations
        if not target_table or target_table == "tenant_integrations":
            cur.execute("""
                SELECT id, tenant_id, provider, calendar_id, expires_at 
                FROM tenant_integrations
                WHERE expires_at < NOW();
            """)
            expired = cur.fetchall()
            if expired:
                self.issues.append(
                    AuditIssue(
                        code="INT-001",
                        severity="WARNING",
                        table="tenant_integrations",
                        message=f"Found {len(expired)} calendar integration(s) with expired access tokens.",
                        details={"integrations": [dict(r) for r in expired]},
                    )
                )

    # -------------------------------------------------------------------------
    # 5. Cross-Check with Local SQLite audits.db
    # -------------------------------------------------------------------------
    def _audit_sqlite_sync(self):
        if not self.sqlite_path or not self.sqlite_path.exists():
            self.cross_db_stats["sqlite_status"] = "No audits.db found at project root"
            return

        try:
            conn = sqlite3.connect(str(self.sqlite_path))
            cur = conn.cursor()
            cur.execute("SELECT call_id, status FROM audits;")
            audits_rows = cur.fetchall()
            conn.close()

            audited_call_ids = [r[0] for r in audits_rows]
            self.cross_db_stats["total_audited_in_sqlite"] = len(audited_call_ids)

            # Check if any audited call_id is absent from Postgres
            if audited_call_ids:
                with self.get_pg_conn() as pg_conn:
                    with pg_conn.cursor() as pg_cur:
                        pg_cur.execute("SELECT id FROM call_logs WHERE id = ANY(%s);", (audited_call_ids,))
                        found_ids = {r[0] for r in pg_cur.fetchall()}
                        ghost_ids = [cid for cid in audited_call_ids if cid not in found_ids]

                        # Check un-audited calls count
                        pg_cur.execute("SELECT count(*) FROM call_logs;")
                        total_pg_calls = pg_cur.fetchone()[0]
                        self.cross_db_stats["total_postgres_calls"] = total_pg_calls
                        self.cross_db_stats["pending_audits"] = max(0, total_pg_calls - len(found_ids))

                        if ghost_ids:
                            self.issues.append(
                                AuditIssue(
                                    code="SYNC-001",
                                    severity="ERROR",
                                    table="call_logs",
                                    message=f"Local audits.db contains {len(ghost_ids)} audited call_id(s) that do not exist in PostgreSQL call_logs.",
                                    details={"ghost_call_ids": ghost_ids},
                                    remediation_sql=f"DELETE FROM audits WHERE call_id IN ({','.join(map(str, ghost_ids))});",
                                )
                            )
        except Exception as e:
            self.cross_db_stats["sqlite_error"] = str(e)

    # -------------------------------------------------------------------------
    # Report Compilation & Formatting
    # -------------------------------------------------------------------------
    def compile_report(self) -> Dict[str, Any]:
        severity_counts = {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        for issue in self.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

        overall_status = "HEALTHY"
        if severity_counts["CRITICAL"] > 0:
            overall_status = "CRITICAL"
        elif severity_counts["ERROR"] > 0:
            overall_status = "DEGRADED"
        elif severity_counts["WARNING"] > 0:
            overall_status = "WARNING"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "issue_counts": severity_counts,
            "total_issues": len(self.issues),
            "table_stats": self.table_stats,
            "cross_db_stats": self.cross_db_stats,
            "issues": [i.to_dict() for i in self.issues],
        }


def format_markdown_report(report: Dict[str, Any]) -> str:
    lines = []
    status_badges = {
        "HEALTHY": "🟢 HEALTHY",
        "WARNING": "🟡 WARNING",
        "DEGRADED": "🟠 DEGRADED",
        "CRITICAL": "🔴 CRITICAL",
    }
    badge = status_badges.get(report["overall_status"], report["overall_status"])

    lines.append(f"# Database Integrity Audit Report")
    lines.append(f"**Audit Status**: {badge}  |  **Generated At**: `{report['timestamp']}`\n")

    lines.append("## 1. Executive Summary")
    counts = report["issue_counts"]
    lines.append(f"- **Critical Errors**: `{counts.get('CRITICAL', 0)}`")
    lines.append(f"- **Errors**: `{counts.get('ERROR', 0)}`")
    lines.append(f"- **Warnings**: `{counts.get('WARNING', 0)}`")
    lines.append(f"- **Info Notices**: `{counts.get('INFO', 0)}`")
    lines.append("")

    if report.get("cross_db_stats"):
        lines.append("## 2. Sync & Volume Overview")
        for k, v in report["cross_db_stats"].items():
            lines.append(f"- **{k.replace('_', ' ').title()}**: `{v}`")
        lines.append("")

    lines.append("## 3. Table Inventory")
    lines.append("| Table Name | Row Count | Columns |")
    lines.append("|---|---|---|")
    for tbl, stats in sorted(report["table_stats"].items()):
        lines.append(f"| `{tbl}` | {stats['row_count']} | {stats['column_count']} |")
    lines.append("")

    lines.append("## 4. Audit Findings & Violations")
    if not report["issues"]:
        lines.append("✅ No relational integrity, hygiene, or isolation issues detected.")
    else:
        for idx, issue in enumerate(report["issues"], start=1):
            sev_icon = {
                "CRITICAL": "🚨 CRITICAL",
                "ERROR": "❌ ERROR",
                "WARNING": "⚠️ WARNING",
                "INFO": "ℹ️ INFO",
            }.get(issue["severity"], issue["severity"])

            lines.append(f"### {idx}. [{issue['code']}] {sev_icon}: {issue['table']}")
            lines.append(f"**Message**: {issue['message']}")
            if issue.get("details"):
                lines.append("```json")
                lines.append(json.dumps(issue["details"], indent=2, default=str))
                lines.append("```")
            if issue.get("remediation_sql"):
                lines.append("**Suggested SQL Remediation**:")
                lines.append("```sql")
                lines.append(issue["remediation_sql"])
                lines.append("```")
            lines.append("")

    return "\n".join(lines)


def format_terminal_summary(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append(f" DATABASE AUDIT SUITE - STATUS: {report['overall_status']}")
    lines.append(f" Timestamp: {report['timestamp']}")
    lines.append("=" * 70)

    # Tables
    lines.append("\nTABLE INVENTORY:")
    for tbl, stats in sorted(report["table_stats"].items()):
        lines.append(f"  • {tbl.ljust(22)}: {str(stats['row_count']).rjust(5)} rows")

    if report.get("cross_db_stats"):
        lines.append("\nCROSS-DATABASE TELEMETRY:")
        for k, v in report["cross_db_stats"].items():
            lines.append(f"  • {k.replace('_', ' ').title()}: {v}")

    # Issues
    lines.append("\nAUDIT VIOLATIONS:")
    if not report["issues"]:
        lines.append("  [OK] All tables, foreign keys, and invariants passed verification.")
    else:
        for issue in report["issues"]:
            prefix = f"[{issue['severity'].ljust(8)}]"
            lines.append(f"  {prefix} ({issue['code']}) {issue['table']}: {issue['message']}")

    lines.append("\n" + "=" * 70)
    lines.append(f"TOTAL ISSUES: {report['total_issues']} (Critical: {report['issue_counts']['CRITICAL']}, Error: {report['issue_counts']['ERROR']}, Warning: {report['issue_counts']['WARNING']}, Info: {report['issue_counts']['INFO']})")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Database & Relational Integrity Auditor for PostgreSQL / CallAudit Pro."
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Output display format (default: summary)",
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Scope the audit to a single target table (e.g., appointments, call_logs)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error", "critical"],
        default="info",
        help="Filter findings by minimum severity level (default: info)",
    )
    parser.add_argument(
        "--fix-sql",
        action="store_true",
        help="Print only the suggested remediation SQL statements",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="File path to save the full audit report (JSON or Markdown)",
    )

    args = parser.parse_args()

    try:
        auditor = DatabaseAuditor(db_url=DATABASE_URL, sqlite_path=SQLITE_DB_PATH)
        report = auditor.run_full_audit(target_table=args.table)

        # Filter by severity if requested
        sev_rank = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
        min_rank = sev_rank[args.min_severity.upper()]
        report["issues"] = [i for i in report["issues"] if sev_rank.get(i["severity"], 0) >= min_rank]

        # Fix SQL mode
        if args.fix_sql:
            sql_fixes = [i["remediation_sql"] for i in report["issues"] if i.get("remediation_sql")]
            if sql_fixes:
                print("-- Suggested SQL Remediation Script --")
                for s in sql_fixes:
                    print(s)
            else:
                print("-- No automated SQL remediation needed or available. --")
            sys.exit(0)

        # Output formats
        output_text = ""
        if args.format == "json":
            output_text = json.dumps(report, indent=2, default=str)
        elif args.format == "markdown":
            output_text = format_markdown_report(report)
        else:
            output_text = format_terminal_summary(report)

        print(output_text)

        # Export if requested
        if args.export:
            export_path = Path(args.export).resolve()
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"\n[+] Audit report saved to {export_path}")

        # Exit code reflects severity
        if report["issue_counts"]["CRITICAL"] > 0:
            sys.exit(2)
        elif report["issue_counts"]["ERROR"] > 0:
            sys.exit(2)
        elif report["issue_counts"]["WARNING"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"[!] Database audit failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
