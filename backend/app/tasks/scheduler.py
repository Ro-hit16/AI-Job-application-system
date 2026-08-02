"""
tasks/scheduler.py — APScheduler periodic job scraping
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.resume import Resume
from app.models.user import User

logger = get_logger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


async def scheduled_pipeline_run():
    """Called by APScheduler every SCRAPE_INTERVAL_MINUTES minutes."""
    logger.info("Scheduled pipeline run starting")
    try:
        from app.agents.supervisor import run_agent_pipeline
        from sqlalchemy import select

        async with get_db_context() as db:
            users = await db.execute(select(User).where(User.is_active == True))
            for user in users.scalars().all():
                resumes = await db.execute(
                    select(Resume).where(Resume.user_id == user.id, Resume.is_primary == True, Resume.is_parsed == True)
                )
                resume = resumes.scalar_one_or_none()
                if resume:
                    await run_agent_pipeline(
                        user_id=str(user.id),
                        resume_id=str(resume.id),
                        triggered_by="scheduler",
                    )
                    logger.info("Scheduled run complete", extra={"user_id": str(user.id)})
    except Exception as e:
        logger.error("Scheduled run failed", extra={"error": str(e)})


def start_scheduler():
    scheduler.add_job(
        scheduled_pipeline_run,
        trigger=IntervalTrigger(minutes=settings.SCRAPE_INTERVAL_MINUTES),
        id="pipeline_run",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started", extra={"interval_minutes": settings.SCRAPE_INTERVAL_MINUTES})


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")