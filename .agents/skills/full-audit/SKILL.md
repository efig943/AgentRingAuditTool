---
name: full-audit
description: >-
  Master full-system audit orchestrator for AgentRing and agentring.dev.
  Coordinates specialist audit skills (code-audit, db-audit, call-logs, gcloud-logs)
  to dissect their respective domains and synthesizes a consolidated executive master report
  with scorecard grades, deployment blockers, and prioritized action items.
---

# Master Full-System Audit Orchestrator Skill

This skill serves as the **Supreme Auditor Orchestrator** for AgentRing. Instead of running fragmented, isolated checks, it dispatches specialized audit agents to dissect their specific domains and aggregates their findings into a single, unified executive report.

---

## The Specialist Audit Constellation

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

---

## Tooling & Usage

Execute the master orchestrator [`run_full_audit.py`](./scripts/run_full_audit.py) from the project root:

### 1. Run Complete Master Audit (Terminal Summary)
```bash
python3 .agents/skills/full-audit/scripts/run_full_audit.py --format summary
```

### 2. Export Master Markdown Report (for Documentation / Incident Reviews)
```bash
python3 .agents/skills/full-audit/scripts/run_full_audit.py --format markdown --export master_system_audit.md
```

### 3. CI/CD Gate Mode (Filter Critical & Error Blockers)
```bash
python3 .agents/skills/full-audit/scripts/run_full_audit.py --format json --min-severity error
```

---

## Interactive Antigravity Prompting

You can invoke this orchestrated audit directly in chat:
- *"Run a full system audit"*
- *"Dissect code, database, and cloud telemetry and paste the findings"*
- *"Check if we are ready to deploy to agentring.dev"*
