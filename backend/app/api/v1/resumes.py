"""
api/v1/resumes.py — Resume Upload & Management

IMPORTANT: Static/named routes (/upload, /template, /tailor-instant, /instant-download/...)
MUST be declared BEFORE the wildcard /{resume_id} route, otherwise FastAPI will try to
coerce the literal path segment (e.g. "template") into a UUID and return 422/404.
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas import ResumeOut, TemplateUpdateRequest
from app.services.pdf_service import get_pdf_service

router = APIRouter(prefix="/resumes", tags=["resumes"])
settings = get_settings()


# ── Pydantic models ───────────────────────────────────────────────────────────

class InstantTailorRequest(BaseModel):
    job_title: str = Field(default="Full-Stack Developer", description="Target job title")
    company: str = Field(default="", description="Company name")
    job_description: str = Field(..., min_length=10, description="Full Job Description text")
    instructions: str = Field(default="", description="Custom tailoring instructions or priorities")
    custom_template: str = Field(default="", description="Optional custom LaTeX (.tex) template string to use")


# ── Static / named routes (must come BEFORE /{resume_id}) ────────────────────

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

    # Pre-parse resume text and skills immediately so the user can run the pipeline or mock interview without delay
    raw_text = ""
    try:
        raw_text = pdf_service.extract_text(file_path)
    except Exception:
        pass

    from app.services.instant_tailor import extract_skills_from_jd
    extracted_skills = extract_skills_from_jd(raw_text) if raw_text else []
    skills_dict = {
        "languages": [s for s in extracted_skills if s in ["Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Rust"]],
        "frameworks": [s for s in extracted_skills if s in ["React.js", "Node.js", "Express.js", "FastAPI", "Django", "Spring Boot", "Next.js"]],
        "databases": [s for s in extracted_skills if s in ["PostgreSQL", "MySQL", "MongoDB", "Redis", "SQL"]],
        "tools": [s for s in extracted_skills if s in ["Docker", "Kubernetes", "AWS", "Git", "CI/CD", "GitHub Actions"]],
        "all": extracted_skills,
    }

    if set_primary:
        # Unset existing primary
        existing = await db.execute(select(Resume).where(Resume.user_id == user_id, Resume.is_primary == True))
        for r in existing.scalars().all():
            r.is_primary = False

    # Fetch user account details to personalize the template
    user_res = await db.execute(select(User).where(User.id == user_id))
    user_obj = user_res.scalar_one_or_none()
    user_name = user_obj.full_name if user_obj else "Candidate"
    user_email = user_obj.email if user_obj else ""

    # Parse candidate phone and contact details from raw_text
    import re as _re
    cand_phone = ""
    phone_m = _re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", raw_text)
    if phone_m:
        cand_phone = phone_m.group(0)

    # Extract email if present in resume, fallback to user_email
    email_m = _re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
    cand_email = email_m.group(0) if email_m else user_email

    # Auto-generate personalized LaTeX resume for this specific user
    try:
        from app.services.latex_resume import get_user_template_path, save_user_resume_template, ROHIT_TEMPLATE_PATH
        user_tpl = get_user_template_path(user_id)
        if not user_tpl.is_file():
            is_rohit = "rohit" in user_email.lower() or "rohit" in user_name.lower()
            if is_rohit and ROHIT_TEMPLATE_PATH.is_file():
                save_user_resume_template(user_id, ROHIT_TEMPLATE_PATH.read_text(encoding="utf-8"))
            else:
                from app.services.latex_generator import build_latex_from_candidate_data
                cand_tex = build_latex_from_candidate_data(
                    candidate_name=user_name,
                    email=cand_email,
                    phone=cand_phone,
                    skills=skills_dict,
                    summary=raw_text[:350] if raw_text else "",
                )
                save_user_resume_template(user_id, cand_tex)
    except Exception as _e:
        pass

    resume = Resume(
        user_id=user_id,
        file_path=file_path,
        original_filename=file.filename,
        raw_text=raw_text,
        skills=skills_dict,
        embedding_id=f"emb_{user_id}",
        is_parsed=bool(raw_text),
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


# ── Dynamic LaTeX Template Management ─────────────────────────────────────────

@router.get("/template", response_model=dict)
async def get_current_template(
    user_id: UUID = Depends(get_current_user_id),
):
    """Get the active resume template for the user (custom if set, else system default)."""
    from app.services.latex_resume import TEMPLATE_PATH, get_user_template_path, load_resume_template
    user_tpl_file = get_user_template_path(user_id)
    is_custom = user_tpl_file.is_file()
    active_template = load_resume_template(user_id)
    default_template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return {
        "template": active_template,
        "is_custom": is_custom,
        "default_template": default_template,
    }


@router.put("/template", response_model=dict)
async def update_custom_template(
    data: TemplateUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Validate and save a user's customized .tex resume template."""
    from app.services.latex_resume import save_user_resume_template
    from app.services.resume_edit import validate_tex

    problem = validate_tex(data.template)
    if problem:
        raise HTTPException(status_code=422, detail=f"Invalid LaTeX template: {problem}")

    save_user_resume_template(user_id, data.template)
    return {
        "message": "Template saved successfully",
        "is_custom": True,
        "template": data.template,
    }


