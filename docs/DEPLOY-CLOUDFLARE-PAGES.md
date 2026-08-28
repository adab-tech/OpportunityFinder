# Move the frontend to Cloudflare Pages (edge-served static assets)

Today, `globalopportunities.app` is a Cloudflare-proxied DNS record pointing
at the Render service, which serves both the API and the static frontend
(`frontend/`) from one Docker container. Every visitor's HTML/CSS/JS still
makes a round trip to Render's origin server (and can hit a cold start on
Render's free tier if it's been idle).

This moves the static frontend onto Cloudflare's edge network instead —
faster worldwide, and immune to Render cold-starts for anything that isn't
an API call — **without touching the backend or admin auth at all.**

## Why this approach specifically

The naive version of this move — point the frontend at a different domain
than the API — breaks admin login. `frontend/js/admin.js` sends every
request with `credentials: 'same-origin'`, and the session cookie
(`app/routes/admin_auth.py`) is `SameSite=Strict`. Both exist specifically
to reject cross-site requests; splitting the domains would require loosening
the cookie to `SameSite=None` and adding CSRF protection to compensate —
real security surface for what should be a pure infra change.

Instead, `frontend/_worker.js` + `frontend/_routes.json` make Cloudflare
Pages proxy `/api/*`, `/health`, `/docs`, `/openapi.json`, and `/redoc`
through to the Render backend server-side, while serving every other path
(`index.html`, `admin.html`, `css/`, `js/`, `robots.txt`, ...) directly from
Cloudflare's edge. From the browser's point of view it's still one origin —
**zero changes to cookies, `admin.js`, or `CORS_ORIGINS`.**

## Setup steps (Cloudflare dashboard)

1. **Workers & Pages → Create → Pages → Connect to Git.** Select the
   `adab-tech/OpportunityFinder` repo, branch `main`.
2. Build settings:
   - **Build command:** leave empty (no build step — this is a static,
     no-framework frontend by design).
   - **Build output directory:** `frontend`
   - **Root directory:** `/` (the repo root, so Pages can still see
     `frontend/_worker.js` and `frontend/_routes.json` at deploy time).
3. Pages auto-detects `_worker.js` in the output directory and runs it in
   **Advanced Mode** instead of the default static-only behavior — no extra
   toggle needed.
4. **Settings → Environment variables** on the Pages project: add
   `API_ORIGIN` = `https://adab-opportunityfinder.onrender.com` (or
   whatever the Render service's own `.onrender.com` URL is). The worker
   falls back to that same URL by default, so this is optional but makes
   the backend host changeable without a code deploy.
5. Deploy. Pages gives you a `*.pages.dev` URL first — verify there before
   touching DNS:
   - `https://<project>.pages.dev/` → the site loads normally
   - `https://<project>.pages.dev/health` → proxies through to Render,
     returns the same JSON the direct Render URL returns
   - `https://<project>.pages.dev/admin.html` → log in as admin and confirm
     the moderation queue loads (this is the real test of the cookie/CORS
     behavior above)

## DNS cutover

Once the `.pages.dev` URL checks out:

1. **Workers & Pages → your project → Custom domains → Add** →
   `globalopportunities.app` (and `www.globalopportunities.app`). Cloudflare
   handles the DNS change for you since the zone is already on Cloudflare —
   this replaces the current proxied `A` record pointing at Render's IP.
2. TLS is automatic (Cloudflare already terminates TLS for this zone).
3. This is reversible in minutes: if anything looks wrong, remove the
   custom domain from the Pages project and re-add the original `A`/`CNAME`
   record pointing back at Render — nothing about the Render service itself
   changes, so it's still serving the full app the whole time as a fallback.

## What does *not* change

- The Render service keeps running exactly as-is — same Docker image, same
  `render.yaml`, same env vars. It's now reached only via the Worker's
  server-to-server `fetch()` rather than directly by browsers, but nothing
  about its own code or config needs to change.
- `CORS_ORIGINS` can stay `*` — CORS only governs browser-initiated
  cross-origin requests, and after this move browsers never talk to Render
  directly.
- Admin auth, session cookies, and every `admin.js` fetch call are
  untouched.
