"""
app/services/latex_resume.py

Turns an LLM's tailored LaTeX output into a compiled, single-page PDF
resume using the user's own Overleaf template, instead of saving a
plain-text file. Kept as its own module (not merged into
llm_service.py) since compiling PDFs is a distinct concern from
talking to Ollama.
"""

import re
import subprocess
import uuid
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "resume_template.tex"


def get_user_template_path(user_id: str | uuid.UUID) -> Path:
    from app.config import get_settings
    settings = get_settings()
    return Path(settings.UPLOAD_DIR) / str(user_id) / "template.tex"


def load_resume_template(user_id: str | uuid.UUID | None = None) -> str:
    """Read the active resume template: user-customized if exists, else default Overleaf template."""
    if user_id:
        user_tpl = get_user_template_path(user_id)
        if user_tpl.is_file():
            try:
                content = user_tpl.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except Exception:
                pass
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def save_user_resume_template(user_id: str | uuid.UUID, tex_content: str) -> Path:
    """Save user-customized resume template."""
    user_tpl = get_user_template_path(user_id)
    user_tpl.parent.mkdir(parents=True, exist_ok=True)
    user_tpl.write_text(tex_content, encoding="utf-8")
    return user_tpl


def reset_user_resume_template(user_id: str | uuid.UUID) -> bool:
    """Reset to default master template."""
    user_tpl = get_user_template_path(user_id)
    if user_tpl.is_file():
        user_tpl.unlink()
        return True
    return False


def extract_latex(llm_output: str) -> str:
    """
    LLMs often wrap code in ```latex ... ``` fences or add a sentence
    of commentary before/after. Strip that so we're left with just the
    document, from \\documentclass to \\end{document}.
    """
    text = llm_output.strip()

    fence_match = re.search(r"```(?:latex|tex)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("\\documentclass")
    end = text.rfind("\\end{document}")
    if start != -1 and end != -1:
        text = text[start : end + len("\\end{document}")]

    return text.strip()


def compile_latex_to_pdf(tex_content: str, output_dir: Path, filename_stem: str) -> tuple[Path | None, str, Path]:
    """
    Compile `tex_content` with pdflatex into output_dir/filename_stem.pdf.

    Returns (pdf_path_or_None, compile_log_text, saved_tex_path).
    pdf_path is None if compilation failed or produced no PDF — callers
    must check for None and NOT treat a failure as a successful resume.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    tex_path = output_dir / f"{filename_stem}.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    log_text = ""
    pdf_path = output_dir / f"{filename_stem}.pdf"

    try:
        # Run twice: hyperref/section numbering can need a second pass
        # to resolve references cleanly. Harmless if not needed.
        for _ in range(2):
            result = subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={output_dir}",
                    str(tex_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            log_text = result.stdout + result.stderr

        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            for ext in (".aux", ".log", ".out"):
                aux_file = output_dir / f"{filename_stem}{ext}"
                if aux_file.exists():
                    aux_file.unlink()
            return pdf_path, log_text, tex_path
        return None, log_text, tex_path

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("LaTeX compilation could not run", extra={"error": str(e)})
        return None, f"{log_text}\n{e}", tex_path


def render_tailored_resume_pdf(tex_content: str, output_dir: Path, app_id: str) -> tuple[Path | None, str, Path]:
    """
    Convenience wrapper used by resume_tailor.py. Returns
    (pdf_path_or_None, compile_log_text, tex_path).

    Tries pdflatex first; if it is not installed or fails, automatically
    falls back to the ReportLab-based PDF generator so users always get
    a proper .pdf file instead of a raw .tex fallback.

    tex_path is always returned so callers have the source available.
    """
    cleaned = extract_latex(tex_content)
    stem = f"resume_{app_id}"
    pdf_path, log_text, tex_path = compile_latex_to_pdf(cleaned, output_dir, stem)

    if pdf_path is not None:
        return pdf_path, log_text, tex_path

    # pdflatex unavailable or failed — try ReportLab
    logger.warning(
        "pdflatex failed or not installed; trying ReportLab fallback",
        extra={"app_id": app_id, "pdflatex_log": (log_text or "")[-500:]},
    )
    try:
        from app.services.resume_pdf_gen import generate_resume_pdf
        rl_pdf, rl_log = generate_resume_pdf(cleaned, output_dir, stem)
        if rl_pdf is not None:
            logger.info("ReportLab PDF generated successfully", extra={"app_id": app_id})
            return rl_pdf, rl_log, tex_path
        logger.error("ReportLab PDF generation also failed", extra={"app_id": app_id, "log": rl_log})
    except Exception as e:
        logger.error("ReportLab fallback raised an exception", extra={"app_id": app_id, "error": str(e)})

    return None, log_text, tex_path