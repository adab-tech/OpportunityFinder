/* Admin login is a real email/password account (see
   app/routes/admin_auth.py) — a signed, httpOnly session cookie handles
   auth after login, so no key/token is ever stored in JS-readable
   storage. `credentials: 'same-origin'` on every admin fetch ensures
   that cookie is actually sent (fetch's default already does this for
   same-origin requests, but being explicit avoids surprises if this
   page is ever served from a different origin than the API). */
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

document.addEventListener('DOMContentLoaded', async () => {
  const authenticated = await checkSession();
  if (authenticated) {
    showLoggedInUI();
  }

  $('keyForm').addEventListener('submit', onLoginSubmit);
  $('logoutBtn').addEventListener('click', onLogout);
  $('modRefresh').addEventListener('click', () => loadModerationQueue());
  $('modApproveAll').addEventListener('click', approveAllVisible);

  $('trendsRange').addEventListener('change', loadTrends);
  $('listingsRefresh').addEventListener('click', () => loadListings());
  $('listingsSearch').addEventListener('input', debounce(() => { listingsPage = 1; loadListings(); }, 350));
  $('listingsTypeFilter').addEventListener('change', () => { listingsPage = 1; loadListings(); });
  $('closeEditModal').addEventListener('click', closeEditModal);
  $('editForm').addEventListener('submit', onEditSubmit);
});

function debounce(fn, ms) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

async function checkSession() {
  try {
    const res = await fetch(`${API_BASE}/admin/session`, { credentials: 'same-origin' });
    if (!res.ok) return false;
    const data = await res.json();
    return !!data.authenticated;
  } catch (_) {
    return false;
  }
}

async function onLoginSubmit(e) {
  e.preventDefault();
  $('loginError').style.display = 'none';
  const email = $('emailInput').value.trim();
  const password = $('passwordInput').value;
  if (!email || !password) return;

  try {
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      $('loginError').textContent = body.detail || `Login failed (${res.status})`;
      $('loginError').style.display = 'block';
      return;
    }
    $('passwordInput').value = '';
    showLoggedInUI();
  } catch (_) {
    $('loginError').textContent = 'Cannot connect to the API.';
    $('loginError').style.display = 'block';
  }
}

async function onLogout() {
  try {
    await fetch(`${API_BASE}/admin/logout`, { method: 'POST', credentials: 'same-origin' });
  } catch (_) { /* best effort — hide the UI regardless */ }
  document.getElementById('keyForm').closest('.admin-card').style.display = 'block';
  $('loggedInBar').style.display = 'none';
  $('results').style.display = 'none';
  $('modSection').style.display = 'none';
  $('listingsSection').style.display = 'none';
  $('errorMsg').style.display = 'none';
}

function showLoggedInUI() {
  document.getElementById('keyForm').closest('.admin-card').style.display = 'none';
  $('loggedInBar').style.display = 'block';
  loadSummary();
  loadTrends();
  modPage = 1;
  loadModerationQueue();
  listingsPage = 1;
  loadListings();
}

