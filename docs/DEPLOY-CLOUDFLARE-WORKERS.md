# Move the frontend to Cloudflare Workers (edge-served static assets)

Today, `globalopportunities.app` is a Cloudflare-proxied DNS record pointing
at the Render service, which serves both the API and the static frontend
(`frontend/`) from one Docker container. Every visitor's HTML/CSS/JS still
makes a round trip to Render's origin server (and can hit a cold start on
Render's free tier if it's been idle).

This moves the static frontend onto Cloudflare's edge network instead —
faster worldwide, and immune to Render cold-starts for anything that isn't
an API call — **without touching the backend or admin auth at all.**

> **Why "Workers" and not "Pages"?** Cloudflare's own current guidance:
> "If you are starting a new project, use Workers instead of Pages. Pages
> continues to work, but new features and optimizations are focused on
> Workers." Since nothing has been deployed yet, this repo targets Workers
> with static assets directly rather than building on the product
> Cloudflare is de-emphasizing.

## Why a worker script at all

The naive version of this move — point the frontend at a different domain
than the API — breaks admin login. `frontend/js/admin.js` sends every
request with `credentials: 'same-origin'`, and the session cookie
(`app/routes/admin_auth.py`) is `SameSite=Strict`. Both exist specifically
to reject cross-site requests; splitting the domains would require loosening
the cookie to `SameSite=None` and adding CSRF protection to compensate —
real security surface for what should be a pure infra change.

Instead, `worker/index.js` + `wrangler.jsonc`'s `assets` binding make
Cloudflare serve every static file (`index.html`, `admin.html`, `css/`,
`js/`, `robots.txt`, ...) directly from the edge, and only fall through to
`worker/index.js` for paths with no matching file — which, by construction,
is exactly `/api/*`, `/health`, `/docs`, `/openapi.json`, and `/redoc`. The
worker proxies those server-side to the Render backend. From the browser's
point of view it's still one origin — **zero changes to cookies,
`admin.js`, or `CORS_ORIGINS`.**

## Setup

### Option A — CLI (`wrangler`), fastest

1. `npx wrangler login` (or set a `CLOUDFLARE_API_TOKEN` env var scoped to
   **Account → Workers Scripts → Edit** and, for the custom-domain step
   below, **Zone → DNS → Edit** on the `globalopportunities.app` zone).
2. From the repo root: `npx wrangler deploy --dry-run` to validate
   `wrangler.jsonc` without publishing anything, then `npx wrangler deploy`
   to actually publish. This creates the Worker (`global-opportunities`)
   and uploads `frontend/` as its static assets in one operation.
3. Wrangler prints a `*.workers.dev` URL — verify there before touching DNS
   (see **Verify** below).
4. Custom domain: `npx wrangler deploy` again after adding a `routes` entry
   to `wrangler.jsonc`, e.g.:
   ```jsonc
   "routes": [
     { "pattern": "globalopportunities.app", "custom_domain": true },
     { "pattern": "www.globalopportunities.app", "custom_domain": true }
   ]
   ```
   Cloudflare handles the DNS change itself since the zone is already on
   Cloudflare.

### Option B — Dashboard

1. **Workers & Pages** (may appear simply as **Workers**, or under a
   **Compute** section — it's an account-level item, not inside the
   domain/zone view) → **Create application** → **Workers** → connect the
   `adab-tech/OpportunityFinder` repo, branch `main`.
2. Build settings: none needed — `wrangler.jsonc` at the repo root already
   declares everything (entry point, assets directory, the `API_ORIGIN`
   default).
3. **Settings → Variables**: optionally override `API_ORIGIN` per
   environment (defaults to the Render `.onrender.com` URL already baked
   into `wrangler.jsonc`).
4. Deploy, then verify on the `*.workers.dev` URL Cloudflare gives you.
5. **Settings → Domains & Routes → Add** → `globalopportunities.app` (and
   `www`) once verified — same one-click DNS handoff as above, and just as
   reversible (remove the route, the old record comes back).

## Verify (before touching DNS, whichever option)

- `https://<worker>.workers.dev/` → the site loads normally
- `https://<worker>.workers.dev/health` → proxies through to Render,
  returns the same JSON the direct Render URL returns
- `https://<worker>.workers.dev/admin.html` → log in as admin and confirm
  the moderation queue loads (this is the real test of the cookie/CORS
  behavior above)

## What does *not* change

- The Render service keeps running exactly as-is — same Docker image, same
  `render.yaml`, same env vars. It's now reached only via the worker's
  server-to-server `fetch()` rather than directly by browsers, but nothing
  about its own code or config needs to change.
- `CORS_ORIGINS` can stay `*` — CORS only governs browser-initiated
  cross-origin requests, and after this move browsers never talk to Render
  directly.
- Admin auth, session cookies, and every `admin.js` fetch call are
  untouched.
