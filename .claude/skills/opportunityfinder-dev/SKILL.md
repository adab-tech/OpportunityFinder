---
name: opportunityfinder-dev
description: OpportunityFinder development workflow — run, test, lint, verify security invariants, and deploy the FastAPI opportunity-discovery app. Use when working on the OpportunityFinder repo (Desktop\Project 101).
version: 1.0.0
---

# OpportunityFinder Dev Workflow (Skills 1.0)

## What this project is

AI-assisted opportunity discovery app: scrapes/ingests scholarships, fellowships,
grants, and jobs, stores them in SQL, and serves them through a FastAPI API plus
a static frontend on the same origin.

- **Repo:** github.com/adab-tech/OpportunityFinder — local folder is `Desktop\Project 101` (name mismatch is intentional)
- **Backend:** FastAPI + SQLAlchemy 2 + APScheduler in `backend/app/`
  - `main.py` — app factory, CORS, health, static-file catch-all
  - `routes/` — opportunities API + scraper trigger
  - `scrapers/` — BaseScraper (polite HTTP), GoogleScraper, OpportunityScraper orchestrator, RSS ingest,
    `url_utils.clean_url`, `deadline_utils.extract_deadline` (shared by scraper + RSS paths — see invariant below)
  - `ingest/rss_feeds.py` — curated feed list (preferred production data source)
  - `bootstrap.py` — curated seeds + first-run background ingest
  - `services/subscribers.py` — saved opportunities + email alerts (no-password: email + manage_token)
  - `services/email_sender.py` — pluggable email delivery (see below)
  - `services/analytics.py` — self-hosted visitor analytics (see below)
  - `scrapers/synopsis.py` — original one-line synopsis generator (rule-based, no LLM)
  - `scrapers/deadline_utils.py` — deadline text extraction + `parse_deadline_date` (structured date)
  - `scrapers/dedup.py` — `normalize_title` for cross-source duplicate detection (see below)
  - `scrapers/expiry.py` — `is_expired` / `is_stale_by_title`: a passed deadline (or, absent
    one, a stale year baked into the title) must never be shown (see below)
  - `services/maintenance.py` — daily sweep deactivating opportunities that expire after ingest
  - `scrapers/google_scraper.py` — web search discovery, tiered: Google CSE API →
    You.com Search API → googlesearch-python scrape → raw HTTP fallback (see below)
  - `migrations.py` — lightweight ALTER TABLE runner for columns added to existing tables (see below)
  - `routes/subscribers.py` — `/api/v1/saved`, `/api/v1/alerts` endpoints
  - `routes/analytics.py` — `/api/v1/analytics/event`, `/api/v1/analytics/summary`
- **Frontend:** static vanilla JS in `frontend/` (no build step), served by the API.
  `admin.html` + `js/admin.js` is a separate, unlisted (not linked from the public site) page
  for the analytics summary and moderation queue — protected by a real admin login
  (email + password, see below), not by site navigation.
- **DB:** SQLite locally, Postgres in production via `DATABASE_URL`

## Schema migrations (no Alembic — by design, for now)

`Base.metadata.create_all()` only creates tables that don't exist yet; it never
adds a column to a table that's already there. `app/migrations.py` handles this
for the handful of additive columns this project has needed (`summary`,
`deadline_at` on `opportunities`) via a simple idempotent `ALTER TABLE ADD
COLUMN`, run at startup right after `create_all()` in `main.py`'s lifespan.

**Whenever you add a column to an existing model**, add a row to
`_PENDING_COLUMNS` in `migrations.py` too, or the deployed app will break with
"no such column" the moment it tries to read/write that field — `create_all()`
silently does nothing for a table that already exists. If the schema keeps
growing, this is the point to switch to Alembic instead of extending this list
further.

## Data quality: original synopses & structured deadlines

- **`summary`** (`scrapers/synopsis.py`, `build_synopsis`) is a rule-based,
  free, no-external-API sentence generated from already-parsed fields
  (type/field/location/deadline/funding amount) — deliberately not an
  LLM call, to keep this sustainable (no per-request cost, no API key,
  no external dependency that can take the ingest pipeline down). The
  frontend renders `summary` in preference to the raw scraped
  `description`. If AI-generated summaries are wanted later, swap the
  implementation inside `build_synopsis` — every caller already treats
  it as compute-once-at-ingest-time.
