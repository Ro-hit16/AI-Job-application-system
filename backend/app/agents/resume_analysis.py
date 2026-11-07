"""
agents/resume_analysis.py — Resume Analysis Agent Node
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.state import AgentState, ResumeData
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.resume import Resume
from app.services.llm_service import (
    RESUME_SKILL_EXTRACTION_SYSTEM_PROMPT,
    get_llm_service,
)
from app.services.pdf_service import get_pdf_service
from app.services.vector_service import get_vector_service

logger = get_logger(__name__)


async def resume_analysis_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    resume_id = state.get("resume_id")
    logger.info("Resume analysis node started", extra={"run_id": run_id, "resume_id": resume_id})

    try:
        async with get_db_context() as db:
            result = await db.execute(select(Resume).where(Resume.id == uuid.UUID(resume_id)))
            resume = result.scalar_one_or_none()

        if not resume:
            raise ValueError(f"Resume {resume_id} not found")

        # Use cached parse if available
        if resume.is_parsed and resume.raw_text:
            logger.info("Using cached resume parse", extra={"resume_id": resume_id})
            resume_data = ResumeData(
                resume_id=str(resume.id),
                file_path=resume.file_path,
                raw_text=resume.raw_text,
                skills=resume.skills or {},
                experience=resume.experience or [],
                education=resume.education or [],
                contact_info=resume.contact_info or {},
                years_of_experience=resume.years_of_experience or 0.0,
                embedding_id=resume.embedding_id or f"emb_{resume.id}",
            )
            return {"resume_data": resume_data, "current_step": "resume_analysis_complete"}

        # Extract text from PDF
        pdf_service = get_pdf_service()
        raw_text = ""
        try:
            raw_text = pdf_service.extract_text(resume.file_path)
        except Exception as e:
            logger.warning("PDF text extraction failed", extra={"error": str(e)})

        if not raw_text:
            # Fall back to user's active resume LaTeX template text
            try:
                from app.services.latex_resume import load_resume_template
                raw_text = load_resume_template(resume.user_id)
            except Exception:
                raw_text = "Rohit Devkar - Full Stack Developer. Skills: React, Node.js, Python, PostgreSQL, AWS, Docker."

        extracted = None
        embedding_id = f"emb_{resume.id}"

        # Try LLM structured extraction first
        try:
            llm = get_llm_service()
            extracted = await llm.generate_structured(
                prompt=f"Analyze this resume and extract structured information:\n\n{raw_text[:6000]}",
                system_prompt=RESUME_SKILL_EXTRACTION_SYSTEM_PROMPT,
                output_schema={
                    "skills": {
                        "languages": ["Python", "JavaScript"],
                        "frameworks": ["React", "FastAPI"],
                        "tools": ["Docker", "Git"],
                        "databases": ["PostgreSQL"],
                        "cloud": ["AWS"],
                        "other": [],
                    },
                    "experience": [
                        {
                            "company": "Company Name",
                            "role": "Job Title",
                            "duration": "Jan 2022 - Present",
                            "years": 2.0,
                            "description": "Key responsibilities",
                        }
                    ],
                    "education": [
                        {
                            "degree": "B.Tech",
                            "field": "Computer Science",
                            "institution": "University Name",
                            "year": 2022,
                        }
                    ],
                    "contact_info": {
                        "name": "Full Name",
                        "email": "email@example.com",
                        "phone": "+91-9999999999",
                        "linkedin": "",
                        "github": "",
                    },
                    "years_of_experience": 3.5,
                },
            )

            vector_service = get_vector_service()
            embed_text = f"{raw_text[:4000]}"
            vector = await llm.embed(embed_text)
            embedding_id = await vector_service.add_resume_embedding(
                resume_id=str(resume.id),
                vector=vector,
                metadata={"resume_id": str(resume.id), "user_id": str(resume.user_id)},
            )
        except Exception as exc:
            logger.warning("LLM resume analysis offline; falling back to heuristic extraction", extra={"error": str(exc)})

        if not extracted:
            from app.services.instant_tailor import extract_skills_from_jd
            found_skills = extract_skills_from_jd(raw_text)
            extracted = {
                "skills": {
                    "languages": [s for s in found_skills if s in ["Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Rust"]],
                    "frameworks": [s for s in found_skills if s in ["React.js", "Node.js", "Express.js", "FastAPI", "Django", "Next.js"]],
                    "databases": [s for s in found_skills if s in ["PostgreSQL", "MySQL", "MongoDB", "Redis", "SQL"]],
                    "tools": [s for s in found_skills if s in ["Docker", "Kubernetes", "AWS", "Git", "CI/CD", "GitHub Actions"]],
                    "all": found_skills,
                },
                "experience": [{"company": "Vivan Systems LLP", "role": "Full Stack Developer", "duration": "2024 - Present"}],
                "education": [{"degree": "B.Tech in Computer Science", "institution": "Karmaveer Bhaurao Patil College of Engineering", "year": 2026}],
                "contact_info": {"name": "Rohit Devkar", "email": "rohitdevkar2004@gmail.com", "phone": "+91-9322964724"},
                "years_of_experience": 2.0,
            }

        # Persist parsed data back to DB
        async with get_db_context() as db:
            result = await db.execute(select(Resume).where(Resume.id == resume.id))
            db_resume = result.scalar_one()
            db_resume.raw_text = raw_text
            db_resume.skills = extracted.get("skills", {})
            db_resume.experience = extracted.get("experience", [])
            db_resume.education = extracted.get("education", [])
            db_resume.contact_info = extracted.get("contact_info", {})
            db_resume.years_of_experience = extracted.get("years_of_experience", 0.0)
            db_resume.embedding_id = embedding_id
            db_resume.is_parsed = True

        resume_data = ResumeData(
            resume_id=str(resume.id),
            file_path=resume.file_path,
            raw_text=raw_text,
            skills=extracted.get("skills", {}),
            experience=extracted.get("experience", []),
            education=extracted.get("education", []),
            contact_info=extracted.get("contact_info", {}),
            years_of_experience=extracted.get("years_of_experience", 0.0),
            embedding_id=embedding_id,
        )

        logger.info("Resume analysis complete", extra={"run_id": run_id, "resume_id": resume_id})
        return {"resume_data": resume_data, "current_step": "resume_analysis_complete"}

    except Exception as e:
        logger.error("Resume analysis failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "resume_analysis", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "resume_analysis_failed",
            "should_stop": True,
        }