@router.delete("/template", response_model=dict)
async def reset_template(
    user_id: UUID = Depends(get_current_user_id),
):
    """Reset the user's template to the system default master template."""
    from app.services.latex_resume import load_resume_template, reset_user_resume_template

    reset_user_resume_template(user_id)
    default_tpl = load_resume_template(None)
    return {
        "message": "Template reset to system default",
        "is_custom": False,
        "template": default_tpl,
    }


# ── Instant JD Resume Tailoring ───────────────────────────────────────────────

@router.post("/tailor-instant", response_model=dict)
async def tailor_resume_from_jd(
    data: InstantTailorRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Directly analyze a pasted Job Description (JD), extract matching & highlighted skills,
    intelligently tailor resume bullet points and summary, and render a high-quality PDF.
    """
    import uuid as _uuid
    from app.services.instant_tailor import format_resume_download_filename, generate_instant_tailored_pdf

    tailor_id = str(_uuid.uuid4())
    output_dir = Path(settings.UPLOAD_DIR) / str(user_id) / "instant_tailored"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"instant_{tailor_id}"

    pdf_path, tailor_data = generate_instant_tailored_pdf(
        job_title=data.job_title,
        company=data.company,
        job_description=data.job_description,
        output_dir=output_dir,
        stem=stem,
        instructions=data.instructions,
        user_id=user_id,
        custom_template=data.custom_template,
    )

    user_res = await db.execute(select(User).where(User.id == user_id))
    user_obj = user_res.scalar_one_or_none()
    candidate_name = user_obj.full_name if user_obj and user_obj.full_name else "Candidate"
    clean_filename = format_resume_download_filename(candidate_name=candidate_name, company=data.company)

    return {
        "tailor_id": tailor_id,
        "matched_skills": tailor_data["matched_skills"],
        "highlighted_skills": tailor_data["highlighted_skills"],
        "match_score": tailor_data["match_score"],
        "bullet_changes": tailor_data["bullet_changes"],
        "download_url": f"/api/v1/resumes/instant-download/{tailor_id}?name={clean_filename}",
        "filename": f"{clean_filename}.pdf",
    }


@router.get("/instant-download/{tailor_id}")
async def download_instant_tailored_resume(
    tailor_id: str,
    name: str = "Candidate_Resume",
    user_id: UUID = Depends(get_current_user_id),
):
    """Download the generated PDF for an instant JD tailoring session."""
    target_path = Path(settings.UPLOAD_DIR) / str(user_id) / "instant_tailored" / f"instant_{tailor_id}.pdf"
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Tailored resume not found or session expired")

    download_filename = f"{name}.pdf" if not name.endswith(".pdf") else name
    return FileResponse(
        path=str(target_path),
        filename=download_filename,
        media_type="application/pdf",
    )


# ── Wildcard routes (MUST be last — after all named/static routes) ─────────────

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
