# Deploy Global Opportunities

Production is two pieces: the **backend** (FastAPI + Postgres) on Render, and the **frontend** (static, no build step) on Cloudflare Workers at the edge, which proxies API calls back to Render so the browser only ever sees one origin. See:

- [DEPLOY-RENDER.md](DEPLOY-RENDER.md) — backend + database, from zero to a live URL
- [DEPLOY-CLOUDFLARE-WORKERS.md](DEPLOY-CLOUDFLARE-WORKERS.md) — moving the frontend to the edge and wiring up the custom domain

This doc covers local development only.

## Docker Compose (local, with Postgres)

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```
docker compose up --build
```

Open **http://localhost:8000/** — Postgres runs in the `db` service; data persists in the `pgdata` volume.

Stop: `docker compose down` (add `-v` to wipe the database).

## Environment reference

Copy `backend/.env.example` to `backend/.env` for local dev. Full definitions live in `backend/app/config.py`; highlights:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite locally; Postgres in production. Prefer [Neon](https://neon.tech)'s free tier over a platform's own free Postgres (e.g. Render) — Render's free Postgres auto-deletes the database 30 days after creation, which has already caused a production outage; Neon's free tier only autosuspends compute when idle and never deletes data. |
| `ENABLE_SCHEDULER` | Background RSS + scrape jobs — set `true` on exactly one instance if you scale horizontally. |
| `CORS_ORIGINS` | Comma-separated origins, or `*`. |
| `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` / `YOU_API_KEY` | Optional; improve discovery beyond the scraping fallback. |
| `RESEND_API_KEY` / `BREVO_API_KEY` / `SENDGRID_API_KEY` | Optional; unset means alert/save-confirmation emails are logged, not sent. If more than one is set, Resend takes priority, then Brevo. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` / `SESSION_SECRET_KEY` | Required together for admin login (analytics + moderation queue). Generate the hash with `backend/scripts/hash_admin_password.py`. Unset means admin endpoints refuse every request. |
| `ADMIN_TOTP_SECRET` | Optional second factor on top of the admin password. Unset (default) means login stays password-only; set it to also require a 6-digit authenticator code. Generate with `backend/scripts/generate_admin_totp_secret.py`. |
| `PUBLIC_BASE_URL` | Builds the manage-your-alerts link in outgoing emails; set to your real domain in production. |

## Health check

- `GET /health` — returns `database: ok` when Postgres/SQLite is reachable.
- `GET /docs` — OpenAPI UI.

## What runs on startup

1. DB tables created if missing.
2. Curated seeds if the database is empty.
3. RSS ingest from stable feeds (ReliefWeb, Scholars4Dev, Opportunity Desk, and more).
4. Background scrape if fewer than ~25 active listings.
5. Scheduler (every 6h by default) if `ENABLE_SCHEDULER=true`.
