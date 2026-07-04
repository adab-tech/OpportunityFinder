"""Self-hosted visitor analytics — event ingestion (public) and a
summary endpoint (admin-key protected). See app/services/analytics.py.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
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


@router.get("/summary")
def summary(
    days: int = Query(default=7, ge=1, le=90),
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=503, detail="Analytics summary is not configured (ADMIN_API_KEY unset)."
        )
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key.")

    return svc.get_summary(db, days=days)
