// AgentRing Financials - Unit Economics & Profit Command Center Client

let pollingInterval = null;
let simTimeout = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  loadFinancials();
  runFinancialSimulation();

  // Periodically refresh financials every 15 seconds
  pollingInterval = setInterval(() => {
    loadFinancials();
  }, 15000);
});

function initEventListeners() {
  // Refresh Button
  const btnRefresh = document.getElementById('btn-refresh');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      btnRefresh.innerHTML = '🔄 Refreshing...';
      btnRefresh.disabled = true;
      loadFinancials().finally(() => {
        runFinancialSimulation();
        setTimeout(() => {
          btnRefresh.innerHTML = '🔄 Refresh Financials';
          btnRefresh.disabled = false;
          showToast('Financials & live usage refreshed!', 'success');
        }, 500);
      });
    });
  }

  // Simulator Listeners
  const simTenantsSlider = document.getElementById('sim-slider-tenants');
  const simCallsSlider = document.getElementById('sim-slider-calls');
  const simDurationSlider = document.getElementById('sim-slider-duration');
  const simPlanSelect = document.getElementById('sim-select-plan');
  const simInfraSelect = document.getElementById('sim-select-infra');

  if (simTenantsSlider) {
    simTenantsSlider.addEventListener('input', (e) => {
      const badge = document.getElementById('sim-badge-tenants');
      if (badge) badge.innerText = `${e.target.value} clients`;
      runFinancialSimulation();
    });
  }

  if (simCallsSlider) {
    simCallsSlider.addEventListener('input', (e) => {
      const badge = document.getElementById('sim-badge-calls');
      if (badge) badge.innerText = `${e.target.value} calls/day`;
      runFinancialSimulation();
    });
  }

  if (simDurationSlider) {
    simDurationSlider.addEventListener('input', (e) => {
      const badge = document.getElementById('sim-badge-duration');
      if (badge) badge.innerText = `${parseFloat(e.target.value).toFixed(1)} mins`;
      runFinancialSimulation();
    });
  }

  if (simPlanSelect) {
    simPlanSelect.addEventListener('change', () => {
      runFinancialSimulation();
    });
  }

  if (simInfraSelect) {
    simInfraSelect.addEventListener('change', () => {
      runFinancialSimulation();
    });
  }
}

