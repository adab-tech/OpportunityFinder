# Deploy on Render (recommended if Fly CLI fails)

No local CLI required — deploy from the Render dashboard in ~5 minutes.

## Steps

1. Create a free Postgres database at **[neon.tech](https://neon.tech)** (sign up, **New Project**, pick any region/name). Once it's created, copy the **connection string** Neon shows you (starts with `postgres://` or `postgresql://`) — you'll need it in step 6.
2. Open **[render.com](https://render.com)** and sign up with your **GitHub** account (`adab-tech`).
3. Click **New +** → **Blueprint**.
4. Connect repository **`adab-tech/OpportunityFinder`** (branch `main`).
5. Render reads `render.yaml` and proposes:
   - Web service: `adab-opportunityfinder`
6. Click **Apply** and wait for the first build (~5–10 min). Then go to the
   web service → **Settings → Environment** and add `DATABASE_URL`, pasting
   in the Neon connection string from step 1 (`render.yaml` no longer
   provisions a database itself, so this must be set manually — Render's
   Blueprint leaves it as `sync: false`). Redeploy after saving it.
7. When status is **Live**, open the URL Render shows, e.g.  
   **https://adab-opportunityfinder.onrender.com**

> **Why Neon instead of Render's own Postgres?** Render's **free** Postgres
> plan auto-deletes the database 30 days after creation — this is what
> caused a production outage here (the app failed to start with
> `could not translate host name "dpg-..." to address`, because Render had
> silently deleted `opportunityfinder-db`). Neon's free tier persists
> indefinitely — it only autosuspends compute when idle, it never deletes
> your data — so it's a safer fit for a long-lived free-tier deployment.

## Verify

- `https://<your-app>.onrender.com/health` → `"status":"healthy"`
- `https://<your-app>.onrender.com/` → OpportunityFinder UI

## Custom domain — globalopportunities.app

**This is no longer how the live domain is wired up.** `globalopportunities.app`
now points at a Cloudflare Worker that serves the frontend from the edge and
proxies API calls to this Render service — see
[DEPLOY-CLOUDFLARE-WORKERS.md](DEPLOY-CLOUDFLARE-WORKERS.md) for the actual
current setup. The steps below are kept for reference if you ever want to run
this backend standalone, pointed at directly by DNS instead of through the
Worker.

In the Render web service → **Settings → Custom Domains**, add both:

- `globalopportunities.app` (apex)
- `www.globalopportunities.app`

Render will show you the exact records to create at your domain registrar's DNS
settings. As of Render's current setup flow that's typically:

| Host | Type | Value |
|------|------|-------|
| `@` (apex) | `A` | the IP Render displays (or `ALIAS`/`ANAME` → the onrender.com hostname, if your registrar supports it) |
| `www` | `CNAME` | the `*.onrender.com` hostname Render displays for this service |

Use whatever Render actually shows on the Custom Domains page at add-time — it
occasionally changes the recommended record type. Render issues a free TLS
cert automatically once DNS verifies (can take a few minutes to a few hours
to propagate). Pick one of the two as primary and redirect the other to it
(Render's domain settings has a toggle for this) — `globalopportunities.app`
(apex) as primary is the natural choice here.

After the domain is live, set these env vars in Render (**Settings → Environment**)
so the app's own links point at the real domain instead of localhost:

| Variable | Value |
|----------|-------|
| `PUBLIC_BASE_URL` | `https://globalopportunities.app` |

(`CORS_ORIGINS` can stay `*` — the frontend is served from Cloudflare's edge
via a Worker that proxies API calls back to this service server-side, not by
the browser making cross-origin requests; see docs/DEPLOY-CLOUDFLARE-WORKERS.md.)

## Free tier notes

- The service **sleeps after ~15 min idle**; first visit may take 30–60s to wake.
- Neon's free Postgres tier also autosuspends compute when idle (a brief
  cold-start on the first query after a quiet period), but unlike Render's
  free Postgres it does not delete the database after 30 days — data
  persists indefinitely. Upgrade either tier when you outgrow its limits.

## Update the app

Push to `main` on GitHub — Render auto-deploys (`autoDeploy: true` in `render.yaml`).
