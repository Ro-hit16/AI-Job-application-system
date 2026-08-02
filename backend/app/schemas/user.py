from datetime import datetime
from typing import Any, Optional
from uuid import UUID
 
from pydantic import BaseModel, EmailStr, Field, field_validator
 
 
# ─── Auth ─────────────────────────────────────────────────────────────────────
 
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
 
 
class UserLogin(BaseModel):
    email: EmailStr
    password: str
 
 
class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
 
    model_config = {"from_attributes": True}
 
 
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
 