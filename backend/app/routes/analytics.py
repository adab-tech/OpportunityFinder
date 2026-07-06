"""Self-hosted visitor analytics — event ingestion (public) and a
summary endpoint (admin-session protected). See app/services/analytics.py.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.admin_auth import require_admin_session
from app.schemas import AnalyticsEventRequest
from app.services import analytics as svc

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/event", status_code=204)
def record_event(request: AnalyticsEventRequest, db: Session = Depends(get_db)):
    # Never errors out to the client — a tracking failure must not be
    # visible to (or block) a real user's browsing experience.
    if request.event_type not in svc.VALID_EVENT_TYPES:
        return
    svc.record_event(db, request.event_type, request.client_id, request.value, request.opportunity_id)


@router.get("/summary", dependencies=[Depends(require_admin_session)])
def summary(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    return svc.get_summary(db, days=days)


@router.get("/trends", dependencies=[Depends(require_admin_session)])
def trends(
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    return {"days": days, "data": svc.get_daily_trends(db, days=days)}
