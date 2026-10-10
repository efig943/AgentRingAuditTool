# Stripe Audit Rule Taxonomy & Reference

This catalog documents the validation rules evaluated by `audit_stripe.py`.

---

## 1. Balances & Authentication (`BAL` / `AUTH`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `AUTH-ERR-001` | `CRITICAL` | Stripe API key rejected or invalid. | Verify `STRIPE_SECRET_KEY` in `.env`. |
| `BAL-NEG-001` | `CRITICAL` | Available balance is negative. | Inspect disputed charges or pending refunds. |
| `BAL-ERR-001` | `ERROR` | Failure retrieving balance from Stripe. | Check Stripe API status or network egress. |

---

## 2. Subscriptions & Billing (`SUB`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `SUB-PAST-DUE` | `WARNING` | Subscription is past due or unpaid. | Trigger customer dunning email with payment update link. |
| `SUB-ERR-001` | `ERROR` | Failure listing subscriptions. | Verify API permissions on Stripe restricted keys. |

---

## 3. Charges & Transactions (`CHG`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `CHG-FAIL-001` | `WARNING` | Customer credit card charge failed or was declined. | Contact customer or verify webhook retry status. |
| `CHG-ERR-001` | `ERROR` | Failure listing charge records. | Check Stripe API permissions. |

---

## 4. Database Reconciliation (`REC`)

| Code | Severity | Description | Remediation |
|---|---|---|---|
| `REC-GHOST-SUB` | `WARNING` | Active Stripe subscription is not linked to any database tenant. | Create tenant or map `stripe_customer_id` in PostgreSQL. |
| `REC-ENTITLEMENT-LEAK` | `ERROR` | Database tenant has `status='active'` but no Stripe subscription ID. | Attach subscription or deactivate tenant access. |
| `REC-UNPAID-ACTIVE` | `ERROR` | Database tenant is active, but linked Stripe subscription is not active. | Deactivate tenant or collect outstanding balance. |
| `REC-STATUS-MISMATCH` | `WARNING` | Database status differs from active Stripe subscription status. | Update `tenants.subscription_status` to match Stripe. |
