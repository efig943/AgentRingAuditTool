// CallAudit Pro - Production Support Client Application

let currentFilter = 'all'; // 'all', 'issues', 'clean', 'unaudited'
let currentChip = null;   // 'customer_mad', 'db_discrepancy', 'weird_interaction'
let currentPreset = 'all';
let currentSearch = '';
let activeCallId = null;
let activeCallData = null;
let pollingInterval = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  loadStats();
  loadCalls();

  // Periodically refresh stats and status every 15 seconds
  pollingInterval = setInterval(() => {
    loadStats(false);
  }, 15000);
});

function initEventListeners() {
  // Top Level Navigation Tabs (Audit vs Financials)
  document.getElementById('nav-btn-audit').addEventListener('click', () => {
    document.getElementById('nav-btn-audit').classList.add('active');
    document.getElementById('nav-btn-financials').classList.remove('active');
    document.getElementById('view-audit').style.display = 'block';
    document.getElementById('view-financials').style.display = 'none';
  });

  document.getElementById('nav-btn-financials').addEventListener('click', () => {
    document.getElementById('nav-btn-financials').classList.add('active');
    document.getElementById('nav-btn-audit').classList.remove('active');
    document.getElementById('view-audit').style.display = 'none';
    document.getElementById('view-financials').style.display = 'flex';
    loadFinancials();
    runFinancialSimulation();
  });

  // Simulator Listeners
  const simTenantsSlider = document.getElementById('sim-slider-tenants');
  const simCallsSlider = document.getElementById('sim-slider-calls');
  const simDurationSlider = document.getElementById('sim-slider-duration');
  const simPlanSelect = document.getElementById('sim-select-plan');

  if (simTenantsSlider) {
    simTenantsSlider.addEventListener('input', (e) => {
      document.getElementById('sim-badge-tenants').innerText = `${e.target.value} clients`;
      runFinancialSimulation();
    });
    simCallsSlider.addEventListener('input', (e) => {
      document.getElementById('sim-badge-calls').innerText = `${e.target.value} calls/day`;
      runFinancialSimulation();
    });
    simDurationSlider.addEventListener('input', (e) => {
      document.getElementById('sim-badge-duration').innerText = `${parseFloat(e.target.value).toFixed(1)} mins`;
      runFinancialSimulation();
    });
    simPlanSelect.addEventListener('change', (e) => {
      const planNames = { starter: 'Starter ($49/mo)', growth: 'Growth ($150/mo)', scale: 'Scale ($299/mo)' };
      document.getElementById('sim-badge-plan').innerText = planNames[e.target.value] || e.target.value;
      runFinancialSimulation();
    });

    const simInfraSelect = document.getElementById('sim-select-infra');
    if (simInfraSelect) {
      simInfraSelect.addEventListener('change', (e) => {
        const badge = document.getElementById('sim-badge-infra');
        if (e.target.value === 'free') {
          badge.innerText = 'Free Tier ($0/mo)';
          badge.style.background = 'rgba(16,185,129,0.2)';
          badge.style.color = '#4ade80';
        } else {
          badge.innerText = 'Pro Tier ($25/mo)';
          badge.style.background = 'rgba(245,158,11,0.2)';
          badge.style.color = '#f59e0b';
        }
        runFinancialSimulation();
      });
    }
  }

  // Status Filter Tabs
  document.querySelectorAll('#status-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('#status-tabs .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      loadCalls();
    });
  });

  // Category Quick Chips
  document.querySelectorAll('.chip-btn').forEach(chip => {
    chip.addEventListener('click', () => {
      const chipType = chip.dataset.chip;
      if (currentChip === chipType) {
        chip.classList.remove('active');
        currentChip = null;
      } else {
        document.querySelectorAll('.chip-btn').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentChip = chipType;
      }
      loadCalls();
    });
  });

  // Date Preset Buttons
  document.querySelectorAll('.date-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentPreset = btn.dataset.preset;
      applyDatePreset(currentPreset);
      loadCalls();
    });
  });

  // Custom Date Filters
  document.getElementById('btn-apply-date-filter').addEventListener('click', () => {
    document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
    currentPreset = 'custom';
    loadCalls();
  });

  document.getElementById('btn-clear-date-filter').addEventListener('click', () => {
    document.getElementById('filter-start-date').value = '';
    document.getElementById('filter-end-date').value = '';
    document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.date-preset-btn[data-preset="all"]').classList.add('active');
    currentPreset = 'all';
    loadCalls();
  });

  // Search Input with debounce
  let searchTimeout = null;
  document.getElementById('search-input').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      currentSearch = e.target.value.trim();
      loadCalls();
    }, 300);
  });

  // Trigger Audit Button
  document.getElementById('btn-trigger-audit').addEventListener('click', () => {
    const timeRange = document.getElementById('audit-time-range').value || 'day';
    triggerAudit(timeRange, false);
  });

  // Deep Re-Audit Button
  document.getElementById('btn-force-audit').addEventListener('click', () => {
    const timeRange = document.getElementById('audit-time-range').value || 'day';
    const rangeLabels = {
      day: 'Today / Past 24h',
      week: 'Past Week (Last 7 Days)',
      month: 'Past Month (Last 30 Days)',
      year: 'Past Year',
      all: 'All Time (Everything)'
    };
    const label = rangeLabels[timeRange] || timeRange;
    if (confirm(`Run Deep Re-Audit with Gemini 3.8 Flash for ${label}? This will thoroughly re-evaluate and verify all calls in this range.`)) {
      triggerAudit(timeRange, true);
    }
  });

  // Auto-sync list view when audit time-range dropdown changes
  document.getElementById('audit-time-range').addEventListener('change', (e) => {
    const val = e.target.value;
    let targetPreset = 'all';
    if (val === 'day') targetPreset = 'today';
    else if (val === 'week') targetPreset = '7days';
    else if (val === 'month') targetPreset = '30days';
    else if (val === 'year' || val === 'all') targetPreset = 'all';

    document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.date-preset-btn[data-preset="${targetPreset}"]`);
    if (btn) btn.classList.add('active');
    currentPreset = targetPreset;
    applyDatePreset(currentPreset);
    loadCalls();
  });

  // Refresh Button
  document.getElementById('btn-refresh').addEventListener('click', () => {
    loadStats();
    loadCalls();
    showToast('Dashboard data refreshed', 'info');
  });

  // Send Test Email
  document.getElementById('btn-test-email').addEventListener('click', sendTestEmail);

  // Toggle Background Daemon
  document.getElementById('toggle-daemon-btn').addEventListener('click', toggleDaemon);

  // Modal Controls
  document.getElementById('modal-close-btn').addEventListener('click', closeModal);
  document.getElementById('inspection-modal').addEventListener('click', (e) => {
    if (e.target.id === 'inspection-modal') closeModal();
  });

  // Modal Tabs
  document.querySelectorAll('.modal-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.modal-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.modal-tab-content').forEach(c => c.style.display = 'none');
      btn.classList.add('active');
      const tabId = 'modaltab-' + btn.dataset.modaltab;
      const target = document.getElementById(tabId);
      if (target) target.style.display = 'block';
    });
  });

  // Modal Action Buttons
  document.getElementById('modal-btn-email').addEventListener('click', () => {
    if (activeCallId) sendEmailForCall(activeCallId);
  });

  document.getElementById('modal-btn-reanalyze').addEventListener('click', () => {
    if (activeCallId) reanalyzeCall(activeCallId);
  });

  document.getElementById('modal-btn-resolve').addEventListener('click', () => {
    if (activeCallId && activeCallData) {
      const willResolve = !activeCallData.resolved;
      toggleResolveCall(activeCallId, willResolve);
    }
  });
}

// Preset date ranges helper
function applyDatePreset(preset) {
  const startInput = document.getElementById('filter-start-date');
  const endInput = document.getElementById('filter-end-date');

  const now = new Date();
  
  if (preset === 'all') {
    startInput.value = '';
    endInput.value = '';
    return;
  }

  const formatLocalISO = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  if (preset === 'today') {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    startInput.value = formatLocalISO(start);
    endInput.value = formatLocalISO(now);
  } else if (preset === 'yesterday') {
    const yStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 0, 0, 0);
    const yEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 23, 59, 59);
    startInput.value = formatLocalISO(yStart);
    endInput.value = formatLocalISO(yEnd);
  } else if (preset === '7days') {
    const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    startInput.value = formatLocalISO(start);
    endInput.value = formatLocalISO(now);
  } else if (preset === '30days') {
    const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    startInput.value = formatLocalISO(start);
    endInput.value = formatLocalISO(now);
  }
}

// Load stats from server
async function loadStats(showLoader = true) {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('Failed to fetch stats');
    const data = await res.json();

    document.getElementById('stat-total-audited').innerText = data.total_audited || 0;
    document.getElementById('stat-clean-count').innerText = data.clean_count || 0;
    document.getElementById('stat-issues-count').innerText = data.issues_count || 0;
    document.getElementById('stat-mad-count').innerText = data.mad_customers_count || 0;
    document.getElementById('stat-db-count').innerText = data.db_discrepancies_count || 0;
    document.getElementById('stat-emailed-count').innerText = data.emailed_count || 0;

    // Percentages and subtexts
    if (data.total_audited > 0) {
      const cleanPct = Math.round((data.clean_count / data.total_audited) * 100);
      document.getElementById('stat-clean-percent').innerText = `${cleanPct}% nominal`;
    }
    document.getElementById('stat-unresolved-sub').innerText = `${data.unresolved_count || 0} unresolved`;
    
    if (data.last_audit_at) {
      const dt = new Date(data.last_audit_at);
      document.getElementById('stat-last-audit-sub').innerText = `Last: ${dt.toLocaleTimeString()}`;
    }

    // System Status Pill & All Green Banner
    const statusPill = document.getElementById('system-status-indicator');
    const statusText = document.getElementById('system-status-text');
    const allGreenBanner = document.getElementById('all-green-banner');
    const tabIssuesBadge = document.getElementById('tab-issues-badge');

    if (data.issues_count > 0) {
      statusPill.className = 'system-status-pill has-issues';
      statusPill.querySelector('.status-dot').className = 'status-dot red';
      statusText.innerText = `${data.issues_count} Active Incidents`;
      allGreenBanner.style.display = 'none';

      tabIssuesBadge.style.display = 'inline-block';
      tabIssuesBadge.innerText = data.issues_count;
    } else if (data.total_audited > 0) {
      statusPill.className = 'system-status-pill all-green';
      statusPill.querySelector('.status-dot').className = 'status-dot green';
      statusText.innerText = 'All Systems Nominal';
      allGreenBanner.style.display = 'flex';
      tabIssuesBadge.style.display = 'none';
    } else {
      allGreenBanner.style.display = 'none';
      tabIssuesBadge.style.display = 'none';
    }

    // Daemon status
    const daemon = data.daemon || {};
    const daemonText = document.getElementById('daemon-status-text');
    const toggleBtn = document.getElementById('toggle-daemon-btn');
    if (daemon.is_running) {
      daemonText.innerText = 'Active';
      daemonText.style.color = '#4ade80';
      toggleBtn.innerText = 'Pause';
    } else {
      daemonText.innerText = 'Paused';
      daemonText.style.color = '#94a3b8';
      toggleBtn.innerText = 'Resume';
    }

    // Scanning progress
    const progressContainer = document.getElementById('scan-progress');
    if (daemon.is_scanning) {
      progressContainer.classList.add('active');
    } else {
      progressContainer.classList.remove('active');
    }

  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

// Load calls list based on current filters
async function loadCalls() {
  const container = document.getElementById('incidents-list');
  
  let url = '/api/calls?limit=100';

  if (currentFilter && currentFilter !== 'all') {
    url += `&filter_type=${encodeURIComponent(currentFilter)}`;
  } else if (currentChip) {
    url += `&filter_type=${encodeURIComponent(currentChip)}`;
  }

  const startDate = document.getElementById('filter-start-date').value;
  const endDate = document.getElementById('filter-end-date').value;
  if (startDate) url += `&start_date=${encodeURIComponent(startDate)}`;
  if (endDate) url += `&end_date=${encodeURIComponent(endDate)}`;

  if (currentSearch) {
    url += `&search=${encodeURIComponent(currentSearch)}`;
  }

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch calls');
    const data = await res.json();
    const calls = data.calls || [];

    if (calls.length === 0) {
      container.innerHTML = `
        <div class="empty-state glass-panel">
          <div class="empty-icon">✅</div>
          <div class="empty-title">No Matching Calls Found</div>
          <div class="empty-sub">No call records match the current filter or date range. Click "Run Call Analysis" to scan new calls.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = calls.map(call => renderCallCard(call)).join('');

    // Attach card event listeners
    container.querySelectorAll('.call-card').forEach(card => {
      const callId = parseInt(card.dataset.callId, 10);
      card.querySelector('.btn-inspect').addEventListener('click', () => openInspection(callId));
      
      const emailBtn = card.querySelector('.btn-send-email');
      if (emailBtn) {
        emailBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          sendEmailForCall(callId);
        });
      }

      const auditNowBtn = card.querySelector('.btn-audit-now');
      if (auditNowBtn) {
        auditNowBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          auditSingleCall(callId);
        });
      }
    });

  } catch (err) {
    console.error('Error fetching calls:', err);
    container.innerHTML = `
      <div class="empty-state glass-panel">
        <div class="empty-icon">⚠️</div>
        <div class="empty-title">Error Loading Call Logs</div>
        <div class="empty-sub">${err.message}</div>
      </div>
    `;
  }
}

