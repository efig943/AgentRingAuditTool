#!/usr/bin/env python3
"""
audit_stripe.py - Comprehensive Stripe Financials & Subscription Reconciliation Auditor.
Part of the 'stripe-audit' skill for CallAudit Pro & agentring.dev.

Performs live Stripe API inspection and cross-system database reconciliation:
1. Live Balances & Cash Reserves (Available, Pending, Currency)
2. Subscription & MRR Health (Active subscriptions, plan tiers, churned/past_due)
3. Charges, Payouts & Transaction Fees (Gross collections, processing fees, failed charges)
4. Database Reconciliation with PostgreSQL (tenants vs Stripe customer/subscription linkage)
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Locate project root and load environment
current_path = Path(__file__).resolve()
PROJECT_ROOT = None
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "audits.db").exists():
        PROJECT_ROOT = parent
        break
if not PROJECT_ROOT:
    PROJECT_ROOT = current_path.parents[4]

sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import stripe
import psycopg2
import psycopg2.extras

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")


class StripeIssue:
    def __init__(
        self,
        code: str,
        severity: str,  # 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        category: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ):
        self.code = code
        self.severity = severity.upper()
        self.category = category
        self.message = message
        self.details = details or {}
        self.suggestion = suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
        }


class StripeAuditor:
    def __init__(self, api_key: str, db_url: Optional[str] = None):
        if not api_key:
            raise ValueError("STRIPE_SECRET_KEY is missing or empty in environment.")
        stripe.api_key = api_key
        self.db_url = db_url
        self.issues: List[StripeIssue] = []
        self.financial_metrics: Dict[str, Any] = {}
        self.reconciliation_stats: Dict[str, Any] = {}

    def run_audit(self) -> Dict[str, Any]:
        self.issues.clear()
        self.financial_metrics.clear()
        self.reconciliation_stats.clear()

        # 1. Balances
        balance_data = self._audit_balances()

        # 2. Subscriptions & MRR
        subs_data = self._audit_subscriptions()

        # 3. Charges & Fees
        charges_data = self._audit_charges()

        # 4. Cross-System Reconciliation with PostgreSQL tenants
        if self.db_url:
            self._audit_database_reconciliation(subs_data)

        return self.compile_report(balance_data, subs_data, charges_data)

    def _audit_balances(self) -> Dict[str, Any]:
        try:
            bal = stripe.Balance.retrieve()
            avail = sum(b.amount for b in bal.available) / 100.0
            pending = sum(b.amount for b in bal.pending) / 100.0
            currency = bal.available[0].currency.upper() if bal.available else "USD"

            if avail < 0:
                self.issues.append(
                    StripeIssue(
                        "BAL-NEG-001", "CRITICAL", "Balance",
                        f"Stripe available balance is negative: -${abs(avail):.2f} {currency}!",
                        suggestion="Check for recent chargebacks or disputed payments."
                    )
                )

            return {
                "available_balance": avail,
                "pending_balance": pending,
                "currency": currency,
            }
        except stripe.error.AuthenticationError:
            self.issues.append(
                StripeIssue(
                    "AUTH-ERR-001", "CRITICAL", "Authentication",
                    "Invalid Stripe API key. Authentication failed with Stripe.",
                    suggestion="Verify STRIPE_SECRET_KEY in .env."
                )
            )
            return {"error": "Authentication failed"}
        except Exception as e:
            self.issues.append(
                StripeIssue(
                    "BAL-ERR-001", "ERROR", "Balance",
                    f"Failed to fetch Stripe balance: {str(e)}"
                )
            )
            return {"error": str(e)}

    def _audit_subscriptions(self) -> List[Dict[str, Any]]:
        active_subs = []
        try:
            subs = stripe.Subscription.list(limit=100, expand=["data.customer"])
            mrr = 0.0

            for s in subs.data:
                sd = s.to_dict()
                status = sd.get("status")
                items = sd.get("items", {}).get("data", [])
                sub_amt = 0.0
                plan_name = "Growth"

                for it in items:
                    p = it.get("price") or {}
                    amt = (p.get("unit_amount") or 0) / 100.0
                    if amt >= 10.0:
                        sub_amt += amt
                        if amt == 49.0:
                            plan_name = "Starter"
                        elif amt == 150.0:
                            plan_name = "Growth"
                        elif amt in (299.0, 300.0):
                            plan_name = "Scale"

                cust = sd.get("customer") or {}
                cust_id = cust.get("id") if isinstance(cust, dict) else cust
                cust_name = cust.get("name") if isinstance(cust, dict) else "Unknown"
                cust_email = cust.get("email") if isinstance(cust, dict) else "Unknown"

                if status == "active":
                    mrr += sub_amt

                if status in ("past_due", "unpaid"):
                    self.issues.append(
                        StripeIssue(
                            "SUB-PAST-DUE", "WARNING", "Subscription",
                            f"Subscription '{sd.get('id')}' for customer '{cust_name}' is {status} (${sub_amt:.2f}/mo).",
                            details={"subscription_id": sd.get("id"), "customer": cust_name, "email": cust_email},
                            suggestion="Check customer payment method and dunning campaign."
                        )
                    )

                active_subs.append({
                    "subscription_id": sd.get("id"),
                    "customer_id": cust_id,
                    "customer_name": cust_name,
                    "customer_email": cust_email,
                    "amount": sub_amt,
                    "plan": plan_name,
                    "status": status,
                    "current_period_start": str(datetime.fromtimestamp(sd.get("current_period_start", 0), timezone.utc)) if sd.get("current_period_start") else None,
                    "current_period_end": str(datetime.fromtimestamp(sd.get("current_period_end", 0), timezone.utc)) if sd.get("current_period_end") else None,
                })

            self.financial_metrics["mrr"] = mrr
            self.financial_metrics["active_subscription_count"] = sum(1 for s in active_subs if s["status"] == "active")
            self.financial_metrics["total_subscriptions"] = len(active_subs)
            return active_subs

        except Exception as e:
            self.issues.append(
                StripeIssue("SUB-ERR-001", "ERROR", "Subscription", f"Failed to list subscriptions: {str(e)}")
            )
            return []

    def _audit_charges(self) -> Dict[str, Any]:
        try:
            charges = stripe.Charge.list(limit=100, expand=["data.balance_transaction", "data.customer"])
            gross = 0.0
            fees = 0.0
            net = 0.0
            succeeded_count = 0
            failed_count = 0
            recent_txs = []

            for ch in charges.data:
                cd = ch.to_dict()
                status = cd.get("status")
                paid = cd.get("paid", False)
                amt = cd.get("amount", 0) / 100.0

                if status == "succeeded" and paid:
                    succeeded_count += 1
                    bt = cd.get("balance_transaction") or {}
                    fee = (bt.get("fee") or 0) / 100.0 if isinstance(bt, dict) else 0.0
                    net_amt = (bt.get("net") or 0) / 100.0 if isinstance(bt, dict) else (amt - fee)
                    gross += amt
                    fees += fee
                    net += net_amt

                    cust = cd.get("customer") or {}
                    recent_txs.append({
                        "charge_id": cd.get("id"),
                        "amount": amt,
                        "fee": fee,
                        "net": net_amt,
                        "customer": cust.get("name") if isinstance(cust, dict) else "Guest",
                        "created": str(datetime.fromtimestamp(cd.get("created", 0), timezone.utc)) if cd.get("created") else None,
                        "receipt_url": cd.get("receipt_url")
                    })
                elif status == "failed":
                    failed_count += 1
                    self.issues.append(
                        StripeIssue(
                            "CHG-FAIL-001", "WARNING", "Charges",
                            f"Failed charge of ${amt:.2f} (Failure message: {cd.get('failure_message', 'Declined')}).",
                            details={"charge_id": cd.get("id"), "failure_code": cd.get("failure_code")},
                            suggestion="Follow up with customer regarding card decline."
                        )
                    )

            effective_fee_pct = (fees / gross * 100.0) if gross > 0 else 0.0
            charges_summary = {
                "total_gross_collected": gross,
                "total_stripe_fees": fees,
                "total_net_collected": net,
                "effective_fee_percentage": round(effective_fee_pct, 2),
                "succeeded_count": succeeded_count,
                "failed_count": failed_count,
                "recent_transactions": recent_txs[:10],
            }
            self.financial_metrics.update(charges_summary)
            return charges_summary

        except Exception as e:
            self.issues.append(
                StripeIssue("CHG-ERR-001", "ERROR", "Charges", f"Failed to list charges: {str(e)}")
            )
            return {}

    def _audit_database_reconciliation(self, active_subs: List[Dict[str, Any]]):
        try:
            conn = psycopg2.connect(self.db_url, connect_timeout=10)
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT id, company_name, stripe_customer_id, stripe_subscription_id, 
                           subscription_status, subscription_plan 
                    FROM tenants;
                """)
                tenants = [dict(r) for r in cur.fetchall()]
            conn.close()

            db_sub_ids = {t["stripe_subscription_id"]: t for t in tenants if t.get("stripe_subscription_id")}
            db_cust_ids = {t["stripe_customer_id"]: t for t in tenants if t.get("stripe_customer_id")}

            reconciled_subs = 0
            ghost_subs = 0
            leak_tenants = 0

            # A. Check Stripe Subs vs DB Tenants
            for sub in active_subs:
                sid = sub["subscription_id"]
                cid = sub["customer_id"]

                matched_tenant = db_sub_ids.get(sid) or db_cust_ids.get(cid)
                if not matched_tenant:
                    ghost_subs += 1
                    self.issues.append(
                        StripeIssue(
                            "REC-GHOST-SUB", "WARNING", "Reconciliation",
                            f"Active Stripe subscription '{sid}' (${sub['amount']:.2f}/mo) has NO matching tenant in PostgreSQL database!",
                            details={"subscription": sub},
                            suggestion="Map this customer/subscription to a valid tenant in the tenants table."
                        )
                    )
                else:
                    reconciled_subs += 1
                    # Check status match
                    db_status = matched_tenant.get("subscription_status")
                    if sub["status"] == "active" and db_status != "active":
                        self.issues.append(
                            StripeIssue(
                                "REC-STATUS-MISMATCH", "WARNING", "Reconciliation",
                                f"Tenant #{matched_tenant['id']} ({matched_tenant['company_name']}) has active Stripe sub, but database status is '{db_status}'.",
                                suggestion=f"UPDATE tenants SET subscription_status = 'active' WHERE id = {matched_tenant['id']};"
                            )
                        )

            # B. Check DB Tenants with 'active' status but no valid Stripe sub
            stripe_active_sids = {s["subscription_id"] for s in active_subs if s["status"] == "active"}
            for t in tenants:
                if t.get("subscription_status") == "active":
                    sid = t.get("stripe_subscription_id")
                    if not sid:
                        leak_tenants += 1
                        self.issues.append(
                            StripeIssue(
                                "REC-ENTITLEMENT-LEAK", "ERROR", "Reconciliation",
                                f"Tenant #{t['id']} ({t['company_name']}) is marked 'active' in database, but has NO Stripe subscription ID!",
                                suggestion="Attach a valid Stripe subscription or set subscription_status = 'inactive'."
                            )
                        )
                    elif sid not in stripe_active_sids:
                        self.issues.append(
                            StripeIssue(
                                "REC-UNPAID-ACTIVE", "ERROR", "Reconciliation",
                                f"Tenant #{t['id']} ({t['company_name']}) has subscription_status='active', but subscription '{sid}' is NOT active in Stripe!",
                                suggestion="Verify subscription state in Stripe or deactivate tenant."
                            )
                        )

            self.reconciliation_stats = {
                "total_db_tenants": len(tenants),
                "reconciled_subscriptions": reconciled_subs,
                "ghost_subscriptions": ghost_subs,
                "unpaid_active_tenants": leak_tenants,
            }

        except Exception as e:
            self.issues.append(
                StripeIssue("REC-ERR-001", "ERROR", "Reconciliation", f"Database reconciliation query failed: {str(e)}")
            )

    def compile_report(self, balance_data: Dict[str, Any], subs: List[Dict[str, Any]], charges: Dict[str, Any]) -> Dict[str, Any]:
        counts = {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        for i in self.issues:
            counts[i.severity] = counts.get(i.severity, 0) + 1

        overall_status = "HEALTHY"
        if counts["CRITICAL"] > 0:
            overall_status = "CRITICAL"
        elif counts["ERROR"] > 0:
            overall_status = "DEGRADED"
        elif counts["WARNING"] > 0:
            overall_status = "WARNING"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "issue_counts": counts,
            "total_issues": len(self.issues),
            "balances": balance_data,
            "financial_summary": self.financial_metrics,
            "reconciliation": self.reconciliation_stats,
            "subscriptions": subs,
            "issues": [i.to_dict() for i in self.issues],
        }


