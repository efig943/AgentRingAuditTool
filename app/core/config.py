import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths - resolve to the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RECEPTIONIST_ENV_PATH = BASE_DIR.parent / "receptionits" / ".env"

# Load local .env first, then fallback to receptionist .env
load_dotenv(BASE_DIR / ".env")
if RECEPTIONIST_ENV_PATH.exists():
    load_dotenv(RECEPTIONIST_ENV_PATH)

DATABASE_URL = os.getenv("DATABASE_URL", "")


# Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Email alerts
ALERT_RECIPIENT_EMAIL = os.getenv("ALERT_RECIPIENT_EMAIL", "ethan.figueredo943@gmail.com")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "ethan.figueredo943@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# Background daemon & dashboard
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5050"))
AUDIT_INTERVAL_SECONDS = int(os.getenv("AUDIT_INTERVAL_SECONDS", "60"))
AUTO_EMAIL_ON_ISSUE = os.getenv("AUTO_EMAIL_ON_ISSUE", "true").lower() in ("true", "1", "yes")

# SQLite local storage
SQLITE_DB_PATH = BASE_DIR / "audits.db"

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
