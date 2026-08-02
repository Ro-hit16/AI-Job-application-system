"""
api/v1/agents.py — Agent pipeline trigger & status
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor import run_agent_pipeline
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.resume import Resume
from app.schemas import PipelineStartRequest, PipelineStatusOut

router = APIRouter(prefix="/agents", tags=["agents"])

# In-memory run store (replace with Redis in production)
_run_store: dict[str, dict] = {}


import uuid as _uuid

@router.post("/run", response_model=PipelineStatusOut)
async def trigger_pipeline(
    payload: PipelineStartRequest,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Resume).where(Resume.id == payload.resume_id, Resume.user_id == user_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Generate run_id HERE, share it with both background task and response
    run_id = str(_uuid.uuid4())
    _run_store[run_id] = {"run_id": run_id, "status": "running"}

    async def _run():
        try:
            result = await run_agent_pipeline(
                user_id=str(user_id),
                resume_id=str(payload.resume_id),
                triggered_by="user",
                portals=payload.portals,
                categories=payload.categories,
                match_threshold=payload.match_threshold,
            )
            _run_store[run_id] = {**result, "run_id": run_id}
        except Exception as e:
            import traceback
            print("PIPELINE CRASH:", traceback.format_exc())  # ← add this
            _run_store[run_id] = {"run_id": run_id, "status": "failed", "error": str(e)}

    background_tasks.add_task(_run)
    return PipelineStatusOut(run_id=run_id, status="running")


@router.get("/status/{run_id}", response_model=PipelineStatusOut)
async def get_run_status(run_id: str, user_id: UUID = Depends(get_current_user_id)):
    run = _run_store.get(run_id)
    if not run:
        return PipelineStatusOut(run_id=run_id, status="running")
    return PipelineStatusOut(**run)
