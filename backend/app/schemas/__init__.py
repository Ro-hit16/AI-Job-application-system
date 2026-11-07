from uuid import UUID
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field, EmailStr


# ---------- User/Auth ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Resumes ----------

class ResumeOut(BaseModel):
    id: UUID
    original_filename: str = Field(alias="original_filename")
    is_primary: bool
    is_parsed: bool
    created_at: datetime

    @property
    def filename(self) -> str:
        return self.original_filename

    class Config:
        from_attributes = True
        populate_by_name = True


# ---------- Jobs ----------

class JobOut(BaseModel):
    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    salary: Optional[str] = None
    portal: Optional[str] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True


class JobSummary(BaseModel):
    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    portal: Optional[str] = None
    url: Optional[str] = None
    salary: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Notifications ----------

class NotificationOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    message: Optional[str] = None
    is_read: bool = False

    class Config:
        from_attributes = True


# ---------- Applications ----------

class ApplicationOut(BaseModel):
    id: UUID
    status: str
    match_score: Optional[float] = None
    created_at: datetime
    applied_at: Optional[datetime] = None
    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    job_id: Optional[UUID] = None
    resume_id: Optional[UUID] = None
    job: Optional[JobSummary] = None
    confirmation_number: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ApprovalAction(BaseModel):
    decision: str
    edit_instructions: Optional[str] = None


# ---------- Agent Pipeline ----------

class PipelineStartRequest(BaseModel):
    resume_id: UUID
    portals: List[str] = []
    categories: List[str] = []
    match_threshold: float = 0.7


class PipelineStatusOut(BaseModel):
    run_id: str
    status: str
    summary: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    template: str