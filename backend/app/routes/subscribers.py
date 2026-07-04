"""Saved opportunities and email alerts — no login required.

A subscriber is identified only by email. Every management action after
signup (viewing saved items, deleting an alert) goes through their
unguessable manage_token, which is emailed to them (see
app/services/email_sender.py — logged to the server console until
RESEND_API_KEY is configured).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    AlertCreateRequest,
    AlertResponse,
    OpportunityResponse,
    SavedOpportunityActionResponse,
    SaveOpportunityRequest,
)
from app.services import subscribers as svc

router = APIRouter(tags=["Saved Opportunities & Alerts"])


@router.post("/saved", response_model=SavedOpportunityActionResponse)
def save_opportunity(request: SaveOpportunityRequest, db: Session = Depends(get_db)):
    result = svc.save_opportunity(db, request.email, request.opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return SavedOpportunityActionResponse(
        status="saved",
        message="Saved. Check your email for a link to manage your saved opportunities.",
    )


@router.get("/saved/{manage_token}", response_model=list[OpportunityResponse])
def list_saved(manage_token: str, db: Session = Depends(get_db)):
    result = svc.list_saved_opportunities(db, manage_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Invalid or expired manage link")
    return result


@router.delete("/saved/{manage_token}/{opportunity_id}", response_model=SavedOpportunityActionResponse)
def unsave(manage_token: str, opportunity_id: int, db: Session = Depends(get_db)):
    removed = svc.unsave_opportunity(db, manage_token, opportunity_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Not found")
    return SavedOpportunityActionResponse(status="removed", message="Removed from your saved list.")


@router.post("/alerts", response_model=SavedOpportunityActionResponse)
def create_alert(request: AlertCreateRequest, db: Session = Depends(get_db)):
    svc.create_alert(
        db,
        email=request.email,
        opportunity_type=request.opportunity_type,
        field=request.field,
        location=request.location,
        keyword=request.keyword,
    )
    return SavedOpportunityActionResponse(
        status="created",
        message="Alert created. Check your email for a link to manage your alerts.",
    )


@router.get("/alerts/{manage_token}", response_model=list[AlertResponse])
def list_alerts(manage_token: str, db: Session = Depends(get_db)):
    result = svc.list_alerts(db, manage_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Invalid or expired manage link")
    return result


@router.delete("/alerts/{manage_token}/{alert_id}", response_model=SavedOpportunityActionResponse)
def delete_alert(manage_token: str, alert_id: int, db: Session = Depends(get_db)):
    removed = svc.delete_alert(db, manage_token, alert_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Not found")
    return SavedOpportunityActionResponse(status="removed", message="Alert removed.")
