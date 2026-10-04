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
    # Telephony (Twilio)
    "twilio_voice_per_min": 0.0140,         # Inbound voice (billed in 60s ceil increments)
    "twilio_streams_per_min": 0.0040,       # Bidirectional Media Streams WebSocket (exact duration)
    "twilio_recording_per_min": 0.0025,     # Dual-channel MP3 call recording
    "phone_number_monthly": 1.15,           # Dedicated Twilio phone number rental per month
    "sms_cost_per_msg": 0.0129,             # Outbound SMS followup/receipt ($0.0079 + carrier fee)
    
    # AI Speech & Intelligence (Google Gemini)
    "gemini_live_per_min": 0.0750,          # Multimodal Live real-time audio WebSocket session
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

# Plan Tiers
PLAN_TIERS = {
    "starter": {
        "name": "Starter",
        "price": 49.00,
        "included_minutes": 150,
        "overage_rate": 0.35,
    },
    "growth": {
        "name": "Growth",
        "price": 150.00,
        "included_minutes": 450,
        "overage_rate": 0.30,
    },
    "scale": {
        "name": "Scale",
        "price": 299.00,
        "included_minutes": 1000,
        "overage_rate": 0.25,
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

def get_financial_summary() -> Dict[str, Any]:
    """
    Calculate real business financial metrics combining live Stripe payment records
    (MRR, charges, fees, balance) and PostgreSQL database records (call_logs, tenants).
    
    Rigorously segments:
      - Current Billing Cycle P&L (Monthly Run-Rate: MRR vs Monthly Direct COGS)
      - Cumulative Lifetime Cash Flow (Cash Collected vs All-Time Burn)
    """
    # 1. Fetch live Stripe metrics
    stripe_data = fetch_stripe_metrics()
    subs_map = stripe_data.get("subscriptions_map", {})

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
            t_record_cost = round(p_frac_mins * COST_RATES["twilio_recording_per_min"], 4)
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
                "period_calls": p_call_count,
                "period_minutes": p_frac_mins,
                "period_billed_minutes": p_billed_mins,
                "all_time_calls": a_call_count,
                "all_time_minutes": round(a_seconds / 60.0, 1),
                "revenue": t_total_revenue,
                "base_revenue": plan_price,
                "overage_revenue": overage_revenue,
                "direct_cogs": t_direct_cogs,
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
        all_time_recording = round(all_time_frac_mins * COST_RATES["twilio_recording_per_min"], 2)
        all_time_live = round(all_time_frac_mins * COST_RATES["gemini_live_per_min"], 2)
        all_time_transcription = round(all_time_total_calls * COST_RATES["gemini_transcription_per_call"], 2)
        all_time_audit = round(all_time_total_calls * COST_RATES["gemini_audit_per_call"], 3)
        all_time_numbers = round(phone_count * COST_RATES["phone_number_monthly"] * 4.0, 2) # approx 4 active tenant months
        
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
        # Variable rate per minute = Voice ($0.0140) + Streams ($0.0040) + Recording ($0.0025) + Gemini Live ($0.0750) = $0.0955
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
        avg_cost_per_call = round((avg_billed_mins_per_call * blended_cogs_per_minute) + per_call_fixed_cogs, 4)

        # Profit Splits on Monthly Gross Profit (50% Founder, 30% Closer, 20% Cold Caller)
        founder_share = round(max(0, period_gross_profit * 0.50), 2)
        sales_closer_share = round(max(0, period_gross_profit * 0.30), 2)
        cold_caller_share = round(max(0, period_gross_profit * 0.20), 2)

        return {
            "revenue_source": "stripe" if stripe_data.get("connected") else "database_fallback",
            "mrr": monthly_mrr,
            "arr": round(monthly_mrr * 12, 2),
            "period_revenue": period_revenue,
            "period_overage_revenue": monthly_overage_rev,
            "active_tenants_count": len(active_tenants),
            "phone_numbers_count": phone_count,
            
            # Current Billing Period P&L (Monthly Run-Rate)
            "current_period": {
                "calls_count": cycle_total_calls,
                "seconds": cycle_total_seconds,
                "fractional_minutes": round(cycle_total_seconds / 60.0, 1),
                "billed_minutes": cycle_total_billed_mins,
                "cogs": {
                    "twilio_voice": round(cycle_twilio_voice, 2),
                    "twilio_streams": round(cycle_twilio_streams, 2),
                    "twilio_recording": round(cycle_twilio_recording, 2),
                    "gemini_live": round(cycle_gemini_live, 2),
                    "gemini_transcription": round(cycle_gemini_transcription, 2),
                    "gemini_audit": round(cycle_gemini_audit, 2),
                    "phone_numbers": round(cycle_phone_numbers, 2),
                    "stripe_fees": round(cycle_stripe_fees, 2),
                    "infrastructure": base_infra,
                    "total_monthly_cogs": cycle_total_cogs
                },
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
                "avg_cost_per_call": avg_cost_per_call,
                "avg_call_duration_seconds": avg_call_seconds,
                "avg_billed_mins_per_call": avg_billed_mins_per_call,
                "monthly_gross_profit": period_gross_profit,
                "monthly_margin_pct": period_gross_margin_pct
            },
            
            # Rate Engine
            "rates": COST_RATES,
            "plans": PLAN_TIERS,
            
            # Team Commission Splits (Monthly P&L)
            "profit_splits": {
                "founder_share_50": founder_share,
                "sales_closer_30": sales_closer_share,
                "cold_caller_20": cold_caller_share
            },
            
            # Per-Tenant Performance Ledger
            "tenant_ledger": tenant_ledger
        }
    finally:
        conn.close()

def simulate_projections(
    tenants_count: int = 25,
    plan_tier: str = "growth",
    calls_per_day_per_tenant: int = 10,
    avg_call_minutes: float = 2.0,
    infra_tier: str = "free"
) -> Dict[str, Any]:
    """
    Interactive SaaS business financial simulator with comprehensive COGS:
    Includes Twilio Voice, Streams, Recording, Gemini Live, Transcription,
    Audit QA, Phone Numbers, Stripe Fees, and Infrastructure.
    """
    plan = PLAN_TIERS.get(plan_tier.lower(), PLAN_TIERS["growth"])
    monthly_plan_price = plan["price"]
    included_mins_per_tenant = plan["included_minutes"]
    overage_rate = plan["overage_rate"]

    # Usage Projections (30 days/month)
    total_calls_month = tenants_count * calls_per_day_per_tenant * 30
    total_minutes_month = round(total_calls_month * avg_call_minutes, 1)
    # Twilio bills in whole-minute increments; with average call duration, billed minutes is slightly higher
    billed_minutes_month = round(total_calls_month * math.ceil(avg_call_minutes), 1)

    # Subscription Revenue
    base_mrr = tenants_count * monthly_plan_price

    # Overage Revenue
    total_included_minutes = tenants_count * included_mins_per_tenant
    overage_minutes = max(0.0, billed_minutes_month - total_included_minutes)
    overage_revenue = round(overage_minutes * overage_rate, 2)

    total_mrr = round(base_mrr + overage_revenue, 2)
    total_arr = round(total_mrr * 12, 2)

    # Comprehensive COGS Calculation
    # 1. Telephony: Voice + Media Streams + Recording
    twilio_voice = round(billed_minutes_month * COST_RATES["twilio_voice_per_min"], 2)
    twilio_streams = round(total_minutes_month * COST_RATES["twilio_streams_per_min"], 2)
    twilio_recording = round(total_minutes_month * COST_RATES["twilio_recording_per_min"], 2)
    twilio_numbers = round(tenants_count * COST_RATES["phone_number_monthly"], 2)
    total_twilio_cost = round(twilio_voice + twilio_streams + twilio_recording + twilio_numbers, 2)

    # 2. AI: Gemini Live + Transcription + Audit
    gemini_live = round(total_minutes_month * COST_RATES["gemini_live_per_min"], 2)
    gemini_transcription = round(total_calls_month * COST_RATES["gemini_transcription_per_call"], 2)
    gemini_audit = round(total_calls_month * COST_RATES["gemini_audit_per_call"], 2)
    total_gemini_cost = round(gemini_live + gemini_transcription + gemini_audit, 2)

    # 3. Payment Gateway: Stripe merchant fees (2.9% + $0.30 per subscriber)
    stripe_fee_per_sub = round(monthly_plan_price * COST_RATES["stripe_fee_pct"] + COST_RATES["stripe_fee_fixed"], 2)
    total_stripe_fees = round(tenants_count * stripe_fee_per_sub, 2)

    # 4. Infrastructure
    infra_cost = 0.00 if str(infra_tier).lower() == "free" else 25.00

    # Total COGS
    total_cogs = round(total_twilio_cost + total_gemini_cost + total_stripe_fees + infra_cost, 2)
    gross_profit = round(total_mrr - total_cogs, 2)
    margin_pct = round((gross_profit / total_mrr * 100), 1) if total_mrr > 0 else 0.0

    # Team Split (50% Founder, 30% Closer, 20% Cold Caller)
    founder_payout = round(max(0, gross_profit * 0.50), 2)
    sales_closer_payout = round(max(0, gross_profit * 0.30), 2)
    cold_caller_payout = round(max(0, gross_profit * 0.20), 2)

    return {
        "inputs": {
            "tenants_count": tenants_count,
            "plan_tier": plan["name"],
            "calls_per_day_per_tenant": calls_per_day_per_tenant,
            "avg_call_minutes": avg_call_minutes
        },
        "volume": {
            "monthly_calls": total_calls_month,
            "monthly_minutes": total_minutes_month,
            "billed_minutes": billed_minutes_month,
            "overage_minutes": overage_minutes
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
            "twilio_numbers": twilio_numbers,
            "total_twilio": total_twilio_cost,
            "gemini_live": gemini_live,
            "gemini_transcription": gemini_transcription,
            "gemini_audit": gemini_audit,
            "total_gemini": total_gemini_cost,
            "stripe_fees": total_stripe_fees,
            "infrastructure": infra_cost,
            "total_cogs": total_cogs
        },
        "profitability": {
            "gross_profit": gross_profit,
            "margin_pct": margin_pct,
            "cost_per_minute": round(total_cogs / total_minutes_month, 4) if total_minutes_month > 0 else 0.0,
            "cost_per_call": round(total_cogs / total_calls_month, 4) if total_calls_month > 0 else 0.0
        },
        "team_splits": {
            "founder_50": founder_payout,
            "sales_closer_30": sales_closer_payout,
            "cold_caller_20": cold_caller_payout
        }
    }
