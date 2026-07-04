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

document.addEventListener('DOMContentLoaded', () => {
  const savedKey = sessionStorage.getItem('of_admin_key');
  if (savedKey) {
    $('keyInput').value = savedKey;
    loadSummary(savedKey);
  }
  $('keyForm').addEventListener('submit', e => {
    e.preventDefault();
    const key = $('keyInput').value.trim();
    if (!key) return;
    sessionStorage.setItem('of_admin_key', key);
    loadSummary(key);
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
