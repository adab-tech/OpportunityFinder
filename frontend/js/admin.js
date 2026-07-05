/* Minimal admin analytics page. Key lives only in sessionStorage
   (cleared when the tab closes) — never persisted to localStorage. */
const API_BASE = (() => {
  if (window.OPPORTUNITYFINDER_API_BASE) return window.OPPORTUNITYFINDER_API_BASE;
  if (window.location && window.location.origin && window.location.origin !== 'null') {
    return `${window.location.origin}/api/v1`;
  }
  return 'http://127.0.0.1:8000/api/v1';
})();

const $ = id => document.getElementById(id);

let modPage = 1;
const MOD_PER_PAGE = 20;

document.addEventListener('DOMContentLoaded', () => {
  const savedKey = sessionStorage.getItem('of_admin_key');
  if (savedKey) {
    $('keyInput').value = savedKey;
    loadSummary(savedKey);
    loadModerationQueue(savedKey);
  }
  $('keyForm').addEventListener('submit', e => {
    e.preventDefault();
    const key = $('keyInput').value.trim();
    if (!key) return;
    sessionStorage.setItem('of_admin_key', key);
    loadSummary(key);
    modPage = 1;
    loadModerationQueue(key);
  });

  $('modRefresh').addEventListener('click', () => {
    const key = sessionStorage.getItem('of_admin_key');
    if (key) loadModerationQueue(key);
  });

  $('modApproveAll').addEventListener('click', () => {
    const key = sessionStorage.getItem('of_admin_key');
    if (key) approveAllVisible(key);
  });
});

