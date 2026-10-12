"""Pure helpers for tailoring a LaTeX resume by rewriting bullet text only."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# One-line bullets in the Overleaf "Jake" template: \resumeItem{...}
ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)\\resumeItem\{(?P<body>.*)\}[ \t]*$", re.MULTILINE
)
_HEADING_MARKERS = ("\\resumeProjectHeading", "\\resumeSubheading", "\\section")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*[A-Za-z0-9+#]|[A-Za-z]")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_FORBIDDEN_RE = re.compile(
    r"\\(?:input|include|write|openout|read|def|edef|gdef|newcommand|renewcommand|"
    r"usepackage|documentclass|begin|end|immediate|catcode|csname)\b"
)
MAX_GROWTH = 1.10  # rewritten bullet may be at most 10% longer -> stays on one page

# Lowercase technologies that must exist in the user's own resume/template to be used.
KNOWN_TECH = frozenset(
    "docker kubernetes aws azure gcp terraform kafka redis graphql spark hadoop "
    "tensorflow pytorch java golang rust scala kotlin swift angular vue django flask "
    "fastapi react node mongodb postgresql postgres mysql jenkins ansible airflow "
    "snowflake sql typescript javascript python ci/cd selenium playwright".split()
)


@dataclass(frozen=True)
class Item:
    index: int
    body: str
    body_start: int
    body_end: int
    context: str


def _strip_latex(s: str) -> str:
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    for ch in "\\{}^~":
        s = s.replace(ch, "")
    return re.sub(r"\s+", " ", s).strip()


def _context(tex: str, pos: int) -> str:
    start = max(tex.rfind(mk, 0, pos) for mk in _HEADING_MARKERS)
    if start < 0:
        return ""
    snippet = tex[start:pos].split("\\resumeItem")[0]
    snippet = snippet.replace("$|$", " | ")
    return _strip_latex(snippet)[:90]


def extract_items(tex: str) -> list[Item]:
    return [
        Item(i, m.group("body"), m.start("body"), m.end("body"), _context(tex, m.start()))
        for i, m in enumerate(ITEM_RE.finditer(tex))
    ]


def _norm(w: str) -> str:
    return w.lower().strip(".-")


def tokens(text: str) -> set[str]:
    return {_norm(w) for w in _WORD_RE.findall(text)}


def invented_terms(plain: str, allowed: set[str]) -> list[str]:
    flagged = []
    for i, w in enumerate(_WORD_RE.findall(plain)):
        lw = _norm(w)
        if lw in allowed:
            continue
        special = any(c in w for c in "+#.") or any(c.isdigit() for c in w)
        if special or (i > 0 and w[0].isupper()) or lw in KNOWN_TECH:
            flagged.append(w)
    return flagged


def sanitize_text(text: str) -> tuple[str, str]:
    """Return (plain, latex_escaped). Raises ValueError on unsafe/empty text."""
    if _FORBIDDEN_RE.search(text):
        raise ValueError("contains forbidden LaTeX command")
    plain = _strip_latex(text)
    if not plain:
        raise ValueError("empty text")
    return plain, re.sub(r"([&%$#_])", r"\\\1", plain)


def apply_edits(
    tex: str, items: list[Item], edits: list, resume_text: str
) -> tuple[str, list[int], list[str]]:
    """Apply validated bullet rewrites. Returns (new_tex, applied_ids, rejection_reasons)."""
    allowed_tokens = tokens(tex) | tokens(resume_text)
    allowed_numbers = set(_NUM_RE.findall(tex)) | set(_NUM_RE.findall(resume_text))
    by_id = {it.index: it for it in items}
    accepted: dict[int, str] = {}
    rejected: list[str] = []

    for e in edits:
        try:
            idx, text = int(e["id"]), e["text"]
        except (KeyError, TypeError, ValueError):
            rejected.append("malformed edit")
            continue
        item = by_id.get(idx)
        if item is None or idx in accepted:
            rejected.append(f"#{idx}: unknown or duplicate id")
            continue
        if not isinstance(text, str):
            rejected.append(f"#{idx}: text not a string")
            continue
        try:
            plain, escaped = sanitize_text(text)
        except ValueError as exc:
            rejected.append(f"#{idx}: {exc}")
            continue
        original = _strip_latex(item.body)
        if plain == original:
            continue
        if len(plain) < 15 or len(plain) > max(len(original) * MAX_GROWTH, 40):
            rejected.append(f"#{idx}: length {len(plain)} vs original {len(original)}")
            continue
        bad_nums = set(_NUM_RE.findall(plain)) - allowed_numbers
        if bad_nums:
            rejected.append(f"#{idx}: invented numbers {sorted(bad_nums)}")
            continue
        bad_terms = invented_terms(plain, allowed_tokens)
        if bad_terms:
            rejected.append(f"#{idx}: terms not in resume {bad_terms[:4]}")
            continue
        accepted[idx] = escaped

    new = tex
    for idx in sorted(accepted, reverse=True):  # reverse keeps earlier offsets valid
        it = by_id[idx]
        new = new[: it.body_start] + accepted[idx] + new[it.body_end :]
    return new, sorted(accepted), rejected


def build_tailor_prompt(job_title, company, job_desc, resume_text, items, edit_instructions="") -> str:
    bullets = "\n".join(
        f"[{it.index}] ({it.context or 'general'}) {_strip_latex(it.body)}" for it in items
    )
    extra = f"\nUser instructions: {edit_instructions}\n" if edit_instructions else ""
    return f"""Target job: {job_title} at {company}

