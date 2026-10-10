# Code Audit Rule Taxonomy & Reference

This reference catalogs every static analysis rule evaluated by `audit_codebase.py`.

---

## 1. Syntax & Imports (`SYN` / `IMP`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `SYN-001` | `CRITICAL` | File contains invalid Python syntax and cannot parse to AST. | Fix syntax error in file. |
| `ARCH-LAYER-001` | `ERROR` | Internal package module imports root legacy shim instead of `app.*`. | Change import to canonical `app.services.*` or `app.db.*`. |

---

## 2. Security & Secrets (`SEC`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `SEC-KEY-STRIPE` | `CRITICAL` | Hardcoded Stripe live secret key (`sk_live_...`). | Revoke key immediately and move to environment secret store. |
| `SEC-KEY-STRIPE-TEST` | `CRITICAL` | Hardcoded Stripe test secret key (`sk_test_...`). | Store key in `.env` and load via `os.getenv("STRIPE_SECRET_KEY")`. |
| `SEC-KEY-TWILIO` | `CRITICAL` | Hardcoded Twilio Account SID (`AC...`). | Store key in `.env` and load via `os.getenv("TWILIO_ACCOUNT_SID")`. |
| `SEC-KEY-GEMINI` | `CRITICAL` | Hardcoded Google Gemini / Cloud API Key (`AIza...`). | Store in `.env` and access via `os.getenv("GEMINI_API_KEY")`. |
| `SEC-SQL-001` | `WARNING` | SQL `execute()` uses Python `f-string` interpolation. | Use parameterized queries (`%s`) to protect against SQL injection. |
| `SEC-SQL-002` | `WARNING` | SQL `execute()` uses Python `%` string formatting. | Pass parameters as a tuple argument to `execute()`. |
| `SEC-DANGEROUS-FUNC` | `CRITICAL` | Usage of dynamic execution functions `eval()` or `exec()`. | Refactor to deterministic logic or safe deserialization. |
| `SEC-GITIGNORE-001` | `CRITICAL` | Sensitive credential/key file exists but is not covered by `.gitignore`. | Add file pattern to `.gitignore` to prevent accidental commit. |

---

## 3. Dependency & Environment Completeness (`DEP` / `ENV`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `DEP-MISSING-001` | `ERROR` | Third-party package is imported in code but absent from `requirements.txt`. | Add package to `requirements.txt` to avoid deployment crashes. |
| `DEP-UNUSED-001` | `INFO` | Package declared in `requirements.txt` is never directly imported. | Confirm if needed for CLI/transitive purposes, or remove. |
| `ENV-UNDOC-001` | `WARNING` | Environment variable accessed in code is absent from `.env.example`. | Add documentation and default placeholder to `.env.example`. |
| `ENV-UNSET-001` | `INFO` | Environment variable is referenced in code but unset in local `.env`. | Add variable to local `.env` if developing this feature. |

---

## 4. Reliability & Code Smells (`REL`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `REL-EXCEPT-001` | `WARNING` | Bare `except:` catches `BaseException` (including `KeyboardInterrupt`). | Specify explicit exception classes or use `except Exception:`. |
| `REL-EXCEPT-002` | `WARNING` | Silent `except Exception: pass` swallows exceptions without logging. | Add `logger.warning()` or `logger.exception()` call. |

---

## 5. Architectural Complexity (`COMP`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `COMP-001` | `INFO` | Function length exceeds 120 lines (mega-function hotspot). | Decompose into smaller, testable sub-functions with single responsibility. |

---

## 6. Frontend & API Contract Alignment (`API`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `API-404-DRIFT` | `ERROR` | Frontend JavaScript calls a route via `fetch()` that is not registered in FastAPI. | Register the missing route or fix the URL in frontend script. |

---

## 7. Cloud Run & GCloud Deployment Readiness (`GCP`)

Target production domain: **`agentring.dev`**

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `GCP-PORT-001` | `ERROR` | Server does not check `$PORT` env variable. Cloud Run injects `$PORT` (8080) for health checks. | Bind to `int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8080")))`. |
| `GCP-IGNORE-001` | `WARNING` | Missing `.gcloudignore`. Local SQLite databases and secrets risk being uploaded to Cloud Build. | Create `.gcloudignore` to exclude `.git`, `.env`, `audits.db`, and `scratch/`. |
| `GCP-HOST-001` | `CRITICAL` | Server host binding restricted to `127.0.0.1` or `localhost`. Cloud Run requires `0.0.0.0`. | Set `host="0.0.0.0"` in ASGI server launcher. |
| `GCP-CORS-001` | `ERROR` | CORS configuration omits `agentring.dev`. Browsers will block client requests. | Add `https://agentring.dev` to `allow_origins`. |
