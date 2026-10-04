from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import psycopg2
import psycopg2.extras
import stripe
import logging
from app.core import config

logger = logging.getLogger("callAuditAgent.financials")

# Pricing & Rate Constants
COST_RATES = {
    "twilio_voice_per_min": 0.0140,       # Twilio inbound voice rate
    "twilio_streams_per_min": 0.0040,     # Twilio bidirectional media stream rate
    "twilio_total_voice_per_min": 0.0180, # Blended Twilio voice + streaming
    "gemini_live_per_min": 0.0750,        # Gemini Live audio in/out blended rate
    "gemini_audit_per_call": 0.0008,      # Gemini 3.8 Flash structured audit cost per call
    "phone_number_monthly": 1.15,         # Twilio local phone number per month
    "base_infra_monthly": 0.00,           # Free Tier for Supabase & Cloud Run ($0/mo)
    "supabase_tier": "free",              # Supabase Free Plan (500MB DB, 50k MAU)
    "cloud_run_tier": "free",             # Google Cloud Run Free Tier (2M req, 180k vCPU-s)
}

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
    """
    # 1. Fetch live Stripe metrics
    stripe_data = fetch_stripe_metrics()
    subs_map = stripe_data.get("subscriptions_map", {})

    conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=10)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 2. Aggregate call logs
        cur.execute("""
            SELECT 
                count(*) as total_calls,
                coalesce(sum(duration_seconds), 0) as total_seconds,
                coalesce(avg(duration_seconds), 0) as avg_seconds
            FROM call_logs;
        """)
        call_stats = cur.fetchone()
        total_calls = call_stats["total_calls"]
        total_seconds = call_stats["total_seconds"]
        total_minutes = round(total_seconds / 60.0, 2)
        avg_seconds = round(float(call_stats["avg_seconds"]), 1)
        avg_minutes = round(avg_seconds / 60.0, 2)

        # 3. Phone numbers count
        cur.execute("SELECT count(*) as count FROM phone_numbers;")
        phone_count = cur.fetchone()["count"]

        # 4. Active tenants from DB
        cur.execute("""
            SELECT id, company_name, subscription_status, subscription_plan, stripe_customer_id, stripe_subscription_id, created_at 
            FROM tenants 
            WHERE subscription_status = 'active';
        """)
        active_tenants = [dict(r) for r in cur.fetchall()]

        # 5. Per-tenant usage breakdown
        cur.execute("""
            SELECT 
                t.id, 
                t.company_name, 
                t.subscription_plan, 
                t.subscription_status,
                t.stripe_customer_id,
                t.stripe_subscription_id,
                count(c.id) as call_count,
                coalesce(sum(c.duration_seconds), 0) as total_seconds
            FROM tenants t
            LEFT JOIN call_logs c ON t.id = c.tenant_id
            GROUP BY t.id, t.company_name, t.subscription_plan, t.subscription_status, t.stripe_customer_id, t.stripe_subscription_id
            HAVING count(c.id) > 0 OR t.subscription_status = 'active'
            ORDER BY total_seconds DESC;
        """)
        tenant_usage_rows = [dict(r) for r in cur.fetchall()]

        # Determine MRR source of truth (Stripe vs DB fallback)
        if stripe_data.get("connected") and stripe_data.get("mrr", 0) > 0:
            mrr = stripe_data["mrr"]
            arr = stripe_data["arr"]
            revenue_source = "stripe"
        else:
            mrr = 0.0
            for t in active_tenants:
                plan_key = (t.get("subscription_plan") or "growth").lower()
                plan_info = PLAN_TIERS.get(plan_key, PLAN_TIERS["growth"])
                mrr += plan_info["price"]
            arr = round(mrr * 12, 2)
            revenue_source = "database_fallback"

        # Compute Actual API Costs to Date (based on real call durations)
        twilio_voice_cost = round(total_minutes * COST_RATES["twilio_voice_per_min"], 2)
        twilio_streams_cost = round(total_minutes * COST_RATES["twilio_streams_per_min"], 2)
        twilio_numbers_cost = round(phone_count * COST_RATES["phone_number_monthly"], 2)
        total_twilio_cost = round(twilio_voice_cost + twilio_streams_cost + twilio_numbers_cost, 2)

        gemini_live_cost = round(total_minutes * COST_RATES["gemini_live_per_min"], 2)
        gemini_audit_cost = round(total_calls * COST_RATES["gemini_audit_per_call"], 3)
        total_gemini_cost = round(gemini_live_cost + gemini_audit_cost, 2)

        total_api_cogs = round(total_twilio_cost + total_gemini_cost, 2)

        # Unit economics
        blended_cogs_per_minute = round(COST_RATES["twilio_total_voice_per_min"] + COST_RATES["gemini_live_per_min"], 4)
        avg_cost_per_call = round((avg_seconds / 60.0) * blended_cogs_per_minute + COST_RATES["gemini_audit_per_call"], 4)

        # Build tenant ledger reconciling with live Stripe subscriptions
        tenant_ledger = []
        for tu in tenant_usage_rows:
            tu_mins = round(tu["total_seconds"] / 60.0, 1)
            cid = tu.get("stripe_customer_id")
            sid = tu.get("stripe_subscription_id")

            # Match with Stripe live subscription if available
            stripe_sub = subs_map.get(cid) or subs_map.get(sid)
            if stripe_sub:
                plan_name = stripe_sub["plan"]
                plan_price = stripe_sub["amount"]
                status = stripe_sub["status"]
            else:
                plan_key = (tu["subscription_plan"] or "starter").lower()
                plan_name = plan_key.capitalize()
                plan_price = PLAN_TIERS.get(plan_key, {}).get("price", 49.0) if tu["subscription_status"] == "active" else 0.0
                status = tu["subscription_status"]

            est_cost = round(tu_mins * blended_cogs_per_minute + tu["call_count"] * COST_RATES["gemini_audit_per_call"], 2)
            est_profit = round(plan_price - est_cost, 2)
            margin = round((est_profit / plan_price * 100), 1) if plan_price > 0 else 0.0

            tenant_ledger.append({
                "tenant_id": tu["id"],
                "company_name": tu["company_name"] or f"Tenant #{tu['id']}",
                "stripe_customer_id": cid,
                "plan": plan_name,
                "status": status,
                "calls": tu["call_count"],
                "minutes": tu_mins,
                "revenue": plan_price,
                "api_cogs": est_cost,
                "profit": est_profit,
                "margin_pct": margin
            })

        # Profit & Margins
        gross_profit = round(mrr - total_api_cogs, 2)
        gross_margin_pct = round((gross_profit / mrr * 100), 1) if mrr > 0 else 0.0

        # Cash collected vs API spend
        gross_collected = stripe_data.get("total_gross_collected", 0.0)
        stripe_fees = stripe_data.get("total_stripe_fees", 0.0)
        net_cash_collected = stripe_data.get("total_net_collected", 0.0)
        net_cash_profit = round(net_cash_collected - total_api_cogs, 2)

        # Profit share breakdown (50% Founder, 30% Closer, 20% Cold Caller)
        founder_share = round(max(0, gross_profit * 0.50), 2)
        sales_closer_share = round(max(0, gross_profit * 0.30), 2)
        cold_caller_share = round(max(0, gross_profit * 0.20), 2)

        return {
            "revenue_source": revenue_source,
            "mrr": mrr,
            "arr": arr,
            "stripe": {
                "connected": stripe_data.get("connected", False),
                "gross_collected": gross_collected,
                "stripe_fees": stripe_fees,
                "net_collected": net_cash_collected,
                "net_cash_profit": net_cash_profit,
                "available_balance": stripe_data.get("available_balance", 0.0),
                "active_subscriptions_count": stripe_data.get("active_subscriptions_count", 0),
                "recent_charges": stripe_data.get("recent_charges", [])
            },
            "total_calls": total_calls,
            "total_minutes": total_minutes,
            "avg_call_duration_seconds": avg_seconds,
            "avg_call_duration_minutes": avg_minutes,
            "active_tenants_count": stripe_data.get("active_subscriptions_count") or len(active_tenants),
            "phone_numbers_count": phone_count,
            "rates": COST_RATES,
            "plans": PLAN_TIERS,
            "actual_costs": {
                "twilio_voice": twilio_voice_cost,
                "twilio_streams": twilio_streams_cost,
                "twilio_numbers": twilio_numbers_cost,
                "twilio_total": total_twilio_cost,
                "gemini_live": gemini_live_cost,
                "gemini_audit": gemini_audit_cost,
                "gemini_total": total_gemini_cost,
                "total_api_cogs": total_api_cogs
            },
            "unit_economics": {
                "cost_per_minute": blended_cogs_per_minute,
                "cost_per_call": avg_cost_per_call,
                "gross_profit": gross_profit,
                "gross_margin_pct": gross_margin_pct
            },
            "profit_splits": {
                "founder_share_50": founder_share,
                "sales_closer_30": sales_closer_share,
                "cold_caller_20": cold_caller_share
            },
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
    Interactive SaaS business financial simulator.
    Models revenues, API costs, profits, and commissions based on growth targets.
    """
    plan = PLAN_TIERS.get(plan_tier.lower(), PLAN_TIERS["growth"])
    monthly_plan_price = plan["price"]
    included_mins_per_tenant = plan["included_minutes"]
    overage_rate = plan["overage_rate"]

    # Call & Usage Projections (30 days/month)
    total_calls_month = tenants_count * calls_per_day_per_tenant * 30
    total_minutes_month = round(total_calls_month * avg_call_minutes, 1)

    # Subscription Revenue
    base_mrr = tenants_count * monthly_plan_price

    # Overage Revenue
    total_included_minutes = tenants_count * included_mins_per_tenant
    overage_minutes = max(0.0, total_minutes_month - total_included_minutes)
    overage_revenue = round(overage_minutes * overage_rate, 2)

    total_mrr = round(base_mrr + overage_revenue, 2)
    total_arr = round(total_mrr * 12, 2)

    # API & COGS Calculation
    twilio_cost = round(total_minutes_month * COST_RATES["twilio_total_voice_per_min"] + tenants_count * COST_RATES["phone_number_monthly"], 2)
    gemini_live_cost = round(total_minutes_month * COST_RATES["gemini_live_per_min"], 2)
    gemini_audit_cost = round(total_calls_month * COST_RATES["gemini_audit_per_call"], 2)
    infra_cost = 0.00 if str(infra_tier).lower() == "free" else 25.00

    total_cogs = round(twilio_cost + gemini_live_cost + gemini_audit_cost + infra_cost, 2)
    gross_profit = round(total_mrr - total_cogs, 2)
    margin_pct = round((gross_profit / total_mrr * 100), 1) if total_mrr > 0 else 0.0

    # Team Split (50/30/20)
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
            "overage_minutes": overage_minutes
        },
        "revenue": {
            "base_mrr": base_mrr,
            "overage_revenue": overage_revenue,
            "total_mrr": total_mrr,
            "total_arr": total_arr
        },
        "costs": {
            "twilio_telephony": twilio_cost,
            "gemini_live_voice": gemini_live_cost,
            "gemini_audit_qa": gemini_audit_cost,
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
