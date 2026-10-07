#!/usr/bin/env python3
"""
fetch_gcloud_logs.py - CLI tool to query, filter, and normalize Google Cloud Logging entries.
Part of the 'gcloud-logs' skill for CallAudit Pro.
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ID = "ai-vp-506402"

def parse_relative_time(val: str) -> datetime:
    """Parse relative time string like '10m', '2h', '7d' or ISO 8601 into UTC datetime."""
    val = val.strip()
    now = datetime.now(timezone.utc)
    lower = val.lower()
    if lower.endswith("m") and lower[:-1].isdigit():
        return now - timedelta(minutes=int(lower[:-1]))
    elif lower.endswith("h") and lower[:-1].isdigit():
        return now - timedelta(hours=int(lower[:-1]))
    elif lower.endswith("d") and lower[:-1].isdigit():
        return now - timedelta(days=int(lower[:-1]))
    else:
        # Standardize ISO string: replace Z with +00:00, ensure uppercase T
        iso_val = val.replace("z", "+00:00").replace("Z", "+00:00")
        if "t" in iso_val:
            parts = iso_val.split("t", 1)
            iso_val = parts[0] + "T" + parts[1]
        dt = datetime.fromisoformat(iso_val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

def build_log_filter(
    service: Optional[str] = None,
    severity: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    search_text: Optional[str] = None,
    project: str = PROJECT_ID
) -> str:
    clauses = ['resource.type="cloud_run_revision"']
    
    if service and service.lower() != "all":
        clauses.append(f'resource.labels.service_name="{service}"')
        
    if severity and severity.upper() != "ALL":
        clauses.append(f'severity>="{severity.upper()}"')
        
    if start_time:
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        clauses.append(f'timestamp>="{start_str}"')
        
    if end_time:
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        clauses.append(f'timestamp<="{end_str}"')
        
    if search_text:
        # Escape quotes in search query
        escaped_search = search_text.replace('"', '\\"')
        clauses.append(f'"{escaped_search}"')
        
    return " AND ".join(clauses)

def run_gcloud_logging(filter_str: str, limit: int = 50, project: str = PROJECT_ID) -> List[Dict[str, Any]]:
    cmd = [
        "gcloud", "logging", "read",
        filter_str,
        f"--project={project}",
        f"--limit={limit}",
        "--format=json"
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if not proc.stdout.strip():
            return []
        raw_entries = json.loads(proc.stdout)
        return raw_entries
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"gcloud command failed: {err_msg}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse gcloud output as JSON: {e}")

def normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Simplify verbose GCP log entry for model consumption."""
    timestamp = entry.get("timestamp")
    severity = entry.get("severity", "DEFAULT")
    resource = entry.get("resource", {})
    labels = resource.get("labels", {})
    service = labels.get("service_name", "unknown")
    
    message = entry.get("textPayload")
    if not message and "jsonPayload" in entry:
        message = entry.get("jsonPayload")
        
    http_req = entry.get("httpRequest")
    http_summary = None
    if http_req:
        http_summary = {
            "method": http_req.get("requestMethod"),
            "url": http_req.get("requestUrl"),
            "status": http_req.get("status"),
            "latency": http_req.get("latency")
        }

    return {
        "timestamp": timestamp,
        "severity": severity,
        "service": service,
        "message": message,
        "http_request": http_summary,
        "log_name": entry.get("logName", "").split("/")[-1]
    }

def main():
    parser = argparse.ArgumentParser(description="Google Cloud Logging Inspector Tool")
    parser.add_argument("--service", default="ai-receptionist", help="Cloud Run service (e.g. ai-receptionist, ai-dashboard, all)")
    parser.add_argument("--severity", help="Minimum severity (e.g. INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--since", help="Relative window (e.g. 10m, 1h, 7d) or ISO 8601 timestamp")
    parser.add_argument("--until", help="ISO 8601 timestamp upper bound")
    parser.add_argument("--around", help="Target ISO 8601 timestamp to search around (+/- window)")
    parser.add_argument("--window-minutes", type=int, default=5, help="Minutes window around target timestamp (default: 5)")
    parser.add_argument("--search", help="Text search string (e.g. Call SID, phone, exception trace)")
    parser.add_argument("--limit", type=int, default=50, help="Max entries to return (default: 50)")
    parser.add_argument("--format", choices=["json", "compact", "raw"], default="compact", help="Output format")
    parser.add_argument("--project", default=PROJECT_ID, help="GCP project ID")

    args = parser.parse_args()

    start_dt = None
    end_dt = None

    if args.around:
        target = parse_relative_time(args.around)
        start_dt = target - timedelta(minutes=args.window_minutes)
        end_dt = target + timedelta(minutes=args.window_minutes)
    else:
        if args.since:
            start_dt = parse_relative_time(args.since)
        if args.until:
            end_dt = parse_relative_time(args.until)

    filter_str = build_log_filter(
        service=args.service,
        severity=args.severity,
        start_time=start_dt,
        end_time=end_dt,
        search_text=args.search,
        project=args.project
    )

    try:
        raw_logs = run_gcloud_logging(filter_str, limit=args.limit, project=args.project)
        normalized = [normalize_entry(e) for e in raw_logs]

        if args.format == "raw":
            print(json.dumps(raw_logs, indent=2))
        elif args.format == "json":
            print(json.dumps({"total": len(normalized), "filter": filter_str, "entries": normalized}, indent=2))
        else: # compact
            print(f"=== GCLOUD LOGS ({len(normalized)} entries | Service: {args.service}) ===")
            print(f"Filter: {filter_str}\n")
            if not normalized:
                print("No log entries found matching criteria.")
                return

            for idx, entry in enumerate(normalized, 1):
                sev = entry["severity"]
                ts = entry["timestamp"]
                srv = entry["service"]
                msg = entry["message"]
                http = entry.get("http_request")
                
                header = f"[{idx}] {ts} [{sev}] ({srv})"
                if http:
                    header += f" HTTP {http.get('method')} {http.get('status')} ({http.get('latency')})"
                print(header)
                if isinstance(msg, dict):
                    print("    " + json.dumps(msg))
                elif msg:
                    print("    " + str(msg).strip().replace("\n", "\n    "))
                print()

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
