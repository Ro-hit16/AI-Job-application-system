"""agents/resume_tailor.py — Resume Tailoring Agent Node"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application
from app.services.latex_resume import load_resume_template, render_tailored_resume_pdf
from app.services.llm_service import (
    COVER_LETTER_SYSTEM_PROMPT,
    RESUME_TAILOR_SYSTEM_PROMPT,
    get_llm_service,
)
from app.services.resume_edit import (
    apply_edits,
    build_tailor_prompt,
    extract_items,
    normalize_cover_letter,
    validate_pdf,
    validate_tex,
)

logger = get_logger(__name__)
settings = get_settings()
RESUME_TEMPLATE = load_resume_template()

# The UI keys off this prefix to show "generation failed".
TAILOR_ERROR_PREFIX = "Resume tailoring failed: "


class TailoringError(RuntimeError):
    pass


async def resume_tailor_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    logger.info("Resume tailor node started", extra={"run_id": run_id})

    applications: list[ApplicationData] = state.get("applications_to_process", [])
    if not applications:
        return {"current_step": "resume_tailor_skipped"}

    llm = get_llm_service()
    succeeded: list[ApplicationData] = []
    errors: list[dict] = []

    for app_data in applications:
        app_id = app_data.get("application_id")
        try:
            await _process_application(llm, state, app_data)
            succeeded.append(app_data)
            logger.info("Resume tailored", extra={"app_id": app_id, "run_id": run_id})
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e) or repr(e)}"
            logger.exception("Tailoring failed", extra={"app_id": app_id, "run_id": run_id})
            errors.append(
                {
                    "step": "resume_tailor",
                    "application_id": str(app_id),
                    "message": msg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            if app_id:
                await _record_failure(str(app_id), msg)

    logger.info(
        "Resume tailor finished",
        extra={"run_id": run_id, "succeeded": len(succeeded), "failed": len(errors)},
    )

    if not succeeded:
        return {
            "applications_to_process": [],
            "errors": errors,
            "last_error": errors[-1]["message"],
            "current_step": "resume_tailor_failed",
        }

    result = {"applications_to_process": succeeded, "current_step": "resume_tailor_complete"}
    if errors:  # partial: failed apps are excluded from the pipeline and recorded
        result["errors"] = errors
    return result


async def _process_application(llm, state: AgentState, app_data: ApplicationData) -> None:
    app_id = app_data.get("application_id")
    try:
        app_id = str(uuid.UUID(str(app_id)))
    except (ValueError, TypeError):
        raise TailoringError("application_id missing or invalid in pipeline state")

    job = app_data.get("job", {})
    resume = app_data.get("resume", {})
    job_title, company = job.get("title", ""), job.get("company", "")
    job_desc = job.get("description", "")
    resume_text = resume.get("raw_text", "")
    if not resume_text.strip():
        raise TailoringError("resume has no text to tailor from")

    tex = await _tailor_latex(
        llm, job_title, company, job_desc, resume_text, state.get("human_edit_instructions", "")
    )
    problem = validate_tex(tex)
    if problem:
        raise TailoringError(problem)

    output_dir = Path(settings.UPLOAD_DIR) / state.get("user_id", "unknown") / "tailored"
    output_dir.mkdir(parents=True, exist_ok=True)

    # pdflatex blocks; keep it off the event loop.
    pdf_path, compile_log, tex_path = await asyncio.to_thread(
        render_tailored_resume_pdf, tex, output_dir, app_id
    )
    selected = _select_resume_artifact(pdf_path, tex_path, compile_log, app_id)

    cover_path, cover_text = None, None
    try:
        raw = await llm.generate(
            _cover_prompt(job_title, company, job_desc, resume_text),
            COVER_LETTER_SYSTEM_PROMPT,
            max_tokens=600,
            temperature=0.4,
        )
        cover_text = normalize_cover_letter(raw)
        cover_file = output_dir / f"cover_{app_id}.txt"
        cover_file.write_text(cover_text, encoding="utf-8")
        cover_path = str(cover_file)
    except Exception as e:  # cover letter is optional; the resume is still valid
        logger.warning("Cover letter skipped", extra={"app_id": app_id, "error": str(e)})

    await _save_result(app_id, str(pdf_path), cover_path)  # raises if the row is missing

    app_data["application_id"] = app_id
    app_data["tailored_resume_path"] = str(pdf_path)
    app_data["cover_letter_path"] = cover_path
    app_data["tailored_content"] = tex
    app_data["cover_letter_content"] = cover_text


async def _tailor_latex(llm, job_title, company, job_desc, resume_text, edit_instructions) -> str:
    items = extract_items(RESUME_TEMPLATE)
    if not items:
        raise TailoringError("template has no \\resumeItem lines; cannot tailor")

    prompt = build_tailor_prompt(job_title, company, job_desc, resume_text, items, edit_instructions)
    problem = "model returned no usable edits"
    for attempt in (1, 2):
        hint = "" if attempt == 1 else (
            "\n\nYour previous answer was unusable. Return ONLY the JSON object and do not "
            "add technologies or numbers that are not in the background."
        )
        raw = await llm.generate(
            prompt + hint, RESUME_TAILOR_SYSTEM_PROMPT, max_tokens=900, json_mode=True
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            problem = f"model returned invalid JSON ({e})"
            continue
        edits = data.get("items") if isinstance(data, dict) else None
        if not isinstance(edits, list):
            problem = "model JSON has no 'items' list"
            continue
        new_tex, applied, rejected = apply_edits(RESUME_TEMPLATE, items, edits, resume_text)
        if rejected:
            logger.info("Rejected bullet edits", extra={"rejected": rejected})
        if applied:
            return new_tex
        problem = "all edits rejected: " + "; ".join(rejected[:3]) if rejected else problem
    raise TailoringError(problem)


def _cover_prompt(job_title, company, job_desc, resume_text) -> str:
    return f"""Write a cover letter for the position of {job_title} at {company}.

