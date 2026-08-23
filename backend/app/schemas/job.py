from datetime import datetime
from typing import Any, Optional
from uuid import UUID
 
from pydantic import BaseModel, EmailStr, Field, field_validator
class JobOut(BaseModel):
    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    description: str
    portal: str
    url: str
    salary: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: Optional[Any] = None
    status: str
    scraped_at: datetime
    expires_at: Optional[datetime] = None
    match_score: Optional[float] = None
    match_reasons: Optional[list[str]] = None
    last_seen_at: Optional[datetime] = None
 
    model_config = {"from_attributes": True}
 
 
class JobFilter(BaseModel):
    portal: Optional[str] = None
    status: Optional[str] = None
    min_score: Optional[float] = None
    search: Optional[str] = None
    limit: int = Field(default=20, le=100)
    offset: int = Field(default=0, ge=0)