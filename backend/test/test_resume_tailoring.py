import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.agents import resume_tailor as rt
from app.services import resume_edit as rx
from app.services.llm_service import LLMError, LLMService

TEX = r"""\documentclass{article}
\begin{document}
\section{Projects}
\resumeProjectHeading{\textbf{Alpha} $|$ \emph{Python, Django}}{2024}
\resumeItemListStart
\resumeItem{Built an API with Django serving 500 users}
\resumeItemListEnd
\resumeProjectHeading{\textbf{Beta} $|$ \emph{React}}{2023}
\resumeItemListStart
\resumeItem{Created a React dashboard}
\resumeItemListEnd
\end{document}
"""
RESUME = "Python Django React API developer. Built an API serving 500 users."
VALID_PDF = b"%PDF-1.5\n" + b"0" * 3000 + b"\n%%EOF\n"
ONE_PAGE_LOG = "Output written on x.pdf (1 page, 3000 bytes)."


# ---- resume_edit ----------------------------------------------------------
def test_extract_items_keeps_projects_separate():
    items = rx.extract_items(TEX)
    assert len(items) == 2
    assert "Alpha" in items[0].context and "Beta" in items[1].context


def test_valid_edit_applied_and_other_bullet_untouched():
    items = rx.extract_items(TEX)
    new, applied, rejected = rx.apply_edits(
        TEX, items, [{"id": 0, "text": "Built a Django API for 500 users with Python"}], RESUME
    )
    assert applied == [0] and not rejected
    assert "Built a Django API for 500 users with Python" in new
    assert "Created a React dashboard" in new


@pytest.mark.parametrize(
    "text",
    [
        "Deployed the Django API with Docker on AWS",   # invented tech
        "Built an API with Django serving 5000 users",  # invented number
        r"\input{/etc/passwd} Built an API with Django",  # LaTeX injection
        "Built an API with Django serving 500 users " * 4,  # too long for one page
    ],
)
def test_bad_edits_rejected(text):
    items = rx.extract_items(TEX)
    new, applied, rejected = rx.apply_edits(TEX, items, [{"id": 0, "text": text}], RESUME)
    assert applied == [] and rejected and new == TEX


def test_special_characters_escaped():
    items = rx.extract_items(TEX)
    new, applied, _ = rx.apply_edits(
        TEX, items, [{"id": 0, "text": "Built API with Django & Python"}], RESUME
    )
    assert applied == [0] and r"Django \& Python" in new


def test_validate_pdf(tmp_path):
    good = tmp_path / "ok.pdf"
    good.write_bytes(VALID_PDF)
    assert rx.validate_pdf(good, ONE_PAGE_LOG) is None
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"NOTPDF" + b"0" * 3000)
    assert "signature" in rx.validate_pdf(bad)
    assert "2 pages" in rx.validate_pdf(good, "Output written on x.pdf (2 pages, 9 bytes).")
    assert rx.validate_pdf(None) is not None
    assert rx.validate_pdf(tmp_path / "missing.pdf") is not None


def test_cover_letter_normalize():
    ok = rx.normalize_cover_letter("Dear Team,\n\n\n\n" + "Text here. " * 40 + "   \n")
    assert "\n\n\n" not in ok
    with pytest.raises(ValueError):
        rx.normalize_cover_letter("Dear [Hiring Manager],\n\n" + "x " * 200)
    with pytest.raises(ValueError):
        rx.normalize_cover_letter("short")


# ---- llm_service ----------------------------------------------------------
def _svc(handler):
    s = LLMService()
    s._transport = httpx.MockTransport(handler)
    s._retry_backoff = 0
    return s


OK_BODY = (
    b'{"message":{"content":"Hel"},"done":false}\n'
    b'{"message":{"content":"lo"},"done":true,"done_reason":"stop"}\n'
)


def test_generate_streams_and_joins():
    s = _svc(lambda req: httpx.Response(200, content=OK_BODY))
    assert asyncio.run(s.generate("hi")) == "Hello"


def test_generate_retries_timeout_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("", request=req)
        return httpx.Response(200, content=OK_BODY)

    assert asyncio.run(_svc(handler).generate("hi")) == "Hello"
    assert len(calls) == 2


def test_generate_persistent_timeout_raises_llmerror():
    def handler(req):
        raise httpx.ReadTimeout("", request=req)

    with pytest.raises(LLMError, match="ReadTimeout"):
        asyncio.run(_svc(handler).generate("hi"))


def test_truncated_output_is_an_error():
    body = b'{"message":{"content":"abc"},"done":true,"done_reason":"length"}\n'
    with pytest.raises(LLMError, match="truncated"):
        asyncio.run(_svc(lambda r: httpx.Response(200, content=body)).generate("hi"))


# ---- node behaviour ---------------------------------------------------------
class FakeLLM:
    def __init__(self, items_json):
        self.items_json = items_json

    async def generate(self, prompt, system_prompt="", **kw):
        if kw.get("json_mode"):
            if isinstance(self.items_json, Exception):
                raise self.items_json
            return self.items_json
        return "Dear Hiring Manager,\n\n" + "I am excited to apply. " * 20 + "\n\nSincerely,"


GOOD_JSON = '{"items":[{"id":0,"text":"Built a Django API for 500 users with Python"}]}'


def _patch(monkeypatch, tmp_path, llm, render=None):
    saved, failures = [], []

    def default_render(tex, out_dir, app_id):
        pdf, tx = out_dir / f"resume_{app_id}.pdf", out_dir / f"resume_{app_id}.tex"
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
    app = {"job": {"title": "Dev", "company": "Acme", "description": "Python"},
           "resume": {"raw_text": RESUME}}
    if app_id:
        app["application_id"] = app_id
    return {"run_id": "t", "user_id": "u", "applications_to_process": [app]}


def test_node_success_writes_real_pdf(monkeypatch, tmp_path):
    saved, failures = _patch(monkeypatch, tmp_path, FakeLLM(GOOD_JSON))
    out = asyncio.run(rt.resume_tailor_node(_state()))
    assert out["current_step"] == "resume_tailor_complete"
    assert len(out["applications_to_process"]) == 1 and not failures
    path = Path(saved[0][1])
    assert path.suffix == ".pdf" and path.read_bytes()[:5] == b"%PDF-"


def test_node_llm_failure_is_reported_not_success(monkeypatch, tmp_path):
    saved, failures = _patch(monkeypatch, tmp_path, FakeLLM(LLMError("boom")))
    out = asyncio.run(rt.resume_tailor_node(_state()))
    assert out["current_step"] == "resume_tailor_failed"
    assert out["applications_to_process"] == [] and not saved and len(failures) == 1


def test_node_compile_failure_saves_no_path(monkeypatch, tmp_path):
    saved, failures = _patch(
        monkeypatch, tmp_path, FakeLLM(GOOD_JSON),
        render=lambda tex, d, a: (None, "! LaTeX Error", None),
    )
    out = asyncio.run(rt.resume_tailor_node(_state()))
    assert out["current_step"] == "resume_tailor_failed" and not saved
    assert "PDF" in failures[0][1]


def test_node_missing_application_id_does_not_invent_one(monkeypatch, tmp_path):
    saved, failures = _patch(monkeypatch, tmp_path, FakeLLM(GOOD_JSON))
    out = asyncio.run(rt.resume_tailor_node(_state(app_id=None)))
    assert out["current_step"] == "resume_tailor_failed" and not saved