def format_markdown_report(report: Dict[str, Any]) -> str:
    lines = []
    badges = {
        "HEALTHY": "🟢 HEALTHY",
        "WARNING": "🟡 WARNING",
        "DEGRADED": "🟠 DEGRADED",
        "CRITICAL": "🔴 CRITICAL",
    }
    badge = badges.get(report["overall_status"], report["overall_status"])

    lines.append("# Stripe Financials & Subscription Audit Report")
    lines.append(f"**Audit Status**: {badge}  |  **Generated**: `{report['timestamp']}`\n")

    lines.append("## 1. Cash Balances & Revenue Metrics")
    b = report.get("balances", {})
    f = report.get("financial_summary", {})
    lines.append(f"- **Available Cash Balance**: `${b.get('available_balance', 0.0):,.2f}` {b.get('currency', 'USD')}")
    lines.append(f"- **Pending Balance**: `${b.get('pending_balance', 0.0):,.2f}`")
    lines.append(f"- **Active SaaS MRR**: `${f.get('mrr', 0.0):,.2f}`/mo")
    lines.append(f"- **Active Paying Subscriptions**: `{f.get('active_subscription_count', 0)}`")
    lines.append(f"- **Total Gross Collected**: `${f.get('total_gross_collected', 0.0):,.2f}`")
    lines.append(f"- **Total Stripe Processing Fees**: `${f.get('total_stripe_fees', 0.0):,.2f}` ({f.get('effective_fee_percentage', 0.0)}%)")
    lines.append(f"- **Total Net Revenue Deposited**: `${f.get('total_net_collected', 0.0):,.2f}`")
    lines.append("")

    rec = report.get("reconciliation", {})
    if rec:
        lines.append("## 2. PostgreSQL Database Reconciliation")
        lines.append(f"- **Total Database Tenants**: `{rec.get('total_db_tenants', 0)}`")
        lines.append(f"- **Properly Linked Subscriptions**: `{rec.get('reconciled_subscriptions', 0)}`")
        lines.append(f"- **Ghost Subscriptions (Unmapped to DB)**: `{rec.get('ghost_subscriptions', 0)}`")
        lines.append(f"- **Entitlement Leaks (Active without Stripe)**: `{rec.get('unpaid_active_tenants', 0)}`")
        lines.append("")

    lines.append("## 3. Active Subscriptions")
    lines.append("| Subscription ID | Customer Name | Email | Plan | Amount | Status |")
    lines.append("|---|---|---|---|---|---|")
    for s in report.get("subscriptions", []):
        lines.append(f"| `{s['subscription_id']}` | {s['customer_name']} | {s['customer_email']} | `{s['plan']}` | ${s['amount']:.2f}/mo | `{s['status']}` |")
    lines.append("")

    lines.append("## 4. Audit Violations & Financial Drift")
    if not report["issues"]:
        lines.append("✅ Zero billing discrepancies, past due subscriptions, or reconciliation leaks detected.")
    else:
        for idx, issue in enumerate(report["issues"], start=1):
            sev_icon = {
                "CRITICAL": "🚨 CRITICAL",
                "ERROR": "❌ ERROR",
                "WARNING": "⚠️ WARNING",
                "INFO": "ℹ️ INFO",
            }.get(issue["severity"], issue["severity"])

            lines.append(f"### {idx}. [{issue['code']}] {sev_icon}: {issue['category']}")
            lines.append(f"**Message**: {issue['message']}")
            if issue.get("suggestion"):
                lines.append(f"💡 **Recommendation**: `{issue['suggestion']}`")
            lines.append("")

    return "\n".join(lines)


