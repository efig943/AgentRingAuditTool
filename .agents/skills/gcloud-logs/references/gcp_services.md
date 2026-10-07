# Google Cloud Logging Architecture & Service Reference

This reference documents the Google Cloud Logging setup for project `ai-vp-506402`.

---

## 1. Cloud Run Microservices

| Service Name | Description | Key Routes & Endpoints | Typical Logs |
|---|---|---|---|
| `ai-receptionist` | Real-time FastAPI voice bridge connecting Twilio WebSockets with Gemini Multimodal Live API. | `/stream/{tenant_id}/{phone}` (WebSocket), `/webhook/twilio`, `/api/tenant/overview` | Audio bridge status, Gemini Live session startup/teardown, tool executions (`capture_lead`, `book_appointment`), connection disconnects. |
| `ai-dashboard` | Next.js/React management console for call review, analytics, and operational configurations. | `/dashboard`, `/api/stripe/webhook`, `/api/calls` | HTTP request logs, auth checks, API route handlers, static asset delivery. |

---

## 2. Log Names & Resource Filter

All Cloud Run revision logs use:
```text
resource.type="cloud_run_revision"
```

Common log streams:
- `projects/ai-vp-506402/logs/run.googleapis.com%2Fstdout`: Standard output from Python/Node applications.
- `projects/ai-vp-506402/logs/run.googleapis.com%2Fstderr`: Error output and tracebacks.
- `projects/ai-vp-506402/logs/run.googleapis.com%2Frequests`: HTTP access logs with status codes and latency.
- `projects/ai-vp-506402/logs/run.googleapis.com%2Fvarlog%2Fsystem`: Container startup, shutdown, and TCP probe logs.

---

## 3. Severity Levels

- `DEFAULT` / `INFO`: Normal operational logging (e.g., Uvicorn request responses, startup logs).
- `WARNING`: Recoverable anomalies (e.g., HTTP 404s, retried connections, slow DB queries).
- `ERROR`: Exceptions, broken WebSockets, unhandled 500 errors, audio packet conversion dropouts.
- `CRITICAL`: Container crash, OOM, failed database connectivity.

---

## 4. Querying Best Practices

- When investigating a specific call, query logs within a **+/- 5 minute window** of the call timestamp:
  ```bash
  python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "<CALL_TIMESTAMP>" --window-minutes 5
  ```
- To check for backend crashes or exceptions:
  ```bash
  python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --severity ERROR --since 24h
  ```
