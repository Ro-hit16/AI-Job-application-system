"""
services/instant_tailor.py
---------------------------
Core engine for instant JD-based resume tailoring and PDF generation.

Features:
1. Fast skill extraction from Job Descriptions (JDs)
2. Intelligent bullet point tailoring highlighting JD skills
3. Direct ReportLab PDF compilation guaranteeing a valid .pdf file
4. On-demand PDF generation fallback for applications and jobs
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.application import Application
from app.models.job import Job
from app.services.latex_resume import load_resume_template
from app.services.resume_edit import extract_items, sanitize_text, validate_pdf, validate_tex
from app.services.resume_pdf_gen import generate_resume_pdf

logger = get_logger(__name__)
settings = get_settings()

# Comprehensive technology & skill catalog for JD matching
TECH_SKILL_CATALOG = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React.js",
    "react.js": "React.js",
    "reactjs": "React.js",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "express": "Express.js",
    "express.js": "Express.js",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "java": "Java",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    "c++": "C++",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "kafka": "Apache Kafka",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "Google Cloud",
    "git": "Git",
    "github": "GitHub Actions",
    "ci/cd": "CI/CD",
    "rest": "RESTful APIs",
    "restful": "RESTful APIs",
    "graphql": "GraphQL",
    "microservices": "Microservices",
    "machine learning": "Machine Learning",
    "ai": "AI Integration",
    "llm": "LLMs",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "tailwind": "Tailwind CSS",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "html": "HTML5",
    "css": "CSS3",
    "agile": "Agile / Scrum",
    "scrum": "Scrum",
    "unit testing": "Unit Testing",
    "pytest": "PyTest",
    "jest": "Jest",
    "jwt": "JWT Auth",
    "oauth": "OAuth",
}


def format_resume_download_filename(candidate_name: str | None = None, company: str | None = None) -> str:
    """
    Format standard industry resume download filename:
    e.g. 'Candidate_Resume_Google' or 'Candidate_Resume' (stem without .pdf extension)
    """
    raw_name = (candidate_name or "Candidate").strip()
    name_clean = re.sub(r"[^\w\s-]", "", raw_name)
    user_stem = "_".join(name_clean.split()) or "Candidate"

    if company and company.strip():
        comp_clean = re.sub(r"[^\w\s-]", "", company.strip())
        comp_stem = "_".join(comp_clean.split())[:30].strip("_")
        if comp_stem:
            return f"{user_stem}_Resume_{comp_stem}"

    return f"{user_stem}_Resume"


def extract_skills_from_jd(text: str) -> list[str]:
    """Extract recognized technologies and technical competencies from text."""
    lower = text.lower()
    found: list[str] = []
    seen = set()

    # Search for multi-word skills first, then single-word
    sorted_catalog = sorted(TECH_SKILL_CATALOG.keys(), key=lambda k: len(k), reverse=True)
    for kw in sorted_catalog:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, lower):
            canonical = TECH_SKILL_CATALOG[kw]
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
    return found


def tailor_resume_content(
    job_title: str,
    company: str,
    job_description: str,
    instructions: str = "",
    user_id: str | uuid.UUID | None = None,
    custom_template: str = "",
) -> dict[str, Any]:
    """
    Produce tailored LaTeX resume content tailored to the JD.
    Returns:
        dict with:
            matched_skills: list[str]
            highlighted_skills: list[str]
            match_score: float
            bullet_changes: list[dict]
            tailored_tex: str
    """
    if custom_template and custom_template.strip():
        base_tex = custom_template.strip()
    else:
        base_tex = load_resume_template(user_id)
    jd_skills = extract_skills_from_jd(f"{job_title} {job_description} {instructions}")

    # Dynamically extract candidate skills from the candidate's active base template & uploaded resume
    candidate_skills = set(extract_skills_from_jd(base_tex))
    if not candidate_skills:
        candidate_skills = {
            "JavaScript", "React.js", "Node.js", "Express.js", "MongoDB", "MySQL",
            "RESTful APIs", "JWT Auth", "Docker", "Git", "GitHub Actions", "CI/CD",
            "Python", "Java", "Tailwind CSS", "HTML5", "CSS3", "Agile / Scrum",
            "AWS", "PostgreSQL", "FastAPI", "AI Integration", "LLMs", "LangGraph",
        }

    matched = [s for s in jd_skills if s in candidate_skills]
    highlighted = jd_skills[:8] if jd_skills else ["Full-Stack Development", "REST APIs", "Modern Web Apps"]

    # Calculate match score (base 75% + up to 23% based on matched skills count)
    match_score = min(98.0, 75.0 + (len(matched) * 3.5)) if matched else 82.0

    items = extract_items(base_tex)
    bullet_changes = []
    tex_working = base_tex

    top_matched_str = ", ".join(matched[:5]) if matched else "Full-Stack Development, React, Node.js, REST APIs"
    role_label = job_title.strip() if job_title.strip() else "Full-Stack Software Engineer"
    company_mention = f" aligned with {company.strip()}'s engineering requirements" if company.strip() else ""

    # ── 1. Tailor Professional Summary ──────────────────────────────────────
    summary_match = re.search(
        r"(\\section\*?\{Professional Summary\}\s*)(.*?)(\s*\\section\*?)",
        tex_working,
        re.DOTALL,
    )
    if summary_match:
        tailored_summary = (
            f"Results-driven {role_label} with proven expertise in building high-performance, "
            f"scalable web applications, robust REST APIs, and end-to-end software solutions{company_mention}. "
            f"Core competencies include {top_matched_str}, cloud deployment (AWS EC2/S3), "
            f"and clean, maintainable architecture practices."
        )
        old_part = summary_match.group(2)
        tex_working = tex_working.replace(old_part, tailored_summary, 1)
        bullet_changes.append({
            "original": old_part[:120] + "...",
            "tailored": tailored_summary[:120] + "...",
            "reason": f"Aligned professional summary to target role '{role_label}'",
        })

    # ── 2. Inject role-aligned competencies into Technical Skills ───────────
    if matched:
        skills_sec_match = re.search(
            r"(\\section\*?\{Technical Skills\}\s*)(.*?)(?=\\end\{document\}|\\section)",
            tex_working, re.DOTALL
        )
        if skills_sec_match:
            sec_body = skills_sec_match.group(2)
            highlight_str = ", ".join(highlighted[:6])
            if "\\textbf{Role-Aligned Competencies:}" not in sec_body:
                new_sec_body = f"\\textbf{{Role-Aligned Competencies:}} {highlight_str} \\\\\n" + sec_body.strip() + "\n"
                tex_working = tex_working.replace(sec_body, new_sec_body, 1)
                bullet_changes.append({
                    "original": "Standard technical skills breakdown",
                    "tailored": f"Prominently featured role-aligned skills: {highlight_str}",
                    "reason": "Prioritized JD matching skills at the top of Technical Skills section",
                })

    # ── 3. Smart bullet tailoring based on JD focus area ────────────────────
    jd_lower = job_description.lower()
    focus_backend = any(w in jd_lower for w in ["backend", "api", "server", "microservice", "django", "flask", "fastapi", "node"])
    focus_frontend = any(w in jd_lower for w in ["frontend", "react", "angular", "ui", "ux", "interface"])
    focus_data = any(w in jd_lower for w in ["data", "pipeline", "etl", "analytics", "hadoop", "spark", "sql", "database"])
    focus_devops = any(w in jd_lower for w in ["devops", "docker", "kubernetes", "ci/cd", "cloud", "aws", "deployment"])
    focus_ai = any(w in jd_lower for w in ["ai", "machine learning", "llm", "nlp", "model", "ml"])

    adapted_count = 0
    used_skills: set[str] = set()

    def pick_skill(candidates: list[str], text_lower: str) -> str | None:
        for s in candidates:
            if s not in used_skills and s.lower() not in text_lower:
                return s
        for s in candidates:
            if s.lower() not in text_lower:
                return s
        return None

    for it in items:
        if adapted_count >= 4:
            break
        body_clean = it.body.strip()
        if len(body_clean) < 30:
            continue
        body_lower = body_clean.lower()

        chosen_skill = None
        embed_phrase = None

        if focus_backend and any(w in body_lower for w in ["api", "backend", "server", "express", "node", "django"]):
            backend_candidates = [s for s in matched if any(kw in s.lower() for kw in ["node", "express", "api", "rest", "postgres", "sql", "mongo", "fastapi", "django", "python"])] or matched
            chosen_skill = pick_skill(backend_candidates, body_lower)
            embed_phrase = f"incorporating {chosen_skill}" if chosen_skill else None
        elif focus_frontend and any(w in body_lower for w in ["react", "frontend", "ui", "component", "interface"]):
            frontend_candidates = [s for s in matched if any(kw in s.lower() for kw in ["react", "typescript", "javascript", "tailwind", "html", "css"])] or matched
            chosen_skill = pick_skill(frontend_candidates, body_lower)
            embed_phrase = f"leveraging {chosen_skill}" if chosen_skill else None
        elif focus_data and any(w in body_lower for w in ["data", "processing", "pipeline", "batch", "records"]):
            data_candidates = [s for s in matched if any(kw in s.lower() for kw in ["data", "sql", "postgres", "mongo", "python", "hadoop"])] or matched
            chosen_skill = pick_skill(data_candidates, body_lower)
            embed_phrase = f"utilizing {chosen_skill}" if chosen_skill else None
        elif focus_devops and any(w in body_lower for w in ["docker", "ci/cd", "deploy", "aws", "cloud"]):
            devops_candidates = [s for s in matched if any(kw in s.lower() for kw in ["docker", "ci/cd", "aws", "git", "cloud", "kubernetes"])] or matched
            chosen_skill = pick_skill(devops_candidates, body_lower)
            embed_phrase = f"with {chosen_skill} automation" if chosen_skill else None
        elif focus_ai and any(w in body_lower for w in ["ai", "llm", "recommend", "chatbot", "model"]):
            ai_candidates = [s for s in matched if any(kw in s.lower() for kw in ["ai", "llm", "langgraph", "langchain", "recommend", "python"])] or matched
            chosen_skill = pick_skill(ai_candidates, body_lower)
            embed_phrase = f"powered by {chosen_skill}" if chosen_skill else None
        elif ("API" in body_clean or "scalable" in body_clean or "developed" in body_lower) and matched:
            chosen_skill = pick_skill(matched, body_lower)
            embed_phrase = f"incorporating {chosen_skill} and industry best practices" if chosen_skill else None

        if chosen_skill and embed_phrase:
            used_skills.add(chosen_skill)
            enhanced = body_clean.rstrip(".")
            if ", " in enhanced:
                parts = enhanced.rsplit(", ", 1)
                enhanced = parts[0] + f", {embed_phrase}, " + parts[1]
            else:
                enhanced = enhanced + f", {embed_phrase}."
            try:
                _, escaped = sanitize_text(enhanced)
                tex_working = tex_working.replace(it.body, escaped, 1)
                bullet_changes.append({
                    "original": body_clean[:90] + "...",
                    "tailored": enhanced[:90] + "...",
                    "reason": f"Emphasized {chosen_skill} relevant to target JD",
                })
                adapted_count += 1
            except Exception:
                pass

    # ── 4. Update DB skills row if JD requests specific DB technologies ──────
    jd_db_skills = [s for s in highlighted if any(db in s for db in ["SQL", "Postgres", "MySQL", "MongoDB", "Redis"])]
    if jd_db_skills:
        db_line_match = re.search(r"(\\textbf\{Database:\})(.*?)(\\\\|\n)", tex_working)
        if db_line_match:
            old_line = db_line_match.group(0)
            db_body = db_line_match.group(2)
            new_db_skills = [s for s in jd_db_skills if s.lower() not in db_body.lower()]
            if new_db_skills:
                new_line = old_line.replace(db_body, db_body.rstrip() + ", " + ", ".join(new_db_skills))
                tex_working = tex_working.replace(old_line, new_line, 1)
                bullet_changes.append({
                    "original": f"Database: {db_body.strip()}",
                    "tailored": f"Database: {db_body.strip()}, {', '.join(new_db_skills)}",
                    "reason": f"Added JD-requested database skills: {', '.join(new_db_skills)}",
                })

    return {
        "matched_skills": matched,
        "highlighted_skills": highlighted,
        "match_score": round(match_score, 1),
        "bullet_changes": bullet_changes,
        "tailored_tex": tex_working,
    }

def generate_instant_tailored_pdf(
    job_title: str,
    company: str,
    job_description: str,
    output_dir: Path,
    stem: str,
    instructions: str = "",
    user_id: str | uuid.UUID | None = None,
    custom_template: str = "",
) -> tuple[Path, dict[str, Any]]:
    """
    Tailor resume and directly compile into a validated PDF.
    Guaranteed to return a valid Path to a .pdf file.
    """
    tailor_data = tailor_resume_content(
        job_title=job_title,
        company=company,
        job_description=job_description,
        instructions=instructions,
        user_id=user_id,
        custom_template=custom_template,
    )
    tex = tailor_data["tailored_tex"]

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path, log = generate_resume_pdf(tex, output_dir, stem)

    if pdf_path is None or validate_pdf(pdf_path) is not None:
        logger.warning("Tailored PDF generation failed; falling back to base template", extra={"log": log})
        fallback_tex = custom_template.strip() if custom_template and custom_template.strip() else load_resume_template(user_id)
        pdf_path, log2 = generate_resume_pdf(fallback_tex, output_dir, stem)
        if pdf_path is None or validate_pdf(pdf_path) is not None:
            raise RuntimeError(f"Could not render resume PDF: {log}; {log2}")

    return pdf_path, tailor_data


async def auto_ensure_application_pdf(
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[Path, str]:
    """
    Ensure the application has a valid .pdf resume on disk and return (path, 'application/pdf').
    
    If the application doesn't have a tailored resume yet, or if it has a stale/error .txt/.tex,
    it automatically generates a clean tailored PDF from the application's job details and
    updates the database record.
    """
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise FileNotFoundError(f"Application {application_id} not found")

    output_dir = Path(settings.UPLOAD_DIR) / str(user_id) / "tailored"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"resume_{application_id}"

    # 1. Check existing path if set
    if app.tailored_resume_path:
        curr = Path(app.tailored_resume_path)
        if curr.is_file():
            # If already a valid PDF
            if curr.suffix.lower() == ".pdf" and validate_pdf(curr) is None:
                return curr, "application/pdf"

            # If it's a .tex or .txt with valid LaTeX content, convert to PDF
            try:
                content = curr.read_text(encoding="utf-8")
                if validate_tex(content) is None:
                    out_pdf, _ = generate_resume_pdf(content, output_dir, stem)
                    if out_pdf and validate_pdf(out_pdf) is None:
                        app.tailored_resume_path = str(out_pdf)
                        await db.commit()
                        return out_pdf, "application/pdf"
            except Exception:
                pass

    # 2. Check sibling .pdf file in standard output_dir
    candidate_pdf = output_dir / f"{stem}.pdf"
    if candidate_pdf.is_file() and validate_pdf(candidate_pdf) is None:
        app.tailored_resume_path = str(candidate_pdf)
        await db.commit()
        return candidate_pdf, "application/pdf"

    # 3. Generate fresh tailored PDF using the job details
    job_title = "Software Engineer"
    company = ""
    job_desc = ""
    if app.job_id:
        job_res = await db.execute(select(Job).where(Job.id == app.job_id))
        job = job_res.scalar_one_or_none()
        if job:
            job_title = job.title or job_title
            company = job.company or ""
            job_desc = job.description or ""

    pdf_path, _ = generate_instant_tailored_pdf(
        job_title=job_title,
        company=company,
        job_description=job_desc,
        output_dir=output_dir,
        stem=stem,
        user_id=user_id,
    )

    app.tailored_resume_path = str(pdf_path)
    if app.error_message and "tailor" in app.error_message.lower():
        app.error_message = None
    await db.commit()

    return pdf_path, "application/pdf"
