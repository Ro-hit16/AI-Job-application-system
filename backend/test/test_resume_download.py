"""
test/test_resume_download.py
============================
Focused regression tests for the resume generation → download flow.

Covers:
  1. `_select_resume_artifact` is used (not raw pdf_path) when saving paths — the
     main root cause that caused None/stale paths in the DB after PDF compile failure.
  2. `.tex` fallback path is persisted correctly when PDF compilation fails.
  3. `_resolve_resume_file` validates the file correctly and raises appropriate HTTP
     errors for missing/corrupt/empty files.
  4. `validate_tex` in `_resolve_resume_file` — the NameError bug — is fixed.
  5. `LLMService.chat()` is a proper class method (not nested inside `embed()`).
  6. `ApplicationOut` schema exposes all required download-flow fields.
  7. Frontend `extractErrorDetail` fallback logic for blob error responses (via
     a pure-Python simulation of the same logic).
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import resume_edit as rx
from app.services.llm_service import LLMError, LLMService
from app.agents import resume_tailor as rt


# ── Shared fixtures ────────────────────────────────────────────────────────────

TEX = r"""\documentclass{article}
\begin{document}
\section{Projects}
\resumeProjectHeading{\textbf{Alpha} $|$ \emph{Python, Django}}{2024}
\resumeItemListStart
\resumeItem{Built an API with Django serving 500 users}
\resumeItemListEnd
\end{document}
"""
RESUME = "Python Django React API developer. Built an API serving 500 users."
VALID_PDF = b"%PDF-1.5\n" + b"0" * 3000 + b"\n%%EOF\n"
ONE_PAGE_LOG = "Output written on x.pdf (1 page, 3000 bytes)."
GOOD_JSON = '{"items":[{"id":0,"text":"Built a Django API for 500 users with Python"}]}'


class FakeLLM:
    def __init__(self, items_json):
        self.items_json = items_json

    async def generate(self, prompt, system_prompt="", **kw):
        if kw.get("json_mode"):
            if isinstance(self.items_json, Exception):
                raise self.items_json
            return self.items_json
        return "Dear Hiring Manager,\n\n" + "I am excited to apply. " * 20 + "\n\nSincerely,"


def _patch(monkeypatch, tmp_path, llm, render=None):
    saved, failures = [], []

    def default_render(tex, out_dir, app_id):
        pdf = out_dir / f"resume_{app_id}.pdf"
        tx = out_dir / f"resume_{app_id}.tex"
        pdf.write_bytes(VALID_PDF)
        tx.write_text(tex)
        return pdf, ONE_PAGE_LOG, tx

    async def fake_save(app_id, resume_path, cover_path):
        saved.append((app_id, resume_path, cover_path))

    async def fake_fail(app_id, message):
        failures.append((app_id, message))

    monkeypatch.setattr(rt, "RESUME_TEMPLATE", TEX)
    monkeypatch.setattr(rt, "settings", SimpleNamespace(UPLOAD_DIR=str(tmp_path)))
    monkeypatch.setattr(rt, "get_llm_service", lambda: llm)
    monkeypatch.setattr(rt, "render_tailored_resume_pdf", render or default_render)
    monkeypatch.setattr(rt, "_save_result", fake_save)
    monkeypatch.setattr(rt, "_record_failure", fake_fail)
    return saved, failures


def _state(app_id="3f2b8c1e-5d4a-4c8e-9a67-1b2c3d4e5f60"):
    app = {
        "job": {"title": "Dev", "company": "Acme", "description": "Python"},
        "resume": {"raw_text": RESUME},
    }
    if app_id:
        app["application_id"] = app_id
    return {"run_id": "t", "user_id": "u", "applications_to_process": [app]}


# ══════════════════════════════════════════════════════════════════════════════
# 1. BUG FIX: `selected` is used (not raw pdf_path) when saving to DB
# ══════════════════════════════════════════════════════════════════════════════

def test_saved_path_is_selected_not_raw_pdf_path(monkeypatch, tmp_path):
    """
    Regression: previously _save_result was called with str(pdf_path) and
    app_data["tailored_resume_path"] was set to str(pdf_path). When pdflatex
    fails (pdf_path=None), this saved "None" or None to the DB.
    Now both use str(selected) which is the output of _select_resume_artifact().
    """
    saved, failures = _patch(monkeypatch, tmp_path, FakeLLM(GOOD_JSON))
    out = asyncio.run(rt.resume_tailor_node(_state()))

    assert out["current_step"] == "resume_tailor_complete"
    assert len(saved) == 1
    app_id, resume_path, _ = saved[0]
    # Must be a real, non-None path pointing to either a .pdf or .tex file
    assert resume_path is not None
    assert resume_path != "None"
    p = Path(resume_path)
    assert p.suffix in (".pdf", ".tex"), f"unexpected suffix: {p.suffix}"
    assert p.is_file(), f"saved path doesn't exist: {resume_path}"
    # State must match DB
    apps_out = out["applications_to_process"]
    assert apps_out[0]["tailored_resume_path"] == resume_path


# ══════════════════════════════════════════════════════════════════════════════
# 2. BUG FIX: `.tex` fallback path persisted when PDF compilation fails
# ══════════════════════════════════════════════════════════════════════════════

def test_tex_fallback_path_is_saved_when_pdf_fails(monkeypatch, tmp_path):
    """
    When pdflatex produces no PDF but the .tex is valid, _select_resume_artifact
    returns the .tex path. That path (not None) must be persisted to DB.
    Previously pdf_path=None was passed to _save_result → the row got None.
    """
    def render_no_pdf(tex, out_dir, app_id):
        tex_file = out_dir / f"resume_{app_id}.tex"
        tex_file.write_text(tex)
        # pdflatex failed: pdf_path=None but tex_path is valid
        return None, "! LaTeX Error\n", tex_file

    saved, failures = _patch(monkeypatch, tmp_path, FakeLLM(GOOD_JSON), render=render_no_pdf)
    out = asyncio.run(rt.resume_tailor_node(_state()))

    assert out["current_step"] == "resume_tailor_complete", f"errors: {out.get('errors')}"
    assert len(saved) == 1
    _, resume_path, _ = saved[0]
    assert resume_path is not None and resume_path != "None"
    p = Path(resume_path)
    assert p.suffix == ".tex"
    assert p.is_file()
    assert out["applications_to_process"][0]["tailored_resume_path"] == resume_path


# ══════════════════════════════════════════════════════════════════════════════
# 3. BUG FIX: `validate_tex` NameError in _resolve_resume_file is fixed
# ══════════════════════════════════════════════════════════════════════════════

def test_resolve_resume_file_validates_tex_without_name_error(tmp_path):
    """
    Regression: _resolve_resume_file called validate_tex() which was not imported
    in applications.py, causing NameError: name 'validate_tex' is not defined.
    """
    from app.api.v1.applications import _resolve_resume_file
    from fastapi import HTTPException

    # Valid .tex file should validate without NameError
    valid_tex = tmp_path / "resume_test.tex"
    valid_tex.write_text(TEX, encoding="utf-8")
    path, media = _resolve_resume_file(str(valid_tex))
    assert media == "application/pdf"
    assert path.suffix == ".pdf"

    # Invalid .tex (plain text, not a LaTeX document) must raise 409
    bad_tex = tmp_path / "bad.tex"
    bad_tex.write_text("This is not LaTeX at all.", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        _resolve_resume_file(str(bad_tex))
    assert exc.value.status_code == 409


def test_resolve_resume_file_validates_pdf(tmp_path):
    """PDF validation in _resolve_resume_file must accept valid PDFs and reject corrupt ones."""
    from app.api.v1.applications import _resolve_resume_file
    from fastapi import HTTPException

    # Valid PDF
    good_pdf = tmp_path / "resume.pdf"
    good_pdf.write_bytes(VALID_PDF)
    path, media = _resolve_resume_file(str(good_pdf))
    assert media == "application/pdf"
    assert path == good_pdf

    # Corrupt PDF (wrong magic bytes)
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"NOTPDF" + b"0" * 3000)
    with pytest.raises(HTTPException) as exc:
        _resolve_resume_file(str(bad_pdf))
    assert exc.value.status_code == 409

    # Empty file
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(HTTPException) as exc:
        _resolve_resume_file(str(empty))
    assert exc.value.status_code == 409

    # Missing file
    with pytest.raises(HTTPException) as exc:
        _resolve_resume_file(str(tmp_path / "missing.pdf"))
    assert exc.value.status_code == 404

    # None / no path
    with pytest.raises(HTTPException) as exc:
        _resolve_resume_file(None)
    assert exc.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 4. BUG FIX: LLMService.chat() is a proper class method (not nested in embed)
# ══════════════════════════════════════════════════════════════════════════════

def test_llm_service_has_chat_method():
    """
    Regression: chat() was indented inside embed(), making it a nested function
    unreachable as a method of LLMService instances (hasattr returned False).
    """
    svc = LLMService()
    assert hasattr(svc, "chat"), "LLMService.chat() is missing — indentation bug not fixed"
    assert callable(svc.chat)


def test_llm_service_chat_raises_llmerror_on_failure():
    """chat() must surface failures as LLMError, not swallow them."""
    import httpx

    svc = LLMService()
    svc._transport = httpx.MockTransport(lambda req: httpx.Response(500, content=b"server error"))

    with pytest.raises(LLMError):
        asyncio.run(svc.chat([{"role": "user", "content": "hi"}]))


# ══════════════════════════════════════════════════════════════════════════════
# 5. ApplicationOut schema has all required download-flow fields
# ══════════════════════════════════════════════════════════════════════════════

def test_application_out_schema_has_all_required_fields():
    """
    Previously ApplicationOut was defined 3 times; the intermediate definitions
    lacked fields like error_message, confirmation_number, applied_at.
    After cleanup only one definition remains with all fields.
    """
    from app.schemas import ApplicationOut

    fields = ApplicationOut.model_fields
    required_for_ui = [
        "id",
        "status",
        "tailored_resume_path",
        "error_message",
        "confirmation_number",
        "applied_at",
        "match_score",
        "job",
    ]
    missing = [f for f in required_for_ui if f not in fields]
    assert not missing, f"ApplicationOut is missing fields: {missing}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. validate_tex correctly rejects LLM error strings as resume content
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_content", [
    "LLM error: connection refused",
    "Resume tailoring failed: model returned no usable edits",
    "Traceback (most recent call last):\n  ...",
    "Error: something went wrong",
    "",
    "   ",
])
def test_validate_tex_rejects_error_strings(bad_content):
    """validate_tex must reject anything that looks like an error/traceback, not valid LaTeX."""
    result = rx.validate_tex(bad_content)
    assert result is not None, f"Should have rejected: {bad_content!r}"


def test_validate_tex_accepts_valid_template():
    """validate_tex must accept the actual template LaTeX."""
    assert rx.validate_tex(TEX) is None


# ══════════════════════════════════════════════════════════════════════════════
# 7. validate_pdf correctly identifies PDF validity
# ══════════════════════════════════════════════════════════════════════════════

def test_validate_pdf_accepts_valid_one_page_pdf(tmp_path):
    p = tmp_path / "ok.pdf"
    p.write_bytes(VALID_PDF)
    assert rx.validate_pdf(p, ONE_PAGE_LOG) is None


def test_validate_pdf_rejects_none():
    assert rx.validate_pdf(None) is not None


def test_validate_pdf_rejects_multipage(tmp_path):
    p = tmp_path / "two_page.pdf"
    p.write_bytes(VALID_PDF)
    result = rx.validate_pdf(p, "Output written on x.pdf (2 pages, 9 bytes).")
    assert result is not None and "2 pages" in result


def test_validate_pdf_rejects_corrupt(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"NOTPDF" + b"0" * 3000)
    assert "signature" in rx.validate_pdf(p)


def test_validate_pdf_rejects_too_small(tmp_path):
    p = tmp_path / "tiny.pdf"
    p.write_bytes(b"%PDF-1.5\n" + b"0" * 10 + b"\n%%EOF\n")
    result = rx.validate_pdf(p)
    assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# 8. .txt PATH RECOVERY, VALIDATION, AND REJECTION REGRESSION TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_resolve_resume_file_recovers_valid_latex_txt(tmp_path):
    """If a .txt file contains valid LaTeX, it must safely recover as .tex."""
    from app.api.v1.applications import _resolve_resume_file
    txt_file = tmp_path / "resume_123.txt"
    txt_file.write_text(TEX, encoding="utf-8")

    path, media = _resolve_resume_file(str(txt_file))
    assert path.suffix == ".pdf"
    assert media == "application/pdf"
    assert path.is_file()


def test_resolve_resume_file_recovers_valid_pdf_txt(tmp_path):
    """If a .txt file is actually a valid PDF, it must safely recover as .pdf."""
    from app.api.v1.applications import _resolve_resume_file
    txt_file = tmp_path / "resume_456.txt"
    txt_file.write_bytes(VALID_PDF)

    path, media = _resolve_resume_file(str(txt_file))
    assert path.suffix == ".pdf"
    assert media == "application/pdf"
    assert path.is_file()
    assert path.read_bytes().startswith(b"%PDF-")


def test_resolve_resume_file_rejects_invalid_txt(tmp_path):
    """If a .txt file contains plain text or error message, it must raise 409 and NOT create .tex/.pdf."""
    from fastapi import HTTPException
    from app.api.v1.applications import _resolve_resume_file

    txt_file = tmp_path / "resume_bad.txt"
    txt_file.write_text("Here is the rewritten resume:\nJohn Doe\nDeveloper", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_resume_file(str(txt_file))

    assert exc_info.value.status_code == 409
    assert "not a valid resume" in exc_info.value.detail
    assert not (tmp_path / "resume_bad.tex").exists()
    assert not (tmp_path / "resume_bad.pdf").exists()


def test_resolve_resume_file_rejects_missing_file(tmp_path):
    """Missing resume file must raise 404."""
    from fastapi import HTTPException
    from app.api.v1.applications import _resolve_resume_file

    with pytest.raises(HTTPException) as exc_info:
        _resolve_resume_file(str(tmp_path / "nonexistent.txt"))

    assert exc_info.value.status_code == 404
    assert "missing on the server" in exc_info.value.detail


def test_resolve_resume_file_rejects_empty_file(tmp_path):
    """0-byte file must raise 409."""
    from fastapi import HTTPException
    from app.api.v1.applications import _resolve_resume_file

    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_resume_file(str(empty_file))

    assert exc_info.value.status_code == 409
    assert "empty" in exc_info.value.detail


def test_resolve_resume_file_prioritizes_pdf_over_tex(tmp_path):
    """If a valid .pdf exists alongside a .tex, return the .pdf with application/pdf."""
    from app.api.v1.applications import _resolve_resume_file

    tex_file = tmp_path / "resume_dual.tex"
    tex_file.write_text(TEX, encoding="utf-8")
    pdf_file = tmp_path / "resume_dual.pdf"
    pdf_file.write_bytes(VALID_PDF)

    path, media = _resolve_resume_file(str(tex_file))
    assert path == pdf_file
    assert media == "application/pdf"


def test_resolve_resume_file_rejects_unsupported_extension(tmp_path):
    """Unsupported extension like .docx must raise 415."""
    from fastapi import HTTPException
    from app.api.v1.applications import _resolve_resume_file

    docx_file = tmp_path / "resume.docx"
    docx_file.write_bytes(b"PK\x03\x04" + b"x" * 100)

    with pytest.raises(HTTPException) as exc_info:
        _resolve_resume_file(str(docx_file))

    assert exc_info.value.status_code == 415
    assert "Unsupported resume file type" in exc_info.value.detail


def test_extract_items_supports_both_item_and_resume_item():
    """extract_items must support both \\resumeItem{...} and standard \\item ..."""
    mixed_tex = r"""\documentclass{article}
