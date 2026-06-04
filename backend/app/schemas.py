from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class OpportunityBase(BaseModel):
    title: str
    description: Optional[str] = None
    opportunity_type: str
    field: Optional[str] = None
    location: Optional[str] = None
    deadline: Optional[str] = None
    url: str
    source_name: Optional[str] = None
    tags: Optional[str] = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityResponse(OpportunityBase):
    id: int
    is_active: bool
    scraped_at: datetime

    class Config:
        from_attributes = True


class PaginatedOpportunities(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int
    data: List[OpportunityResponse]


class ScrapeRequest(BaseModel):
    opportunity_types: Optional[List[str]] = ["scholarship", "fellowship", "grant", "job"]
    extra_keywords: Optional[List[str]] = None
    max_results: int = 50


class ScrapeResponse(BaseModel):
    status: str
    message: str
    scraped_count: int = 0
    saved_count: int = 0


class StatsResponse(BaseModel):
    total: int
    scholarships: int
    fellowships: int
    grants: int
    jobs: int
    last_scraped: Optional[datetime] = None
