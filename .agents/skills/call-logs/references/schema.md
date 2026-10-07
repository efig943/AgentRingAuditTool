# Voice Receptionist Database Schema Reference

This reference documents the Supabase PostgreSQL database tables queried by the `call-logs` skill.

---

## 1. `call_logs` Table

Stores each phone interaction handled by Twilio and the Voice AI backend (`ai-receptionist`).

| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY` | Auto-incrementing unique identifier. |
| `tenant_id` | `INTEGER` | Identifies the business tenant/client (foreign key to `tenants.id`). |
| `caller_phone` | `VARCHAR(32)` | E.164 caller phone number (e.g. `+17144397180`). |
| `status` | `VARCHAR(32)` | Final call state (`completed`, `in-progress`, `busy`, `failed`, `no-answer`). |
| `duration_seconds`| `INTEGER` | Total call audio duration in seconds. |
| `call_sid` | `VARCHAR(64)` | Twilio Call SID (starts with `CA...`). |
| `recording_url` | `TEXT` | Public or authenticated MP3 recording URL. |
| `transcript` | `JSONB` | Array of dialogue turns between AI receptionist and the caller. |
| `created_at` | `TIMESTAMP` | Call initiation timestamp. |

### `transcript` JSON Structure:
```json
[
  {
    "role": "ai",
    "text": "Hi, thank you for calling Boys with Plumbing. How can I assist you today?",
    "timestamp": "2026-10-03T15:15:20.034Z"
  },
  {
    "role": "user",
    "text": "Hi, I have a sink that needs to be repaired.",
    "timestamp": "2026-10-03T15:15:20.034Z"
  }
]
```

---

## 2. `appointments` Table

Stores appointments booked by the AI during the call.

| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY` | Appointment ID. |
| `caller_name` | `VARCHAR(128)` | Name provided by caller. |
| `caller_phone` | `VARCHAR(32)` | Phone number. |
| `start_time` | `TIMESTAMP` | Start time of the scheduled appointment. |
| `end_time` | `TIMESTAMP` | End time of the scheduled appointment. |
| `duration_minutes`| `INTEGER` | Length of appointment in minutes (typically 60). |
| `status` | `VARCHAR(32)` | `scheduled`, `cancelled`, `rescheduled`, `completed`. |
| `service_address`| `TEXT` | Street address for the dispatch/service. |
| `title` | `VARCHAR(256)` | Appointment summary title. |
| `notes` | `TEXT` | Detailed appointment description with caller details and Call SID. |
| `call_sid` | `VARCHAR(64)` | Correlated Twilio Call SID. |
| `metadata_json` | `JSONB` | Extracted JSON parameters (date, time, issue, name, phone). |
| `created_at` | `TIMESTAMP` | Record creation timestamp. |

---

## 3. `leads` Table

Stores intake information and requests extracted from incoming calls.

| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY` | Lead ID. |
| `caller_phone` | `VARCHAR(32)` | Contact phone number. |
| `parsed_data` | `JSONB` | Extracted entity payload (name, address, issue, date, time, call summary, `_call_sid`). |
| `created_at` | `TIMESTAMP` | Record creation timestamp. |
