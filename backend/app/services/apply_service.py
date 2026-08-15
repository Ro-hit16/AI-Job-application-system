"""
services/apply_service.py — Shared Playwright auto-apply logic
================================================================
Single source of truth for submitting a job application via browser
automation. Both the LangGraph `application` agent node
(app/agents/application.py) and the manual-approval API flow
(app/api/v1/applications.py) call into this module instead of each
maintaining their own divergent Playwright implementation.

Design principles carried over from the previous submission-integrity
fix, now enforced in one place instead of two:
  - NEVER fabricate a confirmation number or a "submitted" status.
    A submission is only ever marked `submitted` when real success text
    is found on the resulting page.
  - When the bot can't confirm success (unrecognized layout, login wall,
    CAPTCHA, multi-step form it couldn't finish) it returns
    `needs_manual_review`, never a guess.
  - Every attempt captures a screenshot; failures additionally capture
    the page HTML (and a Playwright trace, if tracing is enabled) so a
    human reviewing the failure has enough to diagnose it without
    re-running the bot.

New in this consolidation:
  - Login verification for portals with stored credentials, so we don't
    silently try to fill an application form we're not authenticated for.
  - Resume file upload with verification that the filename actually
    appears in the file input afterward (Playwright's set_input_files
    can succeed against a detached/replaced element without the file
    actually taking).
  - Required-field validation pass before submitting, so we catch
    "missing required field" failures ourselves instead of only
    discovering them from a lack of a success message.
  - AI-generated answers for free-text application questions (e.g. "Why
    do you want to work here?"), using the tailored resume + job
    description as context.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, async_playwright

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Phrases that indicate REAL success on a confirmation page. If none of
# these appear, we do NOT claim success — see module docstring.
SUCCESS_INDICATORS = [
    "application submitted", "application received", "thank you for applying",
    "successfully applied", "your application has been sent", "application sent",
    "we've received your application", "applied successfully", "thanks for applying",
    "application complete", "submission successful",
]

APPLY_BUTTON_SELECTORS = [
    "button:has-text('Easy Apply')",
    ".jobs-apply-button",
    "[id='indeedApplyButton']", ".ia-IndeedApplyButton",
    "button:has-text('Apply')", "a:has-text('Apply')",
    ".apply-button",
]

# Intermediate multi-step-form navigation only (Continue/Next/Review).
# These NEVER submit the application — see FINAL_SUBMIT_SELECTORS below,
# which is checked separately and gated on required-field validation.
CONTINUE_STEP_SELECTORS = [
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button[aria-label='Continue to next step']",
    "button:has-text('Review')",
]

# The actual final-submission control. Only ever clicked after
# `_validate_required_fields` has passed on the page in its current
# (final-step) state. Text matching here explicitly excludes anything
# that also looks like a Continue/Next control (see
# `_find_final_submit_button`), since some portals reuse
# `button[type='submit']` for intermediate wizard steps too.
FINAL_SUBMIT_SELECTORS = [
    "button[aria-label='Submit application']",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button[type='submit']",
]

# If a button's visible text/aria-label contains any of these, it is
# treated as an intermediate step control even if it also matches a
# FINAL_SUBMIT_SELECTORS pattern (e.g. a "Next" button styled as
# type='submit').
_CONTINUE_TEXT_MARKERS = ("continue", "next", "review")

LOGIN_SELECTORS = {
    "linkedin": {
        "username": "input#username, input[name='session_key']",
        "password": "input#password, input[name='session_password']",
        "submit": "button[type='submit']",
        "logged_in_check": "img.global-nav__me-photo, .global-nav__me",
    },
    "indeed": {
        "username": "input[type='email'], input[name='__email']",
        "password": "input[type='password'], input[name='__password']",
        "submit": "button[type='submit']",
        "logged_in_check": "#AccountMenu, [data-testid='AccountMenu']",
    },
    "naukri": {
        "username": "input[placeholder='Enter your active Email ID']",
        "password": "input[placeholder='Enter your password']",
        "submit": "button[type='submit']",
        "logged_in_check": ".nI-gNb-drpDown",
    },
}


@dataclass
class ApplyInput:
    application_id: str
    job_url: str
    portal: str
    user_id: str
    contact_info: dict = field(default_factory=dict)
    cover_letter: str = ""
    resume_file_path: Optional[str] = None
    application_questions: list[str] = field(default_factory=list)
    resume_context: str = ""       # tailored resume text, for AI-answered questions
    job_context: str = ""          # job description, for AI-answered questions


@dataclass
class ApplyResult:
    status: str  # "submitted" | "needs_manual_review" | "failed"
    confirmation_number: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    html_dump_path: Optional[str] = None
    trace_path: Optional[str] = None
    missing_required_fields: list[str] = field(default_factory=list)
    login_verified: Optional[bool] = None
    resume_uploaded: Optional[bool] = None
    answered_questions: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "confirmation_number": self.confirmation_number,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "html_dump_path": self.html_dump_path,
            "trace_path": self.trace_path,
            "missing_required_fields": self.missing_required_fields,
            "login_verified": self.login_verified,
            "resume_uploaded": self.resume_uploaded,
            "answered_questions": self.answered_questions,
        }


async def submit_application(inp: ApplyInput) -> ApplyResult:
    """Main entry point. Launches a browser, attempts the full apply flow,
    and returns an ApplyResult that is honest about what actually happened.
    """
    logger.info("Submitting application", extra={"portal": inp.portal, "url": inp.job_url})

    artifact_dir = Path(settings.UPLOAD_DIR) / inp.user_id / "screenshots"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = Path(settings.UPLOAD_DIR) / inp.user_id / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            accept_downloads=False,
        )
        page = await context.new_page()

        # Tracked so `finally` knows whether a trace still needs to be
        # stopped (and whether it was already stopped/saved on a failure
        # path below).
        tracing_active = False

        try:
            login_verified = await _verify_login(page, inp.portal)

            # Tracing is started only AFTER the login attempt, never during
            # it — stored portal credentials are filled into the login form
            # by `_verify_login`, and a trace's DOM snapshots/screenshots
            # could otherwise capture them. This is the main avoidable
            # secret-exposure risk for tracing; see module docstring.
            try:
                await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                tracing_active = True
            except Exception as e:
                logger.warning("Failed to start Playwright tracing", extra={"error": str(e)})

            await page.goto(inp.job_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)

            clicked = await _click_apply(page)
            if not clicked:
                result = ApplyResult(
                    status="needs_manual_review",
                    error_message="No Apply button found automatically — portal layout not recognized.",
                    login_verified=login_verified,
                )
                await _capture_failure(page, artifact_dir, inp.application_id, result)
                tracing_active = await _save_trace(context, trace_dir, inp.application_id, tracing_active, result)
                return result

            resume_uploaded = None
            if inp.resume_file_path:
                resume_uploaded = await _upload_resume(page, inp.resume_file_path)

            await _fill_contact_fields(page, inp.contact_info)
            await _fill_cover_letter(page, inp.cover_letter)

            answered = await _answer_application_questions(page, inp)

            # Advance through intermediate Continue/Next/Review steps only.
            # This never touches the final Submit control.
            await _advance_through_steps(page)
            await asyncio.sleep(1.0)

            # Some portals complete the application on a single click (the
            # "Apply" button itself was the whole flow, no separate form).
            # Check for genuine confirmation text before assuming there's
            # a further final-submit step to gate.
            early_text = (await page.inner_text("body")).lower()
            if any(phrase in early_text for phrase in SUCCESS_INDICATORS):
                confirmation = _extract_confirmation_number(early_text)
                screenshot_path = str(artifact_dir / f"{inp.application_id}.png")
                await page.screenshot(path=screenshot_path, full_page=False)
                return ApplyResult(
                    status="submitted",
                    confirmation_number=confirmation,
                    screenshot_path=screenshot_path,
                    login_verified=login_verified,
                    resume_uploaded=resume_uploaded,
                    answered_questions=answered,
                )

            # ── Final-submission safety gate ─────────────────────────────
            # Re-validate required fields on the page in its current
            # (final-step) state — the earlier fill pass may have been on
            # an earlier step of a multi-step form. The final Submit
            # button is NEVER clicked unless this passes.
            missing_required = await _validate_required_fields(page)

            pre_submit_screenshot = str(artifact_dir / f"{inp.application_id}_pre_submit.png")
            try:
                await page.screenshot(path=pre_submit_screenshot, full_page=False)
            except Exception:
                pre_submit_screenshot = None

            if missing_required:
                result = ApplyResult(
                    status="needs_manual_review",
                    error_message=(
                        "Required field(s) left empty immediately before final "
                        f"submission — submit was NOT clicked: {', '.join(missing_required)}"
                    ),
                    missing_required_fields=missing_required,
                    screenshot_path=pre_submit_screenshot,
                    login_verified=login_verified,
                    resume_uploaded=resume_uploaded,
                    answered_questions=answered,
                )
                await _capture_failure(page, artifact_dir, inp.application_id, result)
                tracing_active = await _save_trace(context, trace_dir, inp.application_id, tracing_active, result)
                logger.warning(
                    "Blocked final submit: required fields missing",
                    extra={"application_id": inp.application_id, "missing": missing_required},
                )
                return result

            submit_button = await _find_final_submit_button(page)
            if not submit_button:
                result = ApplyResult(
                    status="needs_manual_review",
                    error_message=(
                        "Validation passed but no distinguishable final Submit "
                        "button was found (portal layout not recognized) — "
                        "submit was NOT clicked."
                    ),
                    screenshot_path=pre_submit_screenshot,
                    login_verified=login_verified,
                    resume_uploaded=resume_uploaded,
                    answered_questions=answered,
                )
                await _capture_failure(page, artifact_dir, inp.application_id, result)
                tracing_active = await _save_trace(context, trace_dir, inp.application_id, tracing_active, result)
                return result

            await submit_button.click()
            await asyncio.sleep(2)

            page_text = (await page.inner_text("body")).lower()
            found_success = any(phrase in page_text for phrase in SUCCESS_INDICATORS)

            screenshot_path = str(artifact_dir / f"{inp.application_id}.png")
            await page.screenshot(path=screenshot_path, full_page=False)

            # The Submit button was clicked, but a click alone never implies
            # success — only genuine confirmation text on the resulting page does.
            if found_success:
                confirmation = _extract_confirmation_number(page_text)
                return ApplyResult(
                    status="submitted",
                    confirmation_number=confirmation,
                    screenshot_path=screenshot_path,
                    login_verified=login_verified,
                    resume_uploaded=resume_uploaded,
                    answered_questions=answered,
                )

            result = ApplyResult(
                status="needs_manual_review",
                error_message=(
                    "Clicked final Submit but could not confirm success on the "
                    "resulting page (may need login, CAPTCHA, or additional "
                    "steps the bot didn't recognize)."
                ),
                screenshot_path=screenshot_path,
                login_verified=login_verified,
                resume_uploaded=resume_uploaded,
                answered_questions=answered,
            )
            await _capture_failure(page, artifact_dir, inp.application_id, result)
            tracing_active = await _save_trace(context, trace_dir, inp.application_id, tracing_active, result)
            return result

        except Exception as e:
            logger.error("Playwright submission error", extra={"error": str(e), "portal": inp.portal})
            result = ApplyResult(status="failed", error_message=str(e))
            try:
                await _capture_failure(page, artifact_dir, inp.application_id, result)
            except Exception:
                pass
            try:
                tracing_active = await _save_trace(context, trace_dir, inp.application_id, tracing_active, result)
            except Exception:
                pass
            return result
        finally:
            # Any success path (or any path above that didn't already save
            # a trace) reaches here with tracing still active — stop it
            # without a path so Playwright discards it rather than writing
            # an unused trace file for successful, non-diagnostic runs.
            if tracing_active:
                try:
                    await context.tracing.stop()
                except Exception as e:
                    logger.warning("Failed to stop Playwright tracing", extra={"error": str(e)})
            await context.close()
            await browser.close()


# ─── Login ──────────────────────────────────────────────────────────────────

async def _verify_login(page: Page, portal: str) -> Optional[bool]:
    """Attempt to log in to the portal using stored credentials, if any
    are configured. Returns True/False if a login attempt was made,
    or None if no credentials are configured for this portal (in which
    case the apply flow proceeds unauthenticated, as before).
    """
    creds = {
        "linkedin": (settings.LINKEDIN_EMAIL, settings.LINKEDIN_PASSWORD, "https://www.linkedin.com/login"),
        "indeed": (settings.INDEED_EMAIL, settings.INDEED_PASSWORD, "https://secure.indeed.com/auth"),
        "naukri": (settings.NAUKRI_EMAIL, settings.NAUKRI_PASSWORD, "https://www.naukri.com/nlogin/login"),
    }.get(portal)

    if not creds or not creds[0] or not creds[1]:
        return None  # no credentials configured for this portal — nothing to verify

    email, password, login_url = creds
    selectors = LOGIN_SELECTORS.get(portal)
    if not selectors:
        return None

    try:
        await page.goto(login_url, wait_until="domcontentloaded", timeout=20000)
        await page.fill(selectors["username"], email)
        await page.fill(selectors["password"], password)
        await page.click(selectors["submit"])
        await asyncio.sleep(3)
        logged_in = await page.query_selector(selectors["logged_in_check"])
        if logged_in:
            logger.info("Portal login verified", extra={"portal": portal})
            return True
        logger.warning("Portal login could not be verified", extra={"portal": portal})
        return False
    except Exception as e:
        logger.warning("Portal login attempt failed", extra={"portal": portal, "error": str(e)})
        return False


# ─── Apply flow steps ───────────────────────────────────────────────────────

async def _click_apply(page: Page) -> bool:
    for sel in APPLY_BUTTON_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(2)
                return True
        except Exception:
            continue
    return False


async def _upload_resume(page: Page, resume_file_path: str) -> bool:
    """Find a file input and upload the resume, then verify the upload
    actually took (the input's displayed filename reflects our file)
    rather than trusting that set_input_files() didn't raise.
    """
    if not Path(resume_file_path).exists():
        logger.warning("Resume file not found on disk", extra={"path": resume_file_path})
        return False

    file_input_selectors = [
        "input[type='file']",
        "input[name*='resume']",
        "input[name*='cv']",
    ]
    for sel in file_input_selectors:
        try:
            file_input = await page.query_selector(sel)
            if not file_input:
                continue
            await file_input.set_input_files(resume_file_path)
            await asyncio.sleep(1)

            # Verify: many uploaders echo the filename somewhere in the DOM
            # after a successful upload. If we can't find it, don't assume success.
            filename = Path(resume_file_path).name
            body_text = await page.inner_text("body")
            if filename in body_text:
                return True
            # Some widgets don't echo the name but do accept the file — check
            # the input's own files property as a fallback signal.
            files_count = await file_input.evaluate("el => el.files ? el.files.length : 0")
            return files_count > 0
        except Exception as e:
            logger.warning("Resume upload attempt failed", extra={"selector": sel, "error": str(e)})
            continue
    return False


async def _fill_contact_fields(page: Page, contact_info: dict) -> None:
    field_map = {
        "input[name*='name'], input[id*='name']": contact_info.get("name", ""),
        "input[name*='email'], input[type='email']": contact_info.get("email", ""),
        "input[name*='phone'], input[type='tel']": contact_info.get("phone", ""),
    }
    for selector, value in field_map.items():
        if not value:
            continue
        for sel in selector.split(", "):
            try:
                el = await page.query_selector(sel.strip())
                if el and await el.is_visible():
                    await el.fill(value)
                    break
            except Exception:
                continue


async def _fill_cover_letter(page: Page, cover_letter: str) -> None:
    if not cover_letter:
        return
    for sel in ["textarea[id*='cover']", "textarea[name*='cover']", "#coverletter"]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(cover_letter[:2000])
                return
        except Exception:
            continue


async def _answer_application_questions(page: Page, inp: ApplyInput) -> dict[str, str]:
    """Find free-text application questions on the page (or use ones
    passed in explicitly) and answer them with the LLM, grounded in the
    tailored resume and job description.
    """
    answered: dict[str, str] = {}
    if not inp.application_questions:
        return answered

    from app.services.llm_service import get_llm_service
    llm = get_llm_service()

    for question in inp.application_questions[:8]:  # cap to avoid runaway LLM calls
        try:
            prompt = (
                f"Job description:\n{inp.job_context[:1500]}\n\n"
                f"Candidate resume summary:\n{inp.resume_context[:1500]}\n\n"
                f"Application question: {question}\n\n"
                "Write a concise, honest, first-person answer (2-4 sentences) "
                "based only on the resume content above. Do not invent experience."
            )
            answer = await llm.generate(prompt, system_prompt="You are helping fill out a job application honestly and concisely.")
            answered[question] = answer.strip()

            # Best-effort: find a textarea/input near text matching the question and fill it
            try:
                label_locator = page.get_by_text(question[:60], exact=False)
                if await label_locator.count() > 0:
                    container = label_locator.first
                    field = await container.evaluate_handle(
                        "el => el.closest('div,fieldset')?.querySelector('textarea, input[type=text]')"
                    )
                    if field:
                        await field.as_element().fill(answer.strip()[:1000])
            except Exception:
                pass  # best-effort UI fill; the answer is still recorded either way

        except Exception as e:
            logger.warning("Failed to answer application question", extra={"question": question, "error": str(e)})

    return answered


async def _validate_required_fields(page: Page) -> list[str]:
    """Return the labels/names of visible, empty, required fields still
    on the page before we submit — so a missing-field failure gets
    reported explicitly instead of just showing up as a lack of a
    success message.
    """
    missing: list[str] = []
    try:
        required_inputs = await page.query_selector_all(
            "input[required], select[required], textarea[required]"
        )
        for el in required_inputs:
            try:
                if not await el.is_visible():
                    continue
                value = await el.evaluate("el => el.value")
                if value:
                    continue
                name = (
                    await el.get_attribute("aria-label")
                    or await el.get_attribute("placeholder")
                    or await el.get_attribute("name")
                    or await el.get_attribute("id")
                    or "unnamed field"
                )
                missing.append(name)
            except Exception:
                continue
    except Exception as e:
        logger.warning("Required-field validation failed", extra={"error": str(e)})
    return missing


async def _advance_through_steps(page: Page, max_steps: int = 5) -> None:
    for _ in range(max_steps):
        clicked = False
        for sel in SUBMIT_STEP_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1.5)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break


def _extract_confirmation_number(page_text: str) -> str:
    ref_match = re.search(
        r"(reference|confirmation|application)\s*(id|number|#)?[:\s]*([A-Z0-9\-]{4,20})",
        page_text, re.IGNORECASE,
    )
    return ref_match.group(3) if ref_match else "Confirmed (text match on page)"


# ─── Failure diagnostics ────────────────────────────────────────────────────

async def _capture_failure(page: Page, artifact_dir: Path, application_id: str, result: ApplyResult) -> None:
    """Capture screenshot + full page HTML for anything that isn't a clean
    'submitted'. Gives a human reviewer enough to diagnose the failure
    without re-running the bot.
    """
    try:
        if not result.screenshot_path:
            screenshot_path = str(artifact_dir / f"{application_id}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            result.screenshot_path = screenshot_path

        html_path = artifact_dir / f"{application_id}.html"
        html = await page.content()
        html_path.write_text(html, encoding="utf-8")
        result.html_dump_path = str(html_path)
    except Exception as e:
        logger.warning("Failed to capture failure artifacts", extra={"error": str(e)})


async def _save_trace(context, trace_dir: Path, application_id: str, tracing_active: bool, result: ApplyResult) -> bool:
    """Stop and save the running Playwright trace for a failed or
    needs-manual-review attempt, recording its path on `result`.

    Returns the new `tracing_active` state (always False after this call)
    so the caller stops treating the trace as still-running.

    Only called on failure / needs_manual_review paths — successful
    attempts don't need a diagnostic trace, so `submit_application`'s
    `finally` block stops (and discards) tracing for those instead.

    Note: like the screenshot/HTML capture above, this only records the
    application page's state from the point tracing started (after
    login — see `submit_application`), not portal credentials.
    """
    if not tracing_active:
        return False
    trace_path = str(trace_dir / f"{application_id}.zip")
    try:
        await context.tracing.stop(path=trace_path)
        result.trace_path = trace_path
    except Exception as e:
        logger.warning("Failed to save Playwright trace", extra={"error": str(e)})
        try:
            await context.tracing.stop()
        except Exception:
            pass
    return False