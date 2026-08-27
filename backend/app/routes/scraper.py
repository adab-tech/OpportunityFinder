import logging
import threading
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.database import SessionLocal
from app.schemas import ScrapeRequest, ScrapeResponse
from app.scrapers.opportunity_scraper import OpportunityScraper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraper", tags=["Scraper"])

# Non-blocking lock: acquired for the whole scrape so concurrent trigger
# requests cannot start a second run (check-and-set is atomic).
_scrape_lock = threading.Lock()

# The "Find new" button on the public homepage calls this endpoint with
# no login required, by design — anyone can ask for a fresh scrape. But
# without a floor between requests, a scripted caller could trigger runs
# back-to-back forever, and each run can burn through the metered
# You.com Search API ($5/1000 calls) or exhaust the Google CSE 100/day
# free quota. This cooldown is global (not per-IP) so it can't be
# sidestepped by spreading requests across source addresses.
_MANUAL_TRIGGER_COOLDOWN_SECONDS = 300
# None means "never triggered yet" — deliberately not 0.0. time.monotonic()'s
# zero point is unspecified (often near system/container boot, not epoch),
# so a container whose clock hasn't yet reached the cooldown value would
# have its very first real request wrongly rejected as "too soon" if we
# measured elapsed time against a 0.0 sentinel.
_last_triggered_at: float | None = None
_cooldown_lock = threading.Lock()


def _enforce_cooldown() -> None:
    global _last_triggered_at
    with _cooldown_lock:
        now = time.monotonic()
        if _last_triggered_at is not None:
            elapsed = now - _last_triggered_at
            if elapsed < _MANUAL_TRIGGER_COOLDOWN_SECONDS:
                wait = int(_MANUAL_TRIGGER_COOLDOWN_SECONDS - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"A scrape was requested recently. Try again in {wait}s.",
                )
        _last_triggered_at = now


@router.post("/run", response_model=ScrapeResponse)
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    _enforce_cooldown()

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
