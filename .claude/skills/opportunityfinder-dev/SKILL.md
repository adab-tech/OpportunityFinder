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
  - `routes/subscribers.py` — `/api/v1/saved`, `/api/v1/alerts` endpoints
- **Frontend:** static vanilla JS in `frontend/` (no build step), served by the API
- **DB:** SQLite locally, Postgres in production via `DATABASE_URL`

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
