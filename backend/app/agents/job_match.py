"""
agents/job_match.py — Job Match Agent Node
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData, JobData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application
from app.models.job import Job
from app.services.llm_service import JOB_SKILL_EXTRACTION_SYSTEM_PROMPT, get_llm_service
from app.services.vector_service import get_vector_service

logger = get_logger(__name__)
settings = get_settings()


async def job_match_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    logger.info("Job match node started", extra={"run_id": run_id})

    try:
        raw_jobs: list[JobData] = state.get("raw_jobs", [])
        resume_data = state.get("resume_data", {})
        threshold = state.get("match_threshold", settings.JOB_MATCH_THRESHOLD)

        if not raw_jobs:
            return {
                "scored_jobs": [],
                "jobs_above_threshold": [],
                "applications_to_process": [],
                "current_step": "job_match_complete_no_jobs",
            }

        if not resume_data.get("embedding_id"):
            return {
                "errors": [{"step": "job_match", "message": "Resume not analysed yet", "timestamp": datetime.now(timezone.utc).isoformat()}],
                "current_step": "job_match_failed",
                "should_stop": True,
            }

        llm = get_llm_service()
        vector_service = get_vector_service()

        # Re-embed the resume text for fresh comparison
        resume_vector = await llm.embed(resume_data.get("raw_text", "")[:4000])

        scored_jobs: list[JobData] = []
        above_threshold: list[JobData] = []
        applications_to_process: list[ApplicationData] = []

        for job in raw_jobs:
            try:
                # Get job vector from ChromaDB or recompute
                job_embed_text = f"{job['title']} {job['company']} {job['description']}"
                job_vector = await llm.embed(job_embed_text)

                score = await vector_service.compute_similarity_score(job_vector, resume_vector)

                # Also do keyword-based scoring boost
                keyword_score, matched_skills = _keyword_score(job, resume_data)
                final_score = round((score * 0.7) + (keyword_score * 0.3), 2)

                job["match_score"] = final_score
                job["match_reasons"] = _build_match_reasons(
                    matched_skills=matched_skills,
                    semantic_score=score,
                    keyword_score=keyword_score,
                )

                # Extract required skills from job description
                skill_data = await llm.generate_structured(
                    prompt=f"Extract required skills from:\n{job['description'][:2000]}",
                    system_prompt=JOB_SKILL_EXTRACTION_SYSTEM_PROMPT,
                    output_schema={
                        "required_skills": ["Python", "React"],
                        "nice_to_have": ["AWS"],
                        "experience_years": 3,
                        "job_type": "full-time",
                    },
                )
                job["required_skills"] = skill_data.get("required_skills", [])

                scored_jobs.append(job)

                # Update job status in DB
                await _update_job_score(job)

                if final_score >= threshold:
                    above_threshold.append(job)
                    # Create Application record
                    app_data = await _create_application(job, resume_data, state.get("user_id"))
                    if app_data:
                        applications_to_process.append(app_data)

                logger.info(
                    "Job scored",
                    extra={"job_id": job.get("id"), "title": job["title"], "score": final_score, "threshold": threshold, "above": final_score >= threshold},
                )

            except Exception as e:
                logger.warning("Job scoring failed", extra={"job": job.get("title"), "error": str(e)})
                continue

        scored_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        above_threshold.sort(key=lambda x: x.get("match_score", 0), reverse=True)

        logger.info(
            "Job match complete",
            extra={"run_id": run_id, "scored": len(scored_jobs), "above_threshold": len(above_threshold)},
        )

        return {
            "scored_jobs": scored_jobs,
            "jobs_above_threshold": above_threshold,
            "applications_to_process": applications_to_process,
            "current_step": "job_match_complete",
        }

    except Exception as e:
        logger.error("Job match node failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "job_match", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "job_match_failed",
        }


def _keyword_score(job: JobData, resume_data: dict) -> tuple[float, list[str]]:
    """Simple keyword overlap score (0-100) as a boost to vector similarity.

    Returns (score, matched_skills) so callers can explain the score.
    """
    skills_flat = []
    for skill_list in resume_data.get("skills", {}).values():
        if isinstance(skill_list, list):
            skills_flat.extend([s.lower() for s in skill_list])

    desc_lower = job.get("description", "").lower()
    if not skills_flat:
        return 50.0, []

    matched = [skill for skill in skills_flat if skill in desc_lower]
    score = min(100.0, (len(matched) / len(skills_flat)) * 100)
    return score, matched


def _build_match_reasons(matched_skills: list[str], semantic_score: float, keyword_score: float) -> list[str]:
    """Human-readable reasons behind a job's match score, for display in the UI."""
    reasons: list[str] = []

    if matched_skills:
        shown = matched_skills[:5]
        extra = len(matched_skills) - len(shown)
        skills_str = ", ".join(s.title() for s in shown)
        if extra > 0:
            skills_str += f" (+{extra} more)"
        reasons.append(f"Resume matches {len(matched_skills)} required skill(s): {skills_str}")
    else:
        reasons.append("No direct skill keyword overlap found in the job description")

    if semantic_score >= 75:
        reasons.append("Strong overall semantic match between resume and job description")
    elif semantic_score >= 50:
        reasons.append("Moderate semantic match between resume and job description")
    else:
        reasons.append("Weak semantic match between resume and job description")

    return reasons


async def _update_job_score(job: JobData) -> None:
    if not job.get("id"):
        return
    try:
        async with get_db_context() as db:
            result = await db.execute(select(Job).where(Job.id == uuid.UUID(job["id"])))
            db_job = result.scalar_one_or_none()
            if db_job:
                db_job.status = "matched"
                db_job.required_skills = job.get("required_skills", [])
                db_job.match_score = job.get("match_score")
                db_job.match_reasons = job.get("match_reasons", [])
    except Exception as e:
        logger.warning("Job DB update failed", extra={"error": str(e)})


async def _create_application(job: JobData, resume_data: dict, user_id: str) -> ApplicationData | None:
    try:
        async with get_db_context() as db:
            app = Application(
                user_id=uuid.UUID(user_id),
                job_id=uuid.UUID(job["id"]),
                resume_id=uuid.UUID(resume_data["resume_id"]),
                match_score=job["match_score"],
                status="pending_approval",
            )
            db.add(app)
            await db.flush()

            return ApplicationData(
                application_id=str(app.id),
                job=job,
                resume=resume_data,
                match_score=job["match_score"],
                status="pending_approval",
            )
    except Exception as e:
        logger.error("Application creation failed", extra={"error": str(e)})
        return None