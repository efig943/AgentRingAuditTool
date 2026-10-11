import os
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import psycopg2
import psycopg2.extras
import stripe
import logging
from app.core import config

logger = logging.getLogger("callAuditAgent.financials")

# Comprehensive Software Service Cost Rates & Pricing Model
COST_RATES = {
    # Telephony (Twilio US Local Inbound)
    "twilio_voice_per_min": 0.0085,         # Real Inbound voice (billed in 60s ceil increments)
    "twilio_streams_per_min": 0.0040,       # Bidirectional Media Streams WebSocket (exact duration)
    "twilio_recording_per_min": 0.0025,     # Dual-channel MP3 call recording (60s ceil)
    "phone_number_monthly": 1.15,           # Dedicated Twilio phone number rental per month
    "sms_cost_per_msg": 0.0129,             # Outbound SMS followup/receipt ($0.0079 + carrier fee)
    
    # AI Speech & Intelligence (Google Gemini 3.8 Live / Flash)
    "gemini_live_per_min": 0.0300,          # Multimodal Live real-time audio WebSocket session (tokens + buffer)
    "gemini_transcription_per_call": 0.0025,# Post-call audio transcription & lead extraction (Flash)
    "gemini_audit_per_call": 0.0008,        # Automated support QA audit & DB integrity check (Flash)
    
    # Payment Gateway (Stripe)
    "stripe_fee_pct": 0.029,                # Credit card processing rate (2.9%)
    "stripe_fee_fixed": 0.30,               # Fixed fee per transaction ($0.30)
    
    # Infrastructure & Hosting
    "base_infra_monthly": 0.00,             # Supabase & Cloud Run Free Tier ($0.00/mo)
    "supabase_tier": "free",
    "cloud_run_tier": "free"
}

# Plan Tiers (calibrated to DialNode Stripe production catalog)
PLAN_TIERS = {
    "starter": {
        "name": "Starter",
        "price": 50.00,
        "included_minutes": 300,
        "overage_rate": 0.40,
    },
    "growth": {
        "name": "Growth",
        "price": 150.00,
        "included_minutes": 1000,
        "overage_rate": 0.40,
    },
    "scale": {
        "name": "Scale",
        "price": 300.00,
        "included_minutes": 2500,
        "overage_rate": 0.40,
    }
}


def calc_billed_minutes(seconds: int) -> int:
    """
    Calculate billable minutes according to Twilio telephony standards.
    Twilio bills voice duration rounded UP to the nearest whole minute (60s increments).
    A 0-second call is 0 minutes; a 1-second call is 1 billed minute.
    """
    if not seconds or seconds <= 0:
        return 0
    return math.ceil(seconds / 60.0)

def fetch_stripe_metrics() -> Dict[str, Any]:
    """
    Fetch live payment, subscription, fee, and balance data directly from Stripe API.
    """
    if not getattr(config, "STRIPE_SECRET_KEY", None):
        return {"connected": False, "mrr": 0.0, "total_gross_collected": 0.0, "charges": [], "subscriptions": []}

    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        # 1. Available & Pending Balance
        bal = stripe.Balance.retrieve()
        avail_bal = sum(b.amount for b in bal.available) / 100.0
        pending_bal = sum(b.amount for b in bal.pending) / 100.0

        # 2. Active Subscriptions
        subs = stripe.Subscription.list(status='active', limit=100, expand=['data.customer'])
        stripe_mrr = 0.0
        active_subs = []
        subs_map = {}

        for s in subs.data:
            sd = s.to_dict()
            items = sd.get('items', {}).get('data', [])
            sub_amt = 0.0
            plan_name = 'Growth'
            for it in items:
                p = it.get('price') or {}
                amt = (p.get('unit_amount') or 0) / 100.0
                if amt >= 10.0:
                    sub_amt += amt
                    if amt == 49.0: plan_name = 'Starter'
                    elif amt == 150.0: plan_name = 'Growth'
                    elif amt in (299.0, 300.0): plan_name = 'Scale'
            
            stripe_mrr += sub_amt
            cust = sd.get('customer') or {}
            cust_id = cust.get('id') if isinstance(cust, dict) else cust
            cust_name = cust.get('name') if isinstance(cust, dict) else 'Unknown'
            cust_email = cust.get('email') if isinstance(cust, dict) else 'Unknown'

            sub_info = {
                'subscription_id': sd.get('id'),
                'customer_id': cust_id,
                'customer_name': cust_name,
                'customer_email': cust_email,
                'amount': sub_amt,
                'plan': plan_name,
                'status': sd.get('status'),
                'current_period_end': sd.get('current_period_end')
            }
            active_subs.append(sub_info)
            if cust_id:
                subs_map[cust_id] = sub_info
            subs_map[sd.get('id')] = sub_info

        # 3. Successful Charges, Gross, Fees, Net
        charges = stripe.Charge.list(limit=100, expand=['data.balance_transaction', 'data.customer'])
        total_gross = 0.0
        total_fees = 0.0
        total_net = 0.0
        recent_charges = []

        for ch in charges.data:
            cd = ch.to_dict()
            if cd.get('status') == 'succeeded' and cd.get('paid'):
                amt = cd.get('amount', 0) / 100.0
                bt = cd.get('balance_transaction') or {}
                fee = (bt.get('fee') or 0) / 100.0 if isinstance(bt, dict) else 0.0
                net = (bt.get('net') or 0) / 100.0 if isinstance(bt, dict) else (amt - fee)
                total_gross += amt
                total_fees += fee
                total_net += net
                cust = cd.get('customer') or {}
                cust_name = cust.get('name') if isinstance(cust, dict) else 'Customer'
                cust_email = cust.get('email') if isinstance(cust, dict) else ''

                recent_charges.append({
                    'id': cd.get('id'),
                    'amount': amt,
                    'fee': fee,
                    'net': net,
                    'currency': cd.get('currency', 'usd').upper(),
                    'customer_name': cust_name,
                    'customer_email': cust_email,
                    'created': cd.get('created'),
                    'receipt_url': cd.get('receipt_url')
                })

        return {
            "connected": True,
            "mrr": round(stripe_mrr, 2),
            "arr": round(stripe_mrr * 12, 2),
            "active_subscriptions_count": len(active_subs),
            "subscriptions": active_subs,
            "subscriptions_map": subs_map,
            "total_gross_collected": round(total_gross, 2),
            "total_stripe_fees": round(total_fees, 2),
            "total_net_collected": round(total_net, 2),
            "available_balance": round(avail_bal, 2),
            "pending_balance": round(pending_bal, 2),
            "charges_count": len(recent_charges),
            "recent_charges": recent_charges[:10]
        }
    except Exception as e:
        logger.error(f"Error communicating with Stripe: {e}")
        return {
            "connected": False,
            "error": str(e),
            "mrr": 0.0,
            "total_gross_collected": 0.0,
            "charges": []
        }

