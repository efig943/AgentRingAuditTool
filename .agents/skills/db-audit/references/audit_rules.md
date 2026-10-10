# Database Audit Rule Taxonomy & Reference

This document catalogs every audit check performed by the `db-audit` skill, including check codes, severity levels, root causes, and standard remediation steps.

---

## 1. Inventory & Schema (`INV`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `INV-001` | `WARNING` | Table has 0 rows. | Check if seeding script ran or if data was truncated. |
| `INV-ERR` | `ERROR` | Metadata query failure. | Verify Postgres role permissions on `information_schema`. |

---

## 2. Foreign Key & Referential Integrity (`FK` / `CFG`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `FK-001` | `CRITICAL` | Child record points to nonexistent or null `tenant_id`. | Run remediation SQL to delete or reassign orphaned rows to valid tenant. |
| `FK-002` | `ERROR` | `appointments.lead_id` references a nonexistent `leads.id`. | Nullify `lead_id` or re-link to correct lead record. |
| `CFG-001` | `ERROR` | Tenant exists without a `tenant_profiles` record. | Complete tenant onboarding or run onboarding seed. |
| `CFG-002` | `WARNING` | Tenant exists without an `agent_configs` entry. | Provision default system prompt and voice model. |
| `CFG-003` | `WARNING` | Tenant has no assigned phone number in `phone_numbers`. | Allocate a Twilio DID number to the tenant. |

---

## 3. Multi-Tenant Security & Isolation (`SEC`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `SEC-001` | `CRITICAL` | `appointments.tenant_id != leads.tenant_id` for linked lead. | Investigate cross-tenant leakage immediately; decouple the mismatched lead ID. |
| `SEC-002` | `CRITICAL` | `appointments.tenant_id != call_logs.tenant_id` for shared `call_sid`. | Fix tenant assignment logic in inbound webhook handler. |

---

## 4. Cross-Entity Correlation & Flow (`COR`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `COR-001` | `WARNING` | `appointments.call_sid` is missing from `call_logs`. | Check if call log insertion failed or call was initiated outside reception system. |
| `COR-002` | `WARNING` | `leads.parsed_data->>'_call_sid'` is missing from `call_logs`. | Investigate delayed or dropped call log persistence in webhook pipeline. |
| `COR-003` | `INFO` | Unlinked appointment matches a lead by caller phone and ±30m window. | Backfill `appointments.lead_id` with candidate `lead.id`. |
| `COR-004` | `WARNING` | `appointments.caller_phone` differs from linked `leads.caller_phone`. | Verify caller provided an alternative callback number during conversation. |

---

## 5. Data Hygiene & Domain Invariants (`HYG`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `HYG-001` | `WARNING` | Phone number is not in valid E.164 format (`+1...`). | Normalize phone numbers on ingestion using `phonenumbers` parser. |
| `HYG-002` | `ERROR` | `call_logs.transcript` is malformed or invalid JSON. | Validate transcript schema before DB write in `ai-receptionist`. |
| `HYG-003` | `WARNING` | Call marked 'completed' (>30s) has 0 transcript turns. | Investigate audio streaming or transcription pipeline dropouts. |
| `HYG-004` | `ERROR` | Call has negative `duration_seconds`. | Ensure call end timestamp calculation never precedes start timestamp. |
| `HYG-005` | `CRITICAL` | `appointments.start_time >= end_time`. | Correct scheduled end time to `start_time + duration_minutes`. |
| `HYG-006` | `WARNING` | Appointment duration does not match `(end_time - start_time)`. | Recompute `duration_minutes` or update interval. |

---

## 6. Integrations & Cross-System Sync (`INT` / `SYNC`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `INT-001` | `WARNING` | OAuth token in `tenant_integrations` has expired. | Trigger Google Calendar / Outlook OAuth refresh workflow. |
| `SYNC-001` | `ERROR` | `audits.db` contains audited `call_id`s absent from PostgreSQL. | Clean up stale audit entries in local SQLite or reconcile test databases. |
