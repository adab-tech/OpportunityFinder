/* =====================================================================
   OpportunityFinder — app.js
   Communicates with the FastAPI backend at API_BASE.
   Change API_BASE if you deploy the backend to a different host/port.
   ===================================================================== */

const API_BASE = (() => {
  if (window.OPPORTUNITYFINDER_API_BASE) {
    return window.OPPORTUNITYFINDER_API_BASE;
  }

  if (window.location && window.location.origin && window.location.origin !== 'null') {
    return `${window.location.origin}/api/v1`;
  }

  return 'http://127.0.0.1:8000/api/v1';
})();

/* ---------- shared state ---------- */
const state = {
  page: 1,
  perPage: 12,
  type: '',
  field: '',
  location: '',
  search: '',
  totalPages: 1,
};

/* ---------- DOM shortcuts ---------- */
const $ = id => document.getElementById(id);
const grid        = $('grid');
const loading     = $('loading');
const emptyState  = $('emptyState');
const pagination  = $('pagination');
const resultsMeta = $('resultsMeta');
const searchInput = $('searchInput');
const scrapeBtn   = $('scrapeBtn');
const modal       = $('modal');
const alertsBtn   = $('alertsBtn');
const saveModal   = $('saveModal');
const alertsModal = $('alertsModal');

/* opportunity id currently targeted by the save modal */
let _pendingSaveId = null;

/* ==========================================================================
   Analytics — self-hosted, no third-party tracker, no cookies.
   A random id lives in localStorage purely to tell "a repeat browser"
   from "a new one" apart in aggregate counts; it never identifies a
   person and nothing here is sold or shared. See app/services/analytics.py.
   ========================================================================== */
function getClientId() {
  const KEY = 'of_client_id';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
    localStorage.setItem(KEY, id);
  }
  return id;
}

function trackEvent(eventType, value, opportunityId) {
  const payload = { event_type: eventType, client_id: getClientId() };
  if (value !== undefined && value !== null && value !== '') payload.value = String(value).slice(0, 200);
  if (opportunityId !== undefined) payload.opportunity_id = opportunityId;

  try {
    const body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      navigator.sendBeacon(`${API_BASE}/analytics/event`, new Blob([body], { type: 'application/json' }));
    } else {
      fetch(`${API_BASE}/analytics/event`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  } catch (_) { /* analytics must never break the real UX */ }
}

/* ==========================================================================
   Boot
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  fetchStats();
  fetchOpportunities();
  bindEvents();
  trackEvent('pageview', window.location.pathname);
});

/* ==========================================================================
   Event wiring
   ========================================================================== */
function bindEvents() {
  /* Search */
  $('searchBtn').addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

  /* Top nav pills */
  document.querySelectorAll('.nav-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.type = btn.dataset.type;
      state.page = 1;
      if (state.type) trackEvent('filter_type', state.type);
      syncTypePills(state.type);
      fetchOpportunities();
    });
  });

  /* Filter type pills */
  document.querySelectorAll('.pill[data-filter="type"]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.pill[data-filter="type"]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.type = btn.dataset.value;
      state.page = 1;
      if (state.type) trackEvent('filter_type', state.type);
      syncNavPills(state.type);
      fetchOpportunities();
    });
  });

  /* Dropdowns */
  $('fieldFilter').addEventListener('change', e => {
    state.field = e.target.value;
    state.page = 1;
    if (state.field) trackEvent('filter_field', state.field);
    fetchOpportunities();
  });

  $('locationFilter').addEventListener('change', e => {
    state.location = e.target.value;
    state.page = 1;
    if (state.location) trackEvent('filter_location', state.location);
    fetchOpportunities();
  });

  /* Scrape triggers */
  scrapeBtn.addEventListener('click', triggerScrape);
  $('emptyBtn').addEventListener('click', triggerScrape);
  $('closeModal').addEventListener('click', () => { modal.style.display = 'none'; });

  /* Save-opportunity modal, and apply-click tracking */
  grid.addEventListener('click', e => {
    const saveBtn = e.target.closest('.btn-save');
    if (saveBtn) {
      _pendingSaveId = Number(saveBtn.dataset.id);
      trackEvent('save_click', null, _pendingSaveId);
      saveModal.style.display = 'flex';
      return;
    }
    const applyLink = e.target.closest('.btn-apply');
    if (applyLink) {
      trackEvent('apply_click', null, Number(applyLink.dataset.id));
    }
  });
  $('closeSaveModal').addEventListener('click', () => { saveModal.style.display = 'none'; });
  $('saveForm').addEventListener('submit', onSaveSubmit);

  /* Alerts modal */
  alertsBtn.addEventListener('click', () => { alertsModal.style.display = 'flex'; });
  $('closeAlertsModal').addEventListener('click', () => { alertsModal.style.display = 'none'; });
  $('alertsForm').addEventListener('submit', onAlertSubmit);
}

