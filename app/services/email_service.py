import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from typing import Dict, Any, List, Optional
from app.core import config
from app.db.storage import mark_email_sent

logger = logging.getLogger("callAuditAgent.email")

def create_smtp_client():
    """Create and authenticate SSL SMTP connection to Gmail."""
    if not config.GMAIL_EMAIL or not config.GMAIL_APP_PASSWORD:
        raise ValueError("Gmail credentials (GMAIL_EMAIL, GMAIL_APP_PASSWORD) are not configured.")
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
    server.login(config.GMAIL_EMAIL, config.GMAIL_APP_PASSWORD)
    return server

def send_issue_alert_email(audit: Dict[str, Any], recipient: Optional[str] = None) -> bool:
    """
    Send an immediate production support alert email for an identified call issue.
    """
    to_email = recipient or config.ALERT_RECIPIENT_EMAIL
    status = audit.get("status", "WARNING")
    call_id = audit.get("call_id")
    caller_phone = audit.get("caller_phone", "Unknown")
    summary = audit.get("summary", "Issue detected during call audit")
    call_time = audit.get("call_created_at", "Unknown")
    duration = audit.get("duration_seconds", 0)
    sentiment = audit.get("customer_sentiment", "Unknown")
    is_mad = audit.get("customer_mad", False)
    db_discrepancy = audit.get("db_discrepancy", False)
    weird_interaction = audit.get("weird_interaction", False)
    db_comparison = audit.get("db_comparison", {})
    incident_report = audit.get("incident_report", "")
    recommended_action = audit.get("recommended_action", "")
    transcript = audit.get("transcript", [])

    severity_color = "#dc2626" if status == "CRITICAL" else "#d97706"
    badge_text = "CRITICAL INCIDENT" if status == "CRITICAL" else "WARNING INCIDENT"

    subject = f"[{badge_text}] Voice Receptionist Alert - Call #{call_id} ({caller_phone})"

    # Generate transcript HTML snippet
    transcript_html = ""
    for turn in transcript[:12]:
        role = turn.get("role", "ai").upper()
        text = turn.get("text", "")
        bg_col = "#1e293b" if role == "AI" else "#0f172a"
        border_col = "#38bdf8" if role == "AI" else "#a855f7"
        transcript_html += f"""
        <div style="margin-bottom: 8px; padding: 8px 12px; background: {bg_col}; border-left: 3px solid {border_col}; border-radius: 4px; font-family: monospace; font-size: 13px;">
            <strong style="color: {border_col};">{role}:</strong> <span style="color: #f1f5f9;">{text}</span>
        </div>
        """

    # DB Comparison HTML
    db_comp_html = f"""
    <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px;">
        <tr style="background: #1e293b; color: #94a3b8; text-align: left;">
            <th style="padding: 8px; border: 1px solid #334155;">Caller Requested / Agreed</th>
            <th style="padding: 8px; border: 1px solid #334155;">Database Recorded</th>
        </tr>
        <tr style="color: #f8fafc;">
            <td style="padding: 8px; border: 1px solid #334155; vertical-align: top;">
                {db_comparison.get('caller_requested', 'N/A')}
            </td>
            <td style="padding: 8px; border: 1px solid #334155; vertical-align: top;">
                {db_comparison.get('database_recorded', 'N/A')}
            </td>
        </tr>
    </table>
    """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
    </head>
    <body style="margin: 0; padding: 20px; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
        <div style="max-width: 650px; margin: 0 auto; background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e1e38 0%, #0f172a 100%); padding: 24px; border-bottom: 2px solid {severity_color};">
                <div style="display: inline-block; background: {severity_color}; color: #ffffff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; padding: 4px 10px; border-radius: 20px; margin-bottom: 12px;">
                    {badge_text}
                </div>
                <h1 style="margin: 0; font-size: 20px; color: #ffffff; font-weight: 700;">
                    Production Support Call Audit Alert
                </h1>
                <p style="margin: 6px 0 0 0; color: #94a3b8; font-size: 14px;">
                    Call ID: <strong>#{call_id}</strong> &bull; Caller: <strong>{caller_phone}</strong> &bull; Time: <strong>{call_time}</strong>
                </p>
            </div>

            <!-- Body -->
            <div style="padding: 24px;">
                <!-- Summary Card -->
                <div style="background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                    <div style="font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600; margin-bottom: 6px;">Finding Summary</div>
                    <div style="font-size: 15px; color: #f8fafc; font-weight: 500; line-height: 1.5;">{summary}</div>
                </div>

                <!-- Issue Badges -->
                <div style="margin-bottom: 20px;">
                    <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase;">Detected Flags:</div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <span style="background: {'#7f1d1d' if is_mad else '#1e293b'}; color: {'#fca5a5' if is_mad else '#64748b'}; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block; margin-right: 6px;">
                            {'😡 Customer Angry/Frustrated' if is_mad else 'Customer Not Angry'}
                        </span>
                        <span style="background: {'#7f1d1d' if db_discrepancy else '#1e293b'}; color: {'#fca5a5' if db_discrepancy else '#64748b'}; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block; margin-right: 6px;">
                            {'⚠️ Database Mismatch' if db_discrepancy else 'Database Matched'}
                        </span>
                        <span style="background: {'#78350f' if weird_interaction else '#1e293b'}; color: {'#fcd34d' if weird_interaction else '#64748b'}; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block;">
                            {'🤖 Weird Interaction / Loop' if weird_interaction else 'Normal Flow'}
                        </span>
                    </div>
                </div>

                <!-- Database Consistency Section -->
                <div style="margin-bottom: 24px;">
                    <div style="font-size: 14px; font-weight: 600; color: #38bdf8; margin-bottom: 8px;">
                        🗄️ Database Verification Check
                    </div>
                    {db_comp_html}
                    {f'<p style="margin-top: 8px; color: #f87171; font-size: 13px;"><strong>Discrepancy Details:</strong> {db_comparison.get("mismatch_details")}</p>' if db_comparison.get("mismatch_details") else ''}
                </div>

                <!-- Incident Report -->
                <div style="margin-bottom: 24px; background: #0f172a; padding: 16px; border-radius: 8px; border: 1px solid #1e293b;">
                    <div style="font-size: 14px; font-weight: 600; color: #fbbf24; margin-bottom: 8px;">
                        📋 Production Incident Report
                    </div>
                    <p style="margin: 0; font-size: 13px; line-height: 1.6; color: #cbd5e1;">
                        {incident_report}
                    </p>
                </div>

                <!-- Recommended Action -->
                <div style="margin-bottom: 24px; background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); padding: 16px; border-radius: 8px;">
                    <div style="font-size: 14px; font-weight: 600; color: #4ade80; margin-bottom: 8px;">
                        🛠️ Recommended Support Action
                    </div>
                    <p style="margin: 0; font-size: 13px; line-height: 1.6; color: #dcfce7;">
                        {recommended_action}
                    </p>
                </div>

                <!-- Transcript Sample -->
                <div>
                    <div style="font-size: 14px; font-weight: 600; color: #a855f7; margin-bottom: 8px;">
                        💬 Call Transcript Excerpt
                    </div>
                    {transcript_html}
                </div>

                <!-- Footer CTA -->
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #1e293b; text-align: center;">
                    <a href="http://localhost:{config.DASHBOARD_PORT}" style="display: inline-block; background: #6366f1; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; font-size: 14px;">
                        Open Local Support Dashboard
                    </a>
                </div>
            </div>

            <!-- Footer Meta -->
            <div style="background: #090d16; padding: 14px; text-align: center; color: #64748b; font-size: 11px;">
                Voice Receptionist Production Support Auditor &bull; Automated Alert System
            </div>
        </div>
    </body>
    </html>
    """

    plain_content = f"""
