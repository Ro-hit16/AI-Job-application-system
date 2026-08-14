# from __future__ import annotations

# import uuid
# from datetime import datetime, timezone

# from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.core.security import get_current_user_id
# from app.database import get_db, get_db_context
# from app.models.application import Application
# from app.models.job import Job
# from app.models.resume import Resume
# from app.schemas import ApplicationOut, ApprovalAction
# from app.core.logging import get_logger

# router = APIRouter(prefix="/applications", tags=["applications"])
# logger = get_logger(__name__)

# # Phrases that indicate REAL success on a confirmation page.
# # If none of these appear, we do NOT claim success.
# SUCCESS_INDICATORS = [
#     "application submitted", "application received", "thank you for applying",
#     "successfully applied", "your application has been sent", "application sent",
#     "we've received your application", "applied successfully", "thanks for applying",
#     "application complete", "submission successful",
# ]


# from sqlalchemy.orm import selectinload

# @router.get("/", response_model=list[ApplicationOut])
# async def list_applications(
#     status: str | None = None,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     query = (
#         select(Application)
#         .options(selectinload(Application.job))
#         .where(Application.user_id == user_id)
#         .order_by(Application.created_at.desc())
#     )
#     if status:
#         query = query.where(Application.status == status)
#     result = await db.execute(query)
#     return result.scalars().all()


