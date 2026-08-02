"""
api/v1/resumes.py — Resume Upload & Management
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.resume import Resume
from app.schemas import ResumeOut
from app.services.pdf_service import get_pdf_service

router = APIRouter(prefix="/resumes", tags=["resumes"])
settings = get_settings()


@router.post("/upload", response_model=ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    set_primary: bool = True,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_SIZE_MB}MB)")

    pdf_service = get_pdf_service()
    file_path = pdf_service.save_upload(content, file.filename, str(user_id))

    if set_primary:
        # Unset existing primary
        existing = await db.execute(select(Resume).where(Resume.user_id == user_id, Resume.is_primary == True))
        for r in existing.scalars().all():
            r.is_primary = False

    resume = Resume(
        user_id=user_id,
        file_path=file_path,
        original_filename=file.filename,
        is_primary=set_primary,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return resume


@router.get("/", response_model=list[ResumeOut])
async def list_resumes(user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc()))
    return result.scalars().all()


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(resume_id: UUID, user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(resume_id: UUID, user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    await db.delete(resume)
    await db.commit()