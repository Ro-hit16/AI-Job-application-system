"""
agents/application.py — Application Agent Node (Playwright Form Fill)

Orchestration only. The actual browser automation lives in
app/services/apply_service.py, shared with the manual-approval API route
in app/api/v1/applications.py, so there is exactly one auto-apply
implementation instead of two that can drift apart.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application
from app.services.apply_service import ApplyInput, resolve_contact_email, submit_application

logger = get_logger(__name__)
settings = get_settings()


async def application_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    logger.info("Application node started", extra={"run_id": run_id})

    # Check human decision
    human_decision = state.get("human_decision")
    if settings.REQUIRE_HUMAN_APPROVAL and human_decision != "approve":
        reason = "rejected_by_user" if human_decision == "reject" else "no_decision"
        logger.info("Application skipped", extra={"reason": reason})
        return {
            "applications_rejected": state.get("applications_rejected", 0) + 1,
            "current_step": "application_skipped",
            "skip_application": True,
        }

    try:
        applications: list[ApplicationData] = state.get("applications_to_process", [])
        submitted_count = 0
        updated_apps: list[ApplicationData] = []

        for app_data in applications:
            if app_data.get("status") not in ("pending_approval", "approved"):
                continue

            try:
                result = await _submit_application(app_data, state)
                updated_apps.append(result)

                if result.get("status") == "submitted":
                    submitted_count += 1
                await _update_application_db(result)

            except Exception as e:
                logger.error("Application submission failed", extra={"error": str(e)})
                app_data["status"] = "failed"
                app_data["error_message"] = str(e)
                await _update_application_db(app_data)
                updated_apps.append(app_data)

        return {
            "applications_to_process": updated_apps,
            "current_application": updated_apps[0] if updated_apps else None,
            "applications_submitted": state.get("applications_submitted", 0) + submitted_count,
            "current_step": "application_complete",
        }

    except Exception as e:
        logger.error("Application node failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "application", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "application_failed",
        }


async def _submit_application(app_data: ApplicationData, state: AgentState) -> ApplicationData:
    job = app_data.get("job", {})
    resume_data = app_data.get("resume", {})
    contact_info = resume_data.get("contact_info", {}) or {}
    cover_letter = app_data.get("cover_letter_content", "")
    user_id = state.get("user_id", "unknown")

    # Resume-extracted email may be missing (LLM extraction isn't 100%
    # reliable) — fall back to the authenticated user's verified account
    # email before building ApplyInput. See resolve_contact_email() for
    # the full priority rules; it never overwrites a valid resume email.
    contact_info = await resolve_contact_email(contact_info, user_id)

    apply_input = ApplyInput(
        application_id=app_data.get("application_id", "unknown"),
        job_url=job.get("url", ""),
        portal=(job.get("portal") or "unknown").lower(),
        user_id=user_id,
        contact_info=contact_info,
        cover_letter=cover_letter,
        resume_file_path=resume_data.get("file_path"),
        application_questions=app_data.get("application_questions", []) or [],
        resume_context=resume_data.get("tailored_content", "") or resume_data.get("summary", ""),
        job_context=job.get("description", ""),
    )

    result = await submit_application(apply_input)

    app_data["status"] = result.status
    app_data["confirmation_number"] = result.confirmation_number
    app_data["confirmation_screenshot_path"] = result.screenshot_path
    app_data["error_message"] = result.error_message
    return app_data


async def _update_application_db(app_data: ApplicationData) -> None:
    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Application).where(Application.id == uuid.UUID(app_data["application_id"]))
            )
            app = result.scalar_one_or_none()
            if app:
                app.status = app_data.get("status", "failed")
                app.confirmation_number = app_data.get("confirmation_number")
                app.confirmation_screenshot_path = app_data.get("confirmation_screenshot_path")
                app.error_message = app_data.get("error_message")
                app.applied_at = datetime.now(timezone.utc) if app_data.get("status") == "submitted" else None
    except Exception as e:
        logger.error("Application DB update failed", extra={"error": str(e)})