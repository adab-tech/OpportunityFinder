"""Admin moderation queue for opportunities discovered via low-trust
open web-search discovery (see app/scrapers/opportunity_scraper.py).

Every row saved by the Google/You.com/scrape pipeline starts life with
`review_status="pending"` and is excluded from every public endpoint by
`routes/opportunities.py::_public_visible`. A human reviews the queue
here and explicitly approves or rejects each one before it can ever be
shown publicly. Curated RSS feeds are a separate, pre-vetted trust tier
and auto-approve (`rss_ingest.py`) — they never appear in this queue.

Protected by the same `X-Admin-Key` header / `ADMIN_API_KEY` setting as
`routes/analytics.py::summary` — unset by default, so this refuses ALL
requests (503) until explicitly configured in the deployment environment.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Opportunity
from app.schemas import (
    BulkModerationRequest,
    BulkModerationResponse,
    ModerationActionResponse,
    PaginatedOpportunities,
)

router = APIRouter(prefix="/admin/moderation", tags=["Moderation"])


def _require_admin(x_admin_key: str | None) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=503, detail="Moderation is not configured (ADMIN_API_KEY unset)."
        )
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key.")


def _get_pending_or_404(db: Session, opportunity_id: int) -> Opportunity:
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@router.get("/pending", response_model=PaginatedOpportunities)
def list_pending(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(x_admin_key)

    q = db.query(Opportunity).filter(Opportunity.review_status == "pending")
    total = q.count()
    items = (
        q.order_by(Opportunity.scraped_at.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return PaginatedOpportunities(
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, (total + per_page - 1) // per_page),
        data=items,
    )


@router.post("/{opportunity_id}/approve", response_model=ModerationActionResponse)
def approve(
    opportunity_id: int,
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(x_admin_key)
    opp = _get_pending_or_404(db, opportunity_id)
    opp.review_status = "approved"
    db.commit()
    return ModerationActionResponse(status="ok", id=opp.id, review_status=opp.review_status)


@router.post("/{opportunity_id}/reject", response_model=ModerationActionResponse)
def reject(
    opportunity_id: int,
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(x_admin_key)
    opp = _get_pending_or_404(db, opportunity_id)
    opp.review_status = "rejected"
    opp.is_active = False
    db.commit()
    return ModerationActionResponse(status="ok", id=opp.id, review_status=opp.review_status)


@router.post("/bulk-approve", response_model=BulkModerationResponse)
def bulk_approve(
    request: BulkModerationRequest,
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(x_admin_key)

    rows = db.query(Opportunity).filter(Opportunity.id.in_(request.ids)).all()
    updated_ids: list[int] = []
    for row in rows:
        row.review_status = "approved"
        updated_ids.append(row.id)
    db.commit()

    return BulkModerationResponse(status="ok", updated=len(updated_ids), ids=updated_ids)
