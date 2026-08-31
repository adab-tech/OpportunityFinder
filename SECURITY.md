# Security Policy

Global Opportunities (globalopportunities.app) is a single-operator project, not a
company with a security team. This policy is scoped and worded accordingly.

## Reporting a vulnerability

Preferred: use GitHub's private vulnerability reporting for this repo
(Settings → Security → "Private vulnerability reporting", or the
"Report a vulnerability" button under the Security tab). This opens a
private advisory only the maintainer can see.

If that option isn't available to you, email **hello@globalopportunities.app**
with:

- a description of the issue and its impact
- steps to reproduce (or a PoC)
- any relevant URLs, request/response examples, or logs

Do not open a public GitHub issue for a security report.

## Scope

**In scope:**

- The live site and API at globalopportunities.app
- The source in this repository (`backend/` FastAPI app, `frontend/` static UI)

**Out of scope:**

- The infrastructure providers this app runs on — Render (hosting),
  Cloudflare (Workers/DNS), Neon (Postgres), and any transactional email
  provider (Resend/Brevo/SendGrid). Vulnerabilities in those platforms
  themselves belong to their own disclosure programs, not this repo.
- Third-party content ingested by the scraper (RSS feeds, search results,
  listing pages on other sites). Report those to the source site.
- Denial of service achieved purely by consuming the app's own rate limits
  as intended (see below).

## What not to do

- No automated scanning, fuzzing, or load testing against the live site.
  It's a small deployment and this can degrade it for other users.
- In particular, don't script or hammer the public "Find new" button
  (`POST /api/v1/scraper/run`). It triggers a real scraping job against
  metered/rate-limited third-party search APIs and is protected by a
  5-minute global cooldown (`backend/app/routes/scraper.py`) — treat that
  cooldown as a hard limit, not a target to test.
- No accessing, modifying, or exfiltrating other users' data beyond what's
  needed to demonstrate a finding.
- No public disclosure until a fix has shipped. Please give reasonable time
  to respond before going public.

## Response expectations

This project is maintained by one person in their spare time, not a 24/7
security team. Expect a best-effort acknowledgment within a few days, not a
guaranteed SLA. Fix timelines depend on severity and available time — you'll
be kept informed once a report is triaged.

## Credentials and committed secrets

If you find a committed secret (API key, token, connection string) in this
repo's history, report it the same way as a vulnerability. As a past
example: if `GOOGLE_API_KEY` or `GOOGLE_CSE_ID` are ever exposed (committed,
logged, or otherwise leaked), they should be revoked and recreated
immediately in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
with new values stored only in `backend/.env` and GitHub Actions secrets
(see `.github/SECRETS.md`) — never in the repo itself. The same applies to
any other API key or credential used by this project (Resend/Brevo/SendGrid
keys, `DATABASE_URL`, etc.).
