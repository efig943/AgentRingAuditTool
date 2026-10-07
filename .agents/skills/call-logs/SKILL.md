---
name: call-logs
description: >-
  Inspect, query, and extract voice receptionist call records from PostgreSQL,
  including call transcripts, duration, status, caller phone numbers, and correlated
  appointments and leads. Use this skill when you need to inspect call data or pull
  call transcripts for auditing.
---

# Call Logs Inspection Skill

This skill provides procedures and CLI tools to query production voice receptionist call records from the Supabase PostgreSQL database, extract full conversation transcripts, and retrieve correlated appointment and lead rows.

---

## Capabilities

1. **Single Call Deep Inspection**: Fetch complete transcript, duration, audio URL, caller phone, and correlated appointments and leads by `call_id` or `call_sid`.
2. **List & Sift Calls**: Retrieve recent calls with pagination, filter for un-audited calls, or filter by timestamp.
3. **Automated DB Correlation**: Automatically maps Twilio `call_sid` and caller phone numbers to `appointments` and `leads` records within the call's time window.

---

## Tooling & Usage

Use the helper script [`fetch_call_logs.py`](./scripts/fetch_call_logs.py) via terminal execution:

### 1. Inspect a Specific Call by ID
```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-id <CALL_ID> --format summary
```
*Use `--format json` to get machine-readable JSON.*

### 2. Inspect a Call by Twilio Call SID
```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-sid <CALL_SID> --format json
```

### 3. List Un-audited Calls
```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --unaudited --limit 10 --format list
```

### 4. Query Recent Calls Since a Given Date
```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --since "2026-10-01T00:00:00Z" --limit 20 --format list
```

---

## References

- Consult [schema.md](./references/schema.md) for full descriptions of `call_logs`, `appointments`, and `leads` table columns and JSON data structures.