function doSearch() {
  state.search = searchInput.value.trim();
  state.page   = 1;
  if (state.search) trackEvent('search', state.search);
  fetchOpportunities();
}

/* Keep top-nav and filter pills in sync */
function syncTypePills(type) {
  document.querySelectorAll('.pill[data-filter="type"]').forEach(b => {
    b.classList.toggle('active', b.dataset.value === type);
  });
}
function syncNavPills(type) {
  document.querySelectorAll('.nav-pill').forEach(b => {
    b.classList.toggle('active', b.dataset.type === type);
  });
}

/* Poll scraper status until idle, refreshing the grid as results arrive */
let _pollTimer = null;
function pollWhileScraping() {
  if (_pollTimer) clearInterval(_pollTimer);
  let ticks = 0;
  const MAX_TICKS = 36; /* ~3 minutes */
  _pollTimer = setInterval(async () => {
    ticks += 1;
    fetchStats();
    fetchOpportunities();
    try {
      const res = await fetch(`${API_BASE}/scraper/status`);
      if (res.ok) {
        const s = await res.json();
        if (!s.scraping_in_progress || ticks >= MAX_TICKS) {
          clearInterval(_pollTimer);
          _pollTimer = null;
          modal.style.display = 'none';
          fetchStats();
          fetchOpportunities();
          if (s.scraping_in_progress) toast('Scrape still running in background.', 'warn');
          else toast('Scrape finished. Browse the latest results.');
        }
      }
    } catch (_) { /* ignore */ }
  }, 5000);
}

/* ==========================================================================
   API calls
   ========================================================================== */
async function fetchStats() {
  try {
    const res = await fetch(`${API_BASE}/opportunities/stats`);
    if (!res.ok) return;
    const d = await res.json();
    animateCount('stat-total',       d.total);
    animateCount('stat-scholarship',  d.scholarships);
    animateCount('stat-fellowship',   d.fellowships);
    animateCount('stat-grant',        d.grants);
    animateCount('stat-job',          d.jobs);
  } catch (_) { /* backend not yet reachable */ }
}

async function fetchOpportunities() {
  showLoading(true);

  const params = new URLSearchParams({ page: state.page, per_page: state.perPage });
  if (state.type)     params.set('opportunity_type', state.type);
  if (state.field)    params.set('field',    state.field);
  if (state.location) params.set('location', state.location);
  if (state.search)   params.set('search',   state.search);

  try {
    const res = await fetch(`${API_BASE}/opportunities/?${params}`);
    if (!res.ok) throw new Error('API error');
    const d = await res.json();
    state.totalPages = d.total_pages;
    renderCards(d.data);
    renderPagination(d.total);
    updateMeta(d.total);
  } catch (err) {
    console.error(err);
    showEmpty('Cannot reach the backend. Make sure the API server is running on port 8000.');
  } finally {
    showLoading(false);
  }
}