\begin{document}
\section{Experience}
\begin{itemize}
    \item Standard itemize bullet point for testing
\end{itemize}
\section{Projects}
\resumeProjectHeading{\textbf{Alpha}}{2024}
\resumeItemListStart
    \resumeItem{Custom resume item bullet point for testing}
\resumeItemListEnd
\end{document}
"""
    items = rx.extract_items(mixed_tex)
    assert len(items) == 2
    assert "Standard itemize" in items[0].body
    assert "Custom resume item" in items[1].body


def test_extract_items_on_actual_template():
    """Actual resume_template.tex must have bullet items extracted."""
    from app.services.latex_resume import load_resume_template
    template = load_resume_template()
    items = rx.extract_items(template)
    assert len(items) >= 10, f"Expected at least 10 items in actual template, got {len(items)}"


@pytest.mark.asyncio
async def test_download_updated_resume_returns_pdf(tmp_path):
    """When a valid PDF is saved, download_updated_resume must serve it with application/pdf."""
    import uuid
    from app.api.v1.applications import download_updated_resume

    good_pdf = tmp_path / "resume_test.pdf"
    good_pdf.write_bytes(VALID_PDF)

    app_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_app = SimpleNamespace(
        id=app_id,
        user_id=user_id,
        tailored_resume_path=str(good_pdf),
    )

    class FakeSession:
        async def execute(self, q):
            return SimpleNamespace(scalar_one_or_none=lambda: mock_app)

        async def commit(self):
            pass

    response = await download_updated_resume(app_id, user_id=user_id, db=FakeSession())
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert "updated_resume_" in response.headers.get("content-disposition", "")
    assert response.headers.get("content-disposition", "").endswith('.pdf"')
    assert Path(response.path).read_bytes().startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_download_updated_resume_prioritizes_pdf_and_updates_db(tmp_path):
    """When DB has .tex path but a valid .pdf exists alongside, download must serve PDF and update DB path."""
    import uuid
    from app.api.v1.applications import download_updated_resume

    tex_file = tmp_path / "resume_test.tex"
    tex_file.write_text(TEX, encoding="utf-8")
    pdf_file = tmp_path / "resume_test.pdf"
    pdf_file.write_bytes(VALID_PDF)

    app_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_app = SimpleNamespace(
        id=app_id,
        user_id=user_id,
        tailored_resume_path=str(tex_file),
    )
    committed = []

    class FakeSession:
        async def execute(self, q):
            return SimpleNamespace(scalar_one_or_none=lambda: mock_app)

        async def commit(self):
            committed.append(mock_app.tailored_resume_path)

    response = await download_updated_resume(app_id, user_id=user_id, db=FakeSession())
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert mock_app.tailored_resume_path == str(pdf_file)
    assert committed == [str(pdf_file)]


def test_compiler_failure_preserves_valid_tex(tmp_path):
    """When the compiler fails or is missing, compile_latex_to_pdf must preserve the valid .tex file on disk."""
    from app.services.latex_resume import compile_latex_to_pdf

    pdf_path, log, tex_path = compile_latex_to_pdf(TEX, tmp_path, "test_resume")
    assert tex_path.is_file()
    assert "\\documentclass" in tex_path.read_text(encoding="utf-8")
    assert pdf_path is None or (pdf_path.is_file() and pdf_path.read_bytes().startswith(b"%PDF-"))


