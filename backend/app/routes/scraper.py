import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException

from app.database import SessionLocal, get_db
from app.scrapers.opportunity_scraper import OpportunityScraper
from app.schemas import ScrapeRequest, ScrapeResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraper", tags=["Scraper"])

_scraping_in_progress = False


@router.post("/run", response_model=ScrapeResponse)
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    global _scraping_in_progress
    if _scraping_in_progress:
        raise HTTPException(status_code=409, detail="Scraping already in progress. Try again later.")

    def _run():
        global _scraping_in_progress
        _scraping_in_progress = True
        db = SessionLocal()
        try:
            scraper = OpportunityScraper(db)
            stats = scraper.run(
                opportunity_types=request.opportunity_types,
                extra_keywords=request.extra_keywords,
                max_results=request.max_results,
            )
            logger.info(f"Background scrape complete: {stats}")
        except Exception as exc:
            logger.error(f"Background scrape error: {exc}")
        finally:
            db.close()
            _scraping_in_progress = False

    background_tasks.add_task(_run)
    return ScrapeResponse(
        status="started",
        message="Scraping started in background. Results will appear as they are found.",
    )


@router.get("/status")
async def scrape_status():
    return {
        "scraping_in_progress": _scraping_in_progress,
        "status": "running" if _scraping_in_progress else "idle",
    }