[PRODUCTION SUPPORT ALERT - {badge_text}]
Call ID: #{call_id}
Caller: {caller_phone}
Time: {call_time}
Duration: {duration}s
Customer Sentiment: {sentiment}

SUMMARY:
{summary}

FLAGS:
- Customer Angry/Frustrated: {is_mad}
- Database Mismatch: {db_discrepancy}
- Weird Interaction: {weird_interaction}

DATABASE CHECK:
Caller Requested: {db_comparison.get('caller_requested', 'N/A')}
Database Recorded: {db_comparison.get('database_recorded', 'N/A')}

INCIDENT REPORT:
{incident_report}

RECOMMENDED ACTION:
{recommended_action}

Open Local Dashboard at: http://localhost:{config.DASHBOARD_PORT}
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Voice AI Auditor <{config.GMAIL_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(plain_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = create_smtp_client()
        server.sendmail(config.GMAIL_EMAIL, [to_email], msg.as_string())
        server.quit()
        mark_email_sent(call_id)
        logger.info(f"Alert email sent successfully to {to_email} for call #{call_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_test_email(recipient: Optional[str] = None) -> Dict[str, Any]:
    """Send a test email to verify SMTP configuration and recipient reception."""
    to_email = recipient or config.ALERT_RECIPIENT_EMAIL
    subject = "✅ Voice AI Audit Agent - Test Notification"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; border-radius: 8px;">
        <h2 style="color: #22c55e;">✅ Call Audit Notification System Active</h2>
        <p>This is a test notification from your <strong>Voice AI Call Audit Agent</strong>.</p>
        <p>The system is connected to your production call logs database, Gemini 3.8 Flash, and Gmail SMTP alerts.</p>
        <p>Recipient: <strong>{to_email}</strong></p>
        <p>When issues like angry customers, AI loops, or database mismatches are detected, you will receive an alert.</p>
    </div>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Voice AI Auditor <{config.GMAIL_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        server = create_smtp_client()
        server.sendmail(config.GMAIL_EMAIL, [to_email], msg.as_string())
        server.quit()
        return {"success": True, "message": f"Test email sent successfully to {to_email}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
