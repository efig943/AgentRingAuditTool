"""
CallAudit Pro - Production Support Voice AI Auditor Entrypoint.
Starts the FastAPI application and background polling daemon.
"""

import sys
from pathlib import Path
import uvicorn

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Expose app for ASGI servers (e.g. uvicorn server:app)
from app.api.server import app
from app.core import config

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=config.DASHBOARD_PORT, reload=False)
