
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Opportunity
from app.schemas import OpportunityResponse, PaginatedOpportunities, StatsResponse

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


def _not_expired(query):
    """A passed deadline must never be shown, full stop — this is a
    query-level guarantee independent of whatever `is_active` happens to
    say, so a stale flag (e.g. before a sweep job runs) can never let an
    expired listing slip through.
    """
    return query.filter(
        or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= date.today())
    )


@router.get("/", response_model=PaginatedOpportunities)
def list_opportunities(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    opportunity_type: str | None = Query(None),
    field: str | None = Query(None),
    location: str | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query("newest", pattern="^(newest|closing)$"),
    db: Session = Depends(get_db),
):
    q = _not_expired(db.query(Opportunity).filter(Opportunity.is_active.is_(True)))

    if opportunity_type:
        q = q.filter(Opportunity.opportunity_type == opportunity_type.lower())

    if field:
        q = q.filter(Opportunity.field.ilike(f"%{field}%"))

    if location:
        q = q.filter(Opportunity.location.ilike(f"%{location}%"))

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Opportunity.title.ilike(term),
                Opportunity.description.ilike(term),
                Opportunity.field.ilike(term),
                Opportunity.source_name.ilike(term),
                Opportunity.location.ilike(term),
            )
        )

    total = q.count()

    # "closing" surfaces the deadlines about to pass first; rows with no
    # parseable deadline sort last so a known date always beats an unknown.
    if sort == "closing":
        order = (Opportunity.deadline_at.asc().nulls_last(), Opportunity.scraped_at.desc())
    else:
        order = (Opportunity.scraped_at.desc(),)

    items = (
        q.order_by(*order)
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


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    counts = dict(
        _not_expired(
            db.query(Opportunity.opportunity_type, func.count(Opportunity.id)).filter(
                Opportunity.is_active.is_(True)
            )
        )
        .group_by(Opportunity.opportunity_type)
        .all()
    )
    last_scraped = db.query(func.max(Opportunity.scraped_at)).scalar()

    return StatsResponse(
        total=sum(counts.values()),
        scholarships=counts.get("scholarship", 0),
        fellowships=counts.get("fellowship", 0),
        grants=counts.get("grant", 0),
        jobs=counts.get("job", 0),
        last_scraped=last_scraped,
    )


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opp = (
        _not_expired(
            db.query(Opportunity).filter(
                Opportunity.id == opportunity_id, Opportunity.is_active.is_(True)
            )
        )
        .first()
    )
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp
