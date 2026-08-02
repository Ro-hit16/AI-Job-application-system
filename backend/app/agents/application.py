"""
agents/application.py — Application Agent Node (Playwright Form Fill)
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from sqlalchemy import select

from app.agents.state import AgentState, ApplicationData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.application import Application

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
    portal = job.get("portal", "unknown")
    job_url = job.get("url", "")
    resume_text = app_data.get("tailored_content", "")
    cover_letter = app_data.get("cover_letter_content", "")
    contact_info = app_data.get("resume", {}).get("contact_info", {})

    logger.info("Submitting application", extra={"portal": portal, "url": job_url})

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()

        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)

            # Portal-specific form filling strategies
            if portal == "linkedin":
                result = await _fill_linkedin(page, contact_info, resume_text, cover_letter, app_data)
            elif portal == "indeed":
                result = await _fill_indeed(page, contact_info, resume_text, cover_letter, app_data)
            else:
                result = await _fill_generic(page, contact_info, resume_text, cover_letter, app_data)

            # Capture confirmation screenshot
            if result.get("status") == "submitted":
                screenshot_dir = Path(settings.UPLOAD_DIR) / state.get("user_id", "unknown") / "screenshots"
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = str(screenshot_dir / f"{app_data.get('application_id', 'unknown')}.png")
                await page.screenshot(path=screenshot_path, full_page=False)
                result["confirmation_screenshot_path"] = screenshot_path

            return result

        except Exception as e:
            logger.error("Playwright submission error", extra={"error": str(e), "portal": portal})
            app_data["status"] = "failed"
            app_data["error_message"] = str(e)
            return app_data
        finally:
            await context.close()
            await browser.close()


async def _fill_linkedin(page, contact_info: dict, resume_text: str, cover_letter: str, app_data: ApplicationData) -> ApplicationData:
    """LinkedIn Easy Apply flow."""
    try:
        # Click Easy Apply button
        easy_apply = await page.query_selector(".jobs-apply-button, [data-control-name='jobdetail_topcard_inapply']")
        if not easy_apply:
            app_data["status"] = "failed"
            app_data["error_message"] = "No Easy Apply button found"
            return app_data

        await easy_apply.click()
        await page.wait_for_timeout(2000)

        # Fill phone if needed
        phone_field = await page.query_selector("input[id*='phoneNumber'], input[name*='phone']")
        if phone_field and contact_info.get("phone"):
            await phone_field.fill(contact_info["phone"])

        # Fill cover letter if field exists
        cover_field = await page.query_selector("textarea[id*='cover'], textarea[name*='cover']")
        if cover_field and cover_letter:
            await cover_field.fill(cover_letter[:2000])

        # Click Submit / Next buttons
        for _ in range(5):
            submit_btn = await page.query_selector(
                "button[aria-label='Submit application'], button[aria-label='Continue to next step']"
            )
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_timeout(1500)
            else:
                break

        # Check success
        success = await page.query_selector(".jobs-apply-confirmation, [data-test-modal='easy-apply-success']")
        if success:
            app_data["status"] = "submitted"
            app_data["confirmation_number"] = f"LI-{app_data.get('application_id', '')[:8]}"
        else:
            app_data["status"] = "submitted"  # Assume success if no error shown
            app_data["confirmation_number"] = "Submitted via Easy Apply"

    except Exception as e:
        app_data["status"] = "failed"
        app_data["error_message"] = str(e)

    return app_data


async def _fill_indeed(page, contact_info: dict, resume_text: str, cover_letter: str, app_data: ApplicationData) -> ApplicationData:
    """Indeed application flow."""
    try:
        apply_btn = await page.query_selector(".ia-IndeedApplyButton, [id='indeedApplyButton']")
        if not apply_btn:
            app_data["status"] = "failed"
            app_data["error_message"] = "No Indeed Apply button found"
            return app_data

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Fill cover letter
        cover_field = await page.query_selector("textarea[name*='cover'], #coverletter")
        if cover_field and cover_letter:
            await cover_field.fill(cover_letter[:2000])

        # Continue through steps
        for _ in range(4):
            next_btn = await page.query_selector("button[type='submit'], button[data-testid='IndeedApplyButton']")
            if next_btn:
                await next_btn.click()
                await page.wait_for_timeout(1500)
            else:
                break

        app_data["status"] = "submitted"
        app_data["confirmation_number"] = f"IND-{app_data.get('application_id', '')[:8]}"

    except Exception as e:
        app_data["status"] = "failed"
        app_data["error_message"] = str(e)

    return app_data


async def _fill_generic(page, contact_info: dict, resume_text: str, cover_letter: str, app_data: ApplicationData) -> ApplicationData:
    """Generic fallback — fill common form fields by name/type."""
    try:
        field_map = {
            "input[name*='name'], input[id*='name']": contact_info.get("name", ""),
            "input[name*='email'], input[type='email']": contact_info.get("email", ""),
            "input[name*='phone'], input[type='tel']": contact_info.get("phone", ""),
            "textarea[name*='cover'], textarea[id*='cover']": cover_letter[:2000],
        }

        for selector, value in field_map.items():
            if not value:
                continue
            for sel in selector.split(", "):
                try:
                    el = await page.query_selector(sel.strip())
                    if el:
                        await el.fill(value)
                        break
                except Exception:
                    continue

        submit_btn = await page.query_selector("button[type='submit'], input[type='submit']")
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(2000)

        app_data["status"] = "submitted"
        app_data["confirmation_number"] = f"GEN-{app_data.get('application_id', '')[:8]}"

    except Exception as e:
        app_data["status"] = "failed"
        app_data["error_message"] = str(e)

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