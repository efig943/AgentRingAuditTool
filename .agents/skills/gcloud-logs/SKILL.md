---
name: gcloud-logs
description: >-
  Query, filter, and inspect Google Cloud Logging entries for Cloud Run microservices
  (ai-receptionist, ai-dashboard), including HTTP requests, latency, exceptions,
  and container lifecycle events. Use this skill when investigating infrastructure
  errors, backend crashes, stream drops, or service health.
---

# Google Cloud Logging Inspection Skill

This skill provides procedures and CLI tools to query, filter, and inspect Google Cloud Logging entries for Google Cloud Run services running under project `ai-vp-506402`.

---

## Capabilities

1. **Service-Targeted Inspection**: Query logs specifically for `ai-receptionist` or `ai-dashboard`.
2. **Timestamp Window Correlation**: Retrieve log entries within a specific window around a call timestamp (`--around "<TIMESTAMP>" --window-minutes 5`).
3. **Severity Filtering**: Filter specifically for `ERROR`, `WARNING`, or `CRITICAL` logs.
4. **Pattern & Call Search**: Search logs for specific strings (e.g. Call SIDs, exception traces, HTTP 500 status).

---

## Tooling & Usage

Use the helper script [`fetch_gcloud_logs.py`](./scripts/fetch_gcloud_logs.py) via terminal execution:

### 1. Inspect Logs Around a Specific Event / Call Timestamp
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --around "2026-10-03T15:15:08Z" --window-minutes 5 --format compact
```

### 2. Search for Errors in the Last 24 Hours
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service all --severity ERROR --since 24h --limit 20
```

### 3. Search for a Specific Call SID or Trace
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --search "CAcb72e35974bd008bc8f378fd6fa5ed8f" --since 7d
```

### 4. Machine-Readable JSON Output
```bash
python3 .agents/skills/gcloud-logs/scripts/fetch_gcloud_logs.py --service ai-receptionist --limit 10 --format json
```

---

## References

- Consult [gcp_services.md](./references/gcp_services.md) for Cloud Run architecture, endpoints, and log stream mappings.