async function loadSummary(key) {
  $('errorMsg').style.display = 'none';
  try {
    const res = await fetch(`${API_BASE}/analytics/summary?days=7`, {
      headers: { 'X-Admin-Key': key },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showError(body.detail || `Request failed (${res.status})`);
      return;
    }
    const data = await res.json();
    render(data);
  } catch (_) {
    showError('Cannot connect to the API.');
  }
}

function showError(msg) {
  $('results').style.display = 'none';
  $('errorMsg').textContent = msg;
  $('errorMsg').style.display = 'block';
}

function render(data) {
  $('results').style.display = 'block';
  $('stat-total').textContent = data.total_events.toLocaleString();
  $('stat-visitors').textContent = data.unique_visitors.toLocaleString();
  $('stat-searches').textContent = (data.event_counts.search || 0).toLocaleString();
  $('stat-applies').textContent = (data.event_counts.apply_click || 0).toLocaleString();

  $('table-searches').innerHTML = rowsHTML(data.top_searches) || emptyRow();

  const filterRows = [
    ...data.top_type_filters.map(r => ({ ...r, value: `Type: ${r.value}` })),
    ...data.top_field_filters.map(r => ({ ...r, value: `Field: ${r.value}` })),
    ...data.top_location_filters.map(r => ({ ...r, value: `Location: ${r.value}` })),
  ];
  $('table-filters').innerHTML = rowsHTML(filterRows) || emptyRow();
}

function rowsHTML(rows) {
  return (rows || []).map(r => `<tr><td>${esc(r.value)}</td><td>${r.count}</td></tr>`).join('');
}

function emptyRow() {
  return '<tr><td colspan="2" style="color: var(--muted);">No data yet.</td></tr>';
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = String(str ?? '');
  return d.innerHTML;
}

/* ---------------- Moderation queue ---------------- */

let modItems = [];

async function loadModerationQueue(key) {
  $('modSection').style.display = 'block';
  $('modError').style.display = 'none';
  try {
    const res = await fetch(
      `${API_BASE}/admin/moderation/pending?page=${modPage}&per_page=${MOD_PER_PAGE}`,
      { headers: { 'X-Admin-Key': key } }
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showModError(body.detail || `Request failed (${res.status})`);
      return;
    }
    const data = await res.json();
    modItems = data.data || [];
    renderModeration(data);
  } catch (_) {
    showModError('Cannot connect to the API.');
  }
}

function showModError(msg) {
  $('modError').textContent = msg;
  $('modError').style.display = 'block';
}

function renderModeration(data) {
  $('modCount').textContent = `${data.total} pending`;

  if (!modItems.length) {
    $('modList').innerHTML = '';
    $('modEmpty').style.display = 'block';
    $('modPagination').style.display = 'none';
    return;
  }
  $('modEmpty').style.display = 'none';
  $('modList').innerHTML = modItems.map(modRowHTML).join('');

  modItems.forEach(item => {
    const approveBtn = document.querySelector(`.btn-approve[data-id="${item.id}"]`);
    const rejectBtn = document.querySelector(`.btn-reject[data-id="${item.id}"]`);
    if (approveBtn) approveBtn.addEventListener('click', () => approveItem(item.id));
    if (rejectBtn) rejectBtn.addEventListener('click', () => rejectItem(item.id));
  });

  renderModPagination(data);
}

function renderModPagination(data) {
  const totalPages = data.total_pages || 1;
  const pager = $('modPagination');
  if (totalPages <= 1) {
    pager.style.display = 'none';
    return;
  }
  pager.style.display = 'flex';
  pager.innerHTML = `
    <button type="button" class="page-btn" id="modPrev" ${data.page <= 1 ? 'disabled' : ''}>Prev</button>
    <span class="page-btn" style="cursor:default;">${data.page} / ${totalPages}</span>
    <button type="button" class="page-btn" id="modNext" ${data.page >= totalPages ? 'disabled' : ''}>Next</button>
  `;
  const key = sessionStorage.getItem('of_admin_key');
  const prevBtn = $('modPrev');
  const nextBtn = $('modNext');
  if (prevBtn) prevBtn.addEventListener('click', () => { modPage = Math.max(1, modPage - 1); loadModerationQueue(key); });
  if (nextBtn) nextBtn.addEventListener('click', () => { modPage += 1; loadModerationQueue(key); });
}

function modRowHTML(item) {
  const type = item.opportunity_type || 'other';
  const labels = { scholarship: 'Scholarship', fellowship: 'Fellowship',
                   grant: 'Grant', job: 'Job', other: 'Other' };
  const bodyText = item.summary || item.description || '';
  const desc = bodyText ? `<p class="mod-row-desc">${esc(bodyText.slice(0, 200))}</p>` : '';
  const scraped = item.scraped_at
    ? new Date(item.scraped_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '';

  const metaParts = [];
  if (item.source_name) metaParts.push(`via ${esc(item.source_name)}`);
  if (scraped) metaParts.push(`Scraped ${scraped}`);

  /* Defense in depth: never render a non-http(s) URL as a link */
  const safeUrl = /^https?:\/\//i.test(item.url || '') ? item.url : '#';

  return `
    <div class="mod-row" data-row-id="${item.id}">
      <div class="mod-row-main">
        <div class="mod-row-top">
          <span class="badge badge-${type}">${labels[type] || type}</span>
        </div>
        <a class="mod-row-title" href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>
        <p class="mod-row-meta">${metaParts.join(' · ')}</p>
        ${desc}
      </div>
      <div class="mod-row-actions">
        <button type="button" class="btn-approve" data-id="${item.id}">Approve</button>
        <button type="button" class="btn-reject" data-id="${item.id}">Reject</button>
      </div>
    </div>
  `;
}

async function approveItem(id) {
  const key = sessionStorage.getItem('of_admin_key');
  if (!key) return;
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/${id}/approve`, {
      method: 'POST',
      headers: { 'X-Admin-Key': key },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showModError(body.detail || `Request failed (${res.status})`);
      return;
    }
    removeRowOptimistically(id);
  } catch (_) {
    showModError('Cannot connect to the API.');
  }
}

async function rejectItem(id) {
  const key = sessionStorage.getItem('of_admin_key');
  if (!key) return;
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/${id}/reject`, {
      method: 'POST',
      headers: { 'X-Admin-Key': key },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showModError(body.detail || `Request failed (${res.status})`);
      return;
    }
    removeRowOptimistically(id);
  } catch (_) {
    showModError('Cannot connect to the API.');
  }
}

async function approveAllVisible(key) {
  if (!modItems.length) return;
  const ids = modItems.map(i => i.id);
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/bulk-approve`, {
      method: 'POST',
      headers: { 'X-Admin-Key': key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showModError(body.detail || `Request failed (${res.status})`);
      return;
    }
    ids.forEach(removeRowOptimistically);
  } catch (_) {
    showModError('Cannot connect to the API.');
  }
}

function removeRowOptimistically(id) {
  modItems = modItems.filter(i => i.id !== id);
  const row = document.querySelector(`.mod-row[data-row-id="${id}"]`);
  if (row) row.remove();

  const countEl = $('modCount');
  const match = countEl.textContent.match(/^(\d+)/);
  if (match) {
    const remaining = Math.max(0, parseInt(match[1], 10) - 1);
    countEl.textContent = `${remaining} pending`;
  }

  if (!modItems.length) {
    $('modEmpty').style.display = 'block';
    $('modPagination').style.display = 'none';
  }
}
