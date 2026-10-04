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

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

# Google Cloud Billing
GCP_BILLING_ACCOUNT_ID = os.getenv("GCP_BILLING_ACCOUNT_ID", "01D9EB-6CC35F-F66906")
GCP_KEY_PATH = None
env_gcp_key = os.getenv("GCP_KEY_PATH")
if env_gcp_key and (BASE_DIR / env_gcp_key).exists():
    GCP_KEY_PATH = BASE_DIR / env_gcp_key
else:
    for f in BASE_DIR.glob("*ai-vp-*.json"):
        GCP_KEY_PATH = f
        break
    if not GCP_KEY_PATH:
        for f in BASE_DIR.glob("*billing*.json"):
            GCP_KEY_PATH = f
            break