function renderCallCard(call) {
  const isUnaudited = !call.status || call.status === 'completed';
  const status = isUnaudited ? 'UNAUDITED' : call.status;
  const callId = call.id || call.call_id;
  const callerPhone = call.caller_phone || 'Unknown';
  const callTime = new Date(call.call_created_at || call.created_at).toLocaleString();
  const duration = call.duration_seconds || 0;
  const summary = call.summary || (isUnaudited ? 'Unaudited call log. Click "Audit Call" to evaluate.' : 'Clean call record.');

  let statusClass = 'status-clean';
  let badgeClass = 'clean';
  if (status === 'CRITICAL') {
    statusClass = 'status-critical';
    badgeClass = 'critical';
  } else if (status === 'WARNING') {
    statusClass = 'status-warning';
    badgeClass = 'warning';
  } else if (isUnaudited) {
    statusClass = '';
    badgeClass = 'warning';
  }

  // Tags
  let chipsHtml = '';
  if (call.customer_mad) {
    chipsHtml += `<span class="issue-chip customer-mad">😡 Angry Customer</span>`;
  }
  if (call.db_discrepancy) {
    chipsHtml += `<span class="issue-chip db-discrepancy">🗄️ Database Mismatch</span>`;
  }
  if (call.weird_interaction) {
    chipsHtml += `<span class="issue-chip weird-flow">🤖 AI Loop / Weird Flow</span>`;
  }
  if (call.call_failure) {
    chipsHtml += `<span class="issue-chip customer-mad">📞 Dropped / Failed Call</span>`;
  }
  if (call.email_sent) {
    chipsHtml += `<span class="issue-chip email-sent">📧 Alert Emailed</span>`;
  }
  if (call.resolved) {
    chipsHtml += `<span class="issue-chip resolved">✓ Resolved</span>`;
  }

  const actionButtons = isUnaudited 
    ? `<button class="btn btn-primary btn-sm btn-audit-now">✨ Audit Call</button>`
    : `
      ${call.has_issues ? `<button class="btn btn-secondary btn-sm btn-send-email" title="Dispatch alert email to ethan.figueredo943@gmail.com">✉️ Alert</button>` : ''}
      <button class="btn btn-secondary btn-sm btn-inspect">🔍 Inspect</button>
    `;

  return `
    <div class="call-card glass-panel ${statusClass}" data-call-id="${callId}">
      <div class="card-top">
        <div class="call-meta-left">
          <span class="call-id-badge">#${callId}</span>
          <span class="status-tag ${badgeClass}">${status}</span>
          <span class="call-phone">📞 ${callerPhone}</span>
          <span class="call-time">🕒 ${callTime}</span>
          <span class="call-duration">⏱️ ${duration}s</span>
        </div>
        <div class="card-actions">
          ${actionButtons}
        </div>
      </div>

      <div class="card-summary-box">
        <div class="card-summary-text">${summary}</div>
      </div>

      ${chipsHtml ? `<div class="card-tags">${chipsHtml}</div>` : ''}
    </div>
  `;
}

