import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import stripe
from app.core import config

stripe.api_key = config.STRIPE_SECRET_KEY

# 1. Balance
bal = stripe.Balance.retrieve()
avail_bal = sum(b.amount for b in bal.available) / 100.0
pending_bal = sum(b.amount for b in bal.pending) / 100.0

# 2. Subscriptions
subs = stripe.Subscription.list(status='active', limit=100, expand=['data.customer'])
stripe_mrr = 0.0
active_subs_list = []
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
    active_subs_list.append({
        'subscription_id': sd.get('id'),
        'customer_id': cust.get('id') if isinstance(cust, dict) else cust,
        'customer_name': cust.get('name') if isinstance(cust, dict) else 'Unknown',
        'customer_email': cust.get('email') if isinstance(cust, dict) else 'Unknown',
        'amount': sub_amt,
        'plan': plan_name,
        'status': sd.get('status')
    })

# 3. Charges & Fees
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
        recent_charges.append({
            'charge_id': cd.get('id'),
            'amount': amt,
            'fee': fee,
            'net': net,
            'customer_name': cust.get('name') if isinstance(cust, dict) else 'Guest',
            'created': cd.get('created'),
            'receipt_url': cd.get('receipt_url')
        })

print(f"Stripe Active MRR: ${stripe_mrr:.2f}")
print(f"Active Subscriptions: {len(active_subs_list)}")
print(f"Total Gross Collected: ${total_gross:.2f}")
print(f"Total Stripe Fees: ${total_fees:.2f}")
print(f"Total Net Collected: ${total_net:.2f}")
print(f"Available Balance: ${avail_bal:.2f}")
for s in active_subs_list:
    print("  Sub:", s)
