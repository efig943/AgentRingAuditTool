# AgentRing &mdash; Financials & Voice AI Call Audit System

A dual-tier production platform for Voice AI receptionists:
1. **Financials & Unit Economics Dashboard**: A real-time executive operations console reconciling live Stripe subscriptions, Twilio telephony, Gemini AI costs, gross profit margins, tenant ledgers, and interactive SaaS growth modeling.
2. **Antigravity Audit Skills**: A decoupled, multi-skill agentic architecture (`call-logs`, `gcloud-logs`, and `call-audit-analyzer`) that diagnoses customer friction, conversational flow anomalies, database discrepancies, and cloud infrastructure dropouts.

---

## 📁 Project Structure

```
callAuditAgent/
├── .agents/skills/                       # Antigravity Specialized Agent Skills
│   ├── call-logs/                        # Skill 1: Supabase PostgreSQL call records
│   │   ├── SKILL.md                      # Skill runbook & progressive disclosure spec
│   │   ├── scripts/fetch_call_logs.py    # CLI tool: fetch calls, transcripts, appointments
│   │   └── references/schema.md          # PostgreSQL database schema documentation
│   ├── gcloud-logs/                      # Skill 2: Google Cloud Run telemetry
│   │   ├── SKILL.md                      # Skill runbook for infrastructure logs
│   │   ├── scripts/fetch_gcloud_logs.py  # CLI tool: query & filter Cloud Run logs
│   │   └── references/gcp_services.md    # Cloud Run architecture & log stream mappings
│   └── call-audit-analyzer/              # Skill 3: Orchestrator / Multi-layer auditor
│       ├── SKILL.md                      # Composite workflow: synthesizes call + cloud logs
│       ├── scripts/save_audit_result.py  # Persistence CLI: writes findings into audits.db
│       ├── references/audit_rubric.md    # Incident taxonomy & severity criteria
│       └── examples/sample_audit_workflow.md # Step-by-step walkthrough for Call #114
├── app/                                  # Core application source code
│   ├── core/
│   │   └── config.py                     # Central environment, rates, and paths
│   ├── db/
│   │   ├── postgres.py                   # Production PostgreSQL queries
│   │   └── storage.py                    # Local SQLite persistence (audits.db)
│   ├── services/
│   │   ├── financials.py                 # Live Stripe, Twilio, and GCP unit economics
│   │   ├── auditor.py                    # Legacy auditor service
│   │   ├── daemon.py                     # Background worker daemon
│   │   └── email_service.py              # Gmail SMTP incident notification dispatch
│   └── api/
│       └── server.py                     # FastAPI application & API endpoints
├── static/                               # Dedicated Financials Command Center UI
│   ├── index.html                        # Single-page financial operations dashboard
│   ├── styles.css                        # Modern dark-mode glassmorphism styling
│   └── app.js                            # Live polling, charts, and simulator engine
├── audits.db                             # Local SQLite database for audit findings
├── server.py                             # Root launcher script (runs uvicorn server)
├── start.sh                              # One-click startup script
├── requirements.txt                      # Python dependencies
├── .env                                  # Environment secrets
└── README.md                             # Architecture documentation & guide
```

---

## 💰 Financials & Unit Economics Command Center

