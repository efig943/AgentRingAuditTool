# Sample Database Audit Report

Below is an authentic sample execution of `audit_database.py` against the production environment.

---

```
======================================================================
 DATABASE AUDIT SUITE - STATUS: WARNING
 Timestamp: 2026-10-10T06:12:10.684277+00:00
======================================================================

TABLE INVENTORY:
  • agent_configs         :     2 rows
  • appointments          :     6 rows
  • call_logs             :   108 rows
  • leads                 :    51 rows
  • phone_numbers         :     2 rows
  • tenant_integrations   :     1 rows
  • tenant_profiles       :    13 rows
  • tenants               :    13 rows
  • users                 :    11 rows

CROSS-DATABASE TELEMETRY:
  • Total Audited In Sqlite: 26
  • Total Postgres Calls: 108
  • Pending Audits: 82

AUDIT VIOLATIONS:
  [WARNING ] (CFG-002) tenants: Found 11 tenants missing agent_configs (voice agent unconfigured).
  [WARNING ] (CFG-003) tenants: Found 11 tenants with no inbound phone_numbers provisioned.
  [INFO    ] (COR-003) appointments: Found 3 unlinked appointments that have candidate leads matching caller_phone and timestamp window.
  [WARNING ] (HYG-001) call_logs: Found 3 records in 'call_logs.caller_phone' with non-standard E.164 phone formats.
  [WARNING ] (HYG-003) call_logs: Found 5 'completed' calls (>30s) with completely empty transcript arrays.
  [WARNING ] (INT-001) tenant_integrations: Found 1 calendar integration(s) with expired access tokens.

======================================================================
TOTAL ISSUES: 6 (Critical: 0, Error: 0, Warning: 5, Info: 1)
======================================================================
```

---

## Triage Walkthrough

1. **Multi-Tenant Security**:
   - `SEC-001` and `SEC-002` passed with 0 violations: No cross-tenant data leaks were detected between appointments, leads, or call records.
2. **Reverse Orphan Configuration (`CFG-002`, `CFG-003`)**:
   - 11 inactive or test tenants exist without prompt configs or inbound phone numbers. These tenants cannot process calls until provisioned.
3. **Correlation Opportunities (`COR-003`)**:
   - 3 appointments are currently unlinked (`lead_id IS NULL`), but corresponding lead records exist for the same caller within 30 minutes of booking. These can be reconciled and linked.
4. **Third-Party Integration Health (`INT-001`)**:
   - Google Calendar token for Tenant #1 expired on `2026-10-10 05:14:06 UTC`. The integration token refresh pipeline should be invoked.
