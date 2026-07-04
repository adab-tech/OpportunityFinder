from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    # scholarship | fellowship | grant | job | other
    opportunity_type = Column(String(50), nullable=False, index=True)
    # STEM, Medicine, Arts, etc.
    field = Column(String(200), index=True)
    location = Column(String(200))
    deadline = Column(String(100))
    url = Column(String(2000), unique=True, nullable=False)
    source_name = Column(String(200))
    tags = Column(String(500))           # comma-separated
    is_active = Column(Boolean, default=True)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Opportunity {self.title[:60]}>"
