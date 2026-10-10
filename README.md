# AgentRing &mdash; Financials & Voice AI Call Audit System

A production platform for Voice AI receptionists and operations:
1. **Financials & Unit Economics Dashboard**: Real-time executive console reconciling live Stripe subscriptions, Twilio telephony, Gemini AI costs, gross profit margins, tenant ledgers, and interactive SaaS growth modeling.
2. **Antigravity Multi-Agent Audit Suite**: Specialized, decoupled skills (`full-audit`, `db-audit`, `code-audit`, `call-logs`, `gcloud-logs`, `call-audit-analyzer`) that dissect the database, codebase, conversational voice records, and Google Cloud Run infrastructure backing `agentring.dev`.

---

## 📁 Project Structure

```
callAuditAgent/
├── .agents/
│   ├── rules/
│   │   └── audit_agents.md               # Workspace chat integration rule & triggers
│   └── skills/                           # Antigravity Specialized Agent Skills
│       ├── full-audit/                   # Master Full-System Orchestrator
│       │   ├── SKILL.md                  # Unified audit runbook
│       │   └── scripts/run_full_audit.py # Master CLI runner & executive scorecard
│       ├── db-audit/                     # PostgreSQL Database & Relational Auditor
│       │   ├── SKILL.md                  # Database audit procedures
│       │   ├── scripts/audit_database.py # CLI: queries all 9 tables, FKs, leaks, hygiene
│       │   ├── references/audit_rules.md # Rule taxonomy (FK, SEC, COR, HYG, INT)
│       │   └── examples/sample_audit_report.md
│       ├── code-audit/                   # Code Quality, Security & Cloud Run Auditor
│       │   ├── SKILL.md                  # Static analysis & deployment runbook
│       │   ├── scripts/audit_codebase.py # CLI: AST syntax, secrets, requirements, Cloud Run
│       │   ├── references/code_rules.md  # Rule taxonomy (SYN, SEC, DEP, ENV, GCP)
│       │   └── examples/sample_code_audit.md
│       ├── stripe-audit/                 # Stripe Financials & Subscription Auditor
│       │   ├── SKILL.md                  # Stripe audit procedures
│       │   ├── scripts/audit_stripe.py   # CLI: live balances, MRR, fees, DB reconciliation
│       │   ├── references/stripe_rules.md# Rule taxonomy (BAL, SUB, CHG, REC)
│       │   └── examples/sample_stripe_audit.md
│       ├── call-logs/                    # Voice Call Database Records
│       │   ├── SKILL.md                  # Progressive disclosure call extractor
│       │   ├── scripts/fetch_call_logs.py# CLI: fetch calls, transcripts, appointments
│       │   └── references/schema.md      # PostgreSQL schema reference
│       ├── gcloud-logs/                  # Google Cloud Run Infrastructure Logs
│       │   ├── SKILL.md                  # Telemetry query procedures
│       │   ├── scripts/fetch_gcloud_logs.py # CLI: Cloud Run log extractor
│       │   └── references/gcp_services.md# Cloud Run architecture mappings
│       └── call-audit-analyzer/          # Voice Call Diagnostic Orchestrator
│           ├── SKILL.md                  # Synthesizes call transcripts + cloud telemetry
│           ├── scripts/save_audit_result.py # Writes findings into local audits.db
│           ├── references/audit_rubric.md# Incident taxonomy & severity criteria
│           └── examples/sample_audit_workflow.md
├── app/                                  # Core application source code
│   ├── core/
│   │   └── config.py                     # Central environment, rates, and paths
│   ├── db/
│   │   ├── postgres.py                   # Production PostgreSQL queries
│   │   └── storage.py                    # Local SQLite persistence (audits.db)
│   ├── services/
│   │   ├── financials.py                 # Live Stripe, Twilio, and GCP unit economics
│   │   ├── auditor.py                    # Auditor service
│   │   ├── daemon.py                     # Background worker daemon
│   │   └── email_service.py              # Gmail SMTP incident notification dispatch
│   └── api/
│       └── server.py                     # FastAPI application & API endpoints
├── static/                               # Financials Command Center Web UI
│   ├── index.html                        # Single-page operations dashboard
│   ├── styles.css                        # Dark-mode glassmorphism styling
│   └── app.js                            # Live polling, charts, and simulator engine
├── audits.db                             # Local SQLite database for audit findings
├── server.py                             # Root launcher script (runs uvicorn server)
├── start.sh                              # One-click startup script
├── requirements.txt                      # Python dependencies
├── .env                                  # Environment secrets
└── README.md                             # Architecture documentation & guide
```

---

## 🛡️ Antigravity Multi-Agent Audit Constellation

All audit skills are natively integrated both **within the AI chat interface** and via **standalone CLI scripts**.

```
                     ┌───────────────────────────────┐
                     │          full-audit           │
                     │  (Master System Orchestrator) │
                     └───────────────┬───────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
  ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
  │  code-audit   │           │   db-audit    │           │  call-logs &  │
  │ (Code & GCP)  │           │ (PostgreSQL)  │           │  gcloud-logs  │
  ├───────────────┤           ├───────────────┤           ├───────────────┤
  │• AST & Syntax │           │• 9 Tables     │           │• 108 Calls    │
  │• requirements │           │• Foreign Keys │           │• Transcripts  │
  │• .env Parity  │           │• Tenant Leaks │           │• Cloud Run    │
  │• Cloud Run    │           │• Hygiene/E.164│           │• Audits Sync  │
  └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      ▼
                      ┌───────────────────────────────┐
                      │ Master Synthesizer & Reporter │
                      │   • Executive Scorecard       │
                      │   • P0 Deployment Blockers    │
                      │   • Domain Dissections        │
                      │   • Actionable Fix Commands   │
                      └───────────────────────────────┘
```

