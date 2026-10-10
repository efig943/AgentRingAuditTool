---
name: db-audit
description: >-
  Inspect, query, and comprehensively audit the entire PostgreSQL database.
  Validates schema health, referential integrity, foreign key consistency, orphaned records
  across tenants/calls/leads/appointments, data hygiene (E.164 phones, JSON structures,
  durations, timestamps), multi-tenant isolation, and local audits.db synchronization.
---

# Database Integrity & Schema Audit Skill

This skill provides automated, production-grade audits of the entire PostgreSQL database backing the voice receptionist platform, cross-referenced with local SQLite telemetry. It verifies that tables are properly populated, foreign key relationships are strictly maintained, multi-tenant boundaries are never breached, and conversational records (calls, appointments, leads) correlate accurately.

---

## Capabilities & Audit Pillars

1. **Table Inventory & Sizing Metrics**:
   - Queries all 9 core platform tables: `tenants`, `tenant_profiles`, `agent_configs`, `phone_numbers`, `tenant_integrations`, `users`, `call_logs`, `leads`, `appointments`.
   - Audits row counts, column schemas, sequence states, and empty tables.

2. **Referential Integrity & Orphan Detection**:
   - **Forward Orphans**: Child records referencing nonexistent `tenants.id` or broken `appointments.lead_id`.
   - **Reverse Orphans**: Tenants missing vital operational configuration (e.g. missing `agent_configs`, no assigned `phone_numbers`, or incomplete onboarding `tenant_profiles`).

3. **Multi-Tenant Isolation & Cross-Entity Consistency**:
   - **Multi-Tenant Leak Checks**: Validates that appointments and linked leads belong to the *same* tenant (`appointments.tenant_id == leads.tenant_id`).
   - **Call Log Correlation**: Ensures `appointments.call_sid` and `leads.parsed_data->>'_call_sid'` map to identical tenants in `call_logs`.
   - **Candidate Link Detection**: Identifies unlinked appointments (`lead_id IS NULL`) where a matching lead exists for that caller within ±30 minutes.
   - **Contact Discrepancies**: Detects phone number mismatches between appointments and linked leads.

4. **Data Hygiene & Domain Invariants**:
   - **E.164 Format Validation**: Enforces international E.164 standards across all phone fields (`+1XXXXXXXXXX`).
   - **JSON / JSONB Schema Integrity**: Verifies `call_logs.transcript` array turn structure, `leads.parsed_data`, and `appointments.metadata_json`.
   - **Temporal Invariants**: Verifies appointment intervals (`start_time < end_time`) and duration calculations (`(end - start) == duration_minutes`).
   - **Call Log Sanity**: Flags negative durations or completed calls (>30s) with 0 transcript turns.
   - **OAuth Health**: Detects expired access tokens in `tenant_integrations` (e.g., Google Calendar).

5. **Cross-System Telemetry & Audit Sync**:
   - Cross-checks the local `audits.db` (SQLite) audit store against PostgreSQL `call_logs` to detect phantom audit records and calculate un-audited backlog volume.

---

## Tooling & Usage

Use the CLI auditor [`audit_database.py`](./scripts/audit_database.py) from the workspace root:

### 1. Run Complete Database Audit (Summary View)
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --format summary
```

### 2. Export Markdown Report for Incident Reviews
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --format markdown --export db_audit_report.md
```

### 3. Machine-Readable JSON (CI/CD Pipelines)
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --format json --min-severity error
```

### 4. Scope Audit to a Single Table
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --table appointments --format summary
```

### 5. Generate Automated Remediation SQL
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --fix-sql
```

---

## Exit Codes

| Exit Code | Status | Meaning |
|---|---|---|
| `0` | `CLEAN` | All integrity checks, invariants, and correlations passed. |
| `1` | `WARNING` | Non-fatal hygiene warnings, expired tokens, or unlinked candidates. |
| `2` | `ERROR / CRITICAL` | Referential integrity breaks, foreign key violations, or cross-tenant leaks. |
| `3` | `FATAL` | Connection error, missing `DATABASE_URL`, or fatal query exception. |

---

## References

- [audit_rules.md](./references/audit_rules.md) &mdash; Detailed taxonomy of all audit error codes, severity ratings, and remediation procedures.
- [sample_audit_report.md](./examples/sample_audit_report.md) &mdash; Example output and triage workflow.
