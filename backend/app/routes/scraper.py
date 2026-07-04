import logging
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.database import SessionLocal
from app.schemas import ScrapeRequest, ScrapeResponse
from app.scrapers.opportunity_scraper import OpportunityScraper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraper", tags=["Scraper"])

# Non-blocking lock: acquired for the whole scrape so concurrent trigger
# requests cannot start a second run (check-and-set is atomic).
_scrape_lock = threading.Lock()


@router.post("/run", response_model=ScrapeResponse)
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    if not _scrape_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Scraping already in progress. Try again later.")

    def _run():
        db = SessionLocal()
        try:
            scraper = OpportunityScraper(db)
            stats = scraper.run(
                opportunity_types=request.opportunity_types,
                extra_keywords=request.extra_keywords,
                max_results=request.max_results,
            )
            logger.info("Background scrape complete: %s", stats)
        except Exception:
            logger.exception("Background scrape error")
        finally:
            db.close()
            _scrape_lock.release()

    background_tasks.add_task(_run)
    return ScrapeResponse(
        status="started",
        message="Scraping started in background. Results will appear as they are found.",
    )


@router.get("/status")
async def scrape_status():
    in_progress = _scrape_lock.locked()
    return {
        "scraping_in_progress": in_progress,
        "status": "running" if in_progress else "idle",
    }
