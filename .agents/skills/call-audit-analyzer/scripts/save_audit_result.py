#!/usr/bin/env python3
"""
save_audit_result.py - CLI tool to validate, persist, and alert on audit findings.
Part of the 'call-audit-analyzer' orchestrator skill for CallAudit Pro.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

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

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from app.db.storage import save_audit, get_audit
from app.db.postgres import fetch_call_by_id, fetch_linked_records
from app.services.email_service import send_issue_alert_email
from app.core import config

REQUIRED_FIELDS = [
    "call_id",
    "status",
    "has_issues",
    "summary",
    "customer_sentiment",
    "incident_report",
    "recommended_action"
]

def validate_and_normalize(audit_dict: Dict[str, Any]) -> Dict[str, Any]:
    # Check missing required fields
    for field in REQUIRED_FIELDS:
        if field not in audit_dict:
            raise ValueError(f"Missing required audit field: '{field}'")

    status = str(audit_dict["status"]).upper()
    if status not in ("CLEAN", "WARNING", "CRITICAL"):
        raise ValueError(f"Invalid status '{status}'. Must be CLEAN, WARNING, or CRITICAL.")
    audit_dict["status"] = status

    # Ensure booleans
    audit_dict["has_issues"] = bool(audit_dict.get("has_issues", False))
    audit_dict["customer_mad"] = bool(audit_dict.get("customer_mad", False))
    audit_dict["weird_interaction"] = bool(audit_dict.get("weird_interaction", False))
    audit_dict["db_discrepancy"] = bool(audit_dict.get("db_discrepancy", False))
    audit_dict["call_failure"] = bool(audit_dict.get("call_failure", False))

    if "audited_at" not in audit_dict:
        audit_dict["audited_at"] = datetime.now().isoformat()

    # Hydrate raw call and db_state if omitted
    call_id = audit_dict["call_id"]
    if not audit_dict.get("call_sid") or "transcript" not in audit_dict:
        raw_call = fetch_call_by_id(call_id)
        if raw_call:
            audit_dict.setdefault("call_sid", raw_call.get("call_sid"))
            audit_dict.setdefault("caller_phone", raw_call.get("caller_phone"))
            audit_dict.setdefault("duration_seconds", raw_call.get("duration_seconds", 0))
            audit_dict.setdefault("call_created_at", str(raw_call.get("created_at")))
            audit_dict.setdefault("transcript", raw_call.get("transcript", []))
            
            if "db_state" not in audit_dict:
                linked = fetch_linked_records(
                    raw_call.get("call_sid"),
                    raw_call.get("caller_phone", ""),
                    raw_call.get("created_at")
                )
                audit_dict["db_state"] = linked

    return audit_dict

def main():
    parser = argparse.ArgumentParser(description="Save Audit Result Tool")
    parser.add_argument("--input-file", help="Path to JSON file with audit output (or pass via stdin)")
    parser.add_argument("--send-alert", action="store_true", help="Send incident alert email if issues detected")
    parser.add_argument("--dry-run", action="store_true", help="Validate payload without saving to audits.db")

    args = parser.parse_args()

    raw_json = ""
    if args.input_file:
        with open(args.input_file, "r") as f:
            raw_json = f.read()
    else:
        raw_json = sys.stdin.read()

    if not raw_json.strip():
        print(json.dumps({"error": "No JSON payload provided in file or stdin."}), file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw_json)
        validated = validate_and_normalize(data)

        if args.dry_run:
            print(json.dumps({"status": "valid", "dry_run": True, "record": validated}, indent=2))
            return

        save_audit(validated)
        email_sent = False

        if args.send_alert or (config.AUTO_EMAIL_ON_ISSUE and validated.get("has_issues") and validated.get("status") == "CRITICAL"):
            try:
                email_sent = send_issue_alert_email(validated)
            except Exception as e:
                email_sent = False
                print(f"Warning: Failed to send alert email: {e}", file=sys.stderr)

        print(json.dumps({
            "status": "success",
            "call_id": validated["call_id"],
            "audit_status": validated["status"],
            "has_issues": validated["has_issues"],
            "email_alert_dispatched": email_sent
        }, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
