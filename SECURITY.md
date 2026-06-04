# Security

If `GOOGLE_API_KEY` or `GOOGLE_CSE_ID` were ever committed or shared, **revoke and recreate** them in [Google Cloud Console](https://console.cloud.google.com/apis/credentials). Store new values only in `backend/.env` and GitHub Actions secrets (see `.github/SECRETS.md`).
