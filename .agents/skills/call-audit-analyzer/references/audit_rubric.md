# Production Support Call Audit Rubric & Taxonomy

This reference details the evaluation criteria used by the `call-audit-analyzer` skill to audit voice AI receptionist calls.

---

## 1. Audit Severity Classifications

| Status | Threshold Criteria | Action Required |
|---|---|---|
| **`CLEAN`** | • Caller intent satisfied or properly escalated.<br>• Database state matches spoken details (date, time, address, name).<br>• No conversational loops, cutoffs, or hallucinations.<br>• Cloud Run logs indicate nominal 200 HTTP responses and clean WebSocket closure. | No action required. Operational health nominal. |
| **`WARNING`** | • Minor conversational friction (e.g. repeated question once, minor confusion resolved).<br>• Minor delay or high latency in response (>1.5s).<br>• Caller hung up after short duration without obvious error.<br>• Non-fatal warning in GCP logs (e.g. 404 on static probe, minor audio buffer under-run). | Logged for monitoring. Support team review optional. |
| **`CRITICAL`** | • **Customer Mad / Friction**: Caller expressed explicit anger, profanity, frustration, or stated intent to complain.<br>• **DB Discrepancy**: Caller requested/confirmed an appointment, but NO appointment was saved, or saved with the WRONG date, time, or address.<br>• **Call Failure / Drop**: Conversation cut off mid-dialogue without farewell.<br>• **Backend Crash**: GCP logs show unhandled 500 error, container restart, or broken WebSocket connection during active dialogue. | High-priority alert dispatched to support engineering. Immediate customer follow-up required. |

---

## 2. Incident Categories (`issue_types`)

1. **`CUSTOMER_SENTIMENT`**:
   - Caller expresses anger, annoyance, irritation, or dissatisfaction with service or AI.
   - Caller expresses confusion due to robotic behavior.

2. **`WEIRD_INTERACTION`**:
   - AI repeats prompts or loops greetings.
   - AI speaks over caller (barge-in failure).
   - AI hallucinates information or misunderstands clear caller statements.
   - Conversation abruptly terminates while caller is still speaking.

3. **`DB_DISCREPANCY`**:
   - Spoken appointment date/time != Database `start_time` / `end_time`.
   - Spoken address != Database `service_address`.
   - Spoken name != Database `caller_name`.
   - Caller confirmed a booking, but zero rows exist in `appointments`.
   - Caller submitted inquiry, but zero rows exist in `leads`.

4. **`CALL_FAILURE`**:
   - Immediate disconnect (0–2 seconds duration, 0 spoken turns).
   - Abrupt socket drop before natural resolution.

5. **`INFRASTRUCTURE_ERROR`**:
   - Cloud Run HTTP 5xx error logged in `ai-receptionist` around call timestamp.
   - Container crash / out-of-memory restart in `ai-receptionist`.
   - Audio resampling or WebSocket buffer timeout.

---

## 3. Output Schema Standard

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
  "summary": "Customer successfully scheduled sink repair for Monday Oct 5 at 9:00 AM; record matches DB.",
  "customer_sentiment": "Positive",
  "db_comparison": {
    "caller_requested": "Sink repair on Monday Oct 5 at 9:00 AM at 1375 Michelle Avenue for Ethan",
    "database_recorded": "Appointment ID 106 for Ethan on 2026-10-05 09:00:00 at 1375 Michelle Avenue",
    "is_consistent": true,
    "mismatch_details": null
  },
  "incident_report": "Caller requested sink repair. AI suggested Monday Oct 5 at 9 AM due to Sunday closure. Caller accepted, provided address and name. Appointment was recorded accurately in appointments table.",
  "recommended_action": "None required."
}
```
