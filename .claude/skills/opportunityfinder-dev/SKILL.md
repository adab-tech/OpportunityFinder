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
  - `scrapers/` — BaseScraper (polite HTTP), GoogleScraper, OpportunityScraper orchestrator, RSS ingest, `url_utils.clean_url`
  - `ingest/rss_feeds.py` — curated feed list (preferred production data source)
  - `bootstrap.py` — curated seeds + first-run background ingest
- **Frontend:** static vanilla JS in `frontend/` (no build step), served by the API
- **DB:** SQLite locally, Postgres in production via `DATABASE_URL`

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
5. **CORS** — wildcard origins must keep `allow_credentials=False` (see `main.py`).

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