# @router.get("/pending", response_model=list[ApplicationOut])
# async def list_pending_approvals(
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(
#         select(Application)
#         .options(selectinload(Application.job))
#         .where(Application.user_id == user_id, Application.status == "pending_approval")
#         .order_by(Application.created_at.desc())
#     )
#     return result.scalars().all()


# @router.get("/stats", response_model=dict)
# async def get_stats(
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(select(Application).where(Application.user_id == user_id))
#     apps = result.scalars().all()
#     return {
#         "total": len(apps),
#         "pending_approval": sum(1 for a in apps if a.status == "pending_approval"),
#         "approved": sum(1 for a in apps if a.status == "approved"),
#         "submitted": sum(1 for a in apps if a.status == "submitted"),
#         "needs_manual_review": sum(1 for a in apps if a.status == "needs_manual_review"),
#         "failed": sum(1 for a in apps if a.status == "failed"),
#         "rejected": sum(1 for a in apps if a.status == "rejected"),
#     }


# @router.get("/{application_id}", response_model=ApplicationOut)
# async def get_application(
#     application_id: uuid.UUID,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(
#         select(Application)
#         .options(selectinload(Application.job))
#         .where(Application.id == application_id, Application.user_id == user_id)
#     )
#     app = result.scalar_one_or_none()
#     if not app:
#         raise HTTPException(status_code=404, detail="Application not found")
#     return app


# @router.post("/{application_id}/approve", response_model=dict)
# async def approve_application(
#     application_id: uuid.UUID,
#     payload: ApprovalAction,
#     background_tasks: BackgroundTasks,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(
#         select(Application).where(Application.id == application_id, Application.user_id == user_id)
#     )
#     app = result.scalar_one_or_none()
#     if not app:
#         raise HTTPException(status_code=404, detail="Application not found")
#     if app.status not in ("pending_approval", "approved"):
#         raise HTTPException(status_code=409, detail=f"Application is '{app.status}', cannot approve")

#     if payload.decision == "approve":
#         app.status = "approved"
#         app.approved_at = datetime.now(timezone.utc)
#         app.reviewer_notes = payload.edit_instructions
#         await db.commit()
#         background_tasks.add_task(_submit_application_background, str(application_id), str(user_id))
#         return {
#             "status": "approved",
#             "message": "Approved. Attempting submission — check status shortly. Verify via screenshot before trusting it went through.",
#             "application_id": str(application_id),
#         }
#     else:
#         app.status = "rejected"
#         app.reviewer_notes = payload.edit_instructions
#         await db.commit()
#         return {"status": "rejected", "message": "Application rejected."}


# @router.post("/approve-all", response_model=dict)
# async def approve_all_pending(
#     background_tasks: BackgroundTasks,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(
#         select(Application).where(Application.user_id == user_id, Application.status == "pending_approval")
#     )
#     apps = result.scalars().all()
#     if not apps:
#         return {"message": "No pending applications", "count": 0}

#     app_ids = []
#     for app in apps:
#         app.status = "approved"
#         app.approved_at = datetime.now(timezone.utc)
#         app_ids.append(str(app.id))
#     await db.commit()

#     for app_id in app_ids:
#         background_tasks.add_task(_submit_application_background, app_id, str(user_id))

#     return {"message": f"Approved {len(app_ids)} applications.", "count": len(app_ids), "application_ids": app_ids}


# @router.post("/submit-approved", response_model=dict)
# async def submit_all_approved(
#     background_tasks: BackgroundTasks,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(
#         select(Application).where(Application.user_id == user_id, Application.status == "approved")
#     )
#     apps = result.scalars().all()
#     if not apps:
#         return {"message": "No approved applications waiting", "count": 0}

#     for app in apps:
#         background_tasks.add_task(_submit_application_background, str(app.id), str(user_id))

#     return {"message": f"Attempting {len(apps)} submissions in background.", "count": len(apps)}


# @router.post("/{application_id}/mark-manual-applied", response_model=dict)
# async def mark_manually_applied(
#     application_id: uuid.UUID,
#     user_id: uuid.UUID = Depends(get_current_user_id),
#     db: AsyncSession = Depends(get_db),
# ):
#     """Use this AFTER you've manually applied yourself and confirmed it on the portal."""
#     result = await db.execute(
#         select(Application).where(Application.id == application_id, Application.user_id == user_id)
#     )
#     app = result.scalar_one_or_none()
#     if not app:
#         raise HTTPException(status_code=404, detail="Application not found")
#     app.status = "submitted"
#     app.confirmation_number = "MANUAL-CONFIRMED"
#     app.applied_at = datetime.now(timezone.utc)
#     await db.commit()
#     return {"status": "submitted", "message": "Marked as manually confirmed applied."}


# # ─── Background submission with HONEST verification ──────────────────────────

# async def _submit_application_background(application_id: str, user_id: str) -> None:
#     logger.info("Background submission started", extra={"app_id": application_id})
#     try:
#         async with get_db_context() as db:
#             result = await db.execute(select(Application).where(Application.id == uuid.UUID(application_id)))
#             app = result.scalar_one_or_none()
#             if not app:
#                 return
#             job_result = await db.execute(select(Job).where(Job.id == app.job_id))
#             job = job_result.scalar_one_or_none()
#             resume_result = await db.execute(select(Resume).where(Resume.id == app.resume_id))
#             resume = resume_result.scalar_one_or_none()

#         if not job:
#             await _update_result(application_id, "failed", error="Job not found in database")
#             return

#         contact_info = resume.contact_info if resume and resume.contact_info else {}

#         cover_letter = ""
#         if app.cover_letter_path:
#             try:
#                 from pathlib import Path
#                 cover_letter = Path(app.cover_letter_path).read_text(encoding="utf-8")
#             except Exception:
#                 pass

#         result = await _attempt_submission(
#             application_id=application_id,
#             job_url=job.url,
#             portal=job.portal,
#             contact_info=contact_info,
#             cover_letter=cover_letter,
#             user_id=user_id,
#         )

#         await _update_result(
#             application_id,
#             result["status"],
#             confirmation=result.get("confirmation_number"),
#             error=result.get("error_message"),
#             screenshot=result.get("screenshot_path"),
#         )

#         from app.services.notification_service import get_notification_service
#         notif = get_notification_service()

#         if result["status"] == "submitted":
#             await notif.notify_application_submitted(
#                 job_title=job.title, company=job.company,
#                 confirmation=result.get("confirmation_number", "Verified on page"),
#             )
#         elif result["status"] == "needs_manual_review":
#             await notif.send_email(
#                 subject=f"⚠️ Needs your review: {job.title} at {job.company}",
#                 body=f"""
#                 <h2>Could not confirm automatic submission</h2>
#                 <p><strong>{job.title}</strong> at <strong>{job.company}</strong></p>
#                 <p>Reason: {result.get('error_message', 'No success confirmation detected on page')}</p>
#                 <p>This usually means the form requires login, has a custom layout, or needs a CAPTCHA.</p>
#                 <p><strong>Please apply manually:</strong> <a href="{job.url}">{job.url}</a></p>
#                 <p>A screenshot of what the bot saw is saved on your server for reference.</p>
#                 """,
#             )
#         else:
#             await notif.notify_application_failed(
#                 job_title=job.title, company=job.company,
#                 error=result.get("error_message", "Unknown error"),
#             )

#     except Exception as e:
#         import traceback
#         full_error = traceback.format_exc()
#         logger.error("Playwright submission failed", extra={"full_traceback": full_error})
#         return {"status": "failed", "error_message": f"Playwright error: {repr(e)} | {full_error}"}


# async def _update_result(application_id: str, status: str, confirmation: str | None = None,
#                           error: str | None = None, screenshot: str | None = None) -> None:
#     try:
#         async with get_db_context() as db:
#             result = await db.execute(select(Application).where(Application.id == uuid.UUID(application_id)))
#             app = result.scalar_one_or_none()
#             if app:
#                 app.status = status
#                 app.confirmation_number = confirmation
#                 app.error_message = error
#                 if screenshot:
#                     app.confirmation_screenshot_path = screenshot
#                 if status == "submitted":
#                     app.applied_at = datetime.now(timezone.utc)
#     except Exception as e:
#         logger.error("Failed to update application result", extra={"error": str(e)})


# async def _attempt_submission(
#     application_id: str, job_url: str, portal: str,
#     contact_info: dict, cover_letter: str, user_id: str,
# ) -> dict:
#     """
#     Attempt Playwright submission. CRITICAL: only returns 'submitted' if
#     real success text is found on the resulting page. Otherwise returns
#     'needs_manual_review' — never fabricates a confirmation number.
#     """
#     from app.config import get_settings
#     from pathlib import Path
#     import asyncio
#     settings = get_settings()

#     try:
#         from playwright.async_api import async_playwright

#         async with async_playwright() as p:
#             browser = await p.chromium.launch(headless=True)
#             context = await browser.new_context(
#                 user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
#             )
#             page = await context.new_page()

#             try:
#                 await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
#                 await asyncio.sleep(2)

#                 screenshot_dir = Path(settings.UPLOAD_DIR) / user_id / "screenshots"
#                 screenshot_dir.mkdir(parents=True, exist_ok=True)
#                 before_screenshot = str(screenshot_dir / f"{application_id}_before.png")
#                 await page.screenshot(path=before_screenshot)

#                 # Try to click apply / submit
#                 clicked_something = await _try_click_apply_flow(page, contact_info, cover_letter)

#                 await asyncio.sleep(2)
#                 after_screenshot = str(screenshot_dir / f"{application_id}.png")
#                 await page.screenshot(path=after_screenshot, full_page=False)

#                 # Get visible page text to check for REAL success indicators
#                 page_text = (await page.inner_text("body")).lower()

#                 found_success = any(phrase in page_text for phrase in SUCCESS_INDICATORS)

#                 if found_success:
#                     # Try to extract a real confirmation/reference number if shown
#                     import re
#                     ref_match = re.search(r"(reference|confirmation|application)\s*(id|number|#)?[:\s]*([A-Z0-9\-]{4,20})", page_text, re.IGNORECASE)
#                     confirmation = ref_match.group(3) if ref_match else "Confirmed (text match on page)"
#                     return {
#                         "status": "submitted",
#                         "confirmation_number": confirmation,
#                         "screenshot_path": after_screenshot,
#                     }
#                 elif not clicked_something:
#                     return {
#                         "status": "needs_manual_review",
#                         "error_message": "No Apply button found automatically — portal layout not recognized. Apply manually.",
#                         "screenshot_path": after_screenshot,
#                     }
#                 else:
#                     return {
#                         "status": "needs_manual_review",
#                         "error_message": "Clicked apply but could not confirm success on the page (may need login, CAPTCHA, or multi-step form). Check screenshot and apply manually if unsure.",
#                         "screenshot_path": after_screenshot,
#                     }

#             finally:
#                 await context.close()
#                 await browser.close()

#     except Exception as e:
#         return {"status": "failed", "error_message": f"Playwright error: {str(e)}"}


# async def _try_click_apply_flow(page, contact_info: dict, cover_letter: str) -> bool:
#     """Attempt to click apply buttons and fill basic fields. Returns True if anything was clicked."""
#     import asyncio
#     clicked = False

#     apply_selectors = [
#         "button:has-text('Apply')", "a:has-text('Apply')",
#         ".jobs-apply-button", "[id='indeedApplyButton']", ".ia-IndeedApplyButton",
#         "button:has-text('Easy Apply')", ".apply-button",
#     ]

#     for sel in apply_selectors:
#         try:
#             btn = await page.query_selector(sel)
#             if btn and await btn.is_visible():
#                 await btn.click()
#                 clicked = True
#                 await asyncio.sleep(2)
#                 break
#         except Exception:
#             continue

#     if not clicked:
#         return False

#     # Try filling common fields
#     field_map = {
#         "input[name*='email'], input[type='email']": contact_info.get("email", ""),
#         "input[name*='phone'], input[type='tel']": contact_info.get("phone", ""),
#         "input[name*='name'], input[id*='name']": contact_info.get("name", ""),
#         "textarea": cover_letter[:2000] if cover_letter else "",
#     }
#     for selector, value in field_map.items():
#         if not value:
#             continue
#         for sel in selector.split(", "):
#             try:
#                 el = await page.query_selector(sel.strip())
#                 if el and await el.is_visible():
#                     await el.fill(value)
#                     break
#             except Exception:
#                 continue

#     # Try clicking through submit/next/continue buttons
#     for _ in range(4):
#         for sel in ["button[type='submit']", "button:has-text('Submit')", "button:has-text('Continue')", "button:has-text('Next')"]:
#             try:
#                 btn = await page.query_selector(sel)
#                 if btn and await btn.is_visible():
#                     await btn.click()
#                     await asyncio.sleep(1.5)
#                     break
#             except Exception:
#                 continue

#     return True


from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database import get_db, get_db_context
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.schemas import ApplicationOut, ApprovalAction
from app.core.logging import get_logger
from app.services.apply_service import ApplyInput, submit_application

router = APIRouter(prefix="/applications", tags=["applications"])
logger = get_logger(__name__)


from sqlalchemy.orm import selectinload

@router.get("/", response_model=list[ApplicationOut])
async def list_applications(
    status: str | None = None,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    if status:
        query = query.where(Application.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/pending", response_model=list[ApplicationOut])
async def list_pending_approvals(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.user_id == user_id, Application.status == "pending_approval")
        .order_by(Application.created_at.desc())
    )
    return result.scalars().all()


@router.get("/stats", response_model=dict)
async def get_stats(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Application).where(Application.user_id == user_id))
    apps = result.scalars().all()
    return {
        "total": len(apps),
        "pending_approval": sum(1 for a in apps if a.status == "pending_approval"),
        "approved": sum(1 for a in apps if a.status == "approved"),
        "submitted": sum(1 for a in apps if a.status == "submitted"),
        "needs_manual_review": sum(1 for a in apps if a.status == "needs_manual_review"),
        "failed": sum(1 for a in apps if a.status == "failed"),
        "rejected": sum(1 for a in apps if a.status == "rejected"),
    }


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.id == application_id, Application.user_id == user_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("/{application_id}/approve", response_model=dict)
async def approve_application(
    application_id: uuid.UUID,
    payload: ApprovalAction,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status not in ("pending_approval", "approved"):
        raise HTTPException(status_code=409, detail=f"Application is '{app.status}', cannot approve")

    if payload.decision == "approve":
        app.status = "approved"
        app.approved_at = datetime.now(timezone.utc)
        app.reviewer_notes = payload.edit_instructions
        await db.commit()
        background_tasks.add_task(_submit_application_background, str(application_id), str(user_id))
        return {
            "status": "approved",
            "message": "Approved. Attempting submission — check status shortly. Verify via screenshot before trusting it went through.",
            "application_id": str(application_id),
        }
    else:
        app.status = "rejected"
        app.reviewer_notes = payload.edit_instructions
        await db.commit()
        return {"status": "rejected", "message": "Application rejected."}


@router.post("/approve-all", response_model=dict)
async def approve_all_pending(
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.user_id == user_id, Application.status == "pending_approval")
    )
    apps = result.scalars().all()
    if not apps:
        return {"message": "No pending applications", "count": 0}

    app_ids = []
    for app in apps:
        app.status = "approved"
        app.approved_at = datetime.now(timezone.utc)
        app_ids.append(str(app.id))
    await db.commit()

    for app_id in app_ids:
        background_tasks.add_task(_submit_application_background, app_id, str(user_id))

    return {"message": f"Approved {len(app_ids)} applications.", "count": len(app_ids), "application_ids": app_ids}


@router.post("/submit-approved", response_model=dict)
async def submit_all_approved(
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.user_id == user_id, Application.status == "approved")
    )
    apps = result.scalars().all()
    if not apps:
        return {"message": "No approved applications waiting", "count": 0}

    for app in apps:
        background_tasks.add_task(_submit_application_background, str(app.id), str(user_id))

    return {"message": f"Attempting {len(apps)} submissions in background.", "count": len(apps)}


