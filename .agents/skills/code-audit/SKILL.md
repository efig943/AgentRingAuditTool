---
name: code-audit
description: >-
  Inspect, analyze, and comprehensively audit the codebase for syntax integrity,
  hardcoded secrets, dependency drift (missing packages in requirements.txt),
  environment variable coverage (.env.example parity), SQL injection / unsafe formatting,
  code smells, function complexity hotspots, and frontend API route alignment.
---

# Codebase Quality, Security & Architecture Audit Skill

This skill provides automated, static analysis auditing for the Python application, APIs, and frontend assets. Built with zero external dependencies using Python's native `ast` engine, it uncovers deployment-breaking dependency omissions, undocumented environment variables, security vulnerabilities, and architecture drift.

---

## Capabilities & Audit Pillars

1. **Syntax, AST & Import Health (`SYN` / `IMP`)**:
   - Parses every `.py` file to verify AST integrity and valid Python syntax.
   - Audits legacy root compatibility shims vs canonical `app.*` package imports.
   - Detects broken imports or circular dependencies.

2. **Security & Secrets Scanning (`SEC`)**:
   - Scans code for hardcoded API keys (Stripe `sk_live_`, `sk_test_`, Twilio Account SIDs, Google Gemini keys, high-entropy tokens).
   - Validates that sensitive files (e.g. Google Cloud service account keys) are covered by `.gitignore`.
   - Flags SQL injection risks: `cur.execute()` calls using `f-string` interpolation or `%` formatting rather than parameterized queries (`%s`).
   - Detects dangerous built-ins (`eval()`, `exec()`).

3. **Dependency Drift & Requirements Validation (`DEP`)**:
   - Compares every third-party `import` across all modules against `requirements.txt`.
   - Flags **Undeclared Dependencies** (packages imported in code but omitted from `requirements.txt` that would crash production builds).
   - Identifies unused dependencies declared in `requirements.txt`.

4. **Environment Configuration Parity (`ENV`)**:
   - Extracts all `os.getenv(...)` and `os.environ[...]` variables across all modules.
   - Cross-references against `.env.example` to detect **Undocumented Environment Variables**.
   - Cross-references against active `.env` to alert developers to unconfigured variables in local environments.

5. **Reliability, Smells & Complexity (`REL` / `COMP`)**:
   - Flags dangerous bare `except:` clauses that catch `BaseException` (including `KeyboardInterrupt`).
   - Detects silent `except Exception: pass` blocks that swallow runtime exceptions without logging.
   - Surfaces **Mega-Function Hotspots** (>120 lines) violating single-responsibility architecture.

6. **Frontend & API Contract Alignment (`API`)**:
   - Extracts registered FastAPI routes in `app/api/server.py`.
   - Scans JavaScript `fetch(...)` URLs in `static/app.js`.
   - Detects 404 dead routes where the frontend requests an endpoint that does not exist in the server.

---

## Tooling & Usage

Use the CLI auditor [`audit_codebase.py`](./scripts/audit_codebase.py) from the workspace root:

### 1. Run Complete Codebase Audit (Terminal Summary)
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --format summary
```

### 2. Export Detailed Markdown Report
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --format markdown --export code_audit_report.md
```

### 3. Machine-Readable JSON for CI/CD Gates
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --format json --min-severity error
```

### 4. Scope Audit to a Specific Module or File
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --path app/services/financials.py --format summary
```

### 5. Filter by Minimum Severity (`info`, `warning`, `error`, `critical`)
```bash
python3 .agents/skills/code-audit/scripts/audit_codebase.py --min-severity warning
```

---

## Exit Codes

| Exit Code | Status | Meaning |
|---|---|---|
| `0` | `CLEAN` | Codebase passed all syntax, security, dependency, and contract checks. |
| `1` | `WARNING` | Non-fatal warnings (SQL formatting, undocumented env vars, bare excepts). |
| `2` | `ERROR / CRITICAL` | Critical flaws: missing dependencies in `requirements.txt`, hardcoded secrets, syntax errors, 404 API route drift. |
| `3` | `FATAL` | Fatal execution failure or IO error. |

---

## References

- [code_rules.md](./references/code_rules.md) &mdash; Comprehensive taxonomy of rule IDs, severities, and remediation guidelines.
- [sample_code_audit.md](./examples/sample_code_audit.md) &mdash; Walkthrough of real findings identified across the project.
