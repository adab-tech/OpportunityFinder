from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OpportunityBase(BaseModel):
    title: str
    description: str | None = None
    opportunity_type: str
    field: str | None = None
    location: str | None = None
    deadline: str | None = None
    url: str
    source_name: str | None = None
    tags: str | None = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityResponse(OpportunityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    scraped_at: datetime


class PaginatedOpportunities(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int
    data: list[OpportunityResponse]


class ScrapeRequest(BaseModel):
    opportunity_types: list[str] | None = Field(
        default_factory=lambda: ["scholarship", "fellowship", "grant", "job"]
    )
    extra_keywords: list[str] | None = None
    max_results: int = Field(default=50, ge=1, le=200)


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
    last_scraped: datetime | None = None


class SaveOpportunityRequest(BaseModel):
    email: EmailStr
    opportunity_id: int


class SavedOpportunityActionResponse(BaseModel):
    status: str
    message: str


class AlertCreateRequest(BaseModel):
    email: EmailStr
    opportunity_type: str | None = None
    field: str | None = None
    location: str | None = None
    keyword: str | None = Field(default=None, max_length=200)


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_type: str | None = None
    field: str | None = None
    location: str | None = None
    keyword: str | None = None
    created_at: datetime
    last_notified_at: datetime | None = None
