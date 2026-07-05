import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.scrapers.opportunity_scraper import OpportunityScraper
from app.services.maintenance import deactivate_expired_opportunities
from app.services.subscribers import run_alert_digest, run_saved_deadline_reminders

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


def _scheduled_alert_digest():
    logger.info("Scheduled alert digest triggered.")
    db = SessionLocal()
    try:
        run_alert_digest(db)
    except Exception:
        logger.exception("Scheduled alert digest error")
    finally:
        db.close()


def _scheduled_saved_reminders():
    logger.info("Scheduled saved-opportunity deadline reminder triggered.")
    db = SessionLocal()
    try:
        run_saved_deadline_reminders(db)
    except Exception:
        logger.exception("Scheduled deadline reminder error")
    finally:
        db.close()


def _scheduled_expiry_sweep():
    logger.info("Scheduled expired-opportunity sweep triggered.")
    db = SessionLocal()
    try:
        deactivate_expired_opportunities(db)
    except Exception:
        logger.exception("Scheduled expiry sweep error")
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
    _scheduler.add_job(
        _scheduled_alert_digest,
        trigger=IntervalTrigger(hours=settings.ALERT_DIGEST_INTERVAL_HOURS),
        id="alert_digest",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _scheduled_saved_reminders,
        trigger=IntervalTrigger(hours=settings.SAVED_REMINDER_INTERVAL_HOURS),
        id="saved_deadline_reminders",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _scheduled_expiry_sweep,
        trigger=IntervalTrigger(hours=24),
        id="expiry_sweep",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        f"Scheduler running — scraping every {settings.SCRAPE_INTERVAL_HOURS}h, "
        f"alert digest every {settings.ALERT_DIGEST_INTERVAL_HOURS}h, "
        f"saved-opportunity reminders every {settings.SAVED_REMINDER_INTERVAL_HOURS}h, "
        f"expiry sweep every 24h."
    )


def shutdown_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
