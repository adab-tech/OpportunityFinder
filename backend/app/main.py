import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from app.bootstrap import run_startup_tasks
from app.config import settings
from app.database import Base, engine
from app.migrations import run_pending_column_migrations
from app.routes import (
    admin_auth,
    admin_listings,
    analytics,
    moderation,
    opportunities,
    scraper,
    subscribers,
)
from app.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    Base.metadata.create_all(bind=engine)
    run_pending_column_migrations(engine)
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    threading.Thread(target=run_startup_tasks, daemon=True).start()
    logger.info("OpportunityFinder API is ready.")
    yield
    # ---- shutdown ----
    shutdown_scheduler()
    logger.info("OpportunityFinder API stopped.")


app = FastAPI(
    title="OpportunityFinder API",
    description=(
        "AI-powered web mining platform that discovers scholarships, "
        "fellowships, grants, and jobs from across the internet."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Credentialed CORS is invalid with a wildcard origin; only enable it
# when explicit origins are configured.
_cors_origins = settings.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(opportunities.router, prefix="/api/v1")
app.include_router(scraper.router, prefix="/api/v1")
app.include_router(subscribers.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(moderation.router, prefix="/api/v1")
app.include_router(admin_auth.router, prefix="/api/v1")
app.include_router(admin_listings.router, prefix="/api/v1")


@app.get("/health", tags=["System"])
def health():
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Health check DB probe failed: %s", exc)

    body = {
        "status": "healthy" if db_ok else "degraded",
        "service": "OpportunityFinder",
        "database": "ok" if db_ok else "unavailable",
        "scheduler": settings.ENABLE_SCHEDULER,
    }
    return JSONResponse(content=body, status_code=200 if db_ok else 503)


@app.get("/api", tags=["System"])
async def root():
    return {
        "service": "OpportunityFinder API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str = ""):
    if path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not found")

    if not FRONTEND_DIR.exists():
        return JSONResponse({"detail": "Frontend not available"}, status_code=404)

    # Resolve and confine to FRONTEND_DIR so encoded "../" segments
    # cannot escape the frontend folder.
    try:
        candidate = (FRONTEND_DIR / path).resolve()
        candidate.relative_to(FRONTEND_DIR.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found") from None

    if candidate.is_file():
        return FileResponse(candidate)

    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")