async function triggerScrape() {
  modal.style.display = 'flex';
  scrapeBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/scraper/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        opportunity_types: ['scholarship', 'fellowship', 'grant', 'job'],
        max_results: 50,
      }),
    });

    if (res.ok) {
      toast('Scraping started! Results will appear automatically.');
      pollWhileScraping();
    } else if (res.status === 409) {
      pollWhileScraping();
      toast('Scraping is already running. Please wait.', 'warn');
    } else {
      toast('Could not start scraping. Check the API server.', 'error');
    }
  } catch (_) {
    toast('Cannot connect to the API. Is the backend running?', 'error');
  } finally {
    scrapeBtn.disabled = false;
  }
}

/* ==========================================================================
   Saved opportunities & alerts (no-password: email + manage link)
   ========================================================================== */
async function onSaveSubmit(e) {
  e.preventDefault();
  const email = $('saveEmailInput').value.trim();
  if (!email || _pendingSaveId == null) return;

  try {
    const res = await fetch(`${API_BASE}/saved`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, opportunity_id: _pendingSaveId }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      toast(body.message || 'Saved! Check your email for a manage link.');
      saveModal.style.display = 'none';
      $('saveForm').reset();
    } else {
      toast(body.detail || 'Could not save this opportunity.', 'error');
    }
  } catch (_) {
    toast('Cannot connect to the API. Is the backend running?', 'error');
  }
}

