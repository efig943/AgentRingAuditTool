# Sample Call Audit Workflow Walkthrough

This walkthrough demonstrates how the `call-audit-analyzer` orchestrator skill executes an audit on **Call #114**.

---

## Step 1: Query Call & Transcript Data via `call-logs`

```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-id 114 --format json
```

### Extracted Evidence:
- **Call SID**: `CAcb72e35974bd008bc8f378fd6fa5ed8f`
- **Timestamp**: `2026-10-03T15:15:08.716864`
- **Duration**: `73s`
- **Caller Phone**: `+17144397180`
- **Transcript**: Caller requested sink repair for Monday Oct 5 at 9:00 AM, address 1375 Michelle Avenue, name Ethan.
- **Correlated DB**: Appointment ID `106` exists with start_time `2026-10-05T09:00:00`, address `1375 Michelle Avenue`, name `Ethan`. Lead ID `68` exists with matching metadata.

---

## Step 2: Query Infrastructure Telemetry via `gcloud-logs`

```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "2026-10-03T15:15:08Z" --window-minutes 10 --format compact
```

### Extracted Evidence:
- Service `ai-receptionist` was running nominally.
- No HTTP 5xx errors or container crash restarts logged during this window.
- Normal request completions (HTTP 200).

---

## Step 3: Synthesize Findings

1. **Customer Sentiment**: Positive / relaxed (caller made light joke about music, AI answered politely).
2. **Dialogue Flow**: Nominal. 15 turns with natural turn-taking and appointment confirmation.
3. **Database Consistency**: 100% consistent. Spoken date, time, and address match `appointments` row 106.
4. **Cloud Infrastructure**: Healthy. No disconnects or server errors.
5. **Verdict**: `CLEAN` (`has_issues: false`).

---

## Step 4: Persist Finding into `audits.db`

```bash
python3 .agents/skills/call-audit-analyzer/scripts/save_audit_result.py << 'EOF'
{
  "call_id": 114,
  "status": "CLEAN",
  "has_issues": false,
  "customer_mad": false,
  "weird_interaction": false,
  "db_discrepancy": false,
  "call_failure": false,
  "issue_types": [],
  "summary": "Customer Ethan successfully booked sink repair for Monday Oct 5 at 9 AM, accurately reflected in appointments table.",
  "customer_sentiment": "Positive",
  "db_comparison": {
    "caller_requested": "Sink repair on Monday Oct 5 at 9:00 AM at 1375 Michelle Avenue for Ethan",
    "database_recorded": "Appointment ID 106 for Ethan on 2026-10-05 09:00 at 1375 Michelle Avenue",
    "is_consistent": true,
    "mismatch_details": null
  },
  "incident_report": "Normal conversation flow. Caller joked about Kanye song, AI politely handled and collected name and address.",
  "recommended_action": "None. Optimal performance."
}
EOF
```

The record is immediately written to `audits.db` and displayed in the CallAudit Pro operations dashboard.
