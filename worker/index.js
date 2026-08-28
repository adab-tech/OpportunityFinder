/**
 * Cloudflare Worker (with static assets) entry point.
 *
 * Lets the static frontend (served from Cloudflare's edge via the
 * `assets` binding in wrangler.jsonc) and the FastAPI backend on Render
 * share one origin from the browser's point of view. Without this,
 * putting the frontend on Workers/Pages while the API stayed on Render
 * would put them on different domains — which breaks admin login
 * outright: admin.js sends every request with credentials:
 * 'same-origin' and the session cookie is SameSite=Strict, both of
 * which deliberately reject cross-site requests. Proxying keeps that
 * security posture unchanged instead of loosening it to SameSite=None.
 *
 * Workers automatically serves a matching static asset before this
 * script ever runs, so this only executes for paths with no matching
 * file — i.e. exactly the API/docs paths below, by construction. No
 * routes file is needed (unlike the Pages Advanced Mode equivalent).
 */

const PROXIED_PREFIXES = ["/api", "/health", "/docs", "/openapi.json", "/redoc"];

function shouldProxy(pathname) {
  return PROXIED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix)
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (shouldProxy(url.pathname)) {
      const origin = env.API_ORIGIN || "https://adab-opportunityfinder.onrender.com";
      const target = new URL(url.pathname + url.search, origin);
      // Cloning onto the new URL keeps method, headers (including
      // Cookie and CF-Connecting-IP), and body intact, so the response
      // (including Set-Cookie) round-trips to the browser unchanged.
      const proxied = new Request(target, request);
      return fetch(proxied);
    }

    // No static asset matched (that path already tried and failed
    // before this script ran) and it isn't a proxied path either.
    return env.ASSETS.fetch(request);
  },
};
