import logging
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.database import SessionLocal
from app.schemas import ScrapeRequest, ScrapeResponse
from app.scrapers.opportunity_scraper import OpportunityScraper
from app.services.rate_limit import CooldownLimiter, RateLimitedError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraper", tags=["Scraper"])

# Non-blocking lock: acquired for the whole scrape so concurrent trigger
# requests cannot start a second run (check-and-set is atomic). This is
# purely an in-process "is a scrape running right now" guard, not
# restart-durable state — if the process restarts, any scrape thread
# holding it is gone too, so resetting on restart is correct here,
# unlike the cooldown below.
_scrape_lock = threading.Lock()

# The "Find new" button on the public homepage calls this endpoint with
# no login required, by design — anyone can ask for a fresh scrape. But
# without a floor between requests, a scripted caller could trigger runs
# back-to-back forever, and each run can burn through the metered
# You.com Search API ($5/1000 calls) or exhaust the Google CSE 100/day
# free quota. This cooldown is global (not per-IP, hence the constant
# key below) so it can't be sidestepped by spreading requests across
# source addresses. Persisted in the DB (app/models.py RateLimitCooldown),
# not process memory — see app/services/rate_limit.py's module docstring
# for why: an in-memory version reset on every restart, so waiting for
# (or triggering) a redeploy was an easy way to skip the cooldown.
_MANUAL_TRIGGER_COOLDOWN_SECONDS = 300
_SCRAPE_COOLDOWN_KEY = "global"
_scrape_cooldown_limiter = CooldownLimiter(_MANUAL_TRIGGER_COOLDOWN_SECONDS, namespace="scrape_trigger")


def _enforce_cooldown() -> None:
    try:
        _scrape_cooldown_limiter.check(_SCRAPE_COOLDOWN_KEY)
    except RateLimitedError:
        wait = _scrape_cooldown_limiter.seconds_remaining(_SCRAPE_COOLDOWN_KEY)
        raise HTTPException(
            status_code=429,
            detail=f"A scrape was requested recently. Try again in {wait}s.",
        ) from None


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
