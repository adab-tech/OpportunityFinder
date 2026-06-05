# Deploy OpportunityFinder

One domain, one container: FastAPI serves `/api/v1` and the static `frontend/` on the same origin (no CORS headaches).

## Option A — Docker Compose (local production test)

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```powershell
cd "C:\Users\Adamu\Desktop\Project 101"
docker compose up --build
```

Open **http://localhost:8000/** — Postgres runs in the `db` service; data persists in the `pgdata` volume.

Stop: `docker compose down` (add `-v` to wipe the database).

## Option B — Fly.io (public URL)

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) and run `fly auth login`.
2. From the repo root:

```powershell
fly launch --no-deploy
fly postgres create --name opportunityfinder-db --region lhr
fly postgres attach opportunityfinder-db
```

3. Set secrets (Fly sets `DATABASE_URL` when you attach Postgres):

```powershell
fly secrets set ENABLE_SCHEDULER=true
# Optional Google CSE:
# fly secrets set GOOGLE_API_KEY=... GOOGLE_CSE_ID=...
```

4. Deploy:

```powershell
fly deploy
```

5. Open the app: `fly open`

### Custom domain on Fly

```powershell
fly certs add finder.yourdomain.com
```

Point DNS (CNAME) to the hostname Fly prints. HTTPS is automatic.

## Option C — Railway / Render

1. Create a **PostgreSQL** database on the platform.
2. Deploy from this GitHub repo (`adab-tech/OpportunityFinder`) with:
   - **Build:** Dockerfile at repo root
   - **Start:** handled by Dockerfile (`PORT` is set by the platform)
3. Environment variables:

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | Postgres URL from the provider (use `postgresql+psycopg2://...` if needed) |
| `ENABLE_SCHEDULER` | `true` (only on **one** instance if you scale horizontally) |
| `CORS_ORIGINS` | `*` or your static site origin if split later |

## Split frontend later (optional)

By default the UI uses same-origin `/api/v1`. To host the UI on GitHub Pages and API elsewhere, set in `frontend/config.js` before deploy:

```javascript
window.OPPORTUNITYFINDER_API_BASE = 'https://your-api.fly.dev/api/v1';
```

And set `CORS_ORIGINS` on the API to your Pages URL.

## Environment reference

Copy `backend/.env.example` to `backend/.env` for local dev.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite locally; Postgres in production |
| `ENABLE_SCHEDULER` | Background RSS + scrape jobs |
| `CORS_ORIGINS` | Comma-separated origins, or `*` |
| `PORT` | Set by Fly/Railway/Render (uvicorn listens here) |
| `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` | Optional; improves discovery |

## Health check

- `GET /health` — returns `database: ok` when Postgres/SQLite is reachable.
- `GET /docs` — OpenAPI UI.

## What runs on startup

1. DB tables created if missing.
2. Curated seeds if the database is empty.
3. RSS ingest from stable feeds (ReliefWeb, Scholars4Dev, Opportunity Desk, etc.).
4. Background scrape if fewer than ~25 active listings.
5. Scheduler (every 6h by default) if `ENABLE_SCHEDULER=true`.

## Next steps (product)

- Register a domain (e.g. `opportunityfinder.app` or `finder.adamu.tech`).
- Add email alerts (Resend + saved searches).
- Add Meilisearch for faster full-text search at scale.