async function loadSummary() {
  $('errorMsg').style.display = 'none';
  try {
    const res = await fetch(`${API_BASE}/analytics/summary?days=7`, { credentials: 'same-origin' });
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

async function loadModerationQueue() {
  $('modSection').style.display = 'block';
  $('modError').style.display = 'none';
  try {
    const res = await fetch(
      `${API_BASE}/admin/moderation/pending?page=${modPage}&per_page=${MOD_PER_PAGE}`,
      { credentials: 'same-origin' }
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
  const prevBtn = $('modPrev');
  const nextBtn = $('modNext');
  if (prevBtn) prevBtn.addEventListener('click', () => { modPage = Math.max(1, modPage - 1); loadModerationQueue(); });
  if (nextBtn) nextBtn.addEventListener('click', () => { modPage += 1; loadModerationQueue(); });
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
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/${id}/approve`, {
      method: 'POST',
      credentials: 'same-origin',
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
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/${id}/reject`, {
      method: 'POST',
      credentials: 'same-origin',
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

async function approveAllVisible() {
  if (!modItems.length) return;
  const ids = modItems.map(i => i.id);
  try {
    const res = await fetch(`${API_BASE}/admin/moderation/bulk-approve`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
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

/* ---------------- Traffic trends chart ---------------- */

async function loadTrends() {
  const days = $('trendsRange').value;
  try {
    const res = await fetch(`${API_BASE}/analytics/trends?days=${days}`, { credentials: 'same-origin' });
    if (!res.ok) return; // trends are a nice-to-have on this page — a failure here shouldn't blank the whole admin page
    const body = await res.json();
    renderTrendsChart(body.data || []);
  } catch (_) { /* leave the chart area empty rather than erroring the whole page */ }
}

/* Hand-rolled SVG line chart — three series (pageviews/searches/applies),
   no charting library, consistent with this project's no-build-step,
   minimal-dependency frontend. */
function renderTrendsChart(data) {
  const el = $('trendsChart');
  if (!data.length) {
    el.innerHTML = '<p style="color:var(--muted); font-size:.85rem; text-align:center; padding:20px 0;">No traffic data yet.</p>';
    return;
  }

  const W = 640, H = 180, PAD = 24;
  const maxVal = Math.max(1, ...data.flatMap(d => [d.pageviews, d.searches, d.applies]));
  const stepX = data.length > 1 ? (W - PAD * 2) / (data.length - 1) : 0;

  const scaleY = v => H - PAD - (v / maxVal) * (H - PAD * 2);
  const scaleX = i => PAD + i * stepX;

  const linePath = key => data
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(i).toFixed(1)} ${scaleY(d[key]).toFixed(1)}`)
    .join(' ');

  const firstLabel = esc(data[0].date);
  const lastLabel = esc(data[data.length - 1].date);

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%; height:auto; display:block;">
      <line x1="${PAD}" y1="${H - PAD}" x2="${W - PAD}" y2="${H - PAD}" stroke="var(--border-soft, #f0efee)" stroke-width="1" />
      <path d="${linePath('pageviews')}" fill="none" stroke="#4f46e5" stroke-width="2" />
      <path d="${linePath('searches')}" fill="none" stroke="#059669" stroke-width="2" />
      <path d="${linePath('applies')}" fill="none" stroke="#d97706" stroke-width="2" />
    </svg>
    <div style="display:flex; justify-content:space-between; font-size:.72rem; color:var(--muted); margin-top:4px;">
      <span>${firstLabel}</span><span>${lastLabel}</span>
    </div>
  `;
}

/* ---------------- Listings management (all statuses, not just pending) ---------------- */

let listingsPage = 1;
const LISTINGS_PER_PAGE = 25;

async function loadListings() {
  $('listingsSection').style.display = 'block';
  $('listingsError').style.display = 'none';
  const search = $('listingsSearch').value.trim();
  const type = $('listingsTypeFilter').value;

  const params = new URLSearchParams({ page: listingsPage, per_page: LISTINGS_PER_PAGE });
  if (search) params.set('search', search);
  if (type) params.set('opportunity_type', type);

  try {
    const res = await fetch(`${API_BASE}/admin/opportunities/?${params}`, { credentials: 'same-origin' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showListingsError(body.detail || `Request failed (${res.status})`);
      return;
    }
    const data = await res.json();
    renderListings(data);
  } catch (_) {
    showListingsError('Cannot connect to the API.');
  }
}

function showListingsError(msg) {
  $('listingsError').textContent = msg;
  $('listingsError').style.display = 'block';
}

function renderListings(data) {
  $('listingsCount').textContent = `${data.total} total`;
  const items = data.data || [];

  if (!items.length) {
    $('listingsList').innerHTML = '';
    $('listingsEmpty').style.display = 'block';
    $('listingsPagination').style.display = 'none';
    return;
  }
  $('listingsEmpty').style.display = 'none';
  $('listingsList').innerHTML = items.map(listingRowHTML).join('');

  items.forEach(item => {
    const editBtn = document.querySelector(`.btn-edit[data-id="${item.id}"]`);
    const toggleBtn = document.querySelector(`.btn-toggle-active[data-id="${item.id}"]`);
    if (editBtn) editBtn.addEventListener('click', () => openEditModal(item));
    if (toggleBtn) toggleBtn.addEventListener('click', () => toggleActive(item));
  });

  renderListingsPagination(data);
}

function renderListingsPagination(data) {
  const totalPages = data.total_pages || 1;
  const pager = $('listingsPagination');
  if (totalPages <= 1) {
    pager.style.display = 'none';
    return;
  }
  pager.style.display = 'flex';
  pager.innerHTML = `
    <button type="button" class="page-btn" id="listingsPrev" ${data.page <= 1 ? 'disabled' : ''}>Prev</button>
    <span class="page-btn" style="cursor:default;">${data.page} / ${totalPages}</span>
    <button type="button" class="page-btn" id="listingsNext" ${data.page >= totalPages ? 'disabled' : ''}>Next</button>
  `;
  const prevBtn = $('listingsPrev');
  const nextBtn = $('listingsNext');
  if (prevBtn) prevBtn.addEventListener('click', () => { listingsPage = Math.max(1, listingsPage - 1); loadListings(); });
  if (nextBtn) nextBtn.addEventListener('click', () => { listingsPage += 1; loadListings(); });
}

function listingRowHTML(item) {
  const type = item.opportunity_type || 'other';
  const labels = { scholarship: 'Scholarship', fellowship: 'Fellowship',
                   grant: 'Grant', job: 'Job', other: 'Other' };

  const statusBadges = [`<span class="badge badge-${type}">${labels[type] || type}</span>`];
  if (!item.is_active) statusBadges.push('<span class="badge badge-inactive">Inactive</span>');
  if (item.review_status === 'pending') statusBadges.push('<span class="badge badge-pending">Pending</span>');
  if (item.review_status === 'rejected') statusBadges.push('<span class="badge badge-rejected">Rejected</span>');

  const metaParts = [];
  if (item.source_name) metaParts.push(`via ${esc(item.source_name)}`);
  if (item.location) metaParts.push(esc(item.location));

  return `
    <div class="listing-row" data-row-id="${item.id}">
      <div class="listing-row-main">
        <div class="listing-row-top">${statusBadges.join('')}</div>
        <div class="listing-row-title">${esc(item.title)}</div>
        <p class="listing-row-meta">${metaParts.join(' · ')}</p>
      </div>
      <div class="listing-row-actions">
        <button type="button" class="btn-approve btn-edit" data-id="${item.id}">Edit</button>
        <button type="button" class="btn-reject btn-toggle-active" data-id="${item.id}">
          ${item.is_active ? 'Deactivate' : 'Reactivate'}
        </button>
      </div>
    </div>
  `;
}

async function toggleActive(item) {
  const action = item.is_active ? 'deactivate' : 'reactivate';
  try {
    const res = await fetch(`${API_BASE}/admin/opportunities/${item.id}/${action}`, {
      method: 'POST',
      credentials: 'same-origin',
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showListingsError(body.detail || `Request failed (${res.status})`);
      return;
    }
    loadListings();
  } catch (_) {
    showListingsError('Cannot connect to the API.');
  }
}

/* ---------------- Edit listing modal ---------------- */

function openEditModal(item) {
  $('editId').value = item.id;
  $('editTitle').value = item.title || '';
  $('editType').value = item.opportunity_type || 'other';
  $('editStatus').value = String(item.is_active);
  $('editField').value = item.field || '';
  $('editLocation').value = item.location || '';
  $('editDeadline').value = item.deadline || '';
  $('editDeadlineAt').value = item.deadline_at || '';
  $('editSourceName').value = item.source_name || '';
  $('editUrl').value = item.url || '';
  $('editSummary').value = item.summary || '';
  $('editDescription').value = item.description || '';
  $('editError').style.display = 'none';
  $('editModal').style.display = 'flex';
}

function closeEditModal() {
  $('editModal').style.display = 'none';
}

async function onEditSubmit(e) {
  e.preventDefault();
  const id = $('editId').value;
  const payload = {
    title: $('editTitle').value.trim(),
    opportunity_type: $('editType').value,
    is_active: $('editStatus').value === 'true',
    field: $('editField').value.trim() || null,
    location: $('editLocation').value.trim() || null,
    deadline: $('editDeadline').value.trim() || null,
    deadline_at: $('editDeadlineAt').value || null,
    source_name: $('editSourceName').value.trim() || null,
    url: $('editUrl').value.trim(),
    summary: $('editSummary').value.trim() || null,
    description: $('editDescription').value.trim() || null,
  };

  try {
    const res = await fetch(`${API_BASE}/admin/opportunities/${id}`, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      $('editError').textContent = body.detail || `Request failed (${res.status})`;
      $('editError').style.display = 'block';
      return;
    }
    closeEditModal();
    loadListings();
  } catch (_) {
    $('editError').textContent = 'Cannot connect to the API.';
    $('editError').style.display = 'block';
  }
}
