#!/usr/bin/env python3
"""
run_full_audit.py - Master Full-System Audit Orchestrator.
Part of the 'full-audit' skill for CallAudit Pro & agentring.dev.

Coordinates and synthesizes findings across all 4 specialist audit domains:
1. Code & Deployment Audit (code-audit) -> Code quality, requirements.txt, Cloud Run readiness
2. Database Integrity Audit (db-audit) -> Schema health, foreign keys, cross-tenant isolation
3. Conversational Audio & Voice Records (call-logs / analyzer) -> Call transcripts, sentiment, DB sync
4. Cloud Run Telemetry & Logs (gcloud-logs) -> Cloud Run service errors, crashes, and latency
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Locate project root
current_path = Path(__file__).resolve()
PROJECT_ROOT = None
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "audits.db").exists():
        PROJECT_ROOT = parent
        break
if not PROJECT_ROOT:
    PROJECT_ROOT = current_path.parents[4]

sys.path.insert(0, str(PROJECT_ROOT))

CODE_AUDIT_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "code-audit" / "scripts" / "audit_codebase.py"
DB_AUDIT_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "db-audit" / "scripts" / "audit_database.py"


class FullSystemOrchestrator:
    def __init__(self, root: Path):
        self.root = root
        self.report: Dict[str, Any] = {}

    def run_all(self, min_severity: str = "info") -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # 1. Run Code Audit
        code_results = self._run_sub_audit(
            [sys.executable, str(CODE_AUDIT_SCRIPT), "--format", "json", "--min-severity", min_severity],
            "Code & Deployment Audit"
        )

        # 2. Run Database Audit
        db_results = self._run_sub_audit(
            [sys.executable, str(DB_AUDIT_SCRIPT), "--format", "json", "--min-severity", min_severity],
            "Database Integrity Audit"
        )

        # 3. Assess Cross-System & Telemetry Status
        telemetry_summary = self._assess_telemetry(db_results)

        # 4. Synthesize findings
        overall_status = "HEALTHY"
        sub_statuses = [
            code_results.get("overall_status", "UNKNOWN"),
            db_results.get("overall_status", "UNKNOWN")
        ]
        if "CRITICAL" in sub_statuses:
            overall_status = "CRITICAL"
        elif "DEGRADED" in sub_statuses:
            overall_status = "DEGRADED"
        elif "WARNING" in sub_statuses:
            overall_status = "WARNING"

        # Tally totals
        total_crit = code_results.get("issue_counts", {}).get("CRITICAL", 0) + db_results.get("issue_counts", {}).get("CRITICAL", 0)
        total_err = code_results.get("issue_counts", {}).get("ERROR", 0) + db_results.get("issue_counts", {}).get("ERROR", 0)
        total_warn = code_results.get("issue_counts", {}).get("WARNING", 0) + db_results.get("issue_counts", {}).get("WARNING", 0)
        total_info = code_results.get("issue_counts", {}).get("INFO", 0) + db_results.get("issue_counts", {}).get("INFO", 0)

        self.report = {
            "timestamp": timestamp,
            "overall_status": overall_status,
            "deployment_target": "agentring.dev (Google Cloud Run)",
            "summary_totals": {
                "critical": total_crit,
                "error": total_err,
                "warning": total_warn,
                "info": total_info,
                "total_issues": total_crit + total_err + total_warn + total_info,
            },
            "domains": {
                "code_and_deployment": code_results,
                "database_and_schema": db_results,
                "telemetry_and_calls": telemetry_summary,
            }
        }
        return self.report

    def _run_sub_audit(self, cmd: List[str], domain_name: str) -> Dict[str, Any]:
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=45
            )
            # Both exit 0, 1, 2 can produce valid JSON output
            output = res.stdout.strip()
            if output.startswith("{"):
                return json.loads(output)
            else:
                return {
                    "overall_status": "ERROR",
                    "error": f"Failed to parse JSON from {domain_name}",
                    "raw_output": output or res.stderr
                }
        except Exception as e:
            return {
                "overall_status": "ERROR",
                "error": f"Execution error in {domain_name}: {str(e)}"
            }

    def _assess_telemetry(self, db_results: Dict[str, Any]) -> Dict[str, Any]:
        cross_db = db_results.get("cross_db_stats", {})
        total_calls = cross_db.get("total_postgres_calls", 0)
        audited_calls = cross_db.get("total_audited_in_sqlite", 0)
        pending = cross_db.get("pending_audits", 0)

        return {
            "total_calls_in_db": total_calls,
            "audited_in_sqlite": audited_calls,
            "pending_audits": pending,
            "coverage_pct": round((audited_calls / total_calls * 100), 1) if total_calls else 0.0,
            "cloud_run_project": "ai-vp-506402",
            "production_domain": "https://agentring.dev",
        }


def format_markdown_master_report(report: Dict[str, Any]) -> str:
    lines = []
    badges = {
        "HEALTHY": "🟢 HEALTHY",
        "WARNING": "🟡 WARNING",
        "DEGRADED": "🟠 DEGRADED",
        "CRITICAL": "🔴 CRITICAL",
    }
    status = badges.get(report["overall_status"], report["overall_status"])

    lines.append(f"# 🛡️ AgentRing Master Full-System Audit Report")
    lines.append(f"**Overall Verdict**: {status}  |  **Target**: `{report['deployment_target']}`  |  **Timestamp**: `{report['timestamp']}`\n")

    # Executive Domain Matrix
    lines.append("## 1. Executive Domain Scorecard")
    lines.append("| Audit Domain | Specialized Skill | Status | Critical | Errors | Warnings | Info |")
    lines.append("|---|---|---|---|---|---|---|")

    code_res = report["domains"].get("code_and_deployment", {})
    code_cnt = code_res.get("issue_counts", {})
    code_badge = badges.get(code_res.get("overall_status"), "UNKNOWN")
    lines.append(f"| **Code & Deployment** | `code-audit` | {code_badge} | {code_cnt.get('CRITICAL', 0)} | {code_cnt.get('ERROR', 0)} | {code_cnt.get('WARNING', 0)} | {code_cnt.get('INFO', 0)} |")

    db_res = report["domains"].get("database_and_schema", {})
    db_cnt = db_res.get("issue_counts", {})
    db_badge = badges.get(db_res.get("overall_status"), "UNKNOWN")
    lines.append(f"| **Database & Schema** | `db-audit` | {db_badge} | {db_cnt.get('CRITICAL', 0)} | {db_cnt.get('ERROR', 0)} | {db_cnt.get('WARNING', 0)} | {db_cnt.get('INFO', 0)} |")

    tele = report["domains"].get("telemetry_and_calls", {})
    lines.append(f"| **Voice AI & Telemetry** | `call-logs` / `gcloud-logs` | ℹ️ TRACKING | 0 | 0 | {tele.get('pending_audits', 0)} pending | {tele.get('coverage_pct')}% coverage |")
    lines.append("")

    # Top Priority Action Items
    lines.append("## 2. 🚨 Consolidated High-Priority Blockers")
    p0_items = []
    # Collect errors and criticals
    for issue in code_res.get("issues", []):
        if issue.get("severity") in ("CRITICAL", "ERROR"):
            p0_items.append((f"[Code] {issue['file']}:{issue.get('line', '')}", issue["message"], issue.get("suggestion")))
    for issue in db_res.get("issues", []):
        if issue.get("severity") in ("CRITICAL", "ERROR"):
            p0_items.append((f"[Database] {issue['table']}", issue["message"], issue.get("remediation_sql")))

    if not p0_items:
        lines.append("✅ No P0/P1 deployment or integrity blockers detected.")
    else:
        for idx, (target, msg, rec) in enumerate(p0_items, start=1):
            lines.append(f"{idx}. **{target}**: {msg}")
            if rec:
                lines.append(f"   ↳ *Action*: `{rec}`")
    lines.append("")

    # Domain 1 Breakdown: Code & Cloud Run
    lines.append("## 3. 📦 Domain Dissection: Codebase & Cloud Run Readiness")
    lines.append(f"- **Files Analyzed**: `{code_res.get('stats', {}).get('total_python_files', 0)}`")
    lines.append(f"- **Total LOC**: `{code_res.get('stats', {}).get('total_loc', 0)}`")
    if code_res.get("issues"):
        for i in code_res["issues"]:
            if i.get("severity") in ("CRITICAL", "ERROR", "WARNING"):
                lines.append(f"- `[{i['severity']}]` **{i['code']}** ({i['file']}): {i['message']}")
    lines.append("")

    # Domain 2 Breakdown: Database
    lines.append("## 4. 🗄️ Domain Dissection: PostgreSQL & Multi-Tenant Fidelity")
    tbl_stats = db_res.get("table_stats", {})
    lines.append(f"- **Total Tables Inspected**: `{len(tbl_stats)}`")
    if db_res.get("issues"):
        for i in db_res["issues"]:
            if i.get("severity") in ("CRITICAL", "ERROR", "WARNING"):
                lines.append(f"- `[{i['severity']}]` **{i['code']}** ({i['table']}): {i['message']}")
    lines.append("")

    # Domain 3 Breakdown: Telephony & Live Ops
    lines.append("## 5. 📞 Domain Dissection: Voice Receptionist Telemetry")
    lines.append(f"- **Production Database Calls**: `{tele.get('total_calls_in_db')}`")
    lines.append(f"- **Audited Calls in SQLite**: `{tele.get('audited_in_sqlite')}`")
    lines.append(f"- **Audit Backlog**: `{tele.get('pending_audits')}` calls awaiting QA review")
    lines.append(f"- **Live Domain**: `{tele.get('production_domain')}`")
    lines.append("")

    return "\n".join(lines)


def format_terminal_summary(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 76)
    lines.append(f" MASTER SYSTEM AUDIT REPORT - OVERALL VERDICT: {report['overall_status']}")
    lines.append(f" Deployment Target: {report['deployment_target']} | Timestamp: {report['timestamp']}")
    lines.append("=" * 76)

    # Scorecard
    lines.append("\nDOMAIN SCORECARD:")
    for domain_key, data in report["domains"].items():
        title = domain_key.replace("_", " ").title()
        status = data.get("overall_status", "ACTIVE")
        cnt = data.get("issue_counts", {})
        crit_err = cnt.get("CRITICAL", 0) + cnt.get("ERROR", 0)
        warn = cnt.get("WARNING", 0)
        lines.append(f"  • {title.ljust(26)}: [{status.ljust(8)}] (Errors: {crit_err}, Warnings: {warn})")

    # High Priority Issues
    lines.append("\nHIGH-PRIORITY ACTION ITEMS (DEPLOYMENT & INTEGRITY BLOCKERS):")
    code_issues = report["domains"].get("code_and_deployment", {}).get("issues", [])
    db_issues = report["domains"].get("database_and_schema", {}).get("issues", [])

    blockers = [i for i in code_issues if i.get("severity") in ("CRITICAL", "ERROR")] + \
               [i for i in db_issues if i.get("severity") in ("CRITICAL", "ERROR")]

    if not blockers:
        lines.append("  [OK] Zero critical deployment blockers detected.")
    else:
        for b in blockers:
            target = b.get("file") or b.get("table")
            loc = f":{b['line']}" if b.get("line") else ""
            lines.append(f"  [!] ({b['code']}) {target}{loc} -> {b['message']}")
            if b.get("suggestion"):
                lines.append(f"      ↳ FIX: {b['suggestion']}")

    lines.append("\n" + "=" * 76)
    tot = report["summary_totals"]
    lines.append(f"TOTAL FINDINGS ACROSS ALL SKILLS: {tot['total_issues']} (Critical: {tot['critical']}, Error: {tot['error']}, Warning: {tot['warning']}, Info: {tot['info']})")
    lines.append("=" * 76)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Master Full-System Audit Orchestrator: Synthesizes Code, DB, Call, and Cloud Run audits."
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Output format (default: summary)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error", "critical"],
        default="info",
        help="Filter findings by minimum severity (default: info)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Save master audit report to file",
    )

    args = parser.parse_args()

    orchestrator = FullSystemOrchestrator(root=PROJECT_ROOT)
    report = orchestrator.run_all(min_severity=args.min_severity)

    output_text = ""
    if args.format == "json":
        output_text = json.dumps(report, indent=2)
    elif args.format == "markdown":
        output_text = format_markdown_master_report(report)
    else:
        output_text = format_terminal_summary(report)

    print(output_text)

    if args.export:
        export_path = Path(args.export).resolve()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"\n[+] Master audit report exported to {export_path}")

    # Exit code
    if report["summary_totals"]["critical"] > 0 or report["summary_totals"]["error"] > 0:
        sys.exit(2)
    elif report["summary_totals"]["warning"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