def fetch_twilio_metrics() -> Dict[str, Any]:
    """
    Fetch live account balance and month-to-date usage records directly from Twilio API.
    """
    sid = getattr(config, "TWILIO_ACCOUNT_SID", None)
    tok = getattr(config, "TWILIO_AUTH_TOKEN", None)
    if not sid or not tok:
        return {
            "connected": False,
            "error": "Twilio credentials not configured in .env",
            "balance": 0.0,
            "currency": "USD",
            "month_to_date_total": 0.0,
            "categories": {}
        }
    
    try:
        from twilio.rest import Client
        client = Client(sid, tok)
        
        # 1. Live account balance
        bal_obj = client.api.v2010.account.balance.fetch()
        balance = float(bal_obj.balance or 0.0)
        currency = (bal_obj.currency or "USD").upper()

        # 2. Current Month Usage Records
        records = client.usage.records.this_month.list()
        month_total = 0.0
        categories_dict = {}
        
        for r in records:
            price = float(r.price or 0.0)
            usage = float(r.usage or 0.0)
            cat = r.category
            
            if cat == "totalprice":
                month_total = price
            elif price > 0 or usage > 0:
                categories_dict[cat] = {
                    "usage": usage,
                    "usage_unit": r.usage_unit or "",
                    "price": round(price, 4),
                    "description": r.description or cat
                }
                
        # If totalprice record wasn't explicitly found, sum individual categories
        if month_total == 0.0 and categories_dict:
            month_total = round(sum(item["price"] for item in categories_dict.values()), 4)

        return {
            "connected": True,
            "account_sid_masked": sid[:6] + "..." + sid[-4:],
            "balance": round(balance, 2),
            "currency": currency,
            "month_to_date_total": round(month_total, 2),
            "categories": categories_dict
        }
    except Exception as e:
        logger.error(f"Error communicating with Twilio: {e}")
        return {
            "connected": False,
            "error": str(e),
            "balance": 0.0,
            "currency": "USD",
            "month_to_date_total": 0.0,
            "categories": {}
        }

def fetch_google_billing_metrics() -> Dict[str, Any]:
    """
    Fetch live Google Cloud billing account information using service account key.
    """
    key_path = getattr(config, "GCP_KEY_PATH", None)
    if not key_path or not os.path.exists(str(key_path)):
        return {
            "connected": False,
            "status": "missing_key",
            "message": "Service account JSON key not found in project folder."
        }
        
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        scopes = [
            "https://www.googleapis.com/auth/cloud-billing.readonly",
            "https://www.googleapis.com/auth/cloud-platform"
        ]
        creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=scopes)
        service = build("cloudbilling", "v1", credentials=creds, cache_discovery=False)
        
        account_id = getattr(config, "GCP_BILLING_ACCOUNT_ID", "01D9EB-6CC35F-F66906")
        account_name = f"billingAccounts/{account_id}" if not str(account_id).startswith("billingAccounts/") else account_id
        
        try:
            acc_info = service.billingAccounts().get(name=account_name).execute()
            return {
                "connected": True,
                "status": "synced",
                "service_account": creds.service_account_email,
                "billing_account_id": account_id,
                "billing_account_name": acc_info.get("displayName", "Bloodhunt"),
                "is_open": acc_info.get("open", True),
                "message": "Connected to Google Cloud Billing API"
            }
        except Exception as perm_err:
            err_str = str(perm_err)
            if "The caller does not have permission" in err_str:
                return {
                    "connected": False,
                    "status": "permission_needed",
                    "service_account": creds.service_account_email,
                    "billing_account_id": account_id,
                    "message": "Service account needs 'Billing Account Viewer' role on Billing Account 01D9EB-6CC35F-F66906."
                }
            return {
                "connected": False,
                "status": "error",
                "service_account": creds.service_account_email,
                "billing_account_id": account_id,
                "message": err_str
            }
    except Exception as e:
        logger.error(f"Error communicating with Google Cloud Billing API: {e}")
        return {
            "connected": False,
            "status": "error",
            "message": str(e)
        }