// Trigger background batch audit
async function triggerAudit(timeRange = 'day', forceAll = false) {
  const progressContainer = document.getElementById('scan-progress');
  const progressLabel = document.getElementById('progress-status-label');
  progressContainer.classList.add('active');

  const rangeDescriptions = {
    day: 'Daily Audit (Past 24 Hours)',
    week: 'Weekly Audit (Last 7 Days)',
    month: 'Monthly Audit (Last 30 Days)',
    year: 'Yearly Audit (Past Year)',
    all: 'Deep Analysis on All Historical Logs (Everything)'
  };
  const desc = rangeDescriptions[timeRange] || timeRange;
  progressLabel.innerText = `Running ${desc} with Gemini 3.8 Flash...`;

  showToast(`Audit initiated: ${desc} ${forceAll ? '(Deep Re-Audit)' : ''}`, 'info');

  try {
    const res = await fetch('/api/audit/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ time_range: timeRange, force_all: forceAll })
    });
    const data = await res.json();
    
    // Poll for completion
    let pollCount = 0;
    const interval = setInterval(async () => {
      pollCount++;
      const statsRes = await fetch('/api/stats');
      const statsData = await statsRes.json();
      const daemon = statsData.daemon || {};

      if (!daemon.is_scanning || pollCount > 60) {
        clearInterval(interval);
        progressContainer.classList.remove('active');
        showToast(`Audit completed for ${desc}!`, 'success');
        loadStats();
        loadCalls();
      }
    }, 2000);

  } catch (err) {
    progressContainer.classList.remove('active');
    showToast(`Audit trigger failed: ${err.message}`, 'error');
  }
}

