import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from app.core import config
from app.db.postgres import fetch_calls
from app.db.storage import get_audited_call_ids, get_audit
from app.services.auditor import audit_call
from app.services.email_service import send_issue_alert_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("callAuditAgent.daemon")

class AuditDaemon:
    def __init__(self):
        self.is_running = False
        self._thread = None
        self._stop_event = threading.Event()
        self.last_run: Optional[str] = None
        self.scanned_count = 0
        self.issues_detected = 0
        self.emails_dispatched = 0
        self.is_scanning = False
        self.current_scan_range = "day"

    def scan_and_audit(self, time_range: str = "day", limit: Optional[int] = None, force_all: bool = False) -> Dict[str, Any]:
        """
        Scan call logs based on day, week, month, year, or all time,
        audit new/requested calls, and dispatch email alerts if issues are detected.
        """
        self.is_scanning = True
        self.current_scan_range = time_range
        logger.info(f"Starting call audit scan for range: '{time_range}' (force_all={force_all})...")
        
        try:
            now = datetime.now()
            start_date = None
            if time_range == "day":
                start_date = now - timedelta(days=1)
            elif time_range == "week":
                start_date = now - timedelta(days=7)
            elif time_range == "month":
                start_date = now - timedelta(days=30)
            elif time_range == "year":
                start_date = now - timedelta(days=365)
            elif time_range == "all":
                start_date = None

            calls = fetch_calls(limit=limit, start_date=start_date)
            audited_ids = set(get_audited_call_ids()) if not force_all else set()

            to_audit = [c for c in calls if c["id"] not in audited_ids]
            logger.info(f"Retrieved {len(calls)} calls in range '{time_range}'. Un-audited: {len(to_audit)}")

            new_issues = []
            audited_results = []

            for call in to_audit:
                call_id = call["id"]
                try:
                    logger.info(f"Auditing Call #{call_id} ({call.get('caller_phone')})...")
                    res = audit_call(call_id, force_recheck=force_all)
                    audited_results.append(res)
                    self.scanned_count += 1

                    if res.get("has_issues"):
                        self.issues_detected += 1
                        new_issues.append(res)
                        
                        # Check if email should be automatically dispatched
                        if config.AUTO_EMAIL_ON_ISSUE and not res.get("email_sent"):
                            logger.info(f"Issue found in call #{call_id}! Dispatching email alert...")
                            email_sent = send_issue_alert_email(res)
                            if email_sent:
                                self.emails_dispatched += 1

                except Exception as e:
                    logger.error(f"Error auditing call #{call_id}: {e}")

            self.last_run = datetime.now().isoformat()
            return {
                "scanned": len(to_audit),
                "issues_found": len(new_issues),
                "emails_sent": self.emails_dispatched,
                "issues": new_issues
            }
        finally:
            self.is_scanning = False

    def _run_loop(self):
        logger.info(f"Audit daemon started with check interval {config.AUDIT_INTERVAL_SECONDS}s")
        while not self._stop_event.is_set():
            try:
                self.scan_and_audit(time_range="day", limit=50)
            except Exception as e:
                logger.error(f"Daemon scan iteration error: {e}")
            
            # Wait for next interval or stop event
            self._stop_event.wait(config.AUDIT_INTERVAL_SECONDS)
        logger.info("Audit daemon stopped.")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "is_scanning": self.is_scanning,
            "current_scan_range": self.current_scan_range,
            "interval_seconds": config.AUDIT_INTERVAL_SECONDS,
            "last_run": self.last_run,
            "scanned_count": self.scanned_count,
            "issues_detected": self.issues_detected,
            "emails_dispatched": self.emails_dispatched,
            "recipient_email": config.ALERT_RECIPIENT_EMAIL,
            "auto_email_enabled": config.AUTO_EMAIL_ON_ISSUE
        }

# Global singleton daemon instance
daemon_instance = AuditDaemon()

if __name__ == "__main__":
    logger.info("Running daemon in foreground mode...")
    d = AuditDaemon()
    d.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        d.stop()