- **`deadline_at`** (`deadline_utils.parse_deadline_date`, via `python-dateutil`)
  is a real date parsed from the free-text `deadline` field, so the frontend
  can compute "3 days left" / "Deadline passed" instead of making people read
  a date and do the math (see `app.js`'s `deadlineBadge`). Null when the
  deadline is "Rolling" or unparseable — the frontend falls back to "Check
  listing for deadline" rather than guessing.
- Backfill scripts for existing rows (same dry-run/`--apply` pattern as
  `reclassify_opportunities.py`): `scripts/backfill_deadlines.py` and
  `scripts/backfill_summary_and_deadline_at.py`.
- **`build_synopsis` prefers real substance over restating fields already
  shown as badges.** Type/field/location are already visible as tags, and
  deadline is already its own countdown badge — a synopsis that just
  reconstructs those into a sentence ("A grant in International
  Development open to applicants in Africa worth $12,000. Deadline: 19
  January 2018.") is redundant, and reads as generic because it *is*
  generic. `extract_meaningful_sentence` pulls the first substantive,
  non-boilerplate sentence from the actual scraped description instead
  (stripping "Applications are now open for...", WordPress's "The post X
  appeared first on Y" footer, and a leading deadline restatement). The
  structured-fields sentence is only a fallback for when no usable
  description text exists at all, and it never restates the deadline.
  Regression tests: `tests/test_synopsis.py`.

## Web search discovery (Google CSE / You.com / scraping fallback)

`GoogleScraper.search()` tries sources in order, using whichever is configured:

1. **Google Custom Search JSON API** — `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` (100 free/day)
2. **You.com Web Search API** — `YOU_API_KEY` only. Endpoint `https://ydc-index.io/v1/search`
   (GET), header `X-API-Key`, param `count` (max 100). Response shape confirmed against
   You.com's real published docs (2026-07-05):
   `{"results": {"web": [{"url": ...}], "news": [{"url": ...}]}}` — **`web` only,
   `news` is deliberately dropped.** `news` was tried first and turned out to be the
   dominant source of off-topic pollution (sports scores, local council stories, game
   patch notes) — You.com's news classifier fires on generic words like "grant" and
   "deadline" regardless of context. **Pricing: $5.00/1,000 calls** (not free-tier
   like Google's 100/day — new accounts get $100 in credit, ~20k calls, but it's
   metered after that).
3. **googlesearch-python** (unofficial scrape, no key)
4. **Direct HTTP to google.com** (last resort)

All three unofficial/official tiers fail closed (return `[]` on any error) so a
misconfigured or down API never crashes a scrape run — it just falls through to
the next tier. Regression tests: `tests/test_google_scraper.py`.

## Content-quality filtering (`scrapers/quality.py`)

Broader web/You.com search discovery still surfaces junk even after the `news`-drop
fix above: page-navigation chrome ("Breadcrumb", "Quick Links"), listicle/roundup
articles ("50+ Scholarships for College Students"), past-tense "who already won"
announcements, and off-topic content that slips through `web` results (sports
trades, gaming patch notes, local politics, markets news) because a generic word
in the story happens to match the search query.

`is_low_quality_title()` is called in both `_save()` methods (`opportunity_scraper.py`,
`rss_ingest.py`) before insert — a title that fails the check is never saved, no
matter which discovery path found it.

**Important design lesson (2026-07-05):** an earlier version of this filter also
*required* the title to contain scholarship/grant/fellowship vocabulary to be
accepted. That was wrong and cost far more than it saved — validated against the
live dataset, it silently killed real, specific, well-known programs that just
don't repeat that vocabulary in their title (Fulbright Foreign Student Program,
Erasmus Mundus Joint Masters, NSF CAREER, Google Africa Applied AI Lab, named
foundation grants, real job postings). Relevance for a scraped/searched title is
already established by ingest context (a curated feed or a targeted search query),
not by the title's own wording — don't reintroduce a positive-vocabulary gate.
Off-topic content is instead caught by concrete negative signals (`_OFF_TOPIC_SIGNALS`)
built from real examples, not a vocabulary whitelist.

Biased toward false negatives over false positives, same principle as expiry
detection above: letting a handful of low-value pages through is far better than
rejecting a real listing. Backfill for rows already live before this existed:
`scripts/backfill_quality.py` (dry-run/`--apply`, same pattern as the other repair
scripts). Regression tests: `tests/test_quality.py`, `tests/test_backfill_quality.py`.

## Moderation gate — open web-search discovery is never auto-published

Two trust tiers, enforced by `Opportunity.review_status` (`"approved" | "pending" | "rejected"`):

1. **Curated RSS feeds** (`scrapers/rss_ingest.py`, a fixed vetted source list in
   `app/ingest/rss_feeds.py`) — pre-vetted, so `_save()` sets `review_status="approved"`
   explicitly and content keeps auto-publishing as before.
2. **Open web-search discovery** (`scrapers/opportunity_scraper.py`, the
   Google CSE/You.com/scrape pipeline) — low-trust by nature (see the You.com
   `news`-pollution incident above): quality filtering alone isn't enough, a
   human must approve each row before it's public. `_save()` sets
   `review_status="pending"` on every insert; nothing here goes live automatically.

`routes/opportunities.py::_public_visible()` filters `review_status == "approved"`
on every public read (list, stats, single lookup) — same hard-requirement
posture as the expiry check below: independent of `is_active`, applied
everywhere, no exceptions.

Admin review happens in `routes/moderation.py` (same admin session-cookie
gate as `routes/analytics.py` — see "Admin login" below): `GET /admin/moderation/pending` (paginated,
oldest first), `POST /{id}/approve`, `POST /{id}/reject` (also sets
`is_active=False`, row kept for audit/dedup — never deleted), `POST /bulk-approve`
with `{"ids": [...]}`. The admin UI lives in `frontend/admin.html` +
`frontend/js/admin.js`, in its own always-shown `#modSection` (deliberately
independent of the analytics section so one failing doesn't hide the other).

Existing rows never disappear when this shipped: the migration's
`DEFAULT 'approved'` backfills every pre-existing row automatically.
Safety-net override tool: `scripts/backfill_review_status.py` (dry-run/`--apply`,
`--set-approved`/`--set-pending` scoped by `--source`/`--type`). Regression
tests: `tests/test_moderation.py`, `tests/test_backfill_review_status.py`.

## Expired opportunities must NEVER show — hard requirement, not best-effort

An opportunity past its deadline showing on the site is a trust-breaking bug,
not a minor issue (explicit, emphatic user requirement, 2026-07-05). Three
layers enforce this, deliberately redundant so no single gap lets one through:

1. **Query-level guarantee** — `routes/opportunities.py`'s `_not_expired()`
   filters every public read (`list`, `stats`, single-item lookup) on
   `deadline_at IS NULL OR deadline_at >= today`. This is the real
   guarantee — it holds even if `is_active` is stale for any reason.
2. **Ingest-time check** — `scrapers/expiry.is_expired()` is called in every
   `_save()` (RSS, scraper) before insert; a listing that's already expired
   (past `deadline_at`, or no parseable deadline but a stale year in the
   title, e.g. "...Recruitment 2019") is inserted with `is_active=False`
   from the start, never `True`.
3. **Daily sweep** — `services/maintenance.deactivate_expired_opportunities`
   runs every 24h via the scheduler, keeping `is_active` accurate for rows
   whose deadline passes *after* ingestion (so the alert digest and other
   `is_active`-based consumers stay correct, not just the public listing).

The title-year heuristic (`is_stale_by_title`) only fires on an *explicit*
past year in the title — never on a yearless title (can't confirm, so it's
left alone) — false negatives (a stale post slips through undetected) are
far preferable to false positives (hiding something genuinely open).

Backfill for rows already live before this existed:
`scripts/backfill_expiry.py` (dry-run/`--apply`, same pattern as the other
repair scripts). Regression tests: `tests/test_expiry.py`,
`tests/test_expired_never_shown.py`, `tests/test_maintenance.py`.

## Admin login (real email/password, replaced the shared key — 2026-07-05)

`admin.html` used to be gated by a single shared secret pasted into a
password box (`X-Admin-Key` / `ADMIN_API_KEY`). That's gone — admin auth
is now a real account: `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH` (env vars),
checked at `POST /api/v1/admin/login` (`routes/admin_auth.py`), which sets
a signed, httpOnly, `SameSite=Strict` session cookie (`of_admin_session`,
12h expiry) on success. `GET /api/v1/admin/session` lets the page silently
check "am I still logged in" on load; `POST /api/v1/admin/logout` clears
the cookie.

- **Password hashing:** PBKDF2-HMAC-SHA256, 600k iterations, stdlib-only
  (`app/security.py`, no new dependency) — never store the plaintext
  password anywhere. Generate `ADMIN_PASSWORD_HASH` once with
  `scripts/hash_admin_password.py` (prompts for the password, prints only
  the hash) and paste it into Render's env vars alongside `ADMIN_EMAIL`
  and a random `SESSION_SECRET_KEY` (`secrets.token_hex(32)`).
- **Session tokens** are a simple `<expiry>.<hmac>` string signed with
  `SESSION_SECRET_KEY` — not a JWT, deliberately, since there's exactly
  one claim ("an admin is logged in until this timestamp") and a full JWT
  library would be unused complexity for a single-admin account.
- **Fails closed**: any of `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH`/
  `SESSION_SECRET_KEY` unset means `/login` returns 503 and every
  protected endpoint (`analytics.summary`, all of `routes/moderation.py`)
  refuses every request via the shared `require_admin_session` dependency.
- **Single admin by design** — this project has one operator today. A real
  accounts table with roles is a reasonable future upgrade if/when there's
  a team, not before (explicit user decision, 2026-07-05).
- `SESSION_COOKIE_SECURE` (default `true`) must be set to `false` for local
  http:// dev — browsers silently refuse to store a `Secure` cookie over
  plain HTTP.

## Self-hosted visitor analytics

No third-party tracker, no cookies, no IP storage at the app layer — a
random `client_id` (crypto.randomUUID, generated client-side, stored in
localStorage) distinguishes repeat browsers from new ones in aggregate
counts only. (This is the *visitor-facing* analytics identifier — unrelated
to the admin session cookie above, which identifies the one operator, not
site visitors.)

- `POST /api/v1/analytics/event` is public and never errors visibly to the
  browser — tracking must never break real usage. Fired from `app.js` on
  pageview, search, each filter type, save/apply clicks, and alert creation.
- `GET /api/v1/analytics/summary` requires a valid admin session (see
  "Admin login" above). **Unset config — refuses ALL requests (503) until
  you configure it.**
- `GET /api/v1/analytics/trends?days=7|30|90` (same auth) returns daily
  pageview/search/apply-click counts for the admin trends chart
  (`services/analytics.get_daily_trends`) — missing days are filled with
  zeros so the chart has no gaps. Rendered as a hand-rolled SVG line
  chart in `admin.js` (`renderTrendsChart`) — no charting library, same
  minimal-dependency posture as the rest of this frontend.
- **`admin.html` is intentionally not linked from the public site** (no
  footer link, no nav entry) — this is serious software, not a hobby
  project, and a visible "Admin" link undercuts that. Reach it by typing
  the URL directly; it's still protected by admin login either way.

## Admin listing management (`routes/admin_listings.py`)

Unlike `routes/moderation.py` (only the pending-review queue),
`/api/v1/admin/opportunities/` exposes and lets you edit **every**
opportunity regardless of `is_active`/`review_status` — once something
is live, an admin can still correct a field or pull it down.

- `GET /admin/opportunities/?search=&opportunity_type=&page=&per_page=` —
  deliberately unfiltered (unlike the public listing's `_public_visible`),
  since an admin needs to see everything to fix it.
- `PATCH /admin/opportunities/{id}` — partial update
  (`AdminOpportunityUpdate` schema, all fields optional); if `title`
  changes, `title_normalized` is recomputed too so a corrected title
  still matches future reposts of the same opportunity from another
  aggregator (see "Cross-source duplicate detection" below).
- `POST /admin/opportunities/{id}/deactivate` / `/reactivate` — quick
  toggle, doesn't require opening the full edit form.
- Frontend: "All listings" section in `admin.html`/`admin.js` — search +
  type filter, paginated table, Edit opens a modal
  (`openEditModal`/`onEditSubmit`), Deactivate/Reactivate is one click.
  Same admin session gate as everything else on this page.

Regression tests: `tests/test_admin_listings.py`.

## Cross-source duplicate detection

The same opportunity is frequently reposted verbatim by two different
aggregator feeds under different URLs — `Opportunity.title_normalized`
(lowercased, punctuation-stripped, whitespace-collapsed, via
`scrapers/dedup.normalize_title`) is checked against active rows before
every save in both `rss_ingest.py` and `opportunity_scraper.py`; a match
is skipped and counted in `stats["duplicates"]`, not inserted.
**Deliberately exact-match, not fuzzy** — year digits are kept in the
normalized title on purpose, since a 2026 cohort and a 2027 cohort of the
same program are genuinely different opportunities and fuzzy matching
risked merging them. `scripts/backfill_dedup.py` (dry-run/`--apply`)
backfills `title_normalized` on existing rows and deactivates (never
deletes) already-ingested duplicate groups, keeping the earliest-seen row.

## Deadline reminders for saved opportunities

`services/subscribers.run_saved_deadline_reminders` emails each
`SavedOpportunity` once when its `Opportunity.deadline_at` falls within
`SAVED_REMINDER_DAYS_BEFORE` (default 3) days and hasn't already passed —
tracked via `SavedOpportunity.reminder_sent_at` so it never repeats. Runs
on `scheduler.py`'s `saved_deadline_reminders` job every
`SAVED_REMINDER_INTERVAL_HOURS` (default 24h). This exists because saving
an opportunity shouldn't silently rely on the person remembering to check
back before it's due.

## SEO

- `index.html` head: OG/Twitter cards, canonical URL, JSON-LD `WebSite` schema, keyword-rich
  meta description, inline SVG favicon (no binary asset needed). Canonical/OG URLs are
  hardcoded to `https://adab-opportunityfinder.onrender.com/` — update them if the domain changes.
- `frontend/robots.txt` and `frontend/sitemap.xml` are served automatically by the existing
  static-file catch-all in `main.py` (no route changes needed) — just edit the files directly.
- **Scraper search queries must never hardcode a year.** `app/scrapers/keywords.py`
  templates use `{year}`, expanded to the current year *and* next year at query-build
  time (`build_google_queries`) — a literal "2026" would silently go stale once 2027
  arrives, since program pages label themselves by intake year. Regression test:
  `tests/test_keyword_queries.py::test_no_hardcoded_year_leaks_into_output`.

## Saved opportunities & email alerts (no-password)

Users are identified only by email — no login/password. Every management
action (viewing saved items, deleting an alert) goes through an unguessable
`manage_token` on the `Subscriber` row, emailed to them after signup.

- **Email delivery is pluggable** (`app/services/email_sender.py`):
  `ConsoleEmailSender` (default) just logs the email — the whole feature
  works end-to-end with zero setup, readable in server logs. Set
  `RESEND_API_KEY` to switch to real delivery via Resend, no code changes.
- **`PUBLIC_BASE_URL`** builds the manage link in emails. Left `None` by
  default so it's derived from the actual `API_PORT` in local dev
  (`Settings.public_base_url()`) — always set it explicitly in production
  (e.g. your Render URL), otherwise manage links will point at localhost.
- **Weekly digest**: `scheduler.py` runs `run_alert_digest()` on
  `ALERT_DIGEST_INTERVAL_HOURS` (default 168h/weekly) — matches each
  `AlertSubscription`'s filters against opportunities ingested since
  `last_notified_at`.
- When testing this in a browser (preview tools, manual QA): **browser
  autofill can silently substitute a real saved email into an email input**
  even when you set the value programmatically — verify the actual
  submitted email server-side (check logs/DB), don't trust that the field
  you filled is what got submitted. Don't add `autocomplete="off"` to fix
  this — autofill is a genuine convenience for this exact "just enter your
  email" flow; the fix is to test more carefully, not to degrade real UX.

## Daily commands (Windows, from repo root)

```powershell
# Run tests + lint (venv already at backend\.venv, Python 3.14)
cd backend
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe -m ruff check .        # add --fix for autofix

# Run the app
.\.venv\Scripts\python.exe run.py                  # dev reload on :8000
# or: double-click start.bat in repo root
```

Dev deps live in `backend/requirements-dev.txt` (pytest, ruff). Prod deps in
`backend/requirements.txt` — pytest must NOT be added there.

## Security invariants (do not regress)

1. **Static file containment** — the catch-all route in `main.py` must resolve
   candidates and confine them to `frontend/` (`candidate.relative_to(FRONTEND_DIR)`).
   The repo root contains personal documents; a traversal bug here leaks them.
   Regression tests: `tests/test_security.py::TestStaticFileContainment`.
2. **URL sanitisation** — every ingest path (scraper `_save`, RSS `_save`) must go
   through `app/scrapers/url_utils.clean_url` (http/https only). This blocks stored-XSS
   via `javascript:` links. Frontend `cardHTML` also guards `safeUrl`.
3. **Personal documents** — were moved out of the repo root on 2026-07-04 to
   `C:\Users\Adamu\Documents\OpportunityFinder-Personal-Docs-Removed` (never
   tracked by git; history confirmed clean). Never save personal files into
   this repo folder again — it's meant to be pure project code.
4. **Scrape lock** — `routes/scraper.py` uses a non-blocking `threading.Lock`;
   keep check-and-set atomic.
5. **Feed type correctness** — a multi-category source (scholarships +
   fellowships + grants + jobs all on one site) must NEVER get one hardcoded
   `opportunity_type` in `app/ingest/rss_feeds.py`. Use per-category feed URLs
   when the site publishes them (guaranteed-correct type), or `"mixed"` to
   trigger per-entry classification via `keywords.detect_opportunity_type`.
   This exact bug mislabeled real opportunities in production once already
   (fixed 2026-07-04) — see `backend/scripts/reclassify_opportunities.py` for
   the one-time repair tool and rerun it (dry-run first!) if a similar
   misconfiguration is ever suspected again.
6. **Deadline extraction must run on every ingest path.** `extract_deadline`
   (in `deadline_utils.py`) is called from both `base_scraper.py` (scraper
   pipeline) and `rss_ingest.py` (RSS pipeline). It was missing from RSS
   entirely until 2026-07-04, silently leaving `deadline: null` on the
   majority of production data despite descriptions clearly stating one.
   If you add a new ingest path, it must call `extract_deadline` too.
   See `backend/scripts/backfill_deadlines.py` to repair existing null
   deadlines (dry-run first).
7. **CORS** — wildcard origins must keep `allow_credentials=False` (see `main.py`).

## Testing rules

- `tests/conftest.py` redirects `DATABASE_URL` to a temp SQLite file **before**
  app imports — never remove that ordering (E402 is ignored for this reason).
- Tests must never touch `backend/opportunities.db` (the dev database).
- New ingest features need a regression test that hostile URLs are rejected.

## Deploy

- **Render** (no CLI): docs/DEPLOY-RENDER.md
- **Fly.io**: `scripts/deploy-fly.ps1` (app `adab-opportunityfinder`, region lhr);
  needs `flyctl auth login` or `FLY_API_TOKEN`
- **Docker local**: `docker compose up --build` (Postgres + API)
- `/health` returns 503 when the DB is down — platform health checks rely on this.
- Container runs as non-root `appuser`; keep it that way.

## CI

`.github/workflows/ci.yml`: ruff check + full pytest on push/PR to main.
Keep `cache-dependency-path` pointed at `requirements-dev.txt`.