def get_financial_summary() -> Dict[str, Any]:
    """
    Calculate real business financial metrics combining live Stripe payment records
    (MRR, charges, fees, balance), live Twilio usage & balance records, Google Cloud Billing records,
    and PostgreSQL database records (call_logs, tenants).
    
    Rigorously segments:
      - Current Billing Cycle P&L (Monthly Run-Rate: MRR vs Monthly Direct COGS)
      - Cumulative Lifetime Cash Flow (Cash Collected vs All-Time Burn)
    """
    # 1. Fetch live Stripe, Twilio, and Google metrics
    stripe_data = fetch_stripe_metrics()
    subs_map = stripe_data.get("subscriptions_map", {})
    twilio_data = fetch_twilio_metrics()
    google_data = fetch_google_billing_metrics()

    conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=10)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 2. Phone numbers count
        cur.execute("SELECT count(*) as count FROM phone_numbers;")
        phone_count = cur.fetchone()["count"]

        # 3. Active tenants from DB
        cur.execute("""
            SELECT id, company_name, subscription_status, subscription_plan, 
                   stripe_customer_id, stripe_subscription_id, 
                   current_period_start, current_period_end, created_at 
            FROM tenants 
            WHERE subscription_status = 'active';
        """)
        active_tenants = [dict(r) for r in cur.fetchall()]

        # 4. Process each active tenant's current billing cycle and all-time usage
        tenant_ledger = []
        monthly_mrr = 0.0
        monthly_overage_rev = 0.0

        # Totals for Current Billing Cycle
        cycle_total_calls = 0
        cycle_total_seconds = 0
        cycle_total_billed_mins = 0
        cycle_twilio_voice = 0.0
        cycle_twilio_streams = 0.0
        cycle_twilio_recording = 0.0
        cycle_gemini_live = 0.0
        cycle_gemini_transcription = 0.0
        cycle_gemini_audit = 0.0
        cycle_phone_numbers = 0.0
        cycle_stripe_fees = 0.0

        # Totals for All-Time Cumulative
        all_time_total_calls = 0
        all_time_total_seconds = 0
        all_time_total_billed_mins = 0

        now = datetime.now()

        for t in active_tenants:
            tid = t["id"]
            cid = t.get("stripe_customer_id")
            sid = t.get("stripe_subscription_id")

            # Determine plan and base subscription price
            stripe_sub = subs_map.get(cid) or subs_map.get(sid)
            if stripe_sub:
                plan_name = stripe_sub["plan"]
                plan_price = stripe_sub["amount"]
                sub_status = stripe_sub["status"]
            else:
                plan_key = (t.get("subscription_plan") or "growth").lower()
                plan_name = plan_key.capitalize()
                plan_price = PLAN_TIERS.get(plan_key, PLAN_TIERS["growth"])["price"] if t["subscription_status"] == "active" else 0.0
                sub_status = t["subscription_status"]

            monthly_mrr += plan_price
            plan_info = PLAN_TIERS.get(plan_name.lower(), PLAN_TIERS["growth"])

            # Define current billing cycle window
            p_start = t.get("current_period_start") or (now - timedelta(days=30))
            p_end = t.get("current_period_end") or now

            # Query calls for this tenant within current billing cycle
            cur.execute("""
                SELECT id, duration_seconds 
                FROM call_logs 
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s;
            """, (tid, p_start, p_end))
            p_calls = cur.fetchall()
            p_call_count = len(p_calls)
            p_seconds = sum(c["duration_seconds"] or 0 for c in p_calls)
            p_frac_mins = round(p_seconds / 60.0, 1)
            p_billed_mins = sum(calc_billed_minutes(c["duration_seconds"] or 0) for c in p_calls)

            # Query all-time calls for this tenant
            cur.execute("""
                SELECT id, duration_seconds 
                FROM call_logs 
                WHERE tenant_id = %s;
            """, (tid,))
            all_calls = cur.fetchall()
            a_call_count = len(all_calls)
            a_seconds = sum(c["duration_seconds"] or 0 for c in all_calls)
            a_billed_mins = sum(calc_billed_minutes(c["duration_seconds"] or 0) for c in all_calls)

            # Current Cycle Costs for this Tenant
            t_voice_cost = round(p_billed_mins * COST_RATES["twilio_voice_per_min"], 4)
            t_stream_cost = round(p_frac_mins * COST_RATES["twilio_streams_per_min"], 4)
            t_record_cost = round(p_billed_mins * COST_RATES["twilio_recording_per_min"], 4)
            t_live_cost = round(p_frac_mins * COST_RATES["gemini_live_per_min"], 4)
            t_transcript_cost = round(p_call_count * COST_RATES["gemini_transcription_per_call"], 4)
            t_audit_cost = round(p_call_count * COST_RATES["gemini_audit_per_call"], 4)
            t_phone_cost = COST_RATES["phone_number_monthly"] # $1.15 dedicated number
            t_stripe_fee = round(plan_price * COST_RATES["stripe_fee_pct"] + COST_RATES["stripe_fee_fixed"], 2) if plan_price > 0 else 0.0

            t_direct_cogs = round(
                t_voice_cost + t_stream_cost + t_record_cost + 
                t_live_cost + t_transcript_cost + t_audit_cost + 
                t_phone_cost + t_stripe_fee, 
                2
            )

            # Overage calculation
            included_mins = plan_info.get("included_minutes", 450)
            overage_mins = max(0, p_billed_mins - included_mins)
            overage_revenue = round(overage_mins * plan_info.get("overage_rate", 0.30), 2)
            monthly_overage_rev += overage_revenue
            t_total_revenue = round(plan_price + overage_revenue, 2)

            t_net_profit = round(t_total_revenue - t_direct_cogs, 2)
            t_margin_pct = round((t_net_profit / t_total_revenue * 100), 1) if t_total_revenue > 0 else 0.0

            # Accumulate cycle totals
            cycle_total_calls += p_call_count
            cycle_total_seconds += p_seconds
            cycle_total_billed_mins += p_billed_mins
            cycle_twilio_voice += t_voice_cost
            cycle_twilio_streams += t_stream_cost
            cycle_twilio_recording += t_record_cost
            cycle_gemini_live += t_live_cost
            cycle_gemini_transcription += t_transcript_cost
            cycle_gemini_audit += t_audit_cost
            cycle_phone_numbers += t_phone_cost
            cycle_stripe_fees += t_stripe_fee

            # Accumulate all-time totals
            all_time_total_calls += a_call_count
            all_time_total_seconds += a_seconds
            all_time_total_billed_mins += a_billed_mins

            tenant_ledger.append({
                "tenant_id": tid,
                "company_name": t["company_name"] or f"Tenant #{tid}",
                "stripe_customer_id": cid,
                "plan": plan_name,
                "status": sub_status,
                # New fields
                "period_calls": p_call_count,
                "period_minutes": p_frac_mins,
                "period_billed_minutes": p_billed_mins,
                "all_time_calls": a_call_count,
                "all_time_minutes": round(a_seconds / 60.0, 1),
                "revenue": t_total_revenue,
                "base_revenue": plan_price,
                "overage_revenue": overage_revenue,
                "direct_cogs": t_direct_cogs,
                # Legacy aliases for cached frontends
                "calls": p_call_count,
                "minutes": p_billed_mins,
                "api_cogs": t_direct_cogs,
                "cost_breakdown": {
                    "twilio_telephony": round(t_voice_cost + t_stream_cost + t_record_cost, 2),
                    "gemini_ai": round(t_live_cost + t_transcript_cost + t_audit_cost, 2),
                    "phone_number": t_phone_cost,
                    "stripe_fee": t_stripe_fee
                },
                "profit": t_net_profit,
                "margin_pct": t_margin_pct
            })

        # Final Monthly Period P&L
        period_revenue = round(monthly_mrr + monthly_overage_rev, 2)
        base_infra = COST_RATES["base_infra_monthly"]
        
        cycle_telephony = round(cycle_twilio_voice + cycle_twilio_streams + cycle_twilio_recording, 2)
        cycle_gemini_ai = round(cycle_gemini_live + cycle_gemini_transcription + cycle_gemini_audit, 2)
        cycle_total_cogs = round(cycle_telephony + cycle_gemini_ai + cycle_phone_numbers + cycle_stripe_fees + base_infra, 2)

        period_gross_profit = round(period_revenue - cycle_total_cogs, 2)
        period_gross_margin_pct = round((period_gross_profit / period_revenue * 100), 1) if period_revenue > 0 else 0.0

        # All-Time Cumulative Burn
        all_time_frac_mins = round(all_time_total_seconds / 60.0, 1)
        all_time_voice = round(all_time_total_billed_mins * COST_RATES["twilio_voice_per_min"], 2)
        all_time_streams = round(all_time_frac_mins * COST_RATES["twilio_streams_per_min"], 2)
        all_time_recording = round(all_time_total_billed_mins * COST_RATES["twilio_recording_per_min"], 2)
        all_time_live = round(all_time_frac_mins * COST_RATES["gemini_live_per_min"], 2)
        all_time_transcription = round(all_time_total_calls * COST_RATES["gemini_transcription_per_call"], 2)
        all_time_audit = round(all_time_total_calls * COST_RATES["gemini_audit_per_call"], 3)
        
        # Dynamic active tenant lifespan based on created_at
        total_tenant_months = 0.0
        for t in active_tenants:
            t_created = t.get("created_at") or now
            tenure_months = max(1.0, (now - t_created).total_seconds() / (30.0 * 86400.0))
            total_tenant_months += tenure_months
        avg_tenure = (total_tenant_months / len(active_tenants)) if active_tenants else 1.0
        all_time_numbers = round(phone_count * COST_RATES["phone_number_monthly"] * avg_tenure, 2)
        
        all_time_api_burn = round(
            all_time_voice + all_time_streams + all_time_recording + 
            all_time_live + all_time_transcription + all_time_audit + all_time_numbers, 
            2
        )

        # Lifetime Cash Reconciliation
        gross_collected = stripe_data.get("total_gross_collected", 0.0)
        stripe_fees = stripe_data.get("total_stripe_fees", 0.0)
        net_cash_collected = stripe_data.get("total_net_collected", 0.0)
        lifetime_net_profit = round(net_cash_collected - all_time_api_burn, 2)

        # Unit Economics (Blended)
        # Variable rate per minute = Voice ($0.0085) + Streams ($0.0040) + Recording ($0.0025) + Gemini Live ($0.0300) = $0.0450
        blended_cogs_per_minute = round(
            COST_RATES["twilio_voice_per_min"] + 
            COST_RATES["twilio_streams_per_min"] + 
            COST_RATES["twilio_recording_per_min"] + 
            COST_RATES["gemini_live_per_min"], 
            4
        )
        # Per call processing = Post-call transcription ($0.0025) + QA audit ($0.0008) = $0.0033
        per_call_fixed_cogs = round(
            COST_RATES["gemini_transcription_per_call"] + 
            COST_RATES["gemini_audit_per_call"], 
            4
        )
        avg_call_seconds = round(all_time_total_seconds / float(all_time_total_calls), 1) if all_time_total_calls > 0 else 0.0
        avg_billed_mins_per_call = round(all_time_total_billed_mins / float(all_time_total_calls), 2) if all_time_total_calls > 0 else 0.0
        avg_frac_mins_per_call = round(avg_call_seconds / 60.0, 3)

        # Precise average cost per call:
        # Whole-minute ceil services: Voice ($0.0085) + Recording ($0.0025)
        # Fractional exact-duration services: Media Streams ($0.0040) + Gemini Live ($0.0300)
        ceil_telephony_per_call = avg_billed_mins_per_call * (COST_RATES["twilio_voice_per_min"] + COST_RATES["twilio_recording_per_min"])
        exact_streaming_per_call = avg_frac_mins_per_call * (COST_RATES["twilio_streams_per_min"] + COST_RATES["gemini_live_per_min"])
        avg_cost_per_call = round(ceil_telephony_per_call + exact_streaming_per_call + per_call_fixed_cogs, 4)

        # Profit Splits on Monthly Gross Profit (50% Founder, 30% Closer, 20% Cold Caller)
        founder_share = round(max(0, period_gross_profit * 0.50), 2)
        sales_closer_share = round(max(0, period_gross_profit * 0.30), 2)
        cold_caller_share = round(max(0, period_gross_profit * 0.20), 2)

        direct_telephony_total = round(cycle_twilio_voice + cycle_twilio_streams + cycle_twilio_recording + cycle_phone_numbers, 2)
        direct_ai_total = round(cycle_gemini_live + cycle_gemini_transcription + cycle_gemini_audit, 2)
        direct_voice_ai_total = round(direct_telephony_total + direct_ai_total, 2)

        monthly_cogs_dict = {
            "twilio_voice": round(cycle_twilio_voice, 2),
            "twilio_streams": round(cycle_twilio_streams, 2),
            "twilio_recording": round(cycle_twilio_recording, 2),
            "twilio_numbers": round(cycle_phone_numbers, 2),
            "gemini_live": round(cycle_gemini_live, 2),
            "gemini_transcription": round(cycle_gemini_transcription, 2),
            "gemini_audit": round(cycle_gemini_audit, 2),
            "phone_numbers": round(cycle_phone_numbers, 2),
            "stripe_fees": round(cycle_stripe_fees, 2),
            "infrastructure": base_infra,
            "direct_telephony": direct_telephony_total,
            "direct_ai": direct_ai_total,
            "direct_voice_ai": direct_voice_ai_total,
            "total_monthly_cogs": cycle_total_cogs,
            "total_api_cogs": cycle_total_cogs  # legacy alias
        }

        stripe_feed_dict = {
            "gross_collected": gross_collected,
            "stripe_fees": stripe_fees,
            "net_collected": net_cash_collected,
            "total_gross_collected": gross_collected,
            "total_stripe_fees": stripe_fees,
            "total_net_collected": net_cash_collected,
            "available_balance": stripe_data.get("available_balance", 0.0),
            "recent_charges": stripe_data.get("recent_charges", [])
        }

        # Telemetry-derived metrics from PostgreSQL for Growth & Capacity Simulator
        cur.execute("SELECT COUNT(*) FROM leads;")
        total_db_leads = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) FROM appointments;")
        total_db_appts = cur.fetchone()["count"]
        cur.execute("SELECT AVG(duration_seconds) FROM call_logs WHERE duration_seconds > 5;")
        ans_row = cur.fetchone()
        avg_answered_seconds = round(float(ans_row["avg"] or 49.5), 1)
        avg_answered_mins = round(avg_answered_seconds / 60.0, 1)

        lead_capture_pct = round((total_db_leads / float(all_time_total_calls)) * 100.0, 1) if all_time_total_calls > 0 else 50.5
        appt_booking_pct = round((total_db_appts / float(all_time_total_calls)) * 100.0, 1) if all_time_total_calls > 0 else 5.8

        cur.execute("""
            WITH daily AS (
                SELECT tenant_id, DATE(created_at) as dt, COUNT(*) as c 
                FROM call_logs 
                GROUP BY tenant_id, DATE(created_at)
            )
            SELECT AVG(c) FROM daily;
        """)
        daily_row = cur.fetchone()
        avg_daily_calls = round(float(daily_row["avg"] or 4.9), 1)

        telemetry_defaults = {
            "tenants_count": len(active_tenants),
            "calls_per_day_per_tenant": avg_daily_calls,
            "avg_call_minutes": avg_answered_mins,
            "transfer_to_human_pct": 1.0,
            "plan_tier": "growth",
            "total_db_calls": all_time_total_calls,
            "avg_answered_seconds": avg_answered_seconds
        }

        return {
            "revenue_source": "stripe" if stripe_data.get("connected") else "database_fallback",
            "mrr": monthly_mrr,
            "arr": round(monthly_mrr * 12, 2),
            "period_revenue": period_revenue,
            "period_overage_revenue": monthly_overage_rev,
            "active_tenants_count": len(active_tenants),
            "phone_numbers_count": phone_count,
            
            # Legacy top-level fields (prevents any cached client from seeing undefined/0)
            "total_calls": cycle_total_calls,
            "total_minutes": cycle_total_billed_mins,
            "avg_call_duration_seconds": avg_call_seconds,
            "actual_costs": monthly_cogs_dict,
            "stripe": stripe_feed_dict,
            
            # Current Billing Period P&L (Monthly Run-Rate)
            "current_period": {
                "calls_count": cycle_total_calls,
                "seconds": cycle_total_seconds,
                "fractional_minutes": round(cycle_total_seconds / 60.0, 1),
                "billed_minutes": cycle_total_billed_mins,
                "cogs": monthly_cogs_dict,
                "gross_profit": period_gross_profit,
                "gross_margin_pct": period_gross_margin_pct
            },

            # Cumulative Lifetime Cash Flow
            "lifetime": {
                "calls_count": all_time_total_calls,
                "seconds": all_time_total_seconds,
                "fractional_minutes": all_time_frac_mins,
                "billed_minutes": all_time_total_billed_mins,
                "gross_collected": gross_collected,
                "stripe_fees": stripe_fees,
                "net_cash_collected": net_cash_collected,
                "lifetime_api_burn": all_time_api_burn,
                "lifetime_net_profit": lifetime_net_profit,
                "available_balance": stripe_data.get("available_balance", 0.0),
                "recent_charges": stripe_data.get("recent_charges", [])
            },

            # Unit Economics & Rates
            "unit_economics": {
                "cost_per_minute": blended_cogs_per_minute,
                "post_call_processing_per_call": per_call_fixed_cogs,
                "cost_per_call": avg_cost_per_call,
                "avg_cost_per_call": avg_cost_per_call,
                "avg_call_duration_seconds": avg_call_seconds,
                "avg_billed_mins_per_call": avg_billed_mins_per_call,
                "gross_profit": period_gross_profit,
                "gross_margin_pct": period_gross_margin_pct,
                "monthly_gross_profit": period_gross_profit,
                "monthly_margin_pct": period_gross_margin_pct
            },
            
            # Rate Engine & Telemetry Defaults
            "rates": COST_RATES,
            "plans": PLAN_TIERS,
            "telemetry_defaults": telemetry_defaults,
            
            # Team Commission Splits (Monthly P&L)
            "profit_splits": {
                "founder_share_50": founder_share,
                "sales_closer_30": sales_closer_share,
                "cold_caller_20": cold_caller_share
            },
            
            # Per-Tenant Performance Ledger
            "tenant_ledger": tenant_ledger,

            # Live Twilio Integration
            "twilio": twilio_data,

            # 3-Way Live Reconciliation (Stripe, Twilio, Gemini)
            "reconciliation": {
                "stripe": {
                    "connected": stripe_data.get("connected", False),
                    "live_balance": stripe_data.get("available_balance", 0.0),
                    "live_fees": stripe_data.get("total_stripe_fees", 0.0),
                    "live_gross": stripe_data.get("total_gross_collected", 0.0),
                    "cycle_fees_calculated": round(cycle_stripe_fees, 2)
                },
                "twilio": {
                    "connected": twilio_data.get("connected", False),
                    "live_balance": twilio_data.get("balance", 0.0),
                    "live_month_to_date": twilio_data.get("month_to_date_total", 0.0),
                    "cycle_telephony_calculated": round(cycle_twilio_voice + cycle_twilio_streams + cycle_twilio_recording + cycle_phone_numbers, 2),
                    "categories": twilio_data.get("categories", {})
                },
                "google": {
                    "connected": google_data.get("connected", False),
                    "status": google_data.get("status", "unknown"),
                    "service_account": google_data.get("service_account"),
                    "billing_account_id": google_data.get("billing_account_id"),
                    "billing_account_name": google_data.get("billing_account_name"),
                    "method": "Real-time per-second token model ($0.0300/min)",
                    "cycle_ai_calculated": round(cycle_gemini_live + cycle_gemini_transcription + cycle_gemini_audit, 2),
                    "message": google_data.get("message")
                }
            },
            "google_cloud": google_data
        }
    finally:
        conn.close()