Job description (key points):
{job_desc[:1200]}

Candidate background (use only these facts):
{resume_text[:1500]}

Format: greeting line, then exactly 3 short paragraphs separated by one blank line,
then "Sincerely," on its own line. Add the candidate's name only if it appears in the
background above; otherwise omit it. Plain text, no placeholders."""


async def _save_result(app_id: str, resume_path: str, cover_path: str | None) -> None:
    async with get_db_context() as db:
        result = await db.execute(select(Application).where(Application.id == uuid.UUID(app_id)))
        app = result.scalar_one_or_none()
        if app is None:
            raise TailoringError(f"Application {app_id} not found in database")
        app.tailored_resume_path = resume_path
        if cover_path:
            app.cover_letter_path = cover_path
        if app.error_message and app.error_message.startswith(TAILOR_ERROR_PREFIX):
            app.error_message = None

def _select_resume_artifact(pdf_path, tex_path, compile_log, app_id) -> Path:
    """Return the validated PDF, else the validated .tex fallback, else raise."""
    pdf_problem = validate_pdf(pdf_path, compile_log)
    if pdf_problem is None:
        return Path(pdf_path)

    logger.error(
        "Resume PDF invalid; trying .tex fallback",
        extra={"app_id": app_id, "problem": pdf_problem,
               "compile_log": (compile_log or "")[-1500:]},
    )
    if tex_path is None:
        raise TailoringError(f"{pdf_problem}; no .tex file was kept")
    tex_file = Path(tex_path)
    try:
        content = tex_file.read_text(encoding="utf-8") if tex_file.is_file() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise TailoringError(f"{pdf_problem}; .tex unreadable: {e}") from e
    tex_problem = validate_tex(content)
    if tex_problem:
        raise TailoringError(f"{pdf_problem}; .tex fallback invalid: {tex_problem}")
    logger.warning("Using .tex fallback", extra={"app_id": app_id, "tex": str(tex_file)})
    return tex_file
async def _record_failure(app_id: str, message: str) -> None:
    """Record the failure on the row; never touches status or any existing paths."""
    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Application).where(Application.id == uuid.UUID(app_id))
            )
            app = result.scalar_one_or_none()
            if app is not None:
                app.error_message = (TAILOR_ERROR_PREFIX + message)[:1000]
    except Exception as e:
        logger.error("Could not record tailoring failure", extra={"app_id": app_id, "error": str(e)})