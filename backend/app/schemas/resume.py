from datetime import datetime
from typing import Any, Optional
from uuid import UUID
 
from pydantic import BaseModel, EmailStr, Field, field_validator

class ResumeOut(BaseModel):
    id: UUID
    original_filename: str
    file_path: str
    is_parsed: bool
    is_primary: bool
    skills: Optional[dict] = None
    experience: Optional[Any] = None
    years_of_experience: Optional[float] = None
    created_at: datetime
 
    model_config = {"from_attributes": True}