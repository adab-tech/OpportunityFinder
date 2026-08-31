# Cloudflare Workers (edge-served static assets)

**This is live in production.** `globalopportunities.app` is a Cloudflare
Worker (`worker/index.js` + `wrangler.jsonc`) that serves the static frontend
(`frontend/`) from the edge and proxies API calls to the Render backend
server-side. This doc is kept as the reference for how that's set up and for
reproducing it (e.g. a fresh Cloudflare account, or a new environment).

Before this move, `globalopportunities.app` was a Cloudflare-proxied DNS
record pointing directly at the Render service, which served both the API
and the static frontend from one Docker container — every visitor's
HTML/CSS/JS made a round trip to Render's origin server, with a possible
cold start on Render's free tier if it had been idle. Moving the static
frontend onto Cloudflare's edge network instead is faster worldwide, and
immune to Render cold-starts for anything that isn't an API call — **without
touching the backend or admin auth at all.**

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

## HTTP security headers

A 2026-08 audit found no security headers (CSP, `X-Frame-Options`,
`X-Content-Type-Options`, etc.) being sent anywhere. Two separate places
needed them, since the two halves of this deployment never share a runtime:

- **The API/docs, proxied to Render** — `backend/app/main.py` has an ASGI
  middleware (`add_security_headers`) that sets them on every response, with
  a path-scoped `Content-Security-Policy`: strict for JSON endpoints, a
  looser CDN/inline-allowing one for `/docs` and `/redoc` (FastAPI's stock
  Swagger UI / ReDoc pages), and one matching the frontend's below for the
  local-dev fallback where this same app serves `frontend/` directly.
- **The static site, edge-served** — `frontend/_headers` (Cloudflare's
  native mechanism for this — see
  [Headers](https://developers.cloudflare.com/workers/static-assets/headers/) —
  confirmed via the Cloudflare docs MCP tool rather than assumed, since it
  supersedes the old Pages-only convention; no `run_worker_first` needed
  since nothing here has to run per-request). Verified against a real
  `wrangler dev` locally, including a gotcha the docs don't call out: hitting
  `/admin.html` 307-redirects to the extensionless `/admin`, so the CSP rule
  has to target `/admin` too or the page that actually gets served carries
  no policy at all.

`Strict-Transport-Security` is unconditional in `_headers` (Cloudflare only
serves this site over HTTPS) but conditional in the backend middleware on
`settings.SESSION_COOKIE_SECURE` — the existing flag for "this is plain-http
local dev" — so local development never gets an HSTS header a plain-http
server can't honour.

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
