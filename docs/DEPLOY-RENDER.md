# Deploy on Render (recommended if Fly CLI fails)

No local CLI required — deploy from the Render dashboard in ~5 minutes.

## Steps

1. Open **[render.com](https://render.com)** and sign up with your **GitHub** account (`adab-tech`).
2. Click **New +** → **Blueprint**.
3. Connect repository **`adab-tech/OpportunityFinder`** (branch `main`).
4. Render reads `render.yaml` and proposes:
   - Web service: `adab-opportunityfinder`
   - Postgres: `opportunityfinder-db`
5. Click **Apply** and wait for the first build (~5–10 min).
6. When status is **Live**, open the URL Render shows, e.g.  
   **https://adab-opportunityfinder.onrender.com**

## Verify

- `https://<your-app>.onrender.com/health` → `"status":"healthy"`
- `https://<your-app>.onrender.com/` → OpportunityFinder UI

## Custom domain — globalopportunities.app

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

(`CORS_ORIGINS` can stay `*` — the frontend is served same-origin from this
same service, so it isn't relying on cross-origin CORS.)

## Free tier notes

- The service **sleeps after ~15 min idle**; first visit may take 30–60s to wake.
- Free Postgres is suitable for early production; upgrade when you outgrow limits.

## Update the app

Push to `main` on GitHub — Render auto-deploys (`autoDeploy: true` in `render.yaml`).
