# CallAudit Pro &mdash; Voice AI Production Support Auditor

An automated production support agent and web dashboard that monitors voice receptionist call logs, detects customer friction (anger, frustration), conversational anomalies (loops, cutoffs, stutters), and database discrepancies (missing/mismatched appointments or leads), and dispatches automated email alerts to `ethan.figueredo943@gmail.com`.

---

## 📁 Project Structure

```
callAuditAgent/
├── app/                              # Core application source code
│   ├── core/
│   │   └── config.py                 # Central environment, paths, rates, constants
│   ├── db/
│   │   ├── postgres.py               # Supabase PostgreSQL queries (calls, appts, leads)
│   │   └── storage.py                # Local SQLite persistence (audits schema & CRUD)
│   ├── services/
│   │   ├── auditor.py                # Gemini 3.8 Flash inspection & deterministic validation
│   │   ├── daemon.py                 # Continuous background scan & alerting thread
│   │   ├── email_service.py          # Gmail SMTP incident notification dispatch
│   │   └── financials.py             # Stripe revenue reconciliation & SaaS unit economics
│   └── api/
│       └── server.py                 # FastAPI application, route handlers, static mount
├── static/                           # Web operations dashboard frontend
│   ├── index.html                    # Single-page operations dashboard
│   ├── styles.css                    # Dark theme design system & dashboard layout
│   └── app.js                        # Frontend interactive controller & charts
├── scripts/                          # Management & utility scripts
│   ├── clean_database.py             # Database audit & purge utility with safety backup
│   ├── test_stripe.py                # Stripe API connection & metric validator
│   └── backups/                      # Timestamped JSON backups
├── audits.db                         # Local SQLite operational database
├── server.py                         # Root launcher script (runs uvicorn / app.api.server:app)
├── start.sh                          # One-click startup script
├── requirements.txt                  # Python package dependencies
├── .env                              # Environment secrets
└── README.md                         # Architecture documentation & quickstart
```

---

## 🛠️ Architecture & Capabilities

1. **Production Support Log Auditor (`app/services/auditor.py`)**:
   - Connects directly to the production PostgreSQL database (Supabase) to read `call_logs`, `appointments`, and `leads`.
   - Uses **Gemini 3.8 Flash** with structured JSON output for deep conversational sentiment and conversational state analysis.
   - Performs a **deterministic database integrity check**: compares spoken intent (caller's requested date, time, name, address) against the actual records saved in `appointments` and `leads`.

2. **Automated Background Daemon (`app/services/daemon.py`)**:
   - Continuously monitors for new or un-audited calls every 60 seconds (configurable).
   - Automatically evaluates calls and dispatches rich HTML incident alert emails to `ethan.figueredo943@gmail.com` when critical issues or warnings are discovered.

3. **Financials & Unit Economics Engine (`app/services/financials.py`)**:
   - Reconciles live Stripe subscriptions, charges, fees, and balance with PostgreSQL tenant call minutes.
   - Computes blended COGS per minute and per call across Twilio Voice, Media Streams, Gemini Live, and Gemini Flash Audits.
   - Calculates real gross profits and automated team commission splits (50% Founder, 30% Closer, 20% Cold Caller).

4. **Production Support Dashboard (`app/api/server.py` & `static/`)**:
   - Runs locally at `http://localhost:5050`.
   - **System Status Bar**: Displays live health state (`ALL GREEN - NOMINAL` vs `X ACTIVE INCIDENTS`).
   - **Metrics Grid**: Real-time counters for Audited Calls, Clean Rate, Flagged Issues, Angry Customers, DB Inconsistencies, and Emailed Alerts.
   - **Financial Command Center**: Live MRR, ARR, Net Cash Collected, Team Commissions, and Interactive Growth Simulator.
   - **One-Click Audit Action**: "Run Call Analysis" with live progress tracking and deep re-audit capabilities.
   - **Multi-Dimensional Sifting & Filters**:
     - Status tabs: `All Calls`, `🚨 Issues Requiring Attention`, `🟢 Clean Calls`, `⏳ Unaudited Logs`.
     - Time & Date filter: Presets (`Today`, `Yesterday`, `Last 7 Days`, `All Time`) plus custom `datetime-local` pickers.
     - Category chips: `😡 Angry Customers`, `🗄️ Database Mismatch`, `🤖 AI Loops / Weird Flow`.
     - Live search: by phone number, Call SID, or issue keywords.
   - **Deep Inspection Drawer**:
     - Side-by-side database verification matrix.
     - Turn-by-turn styled chat transcript.
     - Production root-cause report and recommended resolution.
     - One-click "Dispatch Alert Email", "Re-Analyze Call", and "Mark Resolved".

---

## 🚀 Quick Start

### 1. Start Dashboard & Background Daemon
```bash
cd /Users/figster/Desktop/practice/callAuditAgent
./start.sh
```
Or directly with Python:
```bash
python3 server.py
```
Open your browser at **[http://localhost:5050](http://localhost:5050)**.

---

## ⚙️ Configuration (`.env`)

Configuration is pre-loaded from `.env` (with fallback to `practice/receptionits/.env`):
- `DATABASE_URL`: Production Supabase PostgreSQL connection string.
- `GEMINI_API_KEY`: API key for Gemini 3.8 Flash analysis.
- `STRIPE_SECRET_KEY`: Stripe API key for live financials and subscription sync.
- `ALERT_RECIPIENT_EMAIL`: `ethan.figueredo943@gmail.com`
- `GMAIL_EMAIL`: `ethan.figueredo943@gmail.com`
- `GMAIL_APP_PASSWORD`: Gmail App Password for SMTP alerts.
- `DASHBOARD_PORT`: `5050`
- `AUTO_EMAIL_ON_ISSUE`: `true`
