# GitHub repository secrets

Configure under **Settings → Secrets and variables → Actions** for [adab-tech/OpportunityFinder](https://github.com/adab-tech/OpportunityFinder).

| Secret | Required | Purpose |
|--------|----------|---------|
| `GOOGLE_API_KEY` | Optional | Google Custom Search API (higher quota than scrape fallback) |
| `GOOGLE_CSE_ID` | Optional | Custom Search Engine ID (pair with `GOOGLE_API_KEY`) |

CI runs without these secrets (SQLite + smoke tests only). For production scraping performance, add both keys from [Google Programmable Search](https://developers.google.com/custom-search/v1/introduction).

**Local setup:** copy `backend/.env.example` to `backend/.env` and fill values.

**Sync from local `.env` (run on your machine):**

```powershell
gh secret set GOOGLE_API_KEY --repo adab-tech/OpportunityFinder --body "YOUR_KEY"
gh secret set GOOGLE_CSE_ID --repo adab-tech/OpportunityFinder --body "YOUR_CX_ID"
```
