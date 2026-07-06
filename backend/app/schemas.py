from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OpportunityBase(BaseModel):
    title: str
    description: str | None = None
    summary: str | None = None
    opportunity_type: str
    field: str | None = None
    location: str | None = None
    deadline: str | None = None
    deadline_at: date | None = None
    url: str
    source_name: str | None = None
    tags: str | None = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityResponse(OpportunityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    review_status: str
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


class AnalyticsEventRequest(BaseModel):
    event_type: str
    client_id: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=200)
    opportunity_id: int | None = None


class ModerationActionResponse(BaseModel):
    status: str
    id: int
    review_status: str


class BulkModerationRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class BulkModerationResponse(BaseModel):
    status: str
    updated: int
    ids: list[int]


class AdminOpportunityUpdate(BaseModel):
    """Partial update for the admin listing-management table — every
    field optional, only the ones the admin actually changed are sent.
    """

    title: str | None = None
    description: str | None = None
    summary: str | None = None
    opportunity_type: str | None = None
    field: str | None = None
    location: str | None = None
    deadline: str | None = None
    deadline_at: date | None = None
    url: str | None = None
    source_name: str | None = None
    tags: str | None = None
    is_active: bool | None = None