Job description (truncated):
{job_desc[:1500]}

Candidate background (the ONLY facts you may use):
{resume_text[:2000]}

Current resume bullets (id, project/section, text):
{bullets}
{extra}
Rewrite bullets so the wording better matches the job. Rules:
- Edit only bullets that benefit; skip the rest.
- Each bullet stays about the same length or shorter. Plain text only, no LaTeX.
- Keep each bullet about its own project. Never merge or move content between bullets.
- Do NOT add any technology, skill, tool, achievement or number that is not already
  in the bullet or the candidate background, even if the job description mentions it.
Return ONLY this JSON: {{"items": [{{"id": 0, "text": "rewritten bullet"}}]}}"""


def validate_tex(tex: str) -> str | None:
    if not tex or not tex.strip():
        return "LaTeX is empty"
    head = tex.lstrip().lower()
    if head.startswith(("llm error", "resume tailoring failed", "traceback", "error:")):
        return "File contains an error message, not LaTeX"
    for marker in ("\\documentclass", "\\begin{document}", "\\end{document}"):
        if marker not in tex:
            return f"LaTeX is missing {marker}"
    return None


def validate_pdf(path, compile_log: str = "") -> str | None:
    """Return an error string, or None if the PDF looks valid and is one page."""
    if path is None:
        return "PDF compilation failed (no PDF produced)"
    p = Path(path)
    if not p.is_file():
        return f"PDF not found on disk: {p.name}"
    data = p.read_bytes()
    if len(data) < 2000:
        return f"PDF too small ({len(data)} bytes)"
    if not data.startswith(b"%PDF-"):
        return "File does not start with %PDF- signature"
    if b"%%EOF" not in data[-1024:]:
        return "PDF is truncated (no %%EOF)"
    m = re.search(r"\((\d+) pages?", compile_log or "")
    if m and int(m.group(1)) > 1:
        return f"Resume is {m.group(1)} pages; must fit one page"
    return None


def normalize_cover_letter(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    if re.search(r"\[[A-Za-z ]{3,}\]", text):
        raise ValueError("cover letter contains an unfilled placeholder")
    if len(text) < 300:
        raise ValueError("cover letter too short")
    return text + "\n"