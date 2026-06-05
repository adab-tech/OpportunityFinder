import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.bootstrap import run_startup_tasks
from app.config import settings
from app.database import engine, Base
from app.routes import opportunities, scraper
from app.scheduler import start_scheduler, shutdown_scheduler

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(opportunities.router, prefix="/api/v1")
app.include_router(scraper.router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health():
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Health check DB probe failed: %s", exc)

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "OpportunityFinder",
        "database": "ok" if db_ok else "unavailable",
        "scheduler": settings.ENABLE_SCHEDULER,
    }


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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    if not FRONTEND_DIR.exists():
        return {"detail": "Frontend not available"}

    candidate = FRONTEND_DIR / path
    if candidate.is_file():
        return FileResponse(candidate)

    return FileResponse(FRONTEND_DIR / "index.html")
