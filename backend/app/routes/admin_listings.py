"""Admin listing management — search, edit, and deactivate/reactivate
ANY opportunity (unlike routes/moderation.py, which only handles the
pending-review queue). This is the "proper management" layer: once
something is live, an admin can still correct or pull it.

Protected by the same admin session cookie as routes/analytics.py and
routes/moderation.py (see routes/admin_auth.py::require_admin_session).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Opportunity
from app.routes.admin_auth import require_admin_session
from app.schemas import AdminOpportunityUpdate, OpportunityResponse, PaginatedOpportunities
from app.scrapers.dedup import normalize_title

router = APIRouter(
    prefix="/admin/opportunities", tags=["Admin Listings"], dependencies=[Depends(require_admin_session)]
)


def _get_or_404(db: Session, opportunity_id: int) -> Opportunity:
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@router.get("/", response_model=PaginatedOpportunities)
def list_all(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    opportunity_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Every opportunity regardless of is_active/review_status —
    deliberately unfiltered, unlike the public listing, since an admin
    needs to see (and fix) everything, not just what's currently live.
    """
    q = db.query(Opportunity)

    if opportunity_type:
        q = q.filter(Opportunity.opportunity_type == opportunity_type.lower())

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Opportunity.title.ilike(term),
                Opportunity.source_name.ilike(term),
                Opportunity.location.ilike(term),
            )
        )

    total = q.count()
    items = (
        q.order_by(Opportunity.scraped_at.desc())
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


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
def update(opportunity_id: int, request: AdminOpportunityUpdate, db: Session = Depends(get_db)):
    opp = _get_or_404(db, opportunity_id)

    updates = request.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(opp, field_name, value)

    # Keep the dedup key in sync whenever the title actually changes —
    # otherwise a manually-corrected title stops matching future reposts
    # of the same opportunity from another aggregator.
    if "title" in updates:
        opp.title_normalized = normalize_title(opp.title)

    db.commit()
    db.refresh(opp)
    return opp


@router.post("/{opportunity_id}/deactivate", response_model=OpportunityResponse)
def deactivate(opportunity_id: int, db: Session = Depends(get_db)):
    opp = _get_or_404(db, opportunity_id)
    opp.is_active = False
    db.commit()
    db.refresh(opp)
    return opp


@router.post("/{opportunity_id}/reactivate", response_model=OpportunityResponse)
def reactivate(opportunity_id: int, db: Session = Depends(get_db)):
    opp = _get_or_404(db, opportunity_id)
    opp.is_active = True
    db.commit()
    db.refresh(opp)
    return opp
