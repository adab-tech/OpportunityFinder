# OpportunityFinder

OpportunityFinder is an AI-assisted opportunity discovery app for scholarships, fellowships, grants, and jobs.

## What is included

- `backend/` - FastAPI API, database, scraping, and scheduled refresh jobs
- `frontend/` - static UI that talks to the API
- `opportunities.db` - local SQLite database used during development

## Local development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

Serve the `frontend/` folder with any static web server, then point it at the API.

If the frontend and backend are deployed together on the same domain, the app will use `/api/v1` automatically.
If they are deployed separately, set the API base before loading `js/app.js`:

```html
<script>
  window.OPPORTUNITYFINDER_API_BASE = 'https://your-api-host.example.com/api/v1';
</script>
```

The repo also includes `frontend/config.js` as the deployment hook for that value.
Edit it when you want to point the static frontend at a separate backend host.

If you are running locally from `file://`, the app falls back to `http://127.0.0.1:8000/api/v1`.

## Optional search API keys

`backend/.env.example` includes optional Google Custom Search settings:

- `GOOGLE_API_KEY`
- `GOOGLE_CSE_ID`

Without those keys, the scraper falls back to public search scraping.

## Production notes

- The frontend expects the API to be reachable from the browser.
- The backend enables CORS for all origins, so a deployed frontend can call it from another host.
- Keep `DATABASE_URL` configurable for production deployments.