@router.post("/{application_id}/mark-manual-applied", response_model=dict)
async def mark_manually_applied(
    application_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Use this AFTER you've manually applied yourself and confirmed it on the portal."""
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = "submitted"
    app.confirmation_number = "MANUAL-CONFIRMED"
    app.applied_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "submitted", "message": "Marked as manually confirmed applied."}


# ─── Background submission ──────────────────────────────────────────────────
# Actual browser automation lives in app.services.apply_service, which is the
# single source of truth shared with the LangGraph application agent
# (app/agents/application.py). This module is only responsible for loading
# the DB context the bot needs, invoking that shared service, and persisting
# + notifying on the result.

async def _submit_application_background(application_id: str, user_id: str) -> None:
    logger.info("Background submission started", extra={"app_id": application_id})
    try:
        async with get_db_context() as db:
            result = await db.execute(select(Application).where(Application.id == uuid.UUID(application_id)))
            app = result.scalar_one_or_none()
            if not app:
                return
            job_result = await db.execute(select(Job).where(Job.id == app.job_id))
            job = job_result.scalar_one_or_none()
            resume_result = await db.execute(select(Resume).where(Resume.id == app.resume_id))
            resume = resume_result.scalar_one_or_none()

        if not job:
            await _update_result(application_id, "failed", error="Job not found in database")
            return

        contact_info = resume.contact_info if resume and resume.contact_info else {}

        cover_letter = ""
        if app.cover_letter_path:
            try:
                from pathlib import Path
                cover_letter = Path(app.cover_letter_path).read_text(encoding="utf-8")
            except Exception:
                pass

        resume_file_path = app.tailored_resume_path or (resume.file_path if resume else None)

        apply_input = ApplyInput(
            application_id=application_id,
            job_url=job.url,
            portal=job.portal,
            user_id=user_id,
            contact_info=contact_info,
            cover_letter=cover_letter,
            resume_file_path=resume_file_path,
            resume_context=(resume.raw_text if resume and resume.raw_text else "")[:1500],
            job_context=(job.description or "")[:1500],
        )
        apply_result = await submit_application(apply_input)
        result = apply_result.as_dict()

        await _update_result(
            application_id,
            result["status"],
            confirmation=result.get("confirmation_number"),
            error=result.get("error_message"),
            screenshot=result.get("screenshot_path"),
        )

        from app.services.notification_service import get_notification_service
        notif = get_notification_service()

        if result["status"] == "submitted":
            await notif.notify_application_submitted(
                job_title=job.title, company=job.company,
                confirmation=result.get("confirmation_number", "Verified on page"),
            )
        elif result["status"] == "needs_manual_review":
            await notif.send_email(
                subject=f"⚠️ Needs your review: {job.title} at {job.company}",
                body=f"""
                <h2>Could not confirm automatic submission</h2>
                <p><strong>{job.title}</strong> at <strong>{job.company}</strong></p>
                <p>Reason: {result.get('error_message', 'No success confirmation detected on page')}</p>
                <p>This usually means the form requires login, has a custom layout, or needs a CAPTCHA.</p>
                <p><strong>Please apply manually:</strong> <a href="{job.url}">{job.url}</a></p>
                <p>A screenshot of what the bot saw is saved on your server for reference.</p>
                """,
            )
        else:
            await notif.notify_application_failed(
                job_title=job.title, company=job.company,
                error=result.get("error_message", "Unknown error"),
            )

    except Exception as e:
        import traceback
        full_error = traceback.format_exc()
        logger.error("Playwright submission failed", extra={"full_traceback": full_error})
        await _update_result(application_id, "failed", error=f"Playwright error: {repr(e)}")


async def _update_result(application_id: str, status: str, confirmation: str | None = None,
                          error: str | None = None, screenshot: str | None = None) -> None:
    try:
        async with get_db_context() as db:
            result = await db.execute(select(Application).where(Application.id == uuid.UUID(application_id)))
            app = result.scalar_one_or_none()
            if app:
                app.status = status
                app.confirmation_number = confirmation
                app.error_message = error
                if screenshot:
                    app.confirmation_screenshot_path = screenshot
                if status == "submitted":
                    app.applied_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.error("Failed to update application result", extra={"error": str(e)})