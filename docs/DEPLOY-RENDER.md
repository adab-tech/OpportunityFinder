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

## Custom domain

In the Render web service → **Settings → Custom Domains** → add e.g. `finder.adamu.tech` and set the DNS record Render provides.

## Free tier notes

- The service **sleeps after ~15 min idle**; first visit may take 30–60s to wake.
- Free Postgres is suitable for early production; upgrade when you outgrow limits.

## Update the app

Push to `main` on GitHub — Render auto-deploys (`autoDeploy: true` in `render.yaml`).
