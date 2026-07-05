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
  - `migrations.py` — lightweight ALTER TABLE runner for columns added to existing tables (see below)
  - `routes/subscribers.py` — `/api/v1/saved`, `/api/v1/alerts` endpoints
  - `routes/analytics.py` — `/api/v1/analytics/event`, `/api/v1/analytics/summary`
- **Frontend:** static vanilla JS in `frontend/` (no build step), served by the API.
  `admin.html` + `js/admin.js` is a separate, unlisted (linked only from the footer) page for
  viewing analytics — protected by `ADMIN_API_KEY`, not by site navigation.
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

## Self-hosted visitor analytics

No third-party tracker, no cookies, no IP storage at the app layer — a
random `client_id` (crypto.randomUUID, generated client-side, stored in
localStorage) distinguishes repeat browsers from new ones in aggregate
counts only.

- `POST /api/v1/analytics/event` is public and never errors visibly to the
  browser — tracking must never break real usage. Fired from `app.js` on
  pageview, search, each filter type, save/apply clicks, and alert creation.
- `GET /api/v1/analytics/summary` requires header `X-Admin-Key` matching
  `settings.ADMIN_API_KEY`. **Unset by default — refuses ALL requests (503)
  until you configure it.** Set it in Render's environment to actually use
  `admin.html`.
- **`admin.html` is intentionally not linked from the public site** (no
  footer link, no nav entry) — this is serious software, not a hobby
  project, and a visible "Admin" link undercuts that. Reach it by typing
  the URL directly; it's still protected by `ADMIN_API_KEY` either way.

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
