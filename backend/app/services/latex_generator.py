"""
services/latex_generator.py
----------------------------
Dynamically generates a customized Overleaf-compatible LaTeX (.tex) resume
template from any candidate's parsed resume data or user profile.

Guarantees full user data privacy:
- Every candidate gets their OWN LaTeX resume containing THEIR own name,
  contact details, education, skills, and work history.
- Never cross-contaminates one user's private data with another user's template.
"""
from __future__ import annotations

import re
from typing import Any


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    if not text:
        return ""
    s = str(text)
    # Replace backslashes first
    s = s.replace("\\", "\\textbackslash{}")
    # Replace other specials
    specials = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    for char, escaped in specials.items():
        s = s.replace(char, escaped)
    return s.strip()


def build_latex_from_candidate_data(
    candidate_name: str,
    email: str = "",
    phone: str = "",
    location: str = "",
    linkedin: str = "",
    github: str = "",
    summary: str = "",
    skills: dict[str, list[str]] | None = None,
    experience: list[dict[str, Any]] | None = None,
    education: list[dict[str, Any]] | None = None,
    projects: list[dict[str, Any]] | None = None,
) -> str:
    """
    Construct a complete, compilable LaTeX resume string matching the
    high-standard 1-page Overleaf layout for a specific candidate.
    """
    name_clean = _escape_latex(candidate_name or "Candidate Name")

    # Build Header Links
    header_parts = []
    if email:
        header_parts.append(f"\\href{{mailto:{email}}}{{{_escape_latex(email)}}}")
    if phone:
        header_parts.append(_escape_latex(phone))
    if linkedin:
        clean_li = linkedin if linkedin.startswith("http") else f"https://{linkedin}"
        header_parts.append(f"\\href{{{clean_li}}}{{LinkedIn}}")
    if github:
        clean_gh = github if github.startswith("http") else f"https://{github}"
        header_parts.append(f"\\href{{{clean_gh}}}{{GitHub}}")

    header_contacts_str = " \\;|\\; ".join(header_parts)
    location_str = f"\\\\ \n    {_escape_latex(location)}" if location else ""

    # Build Summary
    clean_summary = _escape_latex(
        summary
        or f"Results-driven Software Engineer with proven expertise across modern full-stack "
        f"technologies, scalable microservices, and end-to-end web architectures."
    )

    # Build Education
    edu_rows = []
    if education:
        for ed in education:
            deg = _escape_latex(ed.get("degree") or ed.get("degree_name") or "Degree in Computer Science")
            inst = _escape_latex(ed.get("institution") or ed.get("college") or ed.get("school") or "University")
            yr = _escape_latex(str(ed.get("year") or ed.get("duration") or "2020 -- 2024"))
            gpa = ed.get("gpa") or ed.get("cgpa") or ed.get("percentage")
            gpa_line = f" & {_escape_latex(str(gpa))} & \\\\[0.1em]" if gpa else " & & \\\\[0.1em]"
            edu_rows.append(f"\\textbf{{{deg}}} & {inst} & {yr} \\\\\n{gpa_line}")
    else:
        edu_rows.append(
            "\\textbf{B.S. in Computer Science} & University & 2020 -- 2024 \\\\\n & & \\\\[0.1em]"
        )
    edu_str = "\n".join(edu_rows)

    # Build Skills
    skill_lines = []
    if skills and isinstance(skills, dict):
        if skills.get("languages"):
            skill_lines.append(f"\\textbf{{Languages:}} {', '.join(_escape_latex(s) for s in skills['languages'])}")
        if skills.get("frameworks"):
            skill_lines.append(f"\\textbf{{Frontend/Frameworks:}} {', '.join(_escape_latex(s) for s in skills['frameworks'])}")
        if skills.get("backend"):
            skill_lines.append(f"\\textbf{{Backend:}} {', '.join(_escape_latex(s) for s in skills['backend'])}")
        if skills.get("databases"):
            skill_lines.append(f"\\textbf{{Databases:}} {', '.join(_escape_latex(s) for s in skills['databases'])}")
        if skills.get("tools"):
            skill_lines.append(f"\\textbf{{DevOps \\& Tools:}} {', '.join(_escape_latex(s) for s in skills['tools'])}")
        if not skill_lines and skills.get("all"):
            skill_lines.append(f"\\textbf{{Technical Skills:}} {', '.join(_escape_latex(s) for s in skills['all'][:15])}")

    if not skill_lines:
        skill_lines = [
            "\\textbf{Languages:} Python, JavaScript, TypeScript, Java, SQL",
            "\\textbf{Frameworks:} React.js, Node.js, Express.js, FastAPI, Next.js",
            "\\textbf{Databases:} PostgreSQL, MongoDB, Redis, MySQL",
            "\\textbf{DevOps \\& Tools:} Docker, Git, GitHub Actions, AWS, CI/CD",
        ]
    skills_str = " \\\\\n".join(skill_lines)

    # Build Experience
    exp_blocks = []
    if experience:
        for exp in experience:
            role = _escape_latex(exp.get("role") or exp.get("title") or "Software Engineer")
            comp = _escape_latex(exp.get("company") or "Company Name")
            dur = _escape_latex(exp.get("duration") or "2023 -- Present")

            bullets = exp.get("bullets") or exp.get("responsibilities") or []
            if not bullets and exp.get("description"):
                desc = exp["description"]
                bullets = [b.strip("-*• ") for b in desc.split("\n") if b.strip()]

            if not bullets:
                bullets = [
                    f"Collaborated with cross-functional teams to design, develop, and deploy production software modules.",
                    f"Engineered resilient API endpoints and optimized database operations, improving execution latency.",
                ]

            bullet_items = "\n".join(f"    \\item {_escape_latex(b)}" for b in bullets[:4])
            exp_blocks.append(
                f"\\textbf{{{role}}} \\hfill {comp} \\hfill {dur}\n"
                f"\\begin{{itemize}}\n"
                f"{bullet_items}\n"
                f"\\end{{itemize}}"
            )
    else:
        exp_blocks.append(
            "\\textbf{Software Engineer} \\hfill Technology Solutions \\hfill 2023 -- Present\n"
            "\\begin{itemize}\n"
            "    \\item Architected and launched full-stack features utilizing modern component libraries and RESTful services.\n"
            "    \\item Optimized database query patterns and API caching, reducing average response latency by 35\\%.\n"
            "\\end{itemize}"
        )
    exp_str = "\n\n".join(exp_blocks)

    # Build Projects
    proj_blocks = []
    if projects:
        for pr in projects:
            title = _escape_latex(pr.get("name") or pr.get("title") or "Full-Stack Application")
            stack = _escape_latex(pr.get("stack") or pr.get("tech") or "")
            stack_str = f" \\textit{{({stack})}}" if stack else ""
            link = pr.get("link") or pr.get("url") or ""
            link_str = f" \\hfill \\href{{{link}}}{{Live Demo}}" if link else ""
            yr = _escape_latex(str(pr.get("year") or ""))
            yr_str = f" \\hfill {yr}" if yr else ""

            bullets = pr.get("bullets") or []
            if not bullets and pr.get("description"):
                bullets = [b.strip("-*• ") for b in pr["description"].split("\n") if b.strip()]
            if not bullets:
                bullets = [
                    "Engineered end-to-end full stack architecture with secure authentication and real-time state synchronization.",
                    "Designed scalable backend schemas and comprehensive API test suites to guarantee reliability.",
                ]

            bullet_items = "\n".join(f"    \\item {_escape_latex(b)}" for b in bullets[:3])
            proj_blocks.append(
                f"\\textbf{{{title}}}{stack_str}{link_str}{yr_str}\n"
                f"\\begin{{itemize}}\n"
                f"{bullet_items}\n"
                f"\\end{{itemize}}"
            )
    else:
        proj_blocks.append(
            "\\textbf{Real-Time Analytics Platform} \\textit{(React, Node.js, PostgreSQL)} \\hfill 2024\n"
            "\\begin{itemize}\n"
            "    \\item Built a reactive dashboard for monitoring service health metrics with sub-second polling updates.\n"
            "    \\item Implemented JWT-based role authorization and Redis caching layers for high concurrent throughput.\n"
            "\\end{itemize}"
        )
    proj_str = "\n\n".join(proj_blocks)

    # Assemble Document
    tex = f"""\\documentclass[10pt,a4paper]{{article}}
\\usepackage[margin=0.85cm]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage[hidelinks]{{hyperref}}
\\usepackage{{titlesec}}
\\usepackage{{tabularx}}

\\renewcommand{{\\baselinestretch}}{{0.95}}
\\titlespacing*{{\\section}}{{0pt}}{{0.3em}}{{0.2em}}
\\setlist[itemize]{{topsep=0.08em, itemsep=0.08em, leftmargin=1.2em}}

\\titleformat{{\\section}}{{\\bfseries\\scshape\\large}}{{}}{{0em}}{{}}[\\titlerule]
\\pagestyle{{empty}}

\\begin{{document}}

%====================
% Header
%====================
\\begin{{center}}
    {{\\LARGE \\textbf{{{name_clean}}}}} \\\\
    {header_contacts_str}{location_str}
\\end{{center}}

%====================
\\section*{{Professional Summary}}
{clean_summary}

%====================
\\section*{{Education}}
\\begin{{tabularx}}{{\\textwidth}}{{@{{}} l X r @{{}}}}
{edu_str}
\\end{{tabularx}}

%====================
\\section*{{Technical Skills}}
{skills_str}

%====================
\\section*{{Professional Experience}}
{exp_str}

%====================
\\section*{{Projects}}
{proj_str}

\\end{{document}}
"""
    return tex

