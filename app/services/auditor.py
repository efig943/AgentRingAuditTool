import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from google import genai
from app.core import config
from app.db.postgres import fetch_call_by_id, fetch_linked_records
from app.db.storage import save_audit, get_audit

logger = logging.getLogger("callAuditAgent.auditor")

def get_genai_client():
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured in .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)

def analyze_call_heuristic(call: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fast rule-based heuristic checks for zero-length or empty calls.
    Returns audit dict if definitive heuristic failure is met, otherwise None.
    """
    transcript = call.get("transcript") or []
    duration = call.get("duration_seconds", 0)

    # Completely blank call / 0-1 sec abandoned call
    if len(transcript) == 0 and duration <= 2:
        return {
            "status": "WARNING",
            "has_issues": True,
            "customer_mad": False,
            "weird_interaction": True,
            "db_discrepancy": False,
            "call_failure": True,
            "issue_types": ["CALL_FAILURE", "ZERO_DURATION"],
            "summary": f"Immediate call disconnect with 0 interaction turns (duration: {duration}s).",
            "customer_sentiment": "Neutral",
            "db_comparison": {
                "caller_requested": "None (call dropped immediately)",
                "database_recorded": "No records",
                "is_consistent": True,
                "mismatch_details": None
            },
            "incident_report": f"Call ended immediately after {duration} seconds with zero spoken turns. Likely a hangup, misdial, or immediate network drop.",
            "recommended_action": "Check Twilio stream logs if frequent. No database action required."
        }
    return None

def audit_call(call_id: int, force_recheck: bool = False) -> Dict[str, Any]:
    """
    Perform a full production support audit on a single call.
    1. Fetches call and correlated appointments & leads from Supabase PostgreSQL.
    2. Runs Gemini 3.8 Flash structured inspection on transcript vs DB state.
    3. Persists audit record in local SQLite DB.
    """
    # Check if already audited and not forcing recheck
    if not force_recheck:
        existing = get_audit(call_id)
        if existing:
            return existing

    call = fetch_call_by_id(call_id)
    if not call:
        raise ValueError(f"Call with ID {call_id} not found in database.")

    call_sid = call.get("call_sid")
    caller_phone = call.get("caller_phone", "")
    created_at = call.get("created_at")
    transcript = call.get("transcript", [])
    duration = call.get("duration_seconds", 0)

    # Fetch correlated DB records
    linked_db = fetch_linked_records(call_sid, caller_phone, created_at)
    appointments = linked_db.get("appointments", [])
    leads = linked_db.get("leads", [])

    created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)

    # Check heuristics first
    heuristic_res = analyze_call_heuristic(call)
    if heuristic_res:
        audit_record = {
            "call_id": call_id,
            "call_sid": call_sid,
            "caller_phone": caller_phone,
            "duration_seconds": duration,
            "call_created_at": created_at_str,
            "transcript": transcript,
            "db_state": linked_db,
            "audited_at": datetime.now().isoformat(),
            **heuristic_res
        }
        save_audit(audit_record)
        return audit_record

    # Perform Gemini 3.8 Flash analysis
    client = get_genai_client()

    prompt = f"""
You are a Senior Production Support Engineer auditing an automated voice AI receptionist call.
Your mission is to audit this call, diagnose any anomalies, and identify whether any customer issues or database discrepancies occurred.

### INCIDENT CATEGORIES TO DETECT:
1. CUSTOMER_SENTIMENT: 
   - Did the caller express anger, frustration, irritation, annoyance, profanity, or deep dissatisfaction?
   - Did the caller complain about previous service, long wait times, or AI inability to answer?

2. WEIRD_INTERACTION:
   - AI repeated phrases, stuttered, looped greeting messages, or spoke over itself.
   - AI misunderstood caller statements, gave nonsensical answers, or hallucinated services not offered.
   - AI abruptly closed/terminated the conversation without waiting for the caller.
   - Caller hung up in confusion or irritation.

3. DB_DISCREPANCY:
   - The caller requested or confirmed an appointment/booking, but NO appointment was created in the database.
   - The caller agreed to a specific date/time (e.g. Oct 6 at 9:00 AM), but the database has a different date/time (e.g. Oct 2 at 10:00 AM).
   - The caller requested to reschedule or cancel, but the database appointment status is wrong or unmodified.
   - Name, address, or phone in the database does not match what the caller stated.
   - Caller provided lead/service information, but no lead was recorded.

4. CALL_FAILURE:
   - Call cut off in mid-sentence or prematurely hung up.
   - Audio buffer issues or stream crash.

### CALL DATA:
- Call ID: {call_id}
- Call SID: {call_sid}
- Caller Phone: {caller_phone}
- Call Duration: {duration} seconds
- Call Timestamp: {created_at_str}

### CALL TRANSCRIPT:
{json.dumps(transcript, indent=2)}

### DATABASE STATE (Appointments & Leads retrieved for this caller/call SID):
Appointments: {json.dumps(appointments, indent=2)}
Leads: {json.dumps(leads, indent=2)}

### INSTRUCTIONS:
- If NO issues happened and the database matches caller intent perfectly, set status="CLEAN", has_issues=false.
- If there are minor weird interactions or minor misalignments, set status="WARNING", has_issues=true.
- If the customer was angry/upset, or a confirmed appointment was omitted/corrupted/scheduled on the wrong date, set status="CRITICAL", has_issues=true.

Return a valid JSON object matching this schema:
{{
  "status": "CLEAN" | "WARNING" | "CRITICAL",
  "has_issues": true | false,
  "customer_mad": true | false,
  "weird_interaction": true | false,
  "db_discrepancy": true | false,
  "call_failure": true | false,
  "issue_types": ["CUSTOMER_SENTIMENT" | "WEIRD_INTERACTION" | "DB_DISCREPANCY" | "CALL_FAILURE"],
  "summary": "Concise 1-sentence diagnostic summary for support dashboard",
  "customer_sentiment": "Positive" | "Neutral" | "Frustrated" | "Angry",
  "db_comparison": {{
      "caller_requested": "Exact appointment/service details requested by caller in transcript",
      "database_recorded": "Exact details recorded in database appointments/leads (or 'None recorded')",
      "is_consistent": true | false,
      "mismatch_details": "Clear description of mismatch if any, otherwise null"
  }},
  "incident_report": "Comprehensive Production Support incident report explaining what happened, citing transcript quotes, and evaluating system behavior.",
  "recommended_action": "Actionable instructions for customer support or engineering to resolve or prevent this issue."
}}
"""

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    try:
        parsed_result = json.loads(response.text)
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}\nRaw: {response.text}")
        parsed_result = {
            "status": "WARNING",
            "has_issues": True,
            "customer_mad": False,
            "weird_interaction": True,
            "db_discrepancy": False,
            "call_failure": False,
            "issue_types": ["AUDIT_PARSER_ERROR"],
            "summary": "Call analyzed but JSON parsing encountered an unexpected structure.",
            "customer_sentiment": "Neutral",
            "db_comparison": {
                "caller_requested": "Unknown",
                "database_recorded": "Unknown",
                "is_consistent": False,
                "mismatch_details": "Failed to parse auditor response"
            },
            "incident_report": response.text,
            "recommended_action": "Review call manually."
        }

    audit_record = {
        "call_id": call_id,
        "call_sid": call_sid,
        "caller_phone": caller_phone,
        "duration_seconds": duration,
        "call_created_at": created_at_str,
        "transcript": transcript,
        "db_state": linked_db,
        "audited_at": datetime.now().isoformat(),
        **parsed_result
    }

    save_audit(audit_record)
    return audit_record