// Toast notification helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ========================================================
// Financials & Business Cost Analytics Logic
// ========================================================
async function loadFinancials() {
  try {
    const res = await fetch('/api/financials');
    if (!res.ok) throw new Error('Failed to fetch financials');
    const data = await res.json();

    const fmtMoney = (val) => '$' + Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fmtInt = (val) => Number(val || 0).toLocaleString('en-US');

    // KPI Cards (Current Billing Cycle)
    if (document.getElementById('fin-mrr')) document.getElementById('fin-mrr').innerText = fmtMoney(data.mrr);
    if (document.getElementById('fin-arr')) document.getElementById('fin-arr').innerText = `Annual Run Rate: ${fmtMoney(data.arr)}`;

    const currentPeriod = data.current_period || {};
    const cycleCogs = currentPeriod.cogs || data.actual_costs || {};
    const totalCogs = cycleCogs.total_monthly_cogs ?? cycleCogs.total_api_cogs ?? 0;
    const billedMins = currentPeriod.billed_minutes ?? data.total_minutes ?? 0;
    const callsCount = currentPeriod.calls_count ?? data.total_calls ?? 0;
    const grossProfit = currentPeriod.gross_profit ?? data.unit_economics?.gross_profit ?? (data.mrr - totalCogs);
    const marginPct = currentPeriod.gross_margin_pct ?? data.unit_economics?.gross_margin_pct ?? (data.mrr > 0 ? (grossProfit / data.mrr * 100) : 0);

    if (document.getElementById('fin-cogs')) document.getElementById('fin-cogs').innerText = fmtMoney(totalCogs);
    if (document.getElementById('fin-cogs-sub')) document.getElementById('fin-cogs-sub').innerText = `Twilio + Gemini + Stripe (${billedMins} billed mins)`;

    if (document.getElementById('fin-gross-profit')) document.getElementById('fin-gross-profit').innerText = fmtMoney(grossProfit);
    if (document.getElementById('fin-margin-pct')) document.getElementById('fin-margin-pct').innerText = `Gross Margin: ${Number(marginPct || 0).toFixed(1)}%`;

    const unit = data.unit_economics || {};
    const costMin = unit.cost_per_minute ?? 0.0955;
    const costCall = unit.avg_cost_per_call ?? unit.cost_per_call ?? 0;
    const avgDuration = unit.avg_call_duration_seconds ?? data.avg_call_duration_seconds ?? 0;

    if (document.getElementById('fin-cost-min')) document.getElementById('fin-cost-min').innerText = `$${Number(costMin).toFixed(4)} / min`;
    if (document.getElementById('fin-cost-call')) document.getElementById('fin-cost-call').innerText = `$${Number(costCall).toFixed(3)} / call`;
    if (document.getElementById('fin-avg-duration-sub')) document.getElementById('fin-avg-duration-sub').innerText = `Avg duration: ${Number(avgDuration).toFixed(0)}s`;

    const splits = data.profit_splits || {};
    if (document.getElementById('fin-founder-share')) {
      document.getElementById('fin-founder-share').innerText = fmtMoney(splits.founder_share_50);
    }
    if (document.getElementById('sim-split-closer')) {
      document.getElementById('sim-split-closer').innerText = fmtMoney(splits.sales_closer_30);
    }
    if (document.getElementById('sim-split-caller')) {
      document.getElementById('sim-split-caller').innerText = fmtMoney(splits.cold_caller_20);
    }

    // Actual Database Spend (Current Billing Cycle)
    if (document.getElementById('fin-actual-calls-count')) document.getElementById('fin-actual-calls-count').innerText = fmtInt(callsCount);
    if (document.getElementById('fin-actual-mins-count')) document.getElementById('fin-actual-mins-count').innerText = fmtInt(billedMins);
    if (document.getElementById('fin-actual-phone-count')) document.getElementById('fin-actual-phone-count').innerText = data.phone_numbers_count || 2;

    if (document.getElementById('fin-actual-twilio-voice')) document.getElementById('fin-actual-twilio-voice').innerText = fmtMoney(cycleCogs.twilio_voice);
    if (document.getElementById('fin-actual-twilio-streams')) document.getElementById('fin-actual-twilio-streams').innerText = fmtMoney(cycleCogs.twilio_streams);
    if (document.getElementById('fin-actual-twilio-recording')) document.getElementById('fin-actual-twilio-recording').innerText = fmtMoney(cycleCogs.twilio_recording);
    if (document.getElementById('fin-actual-gemini-live')) document.getElementById('fin-actual-gemini-live').innerText = fmtMoney(cycleCogs.gemini_live);
    if (document.getElementById('fin-actual-gemini-transcription')) document.getElementById('fin-actual-gemini-transcription').innerText = fmtMoney(cycleCogs.gemini_transcription);
    if (document.getElementById('fin-actual-gemini-audit')) document.getElementById('fin-actual-gemini-audit').innerText = fmtMoney(cycleCogs.gemini_audit);
    if (document.getElementById('fin-actual-twilio-numbers')) document.getElementById('fin-actual-twilio-numbers').innerText = fmtMoney(cycleCogs.phone_numbers || cycleCogs.twilio_numbers);
    if (document.getElementById('fin-actual-stripe-fees')) document.getElementById('fin-actual-stripe-fees').innerText = fmtMoney(cycleCogs.stripe_fees);
    if (document.getElementById('fin-actual-total-cogs')) document.getElementById('fin-actual-total-cogs').innerText = fmtMoney(totalCogs);

    // Cumulative All-Time Reconciliation
    const lifetime = data.lifetime || {};
    const allCalls = lifetime.calls_count ?? data.total_calls ?? 0;
    const allMins = lifetime.billed_minutes ?? data.total_minutes ?? 0;
    const allBurn = lifetime.lifetime_api_burn ?? cycleCogs.total_api_cogs ?? 0;
    if (document.getElementById('fin-lifetime-burn')) {
      document.getElementById('fin-lifetime-burn').innerText = `${fmtMoney(allBurn)} (${allCalls} calls, ${allMins} billed mins)`;
    }

    // Tenant Ledger Table
    const tbody = document.getElementById('fin-tenant-table-body');
    const ledger = data.tenant_ledger || [];
    if (tbody) {
      if (ledger.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 20px;">No tenant records found.</td></tr>';
      } else {
        tbody.innerHTML = ledger.map(t => {
          const isAct = t.status === 'active';
          const badgeClass = isAct ? 'tenant-active-badge' : 'status-tag warning';
          const calls = t.period_calls ?? t.calls ?? 0;
          const mins = t.period_billed_minutes ?? t.minutes ?? (t.period_minutes ? Math.ceil(t.period_minutes) : 0);
          const directCogs = t.direct_cogs ?? t.api_cogs ?? 0;
          const profit = t.profit ?? (t.revenue - directCogs);
          const margin = t.margin_pct ?? (t.revenue > 0 ? ((profit / t.revenue) * 100).toFixed(1) : '0.0');

          return `
            <tr>
              <td style="font-weight: 600; color: #fff;">${t.company_name}</td>
              <td><span class="call-id-badge" style="font-size: 11px;">${t.plan}</span></td>
              <td><span class="${badgeClass}">${t.status || 'inactive'}</span></td>
              <td>${fmtInt(calls)}</td>
              <td>${Number(mins || 0).toFixed(0)}m</td>
              <td style="font-weight: 700; color: #fff;">${fmtMoney(t.revenue)}</td>
              <td style="color: #f87171; font-family: monospace;">${fmtMoney(directCogs)}</td>
              <td style="color: ${profit >= 0 ? '#4ade80' : '#f87171'}; font-weight: 700;">${fmtMoney(profit)}</td>
              <td style="font-weight: 700; color: #38bdf8;">${margin}%</td>
            </tr>
          `;
        }).join('');
      }
    }

    // Live Stripe Section
    const stripeObj = data.stripe || data.lifetime || {};
    const stripeGross = stripeObj.gross_collected ?? stripeObj.total_gross_collected ?? 0;
    const stripeFees = stripeObj.stripe_fees ?? stripeObj.total_stripe_fees ?? 0;
    const stripeNet = stripeObj.net_collected ?? stripeObj.net_cash_collected ?? stripeObj.total_net_collected ?? 0;
    const stripeAvail = stripeObj.available_balance ?? data.lifetime?.available_balance ?? 0;

    if (document.getElementById('fin-stripe-gross')) document.getElementById('fin-stripe-gross').innerText = fmtMoney(stripeGross);
    if (document.getElementById('fin-stripe-fees')) document.getElementById('fin-stripe-fees').innerText = fmtMoney(stripeFees);
    if (document.getElementById('fin-stripe-net')) document.getElementById('fin-stripe-net').innerText = fmtMoney(stripeNet);
    if (document.getElementById('fin-stripe-balance')) document.getElementById('fin-stripe-balance').innerText = fmtMoney(stripeAvail);

    // Live Twilio Section
    const twilio = data.twilio || {};
    if (document.getElementById('fin-twilio-balance')) {
      document.getElementById('fin-twilio-balance').innerText = fmtMoney(twilio.balance);
    }
    if (document.getElementById('fin-twilio-month-billed')) {
      document.getElementById('fin-twilio-month-billed').innerText = fmtMoney(twilio.month_to_date_total);
    }
    if (document.getElementById('fin-twilio-sid')) {
      document.getElementById('fin-twilio-sid').innerText = twilio.account_sid_masked || 'AC...';
    }
    const twilioBadge = document.getElementById('fin-twilio-status-badge');
    if (twilioBadge) {
      if (twilio.connected) {
        twilioBadge.className = 'status-tag clean';
        twilioBadge.innerText = '● Synced';
      } else {
        twilioBadge.className = 'status-tag warning';
        twilioBadge.innerText = 'Offline';
      }
    }

    // Live Google Cloud Section
    const googleCloud = data.google_cloud || data.reconciliation?.google || {};
    const googleBadge = document.getElementById('fin-google-status-badge');
    const googleSub = document.getElementById('fin-google-sub');
    if (googleBadge) {
      if (googleCloud.connected) {
        googleBadge.className = 'status-tag clean';
        googleBadge.innerText = '● Synced';
        if (googleSub) googleSub.innerHTML = `Account: <strong style="color: #4ade80;">${googleCloud.billing_account_name || 'Active'}</strong>`;
      } else if (googleCloud.status === 'permission_needed') {
        googleBadge.className = 'status-tag warning';
        googleBadge.innerText = '● Key Linked';
        if (googleSub) googleSub.innerHTML = `Role: <strong style="color: #fbbf24;">Needs Billing Viewer</strong>`;
      } else {
        googleBadge.className = 'status-tag';
        googleBadge.style.background = 'rgba(168,85,247,0.2)';
        googleBadge.style.color = '#c084fc';
        googleBadge.innerText = '● Rate Synced';
      }
    }

    // Live Stripe Charges Table
    const stripeTbody = document.getElementById('fin-stripe-table-body');
    if (stripeTbody) {
      const charges = stripeObj.recent_charges ?? [];
      if (document.getElementById('fin-stripe-charge-count')) {
        document.getElementById('fin-stripe-charge-count').innerText = `${charges.length} Succeeded Charges`;
      }
      if (charges.length === 0) {
        stripeTbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 20px;">No Stripe charges found.</td></tr>';
      } else {
        stripeTbody.innerHTML = charges.map(ch => {
          const dateStr = ch.created ? new Date(ch.created * 1000).toLocaleString() : 'N/A';
          const receiptBtn = ch.receipt_url 
            ? `<a href="${ch.receipt_url}" target="_blank" class="btn btn-secondary btn-sm" style="padding: 3px 8px; font-size: 11px; text-decoration: none;">🧾 Receipt</a>`
            : '<span style="color: var(--text-dim); font-size: 11px;">N/A</span>';
          
          return `
            <tr>
              <td><span class="call-id-badge" style="font-family: monospace; font-size: 11px;">${ch.id.slice(0, 14)}...</span></td>
              <td>
                <div style="font-weight: 600; color: #fff;">${ch.customer_name}</div>
                <div style="font-size: 11px; color: var(--text-muted);">${ch.customer_email || ''}</div>
              </td>
              <td style="font-weight: 700; color: #4ade80;">${fmtMoney(ch.amount)}</td>
              <td style="color: #f87171; font-family: monospace;">-${fmtMoney(ch.fee)}</td>
              <td style="font-weight: 700; color: #38bdf8;">${fmtMoney(ch.net)}</td>
              <td><span class="status-tag clean" style="font-size: 10.5px;">✓ Paid</span></td>
              <td style="font-size: 12px; color: var(--text-muted);">${dateStr}</td>
              <td>${receiptBtn}</td>
            </tr>
          `;
        }).join('');
      }
    }

  } catch (err) {
    console.error('Error loading financials:', err);
  }
}

