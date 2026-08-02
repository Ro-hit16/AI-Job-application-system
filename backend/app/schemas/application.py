class ApplicationOut(BaseModel):
    id: UUID
    job_id: UUID
    resume_id: Optional[UUID] = None
    match_score: Optional[float] = None
    status: str
    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    confirmation_number: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    applied_at: Optional[datetime] = None
 
    model_config = {"from_attributes": True}
 
 
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
 
from pydantic import BaseModel, EmailStr, Field, field_validator
class ApprovalAction(BaseModel):
    decision: str = Field(description="approve | reject")
    edit_instructions: Optional[str] = None
 
    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        return v
 