// Audit a single call
async function auditSingleCall(callId) {
  showToast(`Auditing Call #${callId}...`, 'info');
  try {
    const res = await fetch(`/api/audit/call/${callId}?force=true`, { method: 'POST' });
    if (!res.ok) throw new Error('Audit failed');
    const data = await res.json();
    showToast(`Call #${callId} audited: ${data.audit.status}`, 'success');
    loadStats();
    loadCalls();
  } catch (err) {
    showToast(`Failed to audit call: ${err.message}`, 'error');
  }
}

// Open deep inspection modal
async function openInspection(callId) {
  activeCallId = callId;
  const modal = document.getElementById('inspection-modal');
  modal.classList.add('active');

  // Reset to first tab
  document.querySelectorAll('.modal-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.modal-tab-content').forEach(c => c.style.display = 'none');
  document.querySelector('.modal-tab-btn[data-modaltab="incident"]').classList.add('active');
  document.getElementById('modaltab-incident').style.display = 'block';

  try {
    const res = await fetch(`/api/calls/${callId}`);
    if (!res.ok) throw new Error('Failed to load call details');
    const data = await res.json();
    activeCallData = data.call;
    const call = data.call;

    // Header info
    document.getElementById('modal-call-title').innerText = `Call Inspection #${call.call_id || call.id} (${call.caller_phone})`;
    
    const badge = document.getElementById('modal-status-badge');
    badge.className = `status-tag ${(call.status || 'clean').toLowerCase()}`;
    badge.innerText = call.status || 'CLEAN';

    // Summary & Meta
    document.getElementById('modal-finding-summary').innerText = call.summary || 'Normal call interaction.';
    document.getElementById('modal-caller-phone').innerText = call.caller_phone || 'N/A';
    document.getElementById('modal-call-time').innerText = new Date(call.call_created_at || call.created_at).toLocaleString();
    document.getElementById('modal-duration').innerText = `${call.duration_seconds || 0} seconds`;

    const sentimentEl = document.getElementById('modal-sentiment');
    sentimentEl.innerText = call.customer_sentiment || 'Neutral';
    sentimentEl.style.color = (call.customer_sentiment === 'Angry' || call.customer_sentiment === 'Frustrated') ? '#f87171' : '#34d399';

    // Database matrix
    const dbComp = call.db_comparison || {};
    document.getElementById('modal-db-caller-req').innerText = dbComp.caller_requested || 'No specific booking requested.';
    document.getElementById('modal-db-recorded').innerText = dbComp.database_recorded || 'No records created.';

    const mismatchAlert = document.getElementById('modal-db-mismatch-alert');
    const mismatchText = document.getElementById('modal-db-mismatch-text');
    if (dbComp.mismatch_details) {
      mismatchAlert.style.display = 'block';
      mismatchText.innerText = dbComp.mismatch_details;
    } else {
      mismatchAlert.style.display = 'none';
    }

    // Incident Report & Recommended Action
    document.getElementById('modal-incident-report').innerText = call.incident_report || 'No incident detected. System functioned as intended.';
    document.getElementById('modal-recommended-action').innerText = call.recommended_action || 'No action needed.';

    // Tab 2: Transcript
    const transcriptContainer = document.getElementById('modal-transcript-container');
    const transcript = call.transcript || [];
    if (transcript.length === 0) {
      transcriptContainer.innerHTML = '<div style="color: var(--text-dim); padding: 20px; text-align: center;">No transcript turns captured for this call.</div>';
    } else {
      transcriptContainer.innerHTML = transcript.map(turn => {
        const role = (turn.role || 'ai').toLowerCase();
        const roleLabel = role === 'user' ? 'Customer' : 'Voice Receptionist AI';
        return `
          <div class="chat-bubble ${role}">
            <div class="bubble-role">${roleLabel}</div>
            <div>${turn.text || ''}</div>
          </div>
        `;
      }).join('');
    }

    // Tab 3: Raw DB JSON
    document.getElementById('modal-raw-db-json').innerText = JSON.stringify(call.db_state || {}, null, 2);

    // Update Resolve button text
    const resolveBtn = document.getElementById('modal-btn-resolve');
    if (call.resolved) {
      resolveBtn.innerText = '↺ Reopen Incident';
      resolveBtn.className = 'btn btn-secondary btn-sm';
    } else {
      resolveBtn.innerText = '✓ Mark Issue Resolved';
      resolveBtn.className = 'btn btn-success btn-sm';
    }

  } catch (err) {
    showToast(`Error opening inspection: ${err.message}`, 'error');
  }
}

