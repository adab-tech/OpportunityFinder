# Global Opportunities

Global Opportunities is an AI-assisted discovery site for scholarships, fellowships, grants, and jobs — plain-English summaries, real deadlines, refreshed automatically.

**Live:** https://globalopportunities.app

## Architecture

- `backend/` — FastAPI API, Postgres (via [Neon](https://neon.tech)), scraping/RSS ingest, and scheduled refresh jobs. Deployed on [Render](https://render.com).
- `frontend/` — static UI, no build step, served from Cloudflare's edge via a Worker (`worker/index.js` + `wrangler.jsonc`). The same worker proxies `/api/*`, `/health`, `/docs`, `/openapi.json`, and `/redoc` to the Render backend, so the browser only ever sees one origin.
- `admin.html` — analytics + a moderation queue, gated behind email/password admin login (`app/routes/admin_auth.py`).

See [docs/DEPLOY-RENDER.md](docs/DEPLOY-RENDER.md) and [docs/DEPLOY-CLOUDFLARE-WORKERS.md](docs/DEPLOY-CLOUDFLARE-WORKERS.md) for the full deploy story, and [docs/DEPLOY.md](docs/DEPLOY.md) for local development and Docker.

## Local development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Copy `backend/.env.example` to `backend/.env` first. With nothing else set, the app runs on SQLite and logs alert/save-confirmation emails to the console instead of sending them.

### Frontend

Serve `frontend/` with any static web server; it talks to the API at the same origin (`/api/v1`) by default. To point it at a separately-hosted backend, set `window.OPPORTUNITYFINDER_API_BASE` in `frontend/config.js`.

### Windows quick start

Double-click `start.bat` — creates a venv, installs backend dependencies, and opens the app at http://127.0.0.1:8000/. Local only, not how production runs.

## Optional discovery API keys

`backend/.env.example` documents `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` (Google Custom Search) and `YOU_API_KEY` (You.com) — both optional. Without them, the scraper falls back to public search scraping.

## Email alerts

Alert and save-confirmation emails are logged to the console by default — no provider required to run or test the feature end-to-end. Set `RESEND_API_KEY`, `BREVO_API_KEY`, or `SENDGRID_API_KEY` to send them for real; see `backend/app/services/email_sender.py`.

## Tests

```powershell
cd backend && python -m pytest tests -v
cd frontend && npm test
```

CI (`.github/workflows/ci.yml`) runs both suites plus `ruff` lint on every push/PR to `main`.
