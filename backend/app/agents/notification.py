"""
agents/notification.py — Notification Agent Node
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
 
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application
from app.models.notification import Notification
from app.services.notification_service import get_notification_service

logger = get_logger(__name__)
settings = get_settings()


async def notification_node(state: AgentState) -> dict:
    """Pre-apply notification: alert user and set awaiting_human_approval flag."""
    run_id = state.get("run_id", "unknown")
    logger.info("Notification node started", extra={"run_id": run_id})

    try:
        applications: list[ApplicationData] = state.get("applications_to_process", [])
        notif_service = get_notification_service()
        sent_ids: list[str] = []

        for app_data in applications:
            try:
                job = app_data.get("job", {})
                app_id = app_data.get("application_id", "")
                score = app_data.get("match_score", 0)

                if settings.REQUIRE_HUMAN_APPROVAL:
                    # Notify user that approval is needed
                    await notif_service.notify_approval_required(
                        job_title=job.get("title", "Unknown"),
                        company=job.get("company", "Unknown"),
                        app_id=app_id,
                    )
                    notif_id = await _store_notification(
                        user_id=state.get("user_id"),
                        application_id=app_id,
                        notif_type="approval_required",
                        title=f"Approval Required: {job.get('title')} at {job.get('company')}",
                        message=f"Match score: {score:.1f}%. Review and approve to apply.",
                        payload={"job": job, "score": score},
                    )
                else:
                    # No approval needed — just notify
                    await notif_service.notify_new_match(
                        job_title=job.get("title", "Unknown"),
                        company=job.get("company", "Unknown"),
                        score=score,
                    )
                    notif_id = await _store_notification(
                        user_id=state.get("user_id"),
                        application_id=app_id,
                        notif_type="new_match",
                        title=f"New Match: {job.get('title')} at {job.get('company')}",
                        message=f"Match score: {score:.1f}%",
                        payload={"job": job, "score": score},
                    )

                if notif_id:
                    sent_ids.append(notif_id)

            except Exception as e:
                logger.error("Notification send failed", extra={"error": str(e)})
                continue

        needs_approval = settings.REQUIRE_HUMAN_APPROVAL and bool(applications)

        return {
            "notifications_sent": sent_ids,
            "awaiting_human_approval": needs_approval,
            "current_step": "awaiting_approval" if needs_approval else "notification_complete",
        }

    except Exception as e:
        logger.error("Notification node failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "notification", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "notification_failed",
        }


async def post_apply_notification_node(state: AgentState) -> dict:
    """Post-apply notification: inform user of submission result."""
    run_id = state.get("run_id", "unknown")
    notif_service = get_notification_service()
    current_app: ApplicationData = state.get("current_application", {})

    if not current_app:
        return {"current_step": "post_notify_skipped"}

    try:
        job = current_app.get("job", {})
        status = current_app.get("status", "unknown")

        if status == "submitted":
            await notif_service.notify_application_submitted(
                job_title=job.get("title", "Unknown"),
                company=job.get("company", "Unknown"),
                confirmation=current_app.get("confirmation_number", "N/A"),
            )
        elif status == "failed":
            await notif_service.notify_application_failed(
                job_title=job.get("title", "Unknown"),
                company=job.get("company", "Unknown"),
                error=current_app.get("error_message", "Unknown error"),
            )

        return {"current_step": "post_notification_complete"}

    except Exception as e:
        logger.error("Post-apply notification failed", extra={"error": str(e)})
        return {"current_step": "post_notification_failed"}


async def _store_notification(
    user_id: str,
    application_id: str,
    notif_type: str,
    title: str,
    message: str,
    payload: dict,
) -> str | None:
    try:
        async with get_db_context() as db:
            notif = Notification(
                user_id=uuid.UUID(user_id),
                application_id=uuid.UUID(application_id) if application_id else None,
                notification_type=notif_type,
                channel="email",
                title=title,
                message=message,
                payload=payload,
                is_sent=True,
                sent_at=datetime.now(timezone.utc),
            )
            db.add(notif)
            await db.flush()
            return str(notif.id)
    except Exception as e:
        logger.error("Notification store failed", extra={"error": str(e)})
        return None
    
class NotificationOut(BaseModel):
    id: UUID
    notification_type: str
    channel: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
 
    model_config = {"from_attributes": True}