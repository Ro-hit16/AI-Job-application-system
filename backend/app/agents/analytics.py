"""
agents/analytics.py — Analytics Agent Node
"""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.agent_log import AgentLog
from app.models.application import Application

logger = get_logger(__name__)


async def analytics_node(state: AgentState) -> dict:
    run_id = state.get("run_id", "unknown")
    user_id = state.get("user_id")
    logger.info("Analytics node started", extra={"run_id": run_id})

    try:
        submitted = state.get("applications_submitted", 0)
        rejected = state.get("applications_rejected", 0)
        found = state.get("jobs_found_count", 0)
        new_jobs = state.get("jobs_new_count", 0)
        errors = state.get("errors", [])

        # Compute lifetime stats for summary
        stats = await _get_user_stats(user_id)

        summary = (
            f"Run {run_id[:8]} complete. "
            f"Scraped {found} jobs ({new_jobs} new). "
            f"Submitted {submitted} applications, rejected {rejected}. "
            f"Lifetime: {stats.get('total_submitted', 0)} submitted, "
            f"{stats.get('success_rate', 0):.0f}% response rate."
        )
        if errors:
            summary += f" {len(errors)} error(s) encountered."

        # Store agent log
        await _store_agent_log(
            agent_name="analytics",
            run_id=run_id,
            user_id=user_id,
            status="success" if not errors else "partial",
            input_data={"jobs_found": found, "new_jobs": new_jobs},
            output_data={
                "submitted": submitted,
                "rejected": rejected,
                "summary": summary,
                "stats": stats,
            },
        )

        logger.info("Analytics complete", extra={"run_id": run_id, "summary": summary})
        return {"summary": summary, "current_step": "complete"}

    except Exception as e:
        logger.error("Analytics node failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "summary": f"Run {run_id[:8]} completed with analytics error: {str(e)}",
            "current_step": "complete",
        }


async def _get_user_stats(user_id: str) -> dict:
    try:
        async with get_db_context() as db:
            total = await db.execute(
                select(func.count(Application.id)).where(Application.user_id == user_id)
            )
            submitted = await db.execute(
                select(func.count(Application.id)).where(
                    Application.user_id == user_id,
                    Application.status == "submitted",
                )
            )
            avg_score = await db.execute(
                select(func.avg(Application.match_score)).where(Application.user_id == user_id)
            )

            total_count = total.scalar() or 0
            submitted_count = submitted.scalar() or 0
            avg = avg_score.scalar() or 0.0

            return {
                "total_submitted": submitted_count,
                "total_applications": total_count,
                "avg_match_score": round(float(avg), 1),
                "success_rate": round((submitted_count / total_count * 100) if total_count else 0, 1),
            }
    except Exception as e:
        logger.warning("Stats query failed", extra={"error": str(e)})
        return {}


async def _store_agent_log(
    agent_name: str,
    run_id: str,
    user_id: str,
    status: str,
    input_data: dict,
    output_data: dict,
) -> None:
    try:
        async with get_db_context() as db:
            log = AgentLog(
                agent_name=agent_name,
                run_id=run_id,
                user_id=user_id,
                status=status,
                input_data=input_data,
                output_data=output_data,
                finished_at=datetime.now(timezone.utc),
            )
            db.add(log)
    except Exception as e:
        logger.warning("Agent log store failed", extra={"error": str(e)})