def simulate_projections(
    tenants_count: int = 10,
    plan_tier: str = "growth",
    calls_per_day_per_tenant: float = 5.0,
    avg_call_minutes: float = 1.0,
    transfer_to_human_pct: float = 0.01,
    infra_tier: str = "free"
) -> Dict[str, Any]:
    """
    Interactive SaaS business financial and capacity simulator grounded in production telemetry:
    - Base Telephony: Twilio Voice ($0.0085/min), Streams ($0.0040/min), Recording ($0.0025/min)
    - Live AI: Gemini 3.8 Live audio tokens ($0.0300/min), Transcription ($0.0025/call), QA ($0.0008/call)
    - Live Transfers: Staff forward leg via Twilio <Dial> ($0.0140/min)
    - Capacity Engineering: Peak hour concurrency via Erlang Poisson distribution, required Twilio lines & Cloud Run instances
    - Merchant Fees: Stripe 2.9% + $0.30 per subscriber
    - Phone Numbers: $1.15/mo per active tenant
    - Plan Tiers: Starter (300m / $50), Growth (1,000m / $150), Scale (2,500m / $300), Overage: $0.40/min
    """
    import math

    if transfer_to_human_pct is not None and transfer_to_human_pct >= 1.0:
        transfer_to_human_pct = transfer_to_human_pct / 100.0
    transfer_to_human_pct = max(0.0, float(transfer_to_human_pct if transfer_to_human_pct is not None else 0.01))

    tier_key = str(plan_tier).lower()
    if tier_key == "blended":
        # Blended SaaS portfolio mix: 60% Growth, 30% Starter, 10% Scale
        monthly_plan_price = round(0.60 * 150.0 + 0.30 * 50.0 + 0.10 * 300.0, 2)  # $135.00
        included_mins_per_tenant = int(round(0.60 * 1000 + 0.30 * 300 + 0.10 * 2500)) # 940 mins
        overage_rate = 0.40
        plan_display_name = "Blended Portfolio (60% Growth, 30% Starter, 10% Scale)"
    else:
        plan = PLAN_TIERS.get(tier_key, PLAN_TIERS["growth"])
        monthly_plan_price = plan["price"]
        included_mins_per_tenant = plan["included_minutes"]
        overage_rate = plan["overage_rate"]
        plan_display_name = plan["name"]

    # Usage Projections (30 days/month)
    total_calls_month = int(round(tenants_count * calls_per_day_per_tenant * 30))
    total_minutes_month = round(total_calls_month * avg_call_minutes, 1)

    # Smooth whole-minute ceiling telephony overhead matching actual DB distribution
    avg_ceil_factor = max(1.0, avg_call_minutes + 0.35) if avg_call_minutes < 1.0 else (avg_call_minutes + 0.40)
    billed_minutes_month = round(total_calls_month * avg_ceil_factor, 1)

    # Subscription Revenue
    base_mrr = round(tenants_count * monthly_plan_price, 2)

    # Overage Revenue
    total_included_minutes = tenants_count * included_mins_per_tenant
    overage_minutes = max(0.0, billed_minutes_month - total_included_minutes)
    overage_revenue = round(overage_minutes * overage_rate, 2)

    total_mrr = round(base_mrr + overage_revenue, 2)
    total_arr = round(total_mrr * 12, 2)

    # Comprehensive COGS Calculation
    # 1. Telephony: Inbound Voice + Media Streams + Recording + Dedicated Numbers + Human Transfers
    twilio_voice = round(billed_minutes_month * COST_RATES["twilio_voice_per_min"], 2)
    twilio_recording = round(billed_minutes_month * COST_RATES["twilio_recording_per_min"], 2)
    twilio_streams = round(total_minutes_month * COST_RATES["twilio_streams_per_min"], 2)
    
    transferred_calls = int(round(total_calls_month * transfer_to_human_pct))
    transferred_minutes = round(transferred_calls * avg_ceil_factor, 1)
    twilio_transfers = round(transferred_minutes * 0.0140, 2)
    twilio_numbers = round(tenants_count * COST_RATES["phone_number_monthly"], 2)
    twilio_usage = round(twilio_voice + twilio_recording + twilio_streams + twilio_transfers, 2)
    total_twilio_cost = round(twilio_usage + twilio_numbers, 2)

    # 2. AI: Gemini Live + Transcription + Audit
    gemini_live = round(total_minutes_month * COST_RATES["gemini_live_per_min"], 2)
    gemini_transcription = round(total_calls_month * COST_RATES["gemini_transcription_per_call"], 2)
    gemini_audit = round(total_calls_month * COST_RATES["gemini_audit_per_call"], 2)
    total_gemini_cost = round(gemini_live + gemini_transcription + gemini_audit, 2)

    # 3. Direct Telephony & AI Cost (before merchant fees & hosting)
    direct_voice_ai_cost = round(total_twilio_cost + total_gemini_cost, 2)

    # 4. Payment Gateway: Stripe merchant fees (2.9% on total MRR processed + $0.30 per subscriber charge)
    total_stripe_fees = round(total_mrr * COST_RATES["stripe_fee_pct"] + (tenants_count * COST_RATES["stripe_fee_fixed"]), 2)

    # 5. Infrastructure
    infra_cost = 0.00 if str(infra_tier).lower() == "free" else 25.00

    total_cogs = round(direct_voice_ai_cost + total_stripe_fees + infra_cost, 2)
    
    gross_profit = round(total_mrr - total_cogs, 2)
    margin_pct = round((gross_profit / total_mrr * 100), 1) if total_mrr > 0 else 0.0
    profit_per_client = round(gross_profit / tenants_count, 2) if tenants_count > 0 else 0.0
    cost_per_call = round(total_cogs / total_calls_month, 4) if total_calls_month > 0 else 0.0
    voice_ai_cost_per_call = round(direct_voice_ai_cost / total_calls_month, 4) if total_calls_month > 0 else 0.0

    # Capacity & Concurrency Engineering
    daily_calls = tenants_count * calls_per_day_per_tenant
    peak_hour_calls = daily_calls * 0.15 # 15% peak hour concentration (telemetry verified)
    traffic_erlangs = peak_hour_calls * (avg_call_minutes / 60.0)
    peak_concurrent_calls = max(1, int(math.ceil(traffic_erlangs + 2.33 * math.sqrt(max(0.1, traffic_erlangs)))))
    cloud_run_containers = max(1, int(math.ceil(peak_concurrent_calls / 20.0)))
    bandwidth_mbps = round((peak_concurrent_calls * 64.0) / 1000.0, 2)
    
    if peak_concurrent_calls <= 50:
        gemini_status = "Healthy (Tier 1 Default)"
    elif peak_concurrent_calls <= 100:
        gemini_status = "Tier 1 Scaling (50-100 Sessions)"
    else:
        gemini_status = "High Concurrency (Enterprise Quota Needed)"

    # Team Split (50% Founder, 30% Closer, 20% Cold Caller)
    founder_payout = round(max(0, gross_profit * 0.50), 2)
    sales_closer_payout = round(max(0, gross_profit * 0.30), 2)
    cold_caller_payout = round(max(0, gross_profit * 0.20), 2)

    return {
        "inputs": {
            "tenants_count": tenants_count,
            "plan_tier": plan_display_name,
            "calls_per_day_per_tenant": calls_per_day_per_tenant,
            "avg_call_minutes": avg_call_minutes,
            "transfer_to_human_pct": round(transfer_to_human_pct * 100, 1),
            "infra_tier": infra_tier
        },
        "volume": {
            "monthly_calls": total_calls_month,
            "monthly_minutes": total_minutes_month,
            "billed_minutes": billed_minutes_month,
            "included_minutes": total_included_minutes,
            "overage_minutes": overage_minutes,
            "transferred_calls": transferred_calls,
            "transferred_minutes": transferred_minutes
        },
        "revenue": {
            "base_mrr": base_mrr,
            "overage_revenue": overage_revenue,
            "total_mrr": total_mrr,
            "total_arr": total_arr
        },
        "costs": {
            "twilio_voice": twilio_voice,
            "twilio_streams": twilio_streams,
            "twilio_recording": twilio_recording,
            "twilio_transfers": twilio_transfers,
            "twilio_usage": twilio_usage,
            "twilio_numbers": twilio_numbers,
            "total_twilio": total_twilio_cost,
            "gemini_live": gemini_live,
            "gemini_transcription": gemini_transcription,
            "gemini_audit": gemini_audit,
            "total_gemini": total_gemini_cost,
            "stripe_fees": total_stripe_fees,
            "infrastructure": infra_cost,
            "direct_voice_ai": direct_voice_ai_cost,
            "total_cogs": total_cogs
        },
        "profitability": {
            "gross_profit": gross_profit,
            "margin_pct": margin_pct,
            "profit_per_client": profit_per_client,
            "cost_per_minute": round(total_cogs / total_minutes_month, 4) if total_minutes_month > 0 else 0.0,
            "cost_per_call": cost_per_call,
            "voice_ai_cost_per_call": voice_ai_cost_per_call
        },
        "capacity": {
            "daily_calls": round(daily_calls, 1),
            "peak_hour_calls": round(peak_hour_calls, 1),
            "traffic_erlangs": round(traffic_erlangs, 2),
            "peak_concurrent_calls": peak_concurrent_calls,
            "cloud_run_containers": cloud_run_containers,
            "twilio_channels_required": peak_concurrent_calls,
            "gemini_status": gemini_status,
            "bandwidth_mbps": bandwidth_mbps
        },
        "team_splits": {
            "founder_50": founder_payout,
            "sales_closer_30": sales_closer_payout,
            "cold_caller_20": cold_caller_payout
        }
    }