def format_terminal_summary(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f" STRIPE FINANCIAL AUDIT - STATUS: {report['overall_status']}")
    lines.append(f" Timestamp: {report['timestamp']}")
    lines.append("=" * 72)

    b = report.get("balances", {})
    f = report.get("financial_summary", {})
    lines.append("\nFINANCIAL OVERVIEW:")
    lines.append(f"  • Available Balance : ${b.get('available_balance', 0.0):,.2f} {b.get('currency', 'USD')}")
    lines.append(f"  • Pending Balance   : ${b.get('pending_balance', 0.0):,.2f}")
    lines.append(f"  • Active SaaS MRR   : ${f.get('mrr', 0.0):,.2f}/mo ({f.get('active_subscription_count', 0)} paying clients)")
    lines.append(f"  • Gross Collected   : ${f.get('total_gross_collected', 0.0):,.2f} (Fees: ${f.get('total_stripe_fees', 0.0):,.2f})")
    lines.append(f"  • Net Deposits      : ${f.get('total_net_collected', 0.0):,.2f}")

    rec = report.get("reconciliation", {})
    if rec:
        lines.append("\nDATABASE RECONCILIATION:")
        lines.append(f"  • Total DB Tenants  : {rec.get('total_db_tenants')}")
        lines.append(f"  • Reconciled Subs   : {rec.get('reconciled_subscriptions')}")
        lines.append(f"  • Ghost Subs        : {rec.get('ghost_subscriptions')}")
        lines.append(f"  • Entitlement Leaks : {rec.get('unpaid_active_tenants')}")

    lines.append("\nAUDIT FINDINGS:")
    if not report["issues"]:
        lines.append("  [OK] All balances, subscriptions, and database entitlements are in sync.")
    else:
        for issue in report["issues"]:
            prefix = f"[{issue['severity'].ljust(8)}]"
            lines.append(f"  {prefix} ({issue['code']}) {issue['category']}: {issue['message']}")
            if issue.get("suggestion"):
                lines.append(f"             ↳ Fix: {issue['suggestion']}")

    lines.append("\n" + "=" * 72)
    counts = report["issue_counts"]
    lines.append(f"TOTAL FINDINGS: {report['total_issues']} (Critical: {counts['CRITICAL']}, Error: {counts['ERROR']}, Warning: {counts['WARNING']}, Info: {counts['INFO']})")
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Stripe Financials & Subscription Reconciliation Auditor."
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Output display format (default: summary)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error", "critical"],
        default="info",
        help="Filter findings by minimum severity (default: info)",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database reconciliation and query only Stripe API",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export report to a file",
    )

    args = parser.parse_args()

    try:
        db_url = None if args.no_db else DATABASE_URL
        auditor = StripeAuditor(api_key=STRIPE_SECRET_KEY, db_url=db_url)
        report = auditor.run_audit()

        # Severity filtering
        sev_rank = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
        min_rank = sev_rank[args.min_severity.upper()]
        report["issues"] = [i for i in report["issues"] if sev_rank.get(i["severity"], 0) >= min_rank]

        output_text = ""
        if args.format == "json":
            output_text = json.dumps(report, indent=2)
        elif args.format == "markdown":
            output_text = format_markdown_report(report)
        else:
            output_text = format_terminal_summary(report)

        print(output_text)

        if args.export:
            export_path = Path(args.export).resolve()
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"\n[+] Stripe audit report saved to {export_path}")

        # Exit code
        if report["issue_counts"]["CRITICAL"] > 0 or report["issue_counts"]["ERROR"] > 0:
            sys.exit(2)
        elif report["issue_counts"]["WARNING"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"[!] Stripe audit failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
