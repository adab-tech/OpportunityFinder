from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.database import get_db
from app.models import Opportunity
from app.schemas import OpportunityResponse, PaginatedOpportunities, StatsResponse

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.get("/", response_model=PaginatedOpportunities)
def list_opportunities(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    opportunity_type: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Opportunity).filter(Opportunity.is_active == True)

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


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    base = db.query(Opportunity).filter(Opportunity.is_active == True)
    total = base.count()

    def count_type(t: str) -> int:
        return base.filter(Opportunity.opportunity_type == t).count()

    last = db.query(Opportunity).order_by(Opportunity.scraped_at.desc()).first()

    return StatsResponse(
        total=total,
        scholarships=count_type("scholarship"),
        fellowships=count_type("fellowship"),
        grants=count_type("grant"),
        jobs=count_type("job"),
        last_scraped=last.scraped_at if last else None,
    )


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opp = (
        db.query(Opportunity)
        .filter(Opportunity.id == opportunity_id, Opportunity.is_active == True)
        .first()
    )
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp
