// AI Energy Consumption Anomaly Detector Frontend
(function() {
  'use strict';

  // State
  let currentOverviewData = null;
  let currentDetectionData = null;
  let currentHouseholdsData = null;
  let selectedAnomalyDate = null;
  let selectedHouseMeter = null;
  let overviewRan = false;
  let detectionRan = false;

  // Navigation
  const pageIds = ['overview', 'detection', 'households', 'method', 'access'];

  function initNav() {
    function showPage() {
      let hash = (location.hash || '#overview').slice(1);
      if (!pageIds.includes(hash)) hash = 'overview';
      if (hash === 'access' && !window.CURRENT_USER_IS_ADMIN) hash = 'overview';

      pageIds.forEach(id => {
        const el = document.getElementById('pg-' + id);
        if (el) el.hidden = (id !== hash);
      });

      document.querySelectorAll('#main-nav a').forEach(a => {
        const target = a.getAttribute('data-go');
        if (target === hash) a.classList.add('on');
        else a.classList.remove('on');
      });

      window.scrollTo(0, 0);

      // Trigger page load
      if (hash === 'overview') {
        if (overviewRan && currentOverviewData) {
          renderOverviewChartAndPanels(currentOverviewData);
        } else {
          renderOverviewEmptyState();
        }
      } else if (hash === 'detection') {
        if (detectionRan && currentDetectionData) {
          renderDetectionChartAndPanels(currentDetectionData);
        } else {
          renderDetectionEmptyState();
        }
      } else if (hash === 'households') {
        loadHouseholds();
      } else if (hash === 'method') {
        loadMethod();
      } else if (hash === 'access') {
        loadAccess();
      }
    }

    window.addEventListener('hashchange', showPage);
    showPage();
  }

  // API Helper
  async function apiFetch(url, options = {}) {
    try {
      const res = await fetch(url, options);
      if (res.status === 401) {
        window.location.href = '/login';
        return null;
      }
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (e) {
      console.error('API error:', e);
      throw e;
    }
  }

  // ==========================================
  // PAGE 1: OVERVIEW
  // ==========================================
  function renderOverviewEmptyState() {
    const chartContainer = document.getElementById('ov-chart-container');
    if (chartContainer) {
      chartContainer.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:290px;color:#5A6575;gap:12px;background:#FBFBFC;border:1px dashed #D3D8E0;border-radius:3px">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#8C97A7" stroke-width="1.6" aria-hidden="true">
            <path d="M3 3v18h18"/><path d="M7 16l4-4 4 2 5-6"/>
          </svg>
          <div style="font-size:14px;color:#1B2430;font-weight:600">Consumption graph not loaded</div>
          <div style="font-size:13px;color:#5A6575">Click <strong>&ldquo;Run detection&rdquo;</strong> above to analyze consumption and display the graph.</div>
        </div>
      `;
    }
    const dtSelect = document.getElementById('ov-dt');
    if (dtSelect && dtSelect.options.length <= 1) {
      dtSelect.innerHTML = '<option value="">Click "Run detection" to inspect</option>';
    }
    const tbody = document.querySelector('#ov-top-houses-table tbody');
    if (tbody && !overviewRan) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#5A6575;padding:24px">Click &ldquo;Run detection&rdquo; above to view household attribution</td></tr>';
    }
  }

  function renderOverviewChartAndPanels(data) {
    if (!data) return;

    // Update KPIs
    document.getElementById('kpi-houses').textContent = data.kpis.houses;
    document.getElementById('kpi-period').textContent = `${data.kpis.period_start} to ${data.kpis.period_end}`;
    document.getElementById('kpi-missing').textContent = `${data.kpis.missing_pct} %`;
    document.getElementById('kpi-anomalies').textContent = data.kpis.anomalies_flagged;

    // Populate inspect dates dropdown
    const dtSelect = document.getElementById('ov-dt');
    dtSelect.innerHTML = '';
    data.anomalies.forEach((a, i) => {
      const opt = document.createElement('option');
      opt.value = a.date;
      opt.textContent = `${a.date} (+${a.increase} kWh, score ${a.score})`;
      if (i === 0) opt.selected = true;
      dtSelect.appendChild(opt);
    });

    // Default selected anomaly
    const targetAnomaly = data.top_anomaly || (data.anomalies.length > 0 ? data.anomalies[0] : null);
    if (targetAnomaly) {
      selectedAnomalyDate = targetAnomaly.date;
      updateOverviewSelectedPanel(targetAnomaly);
      renderOverviewTopHouses(data.top_houses, targetAnomaly.date);
    }

    // Render overview line chart
    renderLineChart('ov-chart-container', data.series, 880, 290, (date) => {
      const found = data.anomalies.find(a => a.date === date);
      if (found) {
        selectedAnomalyDate = found.date;
        dtSelect.value = found.date;
        updateOverviewSelectedPanel(found);
        loadOverviewHousesForDate(found.date);
      }
    });
  }

  async function loadOverview() {
    const data = await apiFetch('/api/overview');
    if (!data) return;
    currentOverviewData = data;
    overviewRan = true;
    renderOverviewChartAndPanels(data);
  }

  function updateOverviewSelectedPanel(a) {
    if (!a) return;
    document.getElementById('ov-sel-date').textContent = a.date;
    document.getElementById('ov-sel-actual').textContent = `${a.actual_total} kWh`;
    document.getElementById('ov-sel-expected').textContent = `${a.expected_total} kWh`;
    document.getElementById('ov-sel-increase').textContent = `+${a.increase} kWh (+${a.pct}%)`;
    document.getElementById('ov-sel-score').textContent = a.score;
    document.getElementById('ov-view-hh-link').onclick = () => {
      selectedAnomalyDate = a.date;
      location.hash = '#households';
    };
  }

  async function loadOverviewHousesForDate(date) {
    document.getElementById('ov-top-houses-date').textContent = date;
    const tbody = document.querySelector('#ov-top-houses-table tbody');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#5A6575">Loading houses...</td></tr>';
    try {
      const rows = await apiFetch(`/api/households?date=${date}&top=5`);
      renderOverviewTopHouses(rows, date);
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#A63D2F">Failed to load house attribution</td></tr>';
    }
  }

  function renderOverviewTopHouses(rows, date) {
    document.getElementById('ov-top-houses-date').textContent = date;
    const tbody = document.querySelector('#ov-top-houses-table tbody');
    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#5A6575">No house data available</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="${i === rows.length - 1 ? 'border-bottom:0' : ''}">
        <td>${r.rank}</td>
        <td>${r.meter}</td>
        <td class="n">${r.actual.toFixed(1)}</td>
        <td class="n">${r.expected.toFixed(1)}</td>
        <td class="n" style="color:${r.excess > 0 ? '#A63D2F' : '#1B2430'}">${r.excess > 0 ? '+' : ''}${r.excess.toFixed(1)}</td>
        <td class="n">${r.share.toFixed(1)}%</td>
      </tr>
    `).join('');
  }

  // ==========================================
  // PAGE 2: DETECTION
  // ==========================================
  function initDetectionControls() {
    const modelSelect = document.getElementById('det-model');
    const threshLabel = document.getElementById('det-thresh-label');
    const threshInput = document.getElementById('det-threshold');

    modelSelect.addEventListener('change', () => {
      if (modelSelect.value === 'Robust z-score (MAD)') {
        threshLabel.textContent = 'Z-threshold';
        threshInput.value = '3.5';
      } else {
        threshLabel.textContent = 'Contamination (%)';
        threshInput.value = '2.0';
      }
    });

    document.getElementById('det-run-btn').addEventListener('click', async () => {
      const btn = document.getElementById('det-run-btn');
      const origText = btn.textContent;
      btn.textContent = 'Running...';
      btn.disabled = true;
      try {
        await loadDetection();
        detectionRan = true;
      } finally {
        btn.textContent = origText;
        btn.disabled = false;
      }
    });

    document.getElementById('det-apply-range-btn').addEventListener('click', async () => {
      if (detectionRan) {
        await loadDetection();
      }
    });
  }

  function renderDetectionEmptyState() {
    const chartContainer = document.getElementById('det-chart-container');
    if (chartContainer) {
      chartContainer.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:305px;color:#5A6575;gap:12px;background:#FBFBFC;border:1px dashed #D3D8E0;border-radius:3px">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#8C97A7" stroke-width="1.6" aria-hidden="true">
            <path d="M3 3v18h18"/><path d="M7 16l4-4 4 2 5-6"/>
          </svg>
          <div style="font-size:14px;color:#1B2430;font-weight:600">Model not executed yet</div>
          <div style="font-size:13px;color:#5A6575">Configure parameters and click <strong>&ldquo;Run detection&rdquo;</strong> above to generate the chart.</div>
        </div>
      `;
    }
    const tbody = document.querySelector('#det-table tbody');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#5A6575;padding:24px">Click &ldquo;Run detection&rdquo; above to scan intervals</td></tr>';
    }
    const scannedEl = document.getElementById('det-sum-scanned');
    if (scannedEl) scannedEl.textContent = '--';
    const flaggedEl = document.getElementById('det-sum-flagged');
    if (flaggedEl) flaggedEl.textContent = '--';
    const threshEl = document.getElementById('det-sum-threshold');
    if (threshEl) threshEl.textContent = '--';
    const lowcovEl = document.getElementById('det-sum-lowcov');
    if (lowcovEl) lowcovEl.textContent = '--';
    const countEl = document.getElementById('det-flagged-count');
    if (countEl) countEl.textContent = '0 flagged';
  }

  function renderDetectionChartAndPanels(data) {
    if (!data) return;

    // Summary panel
    document.getElementById('det-sum-model').textContent = data.summary.model;
    document.getElementById('det-sum-scanned').textContent = data.summary.scanned;
    document.getElementById('det-sum-flagged').textContent = data.summary.flagged;
    document.getElementById('det-sum-threshold').textContent = data.summary.threshold;
    document.getElementById('det-sum-lowcov').textContent = data.summary.low_coverage_days;
    document.getElementById('det-flagged-count').textContent = `${data.summary.flagged} flagged`;

    // Render chart
    renderLineChart('det-chart-container', data.series, 1200, 305, (date) => {
      selectedAnomalyDate = date;
      location.hash = '#households';
    });

    // Render table
    const tbody = document.querySelector('#det-table tbody');
    if (!data.anomalies || data.anomalies.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#5A6575">No anomalies flagged with current settings</td></tr>';
      return;
    }

    tbody.innerHTML = data.anomalies.map((a, i) => `
      <tr class="clickable-row" data-date="${a.date}">
        <td>${i + 1}</td>
        <td><strong>${a.date}</strong></td>
        <td class="n">${a.actual_total.toFixed(1)}</td>
        <td class="n">${a.expected_total.toFixed(1)}</td>
        <td class="n"><span style="color:#A63D2F">+${a.increase.toFixed(1)} (+${a.pct.toFixed(1)}%)</span></td>
        <td class="n">${a.score.toFixed(2)}</td>
        <td><span class="tag">Inspect &rarr;</span></td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr[data-date]').forEach(tr => {
      tr.addEventListener('click', () => {
        selectedAnomalyDate = tr.getAttribute('data-date');
        location.hash = '#households';
      });
    });
  }

  async function loadDetection() {
    const model = document.getElementById('det-model').value;
    const baseline = document.getElementById('det-baseline').value;
    const threshold = document.getElementById('det-threshold').value;
    const trainFrom = document.getElementById('det-train-from').value;
    const trainTo = document.getElementById('det-train-to').value;
    const viewFrom = document.getElementById('det-view-from').value;
    const viewTo = document.getElementById('det-view-to').value;

    const query = new URLSearchParams({
      model: model,
      baseline: baseline,
      threshold: threshold,
      train_from: trainFrom,
      train_to: trainTo,
      from: viewFrom,
      to: viewTo
    });

    const data = await apiFetch(`/api/detect?${query.toString()}`);
    if (!data) return;
    currentDetectionData = data;
    detectionRan = true;
    renderDetectionChartAndPanels(data);
  }

  // ==========================================
  // PAGE 3: HOUSEHOLDS
  // ==========================================
  async function loadHouseholds() {
    // Populate anomaly select from current detection results or fetch overview
    let anomalies = currentDetectionData ? currentDetectionData.anomalies : (currentOverviewData ? currentOverviewData.anomalies : null);
    if (!anomalies) {
      const ov = await apiFetch('/api/overview');
      if (ov) {
        currentOverviewData = ov;
        anomalies = ov.anomalies;
      }
    }

    const select = document.getElementById('hh-anomaly-select');
    select.innerHTML = '';
    (anomalies || []).forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.date;
      opt.textContent = `${a.date} (+${a.increase} kWh, score ${a.score})`;
      if (selectedAnomalyDate && a.date === selectedAnomalyDate) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    if (select.options.length > 0 && !select.value) {
      select.selectedIndex = 0;
    }

    selectedAnomalyDate = select.value || (anomalies && anomalies[0] ? anomalies[0].date : '2019-09-11');
    updateHouseholdsView();
  }

  async function updateHouseholdsView() {
    const date = document.getElementById('hh-anomaly-select').value || selectedAnomalyDate;
    const rankBy = document.getElementById('hh-rank-by').value;
    const topN = document.getElementById('hh-top-n').value;

    if (!date) return;
    selectedAnomalyDate = date;

    const rows = await apiFetch(`/api/households?date=${date}&rank_by=${rankBy}&top=${topN}`);
    if (!rows) return;
    currentHouseholdsData = rows;

    // Render bar chart for top 10
    renderHouseholdBarChart('hh-bar-chart-container', rows.slice(0, 10), (meter) => {
      loadSelectedHouse(meter, date);
    });

    // Render table
    const tbody = document.querySelector('#hh-table tbody');
    tbody.innerHTML = rows.map((r, i) => `
      <tr class="clickable-row ${i === 0 ? 'selected' : ''}" data-meter="${r.meter}" data-rank="${r.rank}">
        <td>${r.rank}</td>
        <td><strong>${r.meter}</strong></td>
        <td class="n">${r.actual.toFixed(1)}</td>
        <td class="n">${r.expected.toFixed(1)}</td>
        <td class="n" style="color:${r.excess > 0 ? '#A63D2F' : '#1B2430'}">${r.excess > 0 ? '+' : ''}${r.excess.toFixed(1)}</td>
        <td class="n">${r.share.toFixed(1)}%</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr[data-meter]').forEach(tr => {
      tr.addEventListener('click', () => {
        tbody.querySelectorAll('tr').forEach(r => r.classList.remove('selected'));
        tr.classList.add('selected');
        const meter = tr.getAttribute('data-meter');
        loadSelectedHouse(meter, date, tr.getAttribute('data-rank'));
      });
    });

    // Automatically load rank 1 house
    if (rows.length > 0) {
      const initialMeter = selectedHouseMeter && rows.some(r => r.meter === selectedHouseMeter) ? selectedHouseMeter : rows[0].meter;
      const initialRank = rows.find(r => r.meter === initialMeter)?.rank || 1;
      loadSelectedHouse(initialMeter, date, initialRank);
    }
  }

  async function loadSelectedHouse(meter, date, rank = null) {
    selectedHouseMeter = meter;
    if (rank) {
      document.getElementById('hh-selected-house-title').textContent = `Selected house: rank ${rank} (${meter})`;
    } else {
      document.getElementById('hh-selected-house-title').textContent = `Selected house: ${meter}`;
    }

    const data = await apiFetch(`/api/house?meter=${meter}&date=${date}`);
    if (!data) return;

    document.getElementById('hh-sel-meter').textContent = data.meter;
    document.getElementById('hh-sel-actual').textContent = data.actual_at_date !== null ? `${data.actual_at_date} kWh` : 'No reading';
    document.getElementById('hh-sel-expected').textContent = data.expected_at_date !== null ? `${data.expected_at_date} kWh` : 'No expected';

    renderHouseDetailChart('hh-house-chart-container', data.history, data.target_date);
  }

  // ==========================================
  // PAGE 4: METHOD
  // ==========================================
  async function loadMethod() {
    const data = await apiFetch('/api/method');
    if (!data) return;

    document.getElementById('m-houses').textContent = data.dataset.houses;
    document.getElementById('m-rows').textContent = Number(data.dataset.rows).toLocaleString();
    document.getElementById('m-period').textContent = data.dataset.period;
    document.getElementById('m-zeros').textContent = data.dataset.zero_count;
    document.getElementById('m-missing').textContent = `${data.dataset.missing_pct} %`;

    const tbody = document.querySelector('#coverage-table tbody');
    tbody.innerHTML = data.coverage.map(c => `
      <tr>
        <td><strong>${c.meter}</strong></td>
        <td>${c.first_date}</td>
        <td>${c.last_date}</td>
        <td class="n">${c.days_with_data}</td>
        <td class="n">${c.coverage_pct}%</td>
      </tr>
    `).join('');
  }

  // ==========================================
  // PAGE 5: ACCESS (ADMIN ONLY)
  // ==========================================
  async function loadAccess() {
    if (!window.CURRENT_USER_IS_ADMIN) return;
    loadUsers();
    loadSignins();
  }

  function showAccessMsg(text, isErr = false) {
    const el = document.getElementById('access-msg');
    el.textContent = text;
    el.style.display = 'block';
    el.className = isErr ? 'err' : 'msg-success';
    el.style.background = isErr ? '#FDF2F1' : '#E8F5E9';
    el.style.border = isErr ? '1px solid #F5C6CB' : '1px solid #C8E6C9';
    setTimeout(() => { el.style.display = 'none'; }, 4000);
  }

  async function loadUsers() {
    const users = await apiFetch('/api/users');
    if (!users) return;

    const tbody = document.querySelector('#users-table tbody');
    tbody.innerHTML = users.map(u => {
      const isSelf = (u.id === window.CURRENT_USER_ID);
      const statusBadge = u.is_active 
        ? '<span class="badge badge-active">Access enabled</span>'
        : '<span class="badge badge-disabled">Access disabled</span>';
      
      const toggleText = u.is_active ? 'Disable' : 'Enable';
      const toggleClass = u.is_active ? 'secondary' : 'btn';

      return `
        <tr>
          <td><strong>${u.display_name}</strong> ${isSelf ? '<small style="color:#5A6575">(You)</small>' : ''}</td>
          <td><code>${u.username}</code></td>
          <td><span style="text-transform:capitalize">${u.role}</span></td>
          <td>${statusBadge}</td>
          <td>${u.last_login || 'Never'}</td>
          <td style="text-align:right">
            <button class="btn sm ${toggleClass}" data-toggle-id="${u.id}" data-active="${u.is_active}" ${isSelf ? 'disabled title="Cannot disable yourself"' : ''}>
              ${toggleText}
            </button>
            <button class="btn sm secondary" data-reset-id="${u.id}" style="margin-left:6px">Reset password</button>
            <button class="btn sm danger" data-delete-id="${u.id}" style="margin-left:6px" ${isSelf ? 'disabled title="Cannot delete yourself"' : ''}>
              Remove
            </button>
          </td>
        </tr>
      `;
    }).join('');

    // Wire user action buttons
    tbody.querySelectorAll('button[data-toggle-id]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-toggle-id');
        const currentActive = parseInt(btn.getAttribute('data-active'));
        const newActive = currentActive === 1 ? 0 : 1;
        try {
          await apiFetch(`/api/users/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: newActive })
          });
          showAccessMsg(`User status updated.`);
          loadUsers();
        } catch (e) {
          showAccessMsg(e.message, true);
        }
      });
    });

    tbody.querySelectorAll('button[data-reset-id]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-reset-id');
        const newPass = prompt("Enter new password for user:");
        if (!newPass) return;
        try {
          await apiFetch(`/api/users/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPass })
          });
          showAccessMsg("Password updated successfully.");
        } catch (e) {
          showAccessMsg(e.message, true);
        }
      });
    });

    tbody.querySelectorAll('button[data-delete-id]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-delete-id');
        if (!confirm("Are you sure you want to permanently remove this user?")) return;
        try {
          await apiFetch(`/api/users/${id}`, { method: 'DELETE' });
          showAccessMsg("User removed successfully.");
          loadUsers();
        } catch (e) {
          showAccessMsg(e.message, true);
        }
      });
    });
  }

  async function loadSignins() {
    const logs = await apiFetch('/api/users/log');
    if (!logs) return;

    const tbody = document.querySelector('#logins-table tbody');
    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#5A6575">No login attempts recorded yet</td></tr>';
      return;
    }

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td><code>${l.username}</code></td>
        <td>${l.ok ? '<span class="badge badge-active">Success</span>' : '<span class="badge badge-disabled">Failed</span>'}</td>
        <td class="n" style="text-align:left">${l.at}</td>
        <td><code>${l.ip || '127.0.0.1'}</code></td>
      </tr>
    `).join('');
  }

  function initAccessForm() {
    const form = document.getElementById('add-user-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const displayName = document.getElementById('new-display-name').value;
      const username = document.getElementById('new-username').value;
      const role = document.getElementById('new-role').value;
      const password = document.getElementById('new-password').value;

      try {
        await apiFetch('/api/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            display_name: displayName,
            username: username,
            role: role,
            password: password
          })
        });
        showAccessMsg("User created successfully.");
        form.reset();
        loadUsers();
      } catch (err) {
        showAccessMsg(err.message, true);
      }
    });
  }

  // ==========================================
  // SVG CHART RENDERING (NO EXTERNAL LIBS)
  // ==========================================

  /**
   * Render Time-Series Line Chart
   * Specs:
   * actual line: #1B2430 2px
   * expected: #1F3A5F dashed 5 4
   * flagged dots: #A63D2F r=5 with 1.5 white stroke
   * gridlines: #E3E6EB
   * axis text: IBM Plex Mono 11px #5A6575
   * low coverage: light grey band #E6E9EE
   */
  function renderLineChart(containerId, series, width = 880, height = 290, onDotClick = null) {
    const container = document.getElementById(containerId);
    if (!container || !series || series.length === 0) {
      if (container) container.innerHTML = '<div style="padding:40px;text-align:center;color:#5A6575">No series data available</div>';
      return;
    }

    const padLeft = 55;
    const padRight = 25;
    const padTop = 30;
    const padBottom = 45;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Y scale
    let maxVal = 0;
    series.forEach(d => {
      if (!d.low_coverage) {
        if (d.actual_total > maxVal) maxVal = d.actual_total;
        if (d.expected_total > maxVal) maxVal = d.expected_total;
      }
    });
    if (maxVal === 0) maxVal = 100;
    // Round maxVal up to pleasant interval
    const yMax = Math.ceil((maxVal * 1.1) / 50) * 50;

    function getX(index) {
      if (series.length <= 1) return padLeft + plotW / 2;
      return padLeft + (index / (series.length - 1)) * plotW;
    }

    function getY(val) {
      const clamped = Math.max(0, Math.min(yMax, val));
      return padTop + plotH - (clamped / yMax) * plotH;
    }

    // Gridlines (4 horizontal lines)
    let gridLinesSvg = '<g stroke="#E3E6EB" stroke-width="1">';
    let yLabelsSvg = '<g font-family="IBM Plex Mono,monospace" font-size="11" fill="#5A6575">';
    const steps = 4;
    for (let s = 0; s <= steps; s++) {
      const v = Math.round((yMax / steps) * s);
      const y = getY(v);
      gridLinesSvg += `<line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" />`;
      yLabelsSvg += `<text x="${padLeft - 10}" y="${y + 4}" text-anchor="end">${v}</text>`;
    }
    gridLinesSvg += '</g>';
    yLabelsSvg += `<text x="12" y="18" font-family="IBM Plex Mono,monospace" font-size="11" fill="#5A6575">kWh</text></g>`;

    // Low coverage bands
    let lowCovSvg = '';
    let inLowCov = false;
    let lowCovStart = 0;

    for (let i = 0; i < series.length; i++) {
      if (series[i].low_coverage && !inLowCov) {
        inLowCov = true;
        lowCovStart = i;
      } else if (!series[i].low_coverage && inLowCov) {
        inLowCov = false;
        const x1 = getX(lowCovStart);
        const x2 = getX(i);
        lowCovSvg += `<rect x="${x1}" y="${padTop}" width="${Math.max(1, x2 - x1)}" height="${plotH}" fill="#E6E9EE" fill-opacity="0.6" />`;
      }
    }
    if (inLowCov) {
      const x1 = getX(lowCovStart);
      const x2 = getX(series.length - 1);
      lowCovSvg += `<rect x="${x1}" y="${padTop}" width="${Math.max(1, x2 - x1)}" height="${plotH}" fill="#E6E9EE" fill-opacity="0.6" />`;
    }

    // X-axis ticks: months or sampled dates
    let xLabelsSvg = '<g font-family="IBM Plex Mono,monospace" font-size="11" fill="#5A6575">';
    // Sample 6-8 dates across range
    const numTicks = Math.min(8, series.length);
    const tickInterval = Math.floor(series.length / numTicks);
    for (let t = 0; t < series.length; t += tickInterval) {
      const x = getX(t);
      const dStr = series[t].date;
      // Show Month-Year (YYYY-MM)
      const label = dStr.slice(0, 7);
      xLabelsSvg += `<text x="${x}" y="${height - 12}" text-anchor="middle">${label}</text>`;
    }
    xLabelsSvg += '</g>';

    // Build actual & expected polylines
    let actPoints = [];
    let expPoints = [];
    let dotsSvg = '';

    series.forEach((d, i) => {
      const x = getX(i);
      if (!d.low_coverage) {
        const yAct = getY(d.actual_total);
        const yExp = getY(d.expected_total);
        actPoints.push(`${x.toFixed(1)},${yAct.toFixed(1)}`);
        expPoints.push(`${x.toFixed(1)},${yExp.toFixed(1)}`);

        if (d.flagged) {
          dotsSvg += `
            <circle cx="${x.toFixed(1)}" cy="${yAct.toFixed(1)}" r="5" fill="#A63D2F" stroke="#fff" stroke-width="1.5" style="cursor:pointer" data-flag-date="${d.date}">
              <title>${d.date}: ${d.actual_total} kWh (flagged anomaly)</title>
            </circle>
          `;
        }
      }
    });

    const expectedPolyline = `<polyline fill="none" stroke="#1F3A5F" stroke-width="1.6" stroke-dasharray="5 4" points="${expPoints.join(' ')}" />`;
    const actualPolyline = `<polyline fill="none" stroke="#1B2430" stroke-width="2" points="${actPoints.join(' ')}" />`;

    const svg = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block" role="img" aria-label="Area X daily consumption chart">
        ${gridLinesSvg}
        ${lowCovSvg}
        ${yLabelsSvg}
        ${xLabelsSvg}
        ${expectedPolyline}
        ${actualPolyline}
        ${dotsSvg}
      </svg>
    `;

    container.innerHTML = svg;

    // Attach click listeners to flagged dots
    if (onDotClick) {
      container.querySelectorAll('circle[data-flag-date]').forEach(c => {
        c.addEventListener('click', (e) => {
          const date = c.getAttribute('data-flag-date');
          onDotClick(date);
        });
      });
    }
  }

  /**
   * Horizontal Bar Chart for Top 10 Excess Houses
   */
  function renderHouseholdBarChart(containerId, topHouses, onBarClick = null) {
    const container = document.getElementById(containerId);
    if (!container || !topHouses || topHouses.length === 0) {
      if (container) container.innerHTML = '<div style="padding:40px;text-align:center;color:#5A6575">No household attribution data</div>';
      return;
    }

    const width = 760;
    const rowH = 34;
    const height = Math.max(200, topHouses.length * rowH + 30);
    const startX = 120;
    const barAreaW = 540;

    let maxExcess = 0;
    topHouses.forEach(h => {
      if (h.excess > maxExcess) maxExcess = h.excess;
    });
    if (maxExcess <= 0) maxExcess = 1;

    let barsSvg = `<line x1="${startX}" y1="10" x2="${startX}" y2="${height - 20}" stroke="#B8C0CB" />`;

    topHouses.forEach((h, i) => {
      const y = 16 + i * rowH;
      const barW = Math.max(4, (Math.max(0, h.excess) / maxExcess) * barAreaW);
      const color = (i === 0) ? '#A63D2F' : '#1F3A5F';

      barsSvg += `
        <text x="${startX - 12}" y="${y + 13}" text-anchor="end" font-size="12" fill="#44505F" font-family="'Public Sans',sans-serif">Rank ${h.rank} (${h.meter})</text>
        <rect x="${startX}" y="${y}" width="${barW.toFixed(1)}" height="18" fill="${color}" style="cursor:pointer;transition:opacity 0.15s" data-meter="${h.meter}">
          <title>${h.meter}: +${h.excess.toFixed(1)} kWh (${h.share.toFixed(1)}%)</title>
        </rect>
        <text x="${(startX + barW + 8).toFixed(1)}" y="${y + 13}" font-family="'IBM Plex Mono',monospace" font-size="12" fill="#1B2430">
          +${h.excess.toFixed(1)} kWh (${h.share.toFixed(1)}%)
        </text>
      `;
    });

    const svg = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block" role="img" aria-label="Horizontal bar chart of estimated excess consumption">
        ${barsSvg}
      </svg>
    `;

    container.innerHTML = svg;

    if (onBarClick) {
      container.querySelectorAll('rect[data-meter]').forEach(rect => {
        rect.addEventListener('click', () => {
          const meter = rect.getAttribute('data-meter');
          onBarClick(meter);
        });
      });
    }
  }

  /**
   * Selected House ±15 Days History Line Chart
   */
  function renderHouseDetailChart(containerId, history, targetDate) {
    const container = document.getElementById(containerId);
    if (!container || !history || history.length === 0) {
      if (container) container.innerHTML = '<div style="padding:20px;text-align:center;color:#5A6575">No history available for house</div>';
      return;
    }

    const width = 600;
    const height = 175;
    const padLeft = 40;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 35;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    let maxVal = 0;
    history.forEach(d => {
      if (d.actual !== null && d.actual > maxVal) maxVal = d.actual;
      if (d.expected !== null && d.expected > maxVal) maxVal = d.expected;
    });
    if (maxVal === 0) maxVal = 10;
    const yMax = Math.ceil((maxVal * 1.1) / 2) * 2;

    function getX(i) {
      if (history.length <= 1) return padLeft + plotW / 2;
      return padLeft + (i / (history.length - 1)) * plotW;
    }

    function getY(val) {
      const clamped = Math.max(0, Math.min(yMax, val));
      return padTop + plotH - (clamped / yMax) * plotH;
    }

    // Grid baseline
    let svgLines = `<line x1="${padLeft}" y1="${padTop + plotH}" x2="${width - padRight}" y2="${padTop + plotH}" stroke="#D3D8DF" />`;
    // Middle dashed gridline
    const midY = getY(yMax / 2);
    svgLines += `<line x1="${padLeft}" y1="${midY}" x2="${width - padRight}" y2="${midY}" stroke="#E6E9EE" stroke-dasharray="3 3" />`;

    let actPoints = [];
    let expPoints = [];
    let targetDotSvg = '';

    history.forEach((d, i) => {
      const x = getX(i);
      if (d.expected !== null) {
        expPoints.push(`${x.toFixed(1)},${getY(d.expected).toFixed(1)}`);
      }
      if (d.actual !== null) {
        const y = getY(d.actual);
        actPoints.push(`${x.toFixed(1)},${y.toFixed(1)}`);
        if (d.date === targetDate) {
          targetDotSvg = `
            <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="#A63D2F" stroke="#fff" stroke-width="1.5">
              <title>Flagged date: ${d.actual} kWh</title>
            </circle>
          `;
        }
      }
    });

    const expPolyline = `<polyline fill="none" stroke="#1F3A5F" stroke-width="1.4" stroke-dasharray="5 4" points="${expPoints.join(' ')}" />`;
    const actPolyline = `<polyline fill="none" stroke="#1B2430" stroke-width="1.8" points="${actPoints.join(' ')}" />`;

    // Axis labels
    const firstDate = history[0].date.slice(5); // MM-DD
    const midIdx = Math.floor(history.length / 2);
    const midDate = history[midIdx].date.slice(5);
    const lastDate = history[history.length - 1].date.slice(5);

    const labels = `
      <g font-family="'IBM Plex Mono',monospace" font-size="11" fill="#5A6575">
        <text x="${padLeft}" y="${height - 12}">${firstDate}</text>
        <text x="${getX(midIdx)}" y="${height - 12}" text-anchor="middle">${midDate} (target)</text>
        <text x="${width - padRight}" y="${height - 12}" text-anchor="end">${lastDate}</text>
      </g>
    `;

    const svg = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block" role="img" aria-label="House actual and expected consumption over 30 days">
        ${svgLines}
        ${expPolyline}
        ${actPolyline}
        ${targetDotSvg}
        ${labels}
      </svg>
    `;

    container.innerHTML = svg;
  }

  // Init on DOM load
  document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initDetectionControls();
    initAccessForm();

    // Overview controls
    const ovRunBtn = document.getElementById('ov-run-btn');
    if (ovRunBtn) {
      ovRunBtn.addEventListener('click', async () => {
        const origText = ovRunBtn.textContent;
        ovRunBtn.textContent = 'Running...';
        ovRunBtn.disabled = true;
        try {
          await loadOverview();
          overviewRan = true;
        } finally {
          ovRunBtn.textContent = origText;
          ovRunBtn.disabled = false;
        }
      });
    }

    const ovDtSelect = document.getElementById('ov-dt');
    if (ovDtSelect) {
      ovDtSelect.addEventListener('change', () => {
        const val = ovDtSelect.value;
        if (currentOverviewData && currentOverviewData.anomalies) {
          const a = currentOverviewData.anomalies.find(x => x.date === val);
          if (a) {
            selectedAnomalyDate = a.date;
            updateOverviewSelectedPanel(a);
            loadOverviewHousesForDate(a.date);
          }
        }
      });
    }

    // Household controls
    const hhUpdateBtn = document.getElementById('hh-update-btn');
    if (hhUpdateBtn) {
      hhUpdateBtn.addEventListener('click', () => {
        updateHouseholdsView();
      });
    }
  });

})();
