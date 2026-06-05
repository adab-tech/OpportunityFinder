import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.scrapers.opportunity_scraper import OpportunityScraper

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler()


def _scheduled_task():
    logger.info("Scheduled ingest triggered.")
    db = SessionLocal()
    try:
        scraper = OpportunityScraper(db)
        stats = scraper.run(max_results=100)
        logger.info(f"Scheduled scrape done: {stats}")
    except Exception as exc:
        logger.error(f"Scheduled scrape error: {exc}")
    finally:
        db.close()


def start_scheduler():
    _scheduler.add_job(
        _scheduled_task,
        trigger=IntervalTrigger(hours=settings.SCRAPE_INTERVAL_HOURS),
        id="opportunity_scraper",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(f"Scheduler running — scraping every {settings.SCRAPE_INTERVAL_HOURS}h.")


def shutdown_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