### 1. `full-audit` (Master System Orchestrator)
Coordinates all domain auditors, aggregates their findings, and outputs an executive scorecard.
```bash
python3 .agents/skills/full-audit/scripts/run_full_audit.py --format summary
python3 .agents/skills/full-audit/scripts/run_full_audit.py --format markdown --export master_audit.md
```

### 2. `db-audit` (PostgreSQL Database & Relational Integrity)
Connects to Supabase PostgreSQL, auditing all 9 tables for foreign key integrity, cross-tenant isolation leaks (`SEC-001`/`SEC-002`), candidate unlinked leads (`COR-003`), E.164 phone formats (`HYG-001`), JSON transcript validity, and expired OAuth tokens.
```bash
python3 .agents/skills/db-audit/scripts/audit_database.py --format summary
python3 .agents/skills/db-audit/scripts/audit_database.py --table appointments
python3 .agents/skills/db-audit/scripts/audit_database.py --fix-sql
```

### 3. `code-audit` (Codebase Quality, Security & Cloud Run Readiness)
AST-based static analysis engine with zero external dependencies. Validates Python syntax, scans for hardcoded secrets/tokens, verifies dependency completeness in `requirements.txt`, checks `.env.example` coverage, and enforces Google Cloud Run deployment requirements for `agentring.dev` (`$PORT` binding, `.gcloudignore`, host binding).
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --format summary
python3 .agents/skills/code-audit/scripts/audit_codebase.py --min-severity error
python3 .agents/skills/code-audit/scripts/audit_codebase.py --path app/services/financials.py
```

### 4. `stripe-audit` (Live Stripe Balances & Subscription Reconciliation)
Queries real-time Stripe balances ($3,581.73), active MRR ($300/mo), processing fees, and performs bidirectional reconciliation against PostgreSQL `tenants` to ensure zero entitlement leaks or unmapped subscriptions.
```bash
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --format summary
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --format markdown --export stripe_audit.md
```

### 5. `call-logs` & `call-audit-analyzer` (Conversational Voice AI)
Extracts turn-by-turn dialogue from PostgreSQL, cross-correlates with Google Cloud Logging telemetry, evaluates customer sentiment, and verifies database appointment fidelity.
```bash
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-id 114 --format summary
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --unaudited --limit 5 --format list
```

### 5. `gcloud-logs` (Google Cloud Run Telemetry)
Queries Google Cloud Logging for `ai-receptionist` and `ai-dashboard` under project `ai-vp-506402`.
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "2026-10-03T15:15:08Z" --window-minutes 5
```

---

## 💬 Interactive Chat Integration

You can trigger any audit directly in the Antigravity chat:

- *"Run a full audit"* &mdash; Dissects code, database, calls, and cloud logs, pasting the unified Master Scorecard.
- *"Audit the database"* &mdash; Inspects all 9 tables, foreign keys, and multi-tenant isolation.
- *"Audit the code"* &mdash; Checks syntax, dependencies, secrets, and Cloud Run readiness.
- *"Audit call #114"* &mdash; Cross-references transcript, customer sentiment, and Cloud Run logs.

---

## 💰 Financials & Unit Economics Command Center

Runs locally at **[http://localhost:5050](http://localhost:5050)** (or `$PORT` on Cloud Run).

- **Live Provider Integration**: Real-time sync of Stripe payments, Twilio voice balances/rates, and GCP project billing.
- **Unit Economics**: Calculates direct COGS ($0.0955/min blended rate), average call cost, gross margin, and team commission splits.
- **Interactive Growth Simulator**: Adjust sliders for clients, call volumes, call durations, and plan tiers (Starter, Growth, Scale).
- **Per-Tenant Ledger**: Detailed P&L breakdown by business tenant.

---

## 🚀 Quick Start

### 1. Launch the Financials Dashboard
```bash
./start.sh
# or: python3 server.py
```
Open **[http://localhost:5050](http://localhost:5050)** in your browser.

### 2. Run Audits from CLI
```bash
# Run Master Full System Audit
python3 .agents/skills/full-audit/scripts/run_full_audit.py
```

---

## ⚙️ Configuration (`.env`)

- `DATABASE_URL`: Production Supabase PostgreSQL connection string.
- `STRIPE_SECRET_KEY`: Stripe API key for live revenue and subscription metrics.
- `TWILIO_ACCOUNT_SID`: Twilio account identifier.
- `TWILIO_AUTH_TOKEN`: Twilio API token for live balance and billing records.
- `GEMINI_API_KEY`: Google GenAI API key.
- `ALERT_RECIPIENT_EMAIL`: Incident email alert destination (`ethan.figueredo943@gmail.com`).
- `DASHBOARD_PORT`: Local server port (default: `5050`, or auto-reads `$PORT` on Cloud Run).
