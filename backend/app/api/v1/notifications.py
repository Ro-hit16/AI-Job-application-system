"""
api/v1/notifications.py — Notifications endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database import get_db
from app.models.notification import Notification
from app.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        query = query.where(Notification.is_read == False)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: UUID, user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id))
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        await db.commit()
        await db.refresh(notif)
    return notif


@router.patch("/read-all", response_model=dict)
async def mark_all_read(user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).where(Notification.user_id == user_id, Notification.is_read == False))
    count = 0
    for n in result.scalars().all():
        n.is_read = True
        count += 1
    await db.commit()
    return {"marked_read": count}