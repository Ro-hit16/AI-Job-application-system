"""
agents/resume_tailor.py — Resume Tailoring Agent Node
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application
from app.services.llm_service import (
    COVER_LETTER_SYSTEM_PROMPT,
    RESUME_TAILOR_SYSTEM_PROMPT,
    get_llm_service,
)
from app.services.latex_resume import load_resume_template, render_tailored_resume_pdf

logger = get_logger(__name__)
settings = get_settings()
RESUME_TEMPLATE = load_resume_template()


async def resume_tailor_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    logger.info("Resume tailor node started", extra={"run_id": run_id})

    try:
        applications: list[ApplicationData] = state.get("applications_to_process", [])
        if not applications:
            return {"current_step": "resume_tailor_skipped"}

        llm = get_llm_service()
        updated_applications: list[ApplicationData] = []

        for app_data in applications:
            try:
                job = app_data.get("job", {})
                resume = app_data.get("resume", {})

                job_title = job.get("title", "")
                company = job.get("company", "")
                job_desc = job.get("description", "")[:3000]
                resume_text = resume.get("raw_text", "")[:3000]
                edit_instructions = state.get("human_edit_instructions", "")

                # Build tailoring prompt — LLM must edit CONTENT only,
                # inside the user's existing LaTeX template, and stay
                # on one page.
                tailor_prompt = f"""
Here is a LaTeX resume template (a single-page Overleaf resume):

{RESUME_TEMPLATE}

Job Title: {job_title}
Company: {company}

Job Description:
{job_desc}

Original Resume (plain text, for reference on background/details):
{resume_text}

{f"Additional Instructions: {edit_instructions}" if edit_instructions else ""}

Rewrite the CONTENT of the LaTeX resume above (professional summary, skills
emphasis, bullet point wording, ordering of relevant items) to best match
this job description. Keep relevant, truthful details from the original
resume where the template already covers them.

STRICT RULES:
- Output ONLY the complete, valid LaTeX document — from \\documentclass to
  \\end{{document}}. No commentary, no explanation, no markdown code fences.
- Keep the exact same LaTeX preamble, packages, formatting commands,
  section structure, and section order as the template. Do not add new
  sections, packages, or change formatting commands.
- The result MUST still fit on a single page — do not add more bullet
  points or content than the template already has; trim or tighten
  wording if needed to stay on one page.
- Only edit the actual resume content (summary text, bullet wording,
  skill emphasis) to better match the job description.
"""
                tailored_content = await llm.generate(
                    prompt=tailor_prompt,
                    system_prompt=RESUME_TAILOR_SYSTEM_PROMPT,
                )

                # Generate cover letter
                cover_prompt = f"""
Write a cover letter for:
Position: {job_title} at {company}

Job Description (key points):
{job_desc[:1500]}

Candidate Background:
{resume_text[:1500]}

Write a professional, concise cover letter (3 paragraphs max).
"""
                cover_letter = await llm.generate(
                    prompt=cover_prompt,
                    system_prompt=COVER_LETTER_SYSTEM_PROMPT,
                )

                # Save to files
                user_id = state.get("user_id", "unknown")
                app_id = app_data.get("application_id", str(uuid.uuid4()))
                output_dir = Path(settings.UPLOAD_DIR) / user_id / "tailored"
                output_dir.mkdir(parents=True, exist_ok=True)

                pdf_path, compile_log = render_tailored_resume_pdf(
                    tailored_content, output_dir, app_id
                )

                if pdf_path is None:
                    logger.error(
                        "Resume LaTeX failed to compile; skipping this application "
                        "rather than saving a broken resume",
                        extra={"app_id": app_id, "compile_log": compile_log[-1000:]},
                    )
                    continue

                resume_path = str(pdf_path)
                cover_path = str(output_dir / f"cover_{app_id}.txt")
                Path(cover_path).write_text(cover_letter, encoding="utf-8")

                # Update application record
                await _update_application(app_id, resume_path, cover_path)

                app_data["tailored_resume_path"] = resume_path
                app_data["cover_letter_path"] = cover_path
                app_data["tailored_content"] = tailored_content
                app_data["cover_letter_content"] = cover_letter
                updated_applications.append(app_data)

                logger.info(
                    "Resume tailored",
                    extra={"app_id": app_id, "job": job_title, "company": company},
                )

            except Exception as e:
                logger.error("Tailoring failed for app", extra={"error": str(e)})
                continue

        return {
            "applications_to_process": updated_applications,
            "current_step": "resume_tailor_complete",
        }

    except Exception as e:
        logger.error("Resume tailor node failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "resume_tailor", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "resume_tailor_failed",
        }


async def _update_application(app_id: str, resume_path: str, cover_path: str) -> None:
    try:
        async with get_db_context() as db:
            result = await db.execute(select(Application).where(Application.id == uuid.UUID(app_id)))
            app = result.scalar_one_or_none()
            if app:
                app.tailored_resume_path = resume_path
                app.cover_letter_path = cover_path
    except Exception as e:
        logger.warning("Application update failed", extra={"error": str(e)})