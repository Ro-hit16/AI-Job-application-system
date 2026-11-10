from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.interview import (
    delete_session,
    get_final_report,
    get_session,
    start_interview,
    submit_answer,
)
from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.job import Job
from app.models.resume import Resume

router = APIRouter(prefix="/interview", tags=["interview"])
logger = get_logger(__name__)


class StartInterviewRequest(BaseModel):
    job_id: Optional[str] = None          # Use existing job from DB
    job_title: Optional[str] = None       # Or enter manually
    company: Optional[str] = None
    job_description: Optional[str] = None
    technical_questions: int = 5
    hr_questions: int = 3
    resume_id: Optional[str] = None       # Use specific resume


class SubmitAnswerRequest(BaseModel):
    session_id: str
    answer: str


@router.post("/start")
async def start_interview_session(
    payload: StartInterviewRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Start a new mock interview session."""

    # Load resume
    if payload.resume_id:
        result = await db.execute(select(Resume).where(
            Resume.id == uuid.UUID(payload.resume_id),
            Resume.user_id == user_id,
        ))
    else:
        result = await db.execute(select(Resume).where(
            Resume.user_id == user_id,
            Resume.is_primary == True,
        ))
    resume = result.scalar_one_or_none()

    if not resume:
        # Try any resume
        result = await db.execute(select(Resume).where(Resume.user_id == user_id))
        resume = result.scalars().first()

    # Resolve resume text with resilient fallbacks
    resume_text = ""
    if resume and resume.raw_text:
        resume_text = resume.raw_text
    elif resume and getattr(resume, "file_path", None):
        try:
            from app.services.pdf_service import get_pdf_service
            resume_text = get_pdf_service().extract_text(resume.file_path)
        except Exception:
            pass

    if not resume_text:
        # Load from candidate master LaTeX template
        try:
            from app.services.latex_resume import load_resume_template
            resume_text = load_resume_template(user_id)
        except Exception:
            from app.models.user import User
            u_res = await db.execute(select(User).where(User.id == user_id))
            u_obj = u_res.scalar_one_or_none()
            u_name = u_obj.full_name if u_obj else "Candidate"
            resume_text = f"{u_name} - Software Developer. Core competencies: React, Node.js, Python, PostgreSQL, AWS, Docker."

    # Load job if job_id provided
    job_title = payload.job_title or "Software Developer"
    company = payload.company or "Tech Company"
    job_description = payload.job_description or ""

    if payload.job_id:
        job_result = await db.execute(select(Job).where(Job.id == uuid.UUID(payload.job_id)))
        job = job_result.scalar_one_or_none()
        if job:
            job_title = job.title
            company = job.company
            job_description = job.description

    try:
        session = await start_interview(
            resume_text=resume_text,
            job_title=job_title,
            company=company,
            job_description=job_description,
            technical_count=payload.technical_questions,
            hr_count=payload.hr_questions,
            user_id=str(user_id),
        )
        return session
    except Exception as e:
        logger.error("Failed to start interview", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")


@router.post("/answer")
async def submit_interview_answer(
    payload: SubmitAnswerRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Submit answer to current question and get evaluation + next question."""
    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    try:
        result = await submit_answer(payload.session_id, payload.answer)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Answer submission failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{session_id}")
async def get_interview_report(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Get final report after completing all questions."""
    try:
        report = await get_final_report(session_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Report generation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session_status(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Get current session status."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    questions = session.get("questions", [])
    curr_idx = session.get("current_index", 0)
    return {
        "session_id": session_id,
        "status": session.get("status", "in_progress"),
        "job_title": session.get("job_title", "Software Developer"),
        "company": session.get("company", "Tech Company"),
        "total_questions": len(questions),
        "answered": curr_idx,
        "remaining": max(0, len(questions) - curr_idx),
        "current_question": questions[curr_idx] if curr_idx < len(questions) else None,
    }


@router.delete("/session/{session_id}")
async def end_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """End and delete an interview session."""
    delete_session(session_id)
    return {"message": "Session ended"}


@router.get("/jobs/list")
async def list_jobs_for_interview(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get list of jobs to practice interview for."""
    result = await db.execute(
        select(Job).order_by(Job.scraped_at.desc()).limit(50)
    )
    jobs = result.scalars().all()
    return [
        {"id": str(j.id), "title": j.title, "company": j.company, "portal": j.portal}
        for j in jobs
    ]