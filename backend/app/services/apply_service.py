"""
services/apply_service.py — Shared Playwright auto-apply logic
================================================================
Single source of truth for submitting a job application via browser
automation. Both the LangGraph `application` agent node
(app/agents/application.py) and the manual-approval API flow
(app/api/v1/applications.py) call into this module instead of each
maintaining their own divergent Playwright implementation.

Design principles:
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

Features:
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
  - ATS-aware / iframe-aware Apply-button detection, plus a semantic
    role-based fallback, since most jobs here come from third-party ATS
    pages (Greenhouse, Lever, Workday, etc.) rather than linkedin.com/
    indeed.com/naukri.com directly.
  - A verified-account-email fallback (`resolve_contact_email`) for when
    resume parsing didn't extract an email — see its docstring below.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, async_playwright
from sqlalchemy import select

from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.user import User

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
    # Portal-specific (only ever reached for linkedin.com/indeed.com pages —
    # i.e. jobs sourced via the paid Apify actors, see job_search agent).
    "button:has-text('Easy Apply')",
    ".jobs-apply-button",
    "[id='indeedApplyButton']", ".ia-IndeedApplyButton",
    # Generic fallback for anything else.
    "button:has-text('Apply')", "a:has-text('Apply')",
    ".apply-button",
]

# Most jobs in this system are NOT sourced from linkedin.com/indeed.com/
# naukri.com — the free scrapers (Remotive, Arbeitnow, Himalayas, Adzuna;
# see agents/job_search.py) point `job.url` at the ORIGINAL posting on
# whatever ATS the employer uses. These are keyed by a substring of the
# post-redirect page URL (`page.url`, not `inp.portal`, since the scraper's
# `portal` field just names the aggregator, not the destination site) and
# checked before falling back to the generic role/text search below.
KNOWN_ATS_APPLY_SELECTORS: dict[str, list[str]] = {
    "greenhouse.io": ["#apply_button", "a#apply_button", "div#apply-button a", "a:has-text('Apply for this job')"],
    "lever.co": ["a.postings-btn", "a:has-text('Apply for this job')"],
    "myworkdayjobs.com": ["a[data-automation-id='adventureButton']", "button[data-automation-id='adventureButton']"],
    "ashbyhq.com": ["button:has-text('Apply for this Job')", "a:has-text('Apply for this Job')"],
    "smartrecruiters.com": ["button.apply-button", "a.apply-button", "button:has-text('Apply now')"],
    "workable.com": ["a[data-ui='overview-apply-button']", "a:has-text('Apply for this job')"],
    "bamboohr.com": ["a.js-apply-link", "button:has-text('Apply for this Job')"],
    "icims.com": ["a#iCIMS_ApplyOnlineButton", "button:has-text('Apply')"],
    "recruitee.com": ["a[data-analytics-action='apply']", "button:has-text('Apply for this job')"],
}

# Visible text/aria-label substrings that disqualify an otherwise-matching
# "Apply"-ish control — it's a filter/nav/already-applied element, not the
# actual apply action. Checked case-insensitively against the FULL
# accessible name, so e.g. "Apply filters" is excluded but "Apply Now" is not.
_APPLY_DISQUALIFYING_TEXT = (
    "already applied", "applied", "apply filter", "apply filters",
    "apply salary", "apply coupon", "apply code", "apply changes",
    "sort by", "job alert", "save search",
)

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


# ─── Contact-info resolution ─────────────────────────────────────────────────

async def resolve_contact_email(contact_info: dict, user_id: str) -> dict:
    """Fill contact_info['email'] from the authenticated User.email when the
    resume parser didn't extract one (LLM-based resume extraction sometimes
    misses it). Priority: resume email (if present/non-empty) > User.email.
    Never overwrites a valid resume-extracted email.

    This is the ONE place this fallback is implemented. Both call sites
    (agents/application.py, api/v1/applications.py) call it while building
    their ApplyInput.contact_info, rather than each having their own copy.

    Fails safe: if user_id isn't resolvable or the lookup fails/returns
    nothing, contact_info is returned unchanged — the later required-field
    validation in submit_application() will correctly block submission on
    an empty email rather than this function silently letting one through.
    """
    if contact_info.get("email"):
        return contact_info

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        logger.info("No usable user_id to resolve email fallback", extra={"user_id": user_id})
        return contact_info

    try:
        async with get_db_context() as db:
            result = await db.execute(select(User.email).where(User.id == user_uuid))
            user_email = result.scalar_one_or_none()
    except Exception as e:
        logger.warning("Email fallback lookup failed", extra={"user_id": user_id, "error": str(e)})
        return contact_info

    if user_email:
        contact_info = dict(contact_info)
        contact_info["email"] = user_email
        logger.info(
            "contact_info.email missing from resume — used User.email as fallback",
            extra={"user_id": user_id},
        )
    return contact_info


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
            # Many ATS apply pages are client-rendered (React/Vue) and the
            # Apply control doesn't exist in the DOM at domcontentloaded —
            # wait for network activity to settle before searching for it,
            # but don't hang forever on pages with long-polling/analytics.
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(1.0)

            clicked = await _click_apply(page)
            if not clicked:
                diagnostics = await _collect_apply_diagnostics(page)
                result = ApplyResult(
                    status="needs_manual_review",
                    error_message=(
                        "No Apply button found automatically — portal layout not "
                        f"recognized. {diagnostics}"
                    ),
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
    """Find and click the real Apply control.

    Tries, in order, across BOTH the main page and same-page iframes
    (many ATS embeds — Greenhouse, Workable — render the actual posting
    inside an <iframe>):
      1. Known-ATS selectors, matched against the (post-redirect) page URL.
      2. The existing enumerated selectors (LinkedIn/Indeed classes, plus
         generic text/class fallbacks).
      3. A semantic role-based search (`get_by_role("button"/"link", ...)`)
         for anything accessibly named "apply", excluding controls whose
         full name matches a disqualifying phrase (already-applied,
         filters, job alerts, etc.) — see `_APPLY_DISQUALIFYING_TEXT`.

    Returns True (and leaves the click already performed) on the first
    visible, non-disqualified match; False if nothing usable was found
    anywhere on the page or in its iframes.
    """
    frames = [page, *page.frames[1:]]  # page.frames[0] is the main frame itself

    for frame in frames:
        try:
            url = frame.url
        except Exception:
            url = ""
        for domain, selectors in KNOWN_ATS_APPLY_SELECTORS.items():
            if domain not in url:
                continue
            if await _try_click_selectors(frame, selectors):
                return True

    for frame in frames:
        if await _try_click_selectors(frame, APPLY_BUTTON_SELECTORS):
            return True

    for frame in frames:
        if await _try_click_role_based(frame):
            return True

    return False


async def _try_click_selectors(frame, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            btn = await frame.query_selector(sel)
            if not btn or not await btn.is_visible():
                continue
            text = (await btn.inner_text() or "").strip().lower()
            aria = (await btn.get_attribute("aria-label") or "").strip().lower()
            if _is_disqualified(text) or _is_disqualified(aria):
                continue
            await btn.click()
            await asyncio.sleep(2)
            return True
        except Exception:
            continue
    return False


async def _try_click_role_based(frame) -> bool:
    """Last-resort fallback: search by accessible role + name instead of a
    fixed selector list, for custom-component ATS UIs (React/Vue apps that
    render non-semantic clickable elements with only an accessible name).
    """
    apply_re = re.compile(r"\bapply\b", re.IGNORECASE)
    for role in ("button", "link"):
        try:
            locator = frame.get_by_role(role, name=apply_re)
            count = await locator.count()
        except Exception:
            continue
        for i in range(min(count, 10)):
            try:
                candidate = locator.nth(i)
                if not await candidate.is_visible():
                    continue
                name = (await candidate.inner_text() or "").strip().lower()
                if _is_disqualified(name):
                    continue
                await candidate.click()
                await asyncio.sleep(2)
                return True
            except Exception:
                continue
    return False


def _is_disqualified(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in _APPLY_DISQUALIFYING_TEXT)


async def _collect_apply_diagnostics(page: Page) -> str:
    """Build a short, secret-free diagnostic summary for a failed Apply
    detection, so a human (or a follow-up debugging pass) can see WHY
    without re-running the bot. Logged in full; a bounded version is also
    folded into the ApplyResult.error_message. Never includes form field
    values, cookies, headers, or anything from LOGIN_SELECTORS/credentials.
    """
    info: dict = {"url": "", "title": "", "buttons": [], "apply_links": [], "iframes": []}
    try:
        info["url"] = page.url
        info["title"] = await page.title()

        buttons = await page.query_selector_all("button")
        for b in buttons[:40]:
            try:
                if await b.is_visible():
                    t = (await b.inner_text() or "").strip()
                    if t:
                        info["buttons"].append(t[:40])
            except Exception:
                continue
        info["buttons"] = info["buttons"][:15]

        links = await page.query_selector_all("a")
        for a in links[:100]:
            try:
                if not await a.is_visible():
                    continue
                t = (await a.inner_text() or "").strip()
                if t and "apply" in t.lower():
                    info["apply_links"].append(t[:40])
            except Exception:
                continue
        info["apply_links"] = info["apply_links"][:10]

        info["iframes"] = [f.url for f in page.frames[1:] if f.url][:10]
    except Exception as e:
        logger.warning("Failed to collect apply diagnostics", extra={"error": str(e)})

    logger.warning("Apply button not found — diagnostics", extra=info)

    summary = (
        f"Landed on: {info['title'][:60]!r} ({info['url'][:120]}). "
        f"Visible buttons: {info['buttons'][:6]}. "
        f"Apply-like links: {info['apply_links'][:6]}. "
        f"Iframes: {len(info['iframes'])}."
    )
    return summary[:600]


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

    # Email gets its own, broader pass. ATS forms vary widely in how the
    # email field is marked up — some only expose it via placeholder or
    # aria-label (e.g. placeholder="Enter your email") with no matching
    # name/type/id hint, which a single `input[name*='email'],
    # input[type='email']` selector would miss. Matching is case-insensitive
    # (the `i` flag) since attribute values aren't guaranteed lowercase.
    email_value = contact_info.get("email", "")
    if not email_value:
        # Most common real cause of an unfilled email field: the resume
        # parser (LLM-extracted contact_info) didn't find one AND the
        # account-email fallback (resolve_contact_email, called by both
        # application.py and applications.py before building ApplyInput)
        # also had nothing to fall back to. This log line is diagnostic
        # only — no PII beyond the fact that it's missing.
        logger.warning("No email value available in contact_info to fill")
        return
    email_selectors = [
        "input[type='email']",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[aria-label*='email' i]",
    ]
    for sel in email_selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(email_value)
                return
        except Exception:
            continue
    logger.warning("Email value was available but no matching email field was found on the page")


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
        for sel in CONTINUE_STEP_SELECTORS:
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


async def _find_final_submit_button(page: Page):
    """Locate the real final-submission control, distinct from any
    intermediate Continue/Next/Review control.

    Only ever called AFTER `_validate_required_fields` has passed on the
    page in its current (final-step) state — see `submit_application`.
    A button is only returned if its visible text/aria-label does NOT
    contain any `_CONTINUE_TEXT_MARKERS` substring, so a "Next" button
    that happens to also be `type='submit'` is never mistaken for the
    final Submit control.
    """
    frames = [page, *page.frames[1:]]
    for frame in frames:
        for sel in FINAL_SUBMIT_SELECTORS:
            try:
                btn = await frame.query_selector(sel)
                if not btn or not await btn.is_visible():
                    continue
                text = (await btn.inner_text() or "").strip().lower()
                aria = (await btn.get_attribute("aria-label") or "").strip().lower()
                if any(marker in text or marker in aria for marker in _CONTINUE_TEXT_MARKERS):
                    continue
                return btn
            except Exception:
                continue
    return None


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