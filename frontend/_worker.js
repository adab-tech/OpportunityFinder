/**
 * Cloudflare Pages Advanced Mode worker.
 *
 * Lets the static frontend and the FastAPI backend (on Render) share one
 * origin from the browser's point of view. Without this, moving the
 * frontend to Pages would put it on a different domain than the API,
 * which breaks admin login outright: admin.js sends every request with
 * credentials: 'same-origin' and the session cookie is SameSite=Strict —
 * both deliberately reject cross-site requests. Proxying keeps that
 * security posture unchanged instead of loosening it to SameSite=None.
 *
 * _routes.json restricts which paths even reach this worker; anything
 * not listed there (index.html, css, js, images, robots.txt, ...) is
 * served directly from Cloudflare's edge and never executes this code.
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

    return env.ASSETS.fetch(request);
  },
};
