import os
import threading
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core import config
from app.db.postgres import fetch_calls, fetch_call_by_id
from app.db.storage import (
    query_audits, get_stats, get_audit, get_audited_call_ids, 
    mark_resolved, mark_email_sent
)
from app.services.auditor import audit_call
from app.services.email_service import send_issue_alert_email, send_test_email
from app.services.daemon import daemon_instance
from app.services.financials import get_financial_summary, simulate_projections

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("callAuditAgent.server")

app = FastAPI(title="Voice AI Receptionist Call Audit Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class AuditRunRequest(BaseModel):
    time_range: Optional[str] = "day" # "day", "week", "month", "year", "all"
    limit: Optional[int] = None
    force_all: Optional[bool] = False
    call_ids: Optional[List[int]] = None

class EmailAlertRequest(BaseModel):
    recipient: Optional[str] = None

class ResolveRequest(BaseModel):
    resolved: bool = True

class SimulationRequest(BaseModel):
    tenants_count: int = 25
    plan_tier: str = "growth"
    calls_per_day_per_tenant: int = 10
    avg_call_minutes: float = 2.0
    infra_tier: Optional[str] = "free"

@app.on_event("startup")
def startup_event():
    logger.info("Initializing Call Audit Agent Server...")
    daemon_instance.start()

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Shutting down Call Audit Agent Server...")
    daemon_instance.stop()

@app.get("/api/stats")
def get_dashboard_stats():
    """Retrieve aggregate audit metrics and daemon status."""
    stats = get_stats()
    stats["daemon"] = daemon_instance.get_status()
    return stats

@app.get("/api/calls")
def list_calls(
    filter_type: Optional[str] = Query(None, description="Filter: all, issues, clean, customer_mad, db_discrepancy, weird_interaction, unaudited"),
    status: Optional[str] = Query(None, description="Status: CLEAN, WARNING, CRITICAL"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    List calls with their audit status, supporting filtering by date/time,
    issue type, sentiment, and search terms.
    """
    if filter_type == "unaudited":
        all_pg_calls = fetch_calls(limit=limit * 2)
        audited_ids = set(get_audited_call_ids())
        unaudited = [c for c in all_pg_calls if c["id"] not in audited_ids]
        
        if start_date:
            unaudited = [c for c in unaudited if str(c["created_at"]) >= start_date]
        if end_date:
            unaudited = [c for c in unaudited if str(c["created_at"]) <= end_date]
        if search:
            s = search.lower()
            unaudited = [c for c in unaudited if s in (c.get("caller_phone") or "").lower() or s in (c.get("call_sid") or "").lower()]

        return {
            "total": len(unaudited),
            "calls": unaudited[offset:offset + limit]
        }

    audits = query_audits(
        status=status,
        filter_type=filter_type,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
        offset=offset
    )
    return {
        "total": len(audits),
        "calls": audits
    }

@app.get("/api/calls/{call_id}")
def get_call_details(call_id: int):
    """Retrieve full audit details, transcript, and DB state for a specific call."""
    audit = get_audit(call_id)
    if not audit:
        raw_call = fetch_call_by_id(call_id)
        if not raw_call:
            raise HTTPException(status_code=404, detail="Call not found")
        return {
            "audited": False,
            "call": raw_call
        }
    return {
        "audited": True,
        "call": audit
    }

@app.post("/api/audit/run")
def trigger_audit(req: AuditRunRequest, background_tasks: BackgroundTasks):
    """
    Trigger analysis on call logs based on day, week, month, year, or all time.
    Audits un-audited calls or re-audits all requested calls.
    """
    if daemon_instance.is_scanning:
        return {
            "status": "in_progress", 
            "message": f"Audit scan is already currently running ({daemon_instance.current_scan_range})."
        }

    def run_worker():
        daemon_instance.scan_and_audit(
            time_range=req.time_range or "day", 
            limit=req.limit, 
            force_all=req.force_all or False
        )

    background_tasks.add_task(run_worker)
    return {
        "status": "started", 
        "time_range": req.time_range or "day",
        "force_all": req.force_all or False,
        "message": f"Audit triggered for time range '{req.time_range or 'day'}' in background."
    }

@app.post("/api/audit/call/{call_id}")
def audit_single_call(call_id: int, force: bool = Query(True)):
    """Run audit immediately on a specific call."""
    try:
        res = audit_call(call_id, force_recheck=force)
        if res.get("has_issues") and config.AUTO_EMAIL_ON_ISSUE and not res.get("email_sent"):
            send_issue_alert_email(res)
        return {"success": True, "audit": res}
    except Exception as e:
        logger.error(f"Audit single call error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audit/email/{call_id}")
def send_email_for_call(call_id: int, req: EmailAlertRequest = None):
    """Send or re-send incident alert email for a call."""
    audit = get_audit(call_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found for this call ID.")
    recipient = req.recipient if req and req.recipient else config.ALERT_RECIPIENT_EMAIL
    success = send_issue_alert_email(audit, recipient=recipient)
    if success:
        return {"success": True, "message": f"Email successfully dispatched to {recipient}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email via SMTP.")

@app.post("/api/email/test")
def test_email_endpoint(req: EmailAlertRequest = None):
    """Send a test email to verify credentials and SMTP deliverability."""
    recipient = req.recipient if req and req.recipient else config.ALERT_RECIPIENT_EMAIL
    result = send_test_email(recipient)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@app.post("/api/calls/{call_id}/resolve")
def resolve_incident(call_id: int, req: ResolveRequest):
    """Mark an incident as resolved or reopen it."""
    mark_resolved(call_id, req.resolved)
    return {"success": True, "call_id": call_id, "resolved": req.resolved}

@app.post("/api/daemon/toggle")
def toggle_daemon(enable: bool = Query(True)):
    """Start or stop the background polling daemon."""
    if enable:
        daemon_instance.start()
    else:
        daemon_instance.stop()
    return daemon_instance.get_status()

@app.get("/api/financials")
def get_financials_endpoint():
    """Retrieve actual business financial metrics, API costs, revenues, and unit economics."""
    try:
        return get_financial_summary()
    except Exception as e:
        logger.error(f"Error fetching financials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/financials/simulate")
def simulate_financials_endpoint(req: SimulationRequest):
    """Run interactive business financial simulation based on growth assumptions."""
    try:
        return simulate_projections(
            tenants_count=req.tenants_count,
            plan_tier=req.plan_tier,
            calls_per_day_per_tenant=req.calls_per_day_per_tenant,
            avg_call_minutes=req.avg_call_minutes,
            infra_tier=req.infra_tier or "free"
        )
    except Exception as e:
        logger.error(f"Error running financial simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount Static Files & Frontend
STATIC_DIR = config.BASE_DIR / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Voice AI Call Audit Agent API running. Static UI not yet created."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=config.DASHBOARD_PORT, reload=False)
