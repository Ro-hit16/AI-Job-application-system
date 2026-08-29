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


def load_resume_template() -> str:
    """Read the user's fixed Overleaf resume template."""
    return TEMPLATE_PATH.read_text(encoding="utf-8")


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


def render_tailored_resume_pdf(tex_content: str, output_dir: Path, app_id: str) -> tuple[Path | None, str]:
    """
    Convenience wrapper used by resume_tailor.py. Returns
    (pdf_path_or_None, compile_log_text).
    """
    cleaned = extract_latex(tex_content)
    pdf_path, log_text, _tex_path = compile_latex_to_pdf(cleaned, output_dir, f"resume_{app_id}")
    return pdf_path, log_text