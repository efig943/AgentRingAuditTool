---
name: call-audit-analyzer
description: >-
  Orchestrate end-to-end voice receptionist call audits by synthesizing call logs & transcripts
  (via call-logs skill) with infrastructure & Cloud Run telemetry (via gcloud-logs skill)
  to identify customer friction, conversational flow anomalies, database discrepancies, and backend
  dropouts, persisting audit findings into audits.db. Use this skill whenever you need to audit,
  diagnose, or investigate a voice call.
---

# Call Audit Analyzer (Orchestrator Skill)

This skill serves as the production support audit orchestrator. Instead of making blind, isolated LLM calls, it combines conversational data from the **`call-logs`** skill with backend infrastructure telemetry from the **`gcloud-logs`** skill to deliver comprehensive, cross-correlated root-cause incident diagnoses.

---

## Architecture: Composite Skill Workflow

```
           ┌───────────────────────┐
           │  call-audit-analyzer  │
           │ (Orchestrator Skill)  │
           └───────────┬───────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
┌──────────────┐               ┌───────────────┐
│  call-logs   │               │  gcloud-logs  │
│ (PostgreSQL) │               │  (Cloud Run)  │
├──────────────┤               ├───────────────┤
│ • Transcripts│               │ • HTTP Latency│
│ • Caller Info│               │ • 500 Errors  │
│ • Appts / DB │               │ • Socket Drops│
└──────┬───────┘               └───────┬───────┘
       │                               │
       └───────────────┬───────────────┘
                       ▼
           ┌───────────────────────┐
           │ Multi-Layer Analysis  │
           │   • Sentiment/Mad?    │
           │   • DB Discrepancy?   │
           │   • Cloud Dropout?    │
           └───────────┬───────────┘
                       ▼
           ┌───────────────────────┐
           │  save_audit_result.py │
           │   • audits.db SQLite  │
           │   • Alert Email (opt) │
           └───────────────────────┘
```

---

## Step-by-Step Procedure

### Step 1: Retrieve Call Logs & Transcript
Use the [`call-logs`](../call-logs/SKILL.md) skill to pull the target call details, turn-by-turn transcript, and correlated appointment/lead records:

```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-id <CALL_ID> --format json
```
*Note the `created_at` timestamp, `call_sid`, `duration_seconds`, and caller phone number.*

### Step 2: Retrieve Correlated GCP Cloud Run Logs
Use the [`gcloud-logs`](../gcloud-logs/SKILL.md) skill to query Cloud Run telemetry for the call's timeframe:

```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "<CALL_TIMESTAMP>" --window-minutes 5 --format compact
```
*If looking for crashes or socket drops, check for `ERROR` severity or search for the `call_sid`:*
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --search "<CALL_SID>" --since 7d
```

### Step 3: Multi-Layer Diagnostic Evaluation
Cross-reference the evidence across 4 layers against the [audit_rubric.md](./references/audit_rubric.md):

1. **Customer Sentiment**:
   - Did the caller express anger, irritation, profanity, or frustration?
   - Sentiment label: `Positive`, `Neutral`, `Frustrated`, or `Angry`.
2. **Conversational Flow**:
   - Did the AI repeat phrases, loop greetings, talk over the user, or hallucinate?
   - Did the call end abruptly without goodbye?
3. **Database Integrity**:
   - Did the caller request an appointment date/time that matches the database `appointments` record?
   - Did caller provide address/name that matches the recorded lead/appointment?
   - If caller requested an appointment but no record was made, mark `db_discrepancy: true`.
4. **Cloud Infrastructure Telemetry**:
   - Did Cloud Run return HTTP 5xx errors or fail health probes around the call time?
   - Did the WebSocket drop unexpectedly?

### Step 4: Formulate the Audit JSON Payload
Build a structured audit record adhering to the standard schema:

```json
{
  "call_id": 114,
  "status": "CLEAN",
  "has_issues": false,
  "customer_mad": false,
  "weird_interaction": false,
  "db_discrepancy": false,
  "call_failure": false,
  "issue_types": [],
  "summary": "Customer successfully booked appointment; dialogue and database fully aligned.",
  "customer_sentiment": "Positive",
  "db_comparison": {
    "caller_requested": "Exact date, time, and service requested by caller",
    "database_recorded": "Exact record found in appointments/leads (or 'None')",
    "is_consistent": true,
    "mismatch_details": null
  },
  "incident_report": "Detailed synthesis referencing transcript quotes and Cloud Run telemetry.",
  "recommended_action": "Actionable instructions for support or engineering."
}
```

### Step 5: Persist Audit Result & Alert
Execute the persistence helper [`save_audit_result.py`](./scripts/save_audit_result.py) to save the verdict into `audits.db` (which immediately updates the CallAudit dashboard):

```bash
python3 .agents/skills/call-audit-analyzer/scripts/save_audit_result.py << 'EOF'
<AUDIT_JSON_PAYLOAD>
EOF
```
*To dispatch an alert email if issues are detected, add `--send-alert`.*

---

## References & Examples

- [audit_rubric.md](./references/audit_rubric.md) &mdash; Evaluation taxonomy, status definitions, and resolution guidelines.
- [sample_audit_workflow.md](./examples/sample_audit_workflow.md) &mdash; Walkthrough of an end-to-end audit on Call #114.
