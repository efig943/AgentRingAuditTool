# Audit Agents Integration Rule

This workspace contains a multi-agent audit suite under `.agents/skills/`. When interacting in the chat, the assistant automatically routes requests to the appropriate specialized audit skill.

---

## Agent Routing & Chat Triggers

| User Chat Prompt | Active Skill | Backend Action |
|---|---|---|
| **"full audit"**, **"audit all"**, **"system audit"**, **"check everything"** | [`full-audit`](../skills/full-audit/SKILL.md) | Executes `run_full_audit.py`, runs all domain audits, and outputs the Master Scorecard. |
| **"audit db"**, **"check database"**, **"audit tables"**, **"check foreign keys"** | [`db-audit`](../skills/db-audit/SKILL.md) | Executes `audit_database.py`, queries all 9 Postgres tables, checks multi-tenant isolation and data hygiene. |
| **"audit code"**, **"check codebase"**, **"check dependencies"**, **"check gcloud deployment"** | [`code-audit`](../skills/code-audit/SKILL.md) | Executes `audit_codebase.py`, verifies AST, `requirements.txt`, `.env.example`, and Cloud Run port/readiness. |
| **"audit call <ID>"**, **"check call <SID>"**, **"did call drop?"** | [`call-audit-analyzer`](../skills/call-audit-analyzer/SKILL.md) | Synthesizes transcript from `call-logs` with Cloud Run telemetry from `gcloud-logs`, evaluates sentiment and DB booking fidelity. |
| **"audit stripe"**, **"read stripe"**, **"stripe balance"**, **"reconcile billing"** | [`stripe-audit`](../skills/stripe-audit/SKILL.md) | Executes `audit_stripe.py`, queries live balances, subscriptions, MRR, and reconciles against `tenants`. |
| **"gcloud logs"**, **"check cloud run"**, **"backend errors"** | [`gcloud-logs`](../skills/gcloud-logs/SKILL.md) | Queries Google Cloud Logging for `ai-receptionist` and `ai-dashboard` services. |

---

## Output Standard in Chat

Whenever an audit is triggered in chat:
1. Run the respective audit tool.
2. Present findings concisely with domain status badges (🟢 HEALTHY, 🟡 WARNING, 🟠 DEGRADED, 🔴 CRITICAL).
3. Always highlight immediate actionable fixes (SQL commands, requirements changes, or environment fixes).