function closeModal() {
  document.getElementById('inspection-modal').classList.remove('active');
  activeCallId = null;
  activeCallData = null;
}

// Send incident email alert for a call
async function sendEmailForCall(callId) {
  showToast(`Dispatching incident alert email for Call #${callId}...`, 'info');
  try {
    const res = await fetch(`/api/audit/email/${callId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipient: 'ethan.figueredo943@gmail.com' })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Email failed to send');
    showToast(data.message || 'Alert email sent successfully!', 'success');
    loadStats();
    loadCalls();
  } catch (err) {
    showToast(`Failed to send email: ${err.message}`, 'error');
  }
}

// Send test email
async function sendTestEmail() {
  showToast('Sending test email to ethan.figueredo943@gmail.com...', 'info');
  try {
    const res = await fetch('/api/email/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipient: 'ethan.figueredo943@gmail.com' })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to send test email');
    showToast(data.message, 'success');
  } catch (err) {
    showToast(`Test email error: ${err.message}`, 'error');
  }
}

// Toggle background daemon
async function toggleDaemon() {
  const daemonText = document.getElementById('daemon-status-text');
  const isCurrentlyActive = daemonText.innerText === 'Active';
  const newStatus = !isCurrentlyActive;

  try {
    const res = await fetch(`/api/daemon/toggle?enable=${newStatus}`, { method: 'POST' });
    const data = await res.json();
    showToast(`Background monitoring daemon ${newStatus ? 'resumed' : 'paused'}.`, 'info');
    loadStats();
  } catch (err) {
    showToast(`Daemon toggle error: ${err.message}`, 'error');
  }
}

// Reanalyze Call with Gemini
async function reanalyzeCall(callId) {
  showToast(`Re-evaluating Call #${callId} with Gemini 3.8 Flash...`, 'info');
  try {
    const res = await fetch(`/api/audit/call/${callId}?force=true`, { method: 'POST' });
    if (!res.ok) throw new Error('Re-analysis failed');
    showToast(`Call #${callId} re-analyzed!`, 'success');
    openInspection(callId);
    loadStats();
    loadCalls();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

// Mark resolved
async function toggleResolveCall(callId, willResolve) {
  try {
    const res = await fetch(`/api/calls/${callId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolved: willResolve })
    });
    if (!res.ok) throw new Error('Failed to update resolution state');
    showToast(`Call #${callId} marked as ${willResolve ? 'resolved' : 'open'}.`, 'success');
    openInspection(callId);
    loadStats();
    loadCalls();
  } catch (err) {
    showToast(`Resolution update error: ${err.message}`, 'error');
  }
}

// Toast notification helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
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

let simTimeout = null;
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

      document.getElementById('sim-out-profit').innerText = fmtMoney(prof.gross_profit);
      document.getElementById('sim-out-margin').innerText = `Gross Margin: ${prof.margin_pct}%`;
      document.getElementById('sim-out-mrr').innerText = fmtMoney(rev.total_mrr);
      document.getElementById('sim-out-arr').innerText = `ARR: ${fmtMoney(rev.total_arr)}`;

      document.getElementById('sim-out-calls').innerText = fmtInt(vol.monthly_calls);
      document.getElementById('sim-out-minutes').innerText = `${fmtInt(vol.billed_minutes || vol.monthly_minutes)}m`;
      document.getElementById('sim-out-cogs').innerText = fmtMoney(costs.total_cogs);
      document.getElementById('sim-out-cost-min').innerText = `$${Number(prof.cost_per_minute || 0).toFixed(4)}`;

      // Team splits
      document.getElementById('sim-split-founder').innerText = fmtMoney(splits.founder_50);
      document.getElementById('sim-split-closer').innerText = fmtMoney(splits.sales_closer_30);
      document.getElementById('sim-split-caller').innerText = fmtMoney(splits.cold_caller_20);

    } catch (err) {
      console.error('Error running simulation:', err);
    }
  }, 100);
}
