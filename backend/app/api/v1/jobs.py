"""
api/v1/jobs.py — Job listing endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database import get_db
from app.models.job import Job
from app.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=list[JobOut])
async def list_jobs(
    portal: str | None = None,
    status: str | None = None,
    search: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Rank by match_score (nulls last) so freshly-matched jobs surface first;
    # falls back to recency for jobs that haven't been scored yet.
    query = select(Job).order_by(Job.match_score.desc().nullslast(), Job.scraped_at.desc())
    if portal:
        query = query.where(Job.portal == portal)
    if status:
        query = query.where(Job.status == status)
    if search:
        query = query.where(or_(Job.title.ilike(f"%{search}%"), Job.company.ilike(f"%{search}%")))
    if min_score is not None:
        query = query.where(Job.match_score >= min_score)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: UUID, user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/resume/download")
async def download_job_tailored_resume(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a tailored PDF resume directly for any job listing."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    from app.config import get_settings
    from app.models.application import Application
    from app.services.instant_tailor import auto_ensure_application_pdf, generate_instant_tailored_pdf

    # Check if application exists
    app_res = await db.execute(
        select(Application).where(Application.job_id == job_id, Application.user_id == user_id)
    )
    from app.services.instant_tailor import format_resume_download_filename

    job_res = await db.execute(select(Job).where(Job.id == job_id))
    job = job_res.scalar_one_or_none()
    company = job.company if job else ""
    clean_name = format_resume_download_filename(candidate_name="Rohit Devkar", company=company)

    app = app_res.scalars().first()
    if app:
        pdf_path, _ = await auto_ensure_application_pdf(app.id, user_id, db)
        return FileResponse(
            path=str(pdf_path),
            filename=f"{clean_name}.pdf",
            media_type="application/pdf",
        )

    # If no application exists yet, generate tailored PDF on the fly for this job
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = get_settings()
    out_dir = Path(settings.UPLOAD_DIR) / str(user_id) / "tailored"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"job_resume_{job_id}"

    pdf_path, _ = generate_instant_tailored_pdf(
        job_title=job.title or "Software Engineer",
        company=job.company or "",
        job_description=job.description or "",
        output_dir=out_dir,
        stem=stem,
    )

    return FileResponse(
        path=str(pdf_path),
        filename=f"{clean_name}.pdf",
        media_type="application/pdf",
    )