Runs locally at **[http://localhost:5050](http://localhost:5050)**.

- **Live Provider Integration**:
  - **Stripe Payments**: Real-time sync of available balance, gross collections, processing fees, and recent succeeded transactions with direct receipt links.
  - **Twilio Telephony**: Live account balance, month-to-date voice spend, and account status.
  - **Google Cloud & AI**: Active project linkage and transparent per-minute cost modeling ($0.075/min for Gemini Multimodal Live).
- **Billing Cycle Direct COGS**:
  - Reconciles actual database calls with Twilio Voice Inbound ($0.0140/min), Media Streams ($0.0040/min), Dual Recording ($0.0025/min), Gemini Live ($0.0750/min), Post-Call Transcription ($0.0025/call), QA Audits ($0.0008/call), and dedicated numbers ($1.15/mo).
- **Unit Economics & P&L**:
  - Displays blended cost per minute ($0.0955/min), average cost per call, gross profit, and gross profit margin percentage.
  - Automatic team commission splits: 50% Founder, 30% Closer, 20% Cold Caller.
- **Interactive Growth Simulator**:
  - Model SaaS business metrics by adjusting sliders for paying tenants, calls/day, average duration, plan tiers (Starter, Growth, Scale), and infrastructure tiers.
- **Per-Tenant Ledger**:
  - Live breakdown of calls, billed minutes, base subscription revenue, direct COGS, net margin, and profitability per tenant.

---

## 🛠️ Antigravity Audit Skills

Call auditing is decoupled from the web UI and handled via Antigravity Skills located in [`.agents/skills/`](./.agents/skills/):

```
                   ┌─────────────────────────┐
                   │   call-audit-analyzer   │
                   │   (Orchestrator Skill)  │
                   └────────────┬────────────┘
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
                    ┌─────────────────────────┐
                    │  Multi-Layer Diagnosis  │
                    │   • Sentiment Analysis  │
                    │   • DB Fidelity Check   │
                    │   • Cloud Infrastructure│
                    └───────────┬─────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │   save_audit_result.py  │
                    │   • audits.db SQLite    │
                    │   • Alert Email (opt)   │
                    └─────────────────────────┘
```

### 1. `call-logs` Skill
Extracts voice receptionist call records from Supabase PostgreSQL, parsing transcripts and joining correlated appointments and leads.

```bash
# Inspect a single call with human-readable summary
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --call-id 114 --format summary

# List recent unaudited calls
python3 .agents/skills/call-logs/scripts/fetch_call_logs.py --unaudited --limit 5 --format list
```

### 2. `gcloud-logs` Skill
Queries Google Cloud Logging for Cloud Run services (`ai-receptionist`, `ai-dashboard`) under project `ai-vp-506402`.

```bash
# Query logs around a specific call timestamp (+/- 5 min window)
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "2026-10-03T15:15:08Z" --window-minutes 5

# Check for backend errors in the past 24 hours
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service all --severity ERROR --since 24h
```

### 3. `call-audit-analyzer` Skill (Orchestrator)
Synthesizes application dialogue with backend telemetry to perform root-cause incident analyses, saving structured results directly into `audits.db`.

```bash
# Save an audit verdict to audits.db
python3 .agents/skills/call-audit-analyzer/scripts/save_audit_result.py << 'EOF'
{
  "call_id": 114,
  "status": "CLEAN",
  "has_issues": false,
  "summary": "Customer successfully scheduled sink repair; database row matches intent.",
  "customer_sentiment": "Positive",
  "incident_report": "Natural conversation flow with zero anomalies.",
  "recommended_action": "None required."
}
EOF
```

---

## 🚀 Quick Start

### 1. Launch the Financials Dashboard
```bash
cd /Users/figster/Desktop/practice/callAuditAgent
./start.sh
```
Or directly:
```bash
python3 server.py
```
Open **[http://localhost:5050](http://localhost:5050)** in your browser.

### 2. Run Audits via Antigravity Agent
Simply ask in the AI chat:
- *"Audit call #114"*
- *"Find unaudited calls and audit them"*
- *"Check if call #115 dropped due to a Cloud Run backend error"*

---

## ⚙️ Configuration (`.env`)

- `DATABASE_URL`: Production Supabase PostgreSQL connection string.
- `STRIPE_SECRET_KEY`: Stripe API key for live revenue and subscription metrics.
- `TWILIO_ACCOUNT_SID`: Twilio account identifier.
- `TWILIO_AUTH_TOKEN`: Twilio API token for live balance and billing records.
- `GEMINI_API_KEY`: Google GenAI API key.
- `ALERT_RECIPIENT_EMAIL`: Incident email alert destination (`ethan.figueredo943@gmail.com`).
- `DASHBOARD_PORT`: Local server port (default: `5050`).