async function onAlertSubmit(e) {
  e.preventDefault();
  const email = $('alertsEmailInput').value.trim();
  if (!email) return;

  const payload = { email };
  if (state.type)     payload.opportunity_type = state.type;
  if (state.field)    payload.field = state.field;
  if (state.location) payload.location = state.location;
  if (state.search)   payload.keyword = state.search;

  try {
    const res = await fetch(`${API_BASE}/alerts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      trackEvent('alert_create');
      toast(body.message || 'Alert created! Check your email for a manage link.');
      alertsModal.style.display = 'none';
      $('alertsForm').reset();
    } else {
      toast(body.detail || 'Could not create this alert.', 'error');
    }
  } catch (_) {
    toast('Cannot connect to the API. Is the backend running?', 'error');
  }
}

/* ==========================================================================
   Rendering
   ========================================================================== */
function renderCards(items) {
  if (!items || items.length === 0) {
    showEmpty();
    grid.innerHTML = '';
    return;
  }
  emptyState.style.display = 'none';
  grid.innerHTML = items.map(cardHTML).join('');
}

/* Build a deadline badge that tells people the actual urgency instead of
   leaving them to read a date and do the math themselves. */
function deadlineBadge(opp) {
  if (opp.deadline_at) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const due = new Date(opp.deadline_at + 'T00:00:00');
    const daysLeft = Math.round((due - today) / 86400000);

    if (daysLeft < 0)  return { text: 'Deadline passed', cls: 'tag-deadline-passed' };
    if (daysLeft === 0) return { text: 'Deadline is today', cls: 'tag-deadline-urgent' };
    if (daysLeft === 1) return { text: '1 day left', cls: 'tag-deadline-urgent' };
    if (daysLeft <= 7)  return { text: `${daysLeft} days left`, cls: 'tag-deadline-urgent' };
    if (daysLeft <= 30) return { text: `${daysLeft} days left`, cls: 'tag-deadline-soon' };
    return { text: `Deadline ${opp.deadline || due.toLocaleDateString()}`, cls: 'tag-deadline' };
  }
  if (opp.deadline === 'Rolling') return { text: 'Rolling deadline', cls: 'tag-deadline-rolling' };
  if (opp.deadline) return { text: opp.deadline, cls: 'tag-deadline' };
  return { text: 'Check listing for deadline', cls: 'tag-deadline-unknown' };
}

function cardHTML(opp) {
  const type   = opp.opportunity_type || 'other';
  const labels = { scholarship: 'Scholarship', fellowship: 'Fellowship',
                   grant: 'Grant', job: 'Job', other: 'Other' };

  const dl       = deadlineBadge(opp);
  const deadline = `<span class="tag ${dl.cls}">${esc(dl.text)}</span>`;
  const field    = opp.field    ? `<span class="tag">${esc(opp.field)}</span>`    : '';
  const location = opp.location ? `<span class="tag">${esc(opp.location)}</span>` : '';
  /* Prefer our own original synopsis over the raw scraped description,
     so people get a plain-English idea of the opportunity at a glance. */
  const bodyText = opp.summary || opp.description;
  const desc     = bodyText
    ? `<p class="card-desc">${esc(bodyText.slice(0, 240))}</p>` : '';
  const added    = new Date(opp.scraped_at).toLocaleDateString('en-US',
    { month: 'short', day: 'numeric', year: 'numeric' });

  /* Defense in depth: never render a non-http(s) URL as a link */
  const safeUrl = /^https?:\/\//i.test(opp.url || '') ? opp.url : '#';

  return `
    <article class="card">
      <div class="card-accent accent-${type}"></div>
      <div class="card-body">
        <div class="card-top">
          <span class="badge badge-${type}">${labels[type] || type}</span>
        </div>
        <h3 class="card-title">${esc(opp.title)}</h3>
        ${opp.source_name ? `<p class="card-source">via ${esc(opp.source_name)}</p>` : ''}
        ${desc}
        <div class="card-tags">${field}${location}${deadline}</div>
      </div>
      <div class="card-foot">
        <span class="card-date">Added ${added}</span>
        <button class="btn-save" data-id="${opp.id}" title="Save this opportunity">Save</button>
        <a href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer" data-id="${opp.id}"
           class="btn-apply apply-${type}">Apply →</a>
      </div>
    </article>`;
}

function renderPagination(total) {
  if (state.totalPages <= 1) { pagination.innerHTML = ''; return; }

  const MAX_VISIBLE = 7;
  let start = Math.max(1, state.page - Math.floor(MAX_VISIBLE / 2));
  let end   = Math.min(state.totalPages, start + MAX_VISIBLE - 1);
  if (end - start < MAX_VISIBLE - 1) start = Math.max(1, end - MAX_VISIBLE + 1);

  const btns = [];
  btns.push(pgBtn('‹ Prev', state.page - 1, state.page === 1));
  for (let i = start; i <= end; i++) btns.push(pgBtn(i, i, false, i === state.page));
  btns.push(pgBtn('Next ›', state.page + 1, state.page === state.totalPages));

  pagination.innerHTML = btns.join('');
}

function pgBtn(label, targetPage, disabled, active = false) {
  return `<button class="page-btn${active ? ' active' : ''}"
    ${disabled ? 'disabled' : ''}
    onclick="goPage(${targetPage})">${label}</button>`;
}

/* Called from inline onclick in pagination buttons */
function goPage(p) {
  state.page = p;
  window.scrollTo({ top: 0, behavior: 'smooth' });
  fetchOpportunities();
}

function updateMeta(total) {
  if (!total) { resultsMeta.textContent = 'No results found'; return; }
  const s = (state.page - 1) * state.perPage + 1;
  const e = Math.min(state.page * state.perPage, total);
  resultsMeta.textContent = `Showing ${s.toLocaleString()}–${e.toLocaleString()} of ${total.toLocaleString()} opportunities`;
}

/* ==========================================================================
   UI helpers
   ========================================================================== */
function showLoading(on) {
  loading.style.display = on ? 'block' : 'none';
  if (on) grid.innerHTML = '';
}

function showEmpty(msg = null) {
  emptyState.style.display = 'block';
  if (msg) $('emptyMsg').textContent = msg;
}

function toast(msg, level = 'info') {
  const colours = { info: '#1e293b', warn: '#d97706', error: '#dc2626' };
  const el = document.createElement('div');
  el.className = 'toast';
  el.style.background = colours[level] || colours.info;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3100);
}

function animateCount(id, target) {
  const el = $(id);
  if (!el || isNaN(target)) return;
  /* rAF doesn't fire in hidden/background tabs — set the value directly
     so stats never sit at "—" for someone who opened us in a new tab. */
  if (document.hidden) { el.textContent = target.toLocaleString(); return; }
  const start    = parseInt(el.textContent) || 0;
  const duration = 900;
  const t0       = performance.now();
  const tick = now => {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(start + (target - start) * eased).toLocaleString();
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* XSS-safe HTML escaping */
function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}