async function runFinancialSimulation() {
  clearTimeout(simTimeout);
  simTimeout = setTimeout(async () => {
    const tenantsCount = parseInt(document.getElementById('sim-slider-tenants')?.value, 10) || 25;
    const planTier = document.getElementById('sim-select-plan')?.value || 'growth';
    const callsPerDay = parseInt(document.getElementById('sim-slider-calls')?.value, 10) || 10;
    const avgMinutes = parseFloat(document.getElementById('sim-slider-duration')?.value) || 2.0;
    const infraTier = document.getElementById('sim-select-infra')?.value || 'free';

    try {
      const res = await fetch('/api/financials/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenants_count: tenantsCount,
          plan_tier: planTier,
          calls_per_day_per_tenant: callsPerDay,
          avg_call_minutes: avgMinutes,
          infra_tier: infraTier
        })
      });
      if (!res.ok) throw new Error('Simulation failed');
      const sim = await res.json();

      const fmtMoney = (val) => '$' + Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const fmtInt = (val) => Number(val || 0).toLocaleString('en-US');

      // Update outputs
      const rev = sim.revenue || {};
      const prof = sim.profitability || {};
      const costs = sim.costs || {};
      const vol = sim.volume || {};
      const splits = sim.team_splits || {};

      if (document.getElementById('sim-out-profit')) document.getElementById('sim-out-profit').innerText = fmtMoney(prof.gross_profit);
      if (document.getElementById('sim-out-margin')) document.getElementById('sim-out-margin').innerText = `Gross Margin: ${prof.margin_pct}%`;
      if (document.getElementById('sim-out-mrr')) document.getElementById('sim-out-mrr').innerText = fmtMoney(rev.total_mrr);
      if (document.getElementById('sim-out-arr')) document.getElementById('sim-out-arr').innerText = `ARR: ${fmtMoney(rev.total_arr)}`;

      if (document.getElementById('sim-out-calls')) document.getElementById('sim-out-calls').innerText = fmtInt(vol.monthly_calls);
      if (document.getElementById('sim-out-minutes')) document.getElementById('sim-out-minutes').innerText = `${fmtInt(vol.billed_minutes || vol.monthly_minutes)}m`;
      if (document.getElementById('sim-out-cogs')) document.getElementById('sim-out-cogs').innerText = fmtMoney(costs.total_cogs);
      if (document.getElementById('sim-out-cost-min')) document.getElementById('sim-out-cost-min').innerText = `$${Number(prof.cost_per_minute || 0).toFixed(4)}`;

      // Team splits
      if (document.getElementById('sim-split-founder')) document.getElementById('sim-split-founder').innerText = fmtMoney(splits.founder_50);
      if (document.getElementById('sim-out-closer-share')) document.getElementById('sim-out-closer-share').innerText = fmtMoney(splits.sales_closer_30);
      if (document.getElementById('sim-out-caller-share')) document.getElementById('sim-out-caller-share').innerText = fmtMoney(splits.cold_caller_20);

    } catch (err) {
      console.error('Error running simulation:', err);
    }
  }, 100);
}
