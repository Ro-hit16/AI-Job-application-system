"""
services/resume_pdf_gen.py
---------------------------
High-fidelity LaTeX resume to PDF compiler using ReportLab.
Renders resumes that match Overleaf's LaTeX output in layout,
typography (Times serif), 1-page alignment, and clickable hyperlinks.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN = 24.1  # 0.85 cm
CONTENT_W = PAGE_W - 2 * MARGIN


def latex_to_xml(s: str) -> str:
    """Convert LaTeX formatting into ReportLab Paragraph XML-compatible markup."""
    if not s:
        return ""

    # Convert \href{url}{text} to working HTML link
    def href_sub(m):
        url, text = m.group(1).strip(), m.group(2).strip()
        # Clean text of nested commands
        text = re.sub(r"\\textbf\{([^}]+)\}", r"<b>\1</b>", text)
        if "Live Demo" in text:
            return f'<a href="{url}"><font color="#0b57d0"><u>{text}</u></font></a>'
        return f'<a href="{url}"><font color="#000000">{text}</font></a>'

    s = re.sub(r"\\href\{([^}]+)\}\{([^}]+)\}", href_sub, s)

    # Convert \textbf and \textit / \emph
    for _ in range(3):
        s = re.sub(r"\\textbf\{([^{}]+)\}", r"<b>\1</b>", s)
        s = re.sub(r"\\textit\{([^{}]+)\}", r"<i>\1</i>", s)
        s = re.sub(r"\\emph\{([^{}]+)\}", r"<i>\1</i>", s)

    # Convert dashes & spaces
    s = s.replace("---", "—").replace("--", "–")
    s = s.replace(r"\;", " ")

    # Unescape LaTeX specials
    s = s.replace(r"\%", "%").replace(r"\$", "$").replace(r"\_", "_").replace(r"\#", "#")
    s = s.replace(r"\&", "&amp;")

    # XML escape any remaining bare & (that aren't already part of &amp;, &lt;, &gt;, &nbsp;)
    s = re.sub(r"&(?!amp;|lt;|gt;|nbsp;)", "&amp;", s)

    # Remove remaining generic LaTeX commands like \small, \Large, \normalsize, etc.
    s = re.sub(r"\\[a-zA-Z]+\*?\{?\}?", "", s)
    s = re.sub(r"[{}^~$]", "", s)

    # Collapse multiple whitespace
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "name": ParagraphStyle(
            "name", fontName="Times-Bold", fontSize=18, leading=20,
            alignment=1, textColor=colors.black, spaceAfter=2
        ),
        "contact": ParagraphStyle(
            "contact", fontName="Times-Roman", fontSize=8.5, leading=11,
            alignment=1, textColor=colors.black, spaceAfter=2
        ),
        "city": ParagraphStyle(
            "city", fontName="Times-Roman", fontSize=8.5, leading=11,
            alignment=1, textColor=colors.black, spaceAfter=3
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Times-Bold", fontSize=10.5, leading=12,
            textColor=colors.black, spaceBefore=4, spaceAfter=1
        ),
        "para": ParagraphStyle(
            "para", fontName="Times-Roman", fontSize=8.5, leading=11,
            textColor=colors.black, spaceAfter=2
        ),
        "cell_left": ParagraphStyle(
            "cell_left", fontName="Times-Roman", fontSize=8.5, leading=11,
            textColor=colors.black, spaceAfter=0
        ),
        "cell_mid": ParagraphStyle(
            "cell_mid", fontName="Times-Roman", fontSize=8.5, leading=11,
            alignment=1, textColor=colors.black, spaceAfter=0
        ),
        "cell_right": ParagraphStyle(
            "cell_right", fontName="Times-Roman", fontSize=8.5, leading=11,
            alignment=2, textColor=colors.black, spaceAfter=0
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Times-Roman", fontSize=8.5, leading=10.8,
            textColor=colors.black, leftIndent=12, firstLineIndent=-12, spaceAfter=1
        ),
    }


def generate_resume_pdf(tex: str, output_dir: Path, stem: str) -> tuple[Path | None, str]:
    """
    Parse a LaTeX resume string and render a high-fidelity single-page PDF.
    Returns (pdf_path, status_log).
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{stem}.pdf"

        styles = build_styles()

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
        )

        story = []

        # Strip line comments (% ...)
        clean_tex = re.sub(r"(?m)^%[^\n]*\n?", "", tex)

        # 1. Header block (\begin{center} ... \end{center})
        center_m = re.search(r"\\begin\{center\}(.*?)\\end\{center\}", clean_tex, re.DOTALL)
        if center_m:
            c_body = center_m.group(1).strip()
            lines = [l.strip() for l in re.split(r"\\\\", c_body) if l.strip()]
            if lines:
                name_xml = latex_to_xml(lines[0])
                story.append(Paragraph(name_xml, styles["name"]))
            if len(lines) > 1:
                contact_raw = lines[1]
                contact_raw = re.sub(r"\\;\|\\;?", " — ", contact_raw)
                contact_raw = re.sub(r"\|", " — ", contact_raw)
                contact_xml = latex_to_xml(contact_raw)
                story.append(Paragraph(contact_xml, styles["contact"]))
            if len(lines) > 2:
                city_xml = latex_to_xml(lines[2])
                story.append(Paragraph(city_xml, styles["city"]))

        # 2. Sections
        section_re = re.compile(r"\\section\*?\{([^}]+)\}(.*?)(?=\\section\*?\{|\\end\{document\}|$)", re.DOTALL)

        for sm in section_re.finditer(clean_tex):
            sec_title = sm.group(1).strip()
            sec_body = sm.group(2).strip()

            sec_title_xml = latex_to_xml(sec_title)
            story.append(Paragraph(sec_title_xml, styles["section_title"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceBefore=1, spaceAfter=3))

            sec_title_lower = sec_title.lower()

            # --- Education (\begin{tabularx} ... \end{tabularx}) ---
            if "education" in sec_title_lower:
                tab_m = re.search(r"\\begin\{tabularx\}.*?\}(.*?)\\end\{tabularx\}", sec_body, re.DOTALL)
                if tab_m:
                    tab_inner = tab_m.group(1)
                    first_open = tab_inner.find("{")
                    if first_open != -1:
                        depth = 0
                        close_idx = -1
                        for idx, ch in enumerate(tab_inner[first_open:], start=first_open):
                            if ch == "{":
                                depth += 1
                            elif ch == "}":
                                depth -= 1
                                if depth == 0:
                                    close_idx = idx
                                    break
                        if close_idx != -1:
                            tab_inner = tab_inner[close_idx + 1 :]

                    raw_rows = [r.strip() for r in re.split(r"\\\\(?:\[[^\]]*\])?", tab_inner) if r.strip()]
                    i = 0
                    while i < len(raw_rows):
                        cells = [latex_to_xml(c) for c in raw_rows[i].split("&")]
                        col1 = cells[0] if len(cells) > 0 else ""
                        col2 = cells[1] if len(cells) > 1 else ""
                        col3 = cells[2] if len(cells) > 2 else ""

                        if i + 1 < len(raw_rows):
                            next_cells = [latex_to_xml(c) for c in raw_rows[i + 1].split("&")]
                            if len(next_cells) > 1 and not next_cells[0].strip() and next_cells[1].strip():
                                detail_text = next_cells[1].strip()
                                col2 = f"{col2}<br/>{detail_text}" if col2 else detail_text
                                i += 1

                        p1 = Paragraph(col1, styles["cell_left"])
                        p2 = Paragraph(col2, styles["cell_left"])
                        p3 = Paragraph(col3, styles["cell_right"])

                        t = Table([[p1, p2, p3]], colWidths=[175, 275, 97])
                        t.setStyle(TableStyle([
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                        ]))
                        story.append(t)
                        i += 1
                continue

            # --- Technical Skills (lines separated by \\) ---
            if "technical skills" in sec_title_lower:
                skill_lines = [l.strip() for l in re.split(r"\\\\", sec_body) if l.strip()]
                for sl in skill_lines:
                    sl_xml = latex_to_xml(sl)
                    if sl_xml:
                        story.append(Paragraph(sl_xml, styles["para"]))
                continue

            # --- Experience, Projects, Achievements ---
            parts = re.split(r"(\\begin\{itemize\}.*?\\end\{itemize\})", sec_body, flags=re.DOTALL)
            current_heading_text = ""

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                if part.startswith(r"\begin{itemize}"):
                    if current_heading_text:
                        h_parts = re.split(r"\\hfill", current_heading_text)
                        h_clean = [latex_to_xml(hp) for hp in h_parts if hp.strip()]
                        if len(h_clean) == 3:
                            if "Live Demo" in h_clean[1]:
                                p1 = Paragraph(h_clean[0], styles["cell_left"])
                                p2 = Paragraph(h_clean[1], styles["cell_right"])
                                p3 = Paragraph(h_clean[2], styles["cell_right"])
                                t = Table([[p1, p2, p3]], colWidths=[370, 80, 97])
                            else:
                                p1 = Paragraph(h_clean[0], styles["cell_left"])
                                p2 = Paragraph(h_clean[1], styles["cell_mid"])
                                p3 = Paragraph(h_clean[2], styles["cell_right"])
                                t = Table([[p1, p2, p3]], colWidths=[200, 250, 97])
                        elif len(h_clean) == 2:
                            p1 = Paragraph(h_clean[0], styles["cell_left"])
                            p3 = Paragraph(h_clean[1], styles["cell_right"])
                            t = Table([[p1, p3]], colWidths=[450, 97])
                        else:
                            p1 = Paragraph(h_clean[0], styles["cell_left"])
                            t = Table([[p1]], colWidths=[CONTENT_W])

                        t.setStyle(TableStyle([
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 1),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ]))
                        story.append(t)
                        current_heading_text = ""

                    # Extract itemize bullets
                    inner = part[len(r"\begin{itemize}"):-len(r"\end{itemize}")].strip()
                    raw_bullets = re.split(r"\\(?:resumeItem|item)(?:\[[^\]]*\])?", inner)
                    for b in raw_bullets[1:]:
                        b = b.strip()
                        if b.startswith("{") and b.endswith("}"):
                            b = b[1:-1].strip()
                        b_xml = latex_to_xml(b)
                        if b_xml:
                            story.append(Paragraph(f"• {b_xml}", styles["bullet"]))
                    story.append(Spacer(1, 2))
                else:
                    if r"\hfill" in part:
                        current_heading_text = part
                    else:
                        part_xml = latex_to_xml(part)
                        if part_xml:
                            story.append(Paragraph(part_xml, styles["para"]))

            if current_heading_text:
                h_parts = re.split(r"\\hfill", current_heading_text)
                h_clean = [latex_to_xml(hp) for hp in h_parts if hp.strip()]
                if len(h_clean) >= 2:
                    p1 = Paragraph(h_clean[0], styles["cell_left"])
                    p3 = Paragraph(h_clean[-1], styles["cell_right"])
                    t = Table([[p1, p3]], colWidths=[450, 97])
                    t.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    story.append(t)

            story.append(Spacer(1, 2))

        doc.build(story)

        if out_path.is_file() and out_path.stat().st_size > 500:
            return out_path, "PDF generated successfully matching Overleaf layout"
        return None, "Generated PDF file is missing or empty"

    except Exception as e:
        return None, f"PDF generation failed: {e}"


# Backwards compatibility helper
class ParsedResume:
    def __init__(self):
        self.name = ""
        self.contact = ""
        self.city = ""
        self.sections = []


def parse_latex_resume(tex: str) -> ParsedResume:
    r = ParsedResume()
    center_m = re.search(r"\\begin\{center\}(.*?)\\end\{center\}", tex, re.DOTALL)
    if center_m:
        lines = [l.strip() for l in re.split(r"\\\\", center_m.group(1)) if l.strip()]
        if lines:
            r.name = latex_to_xml(lines[0])
        if len(lines) > 1:
            r.contact = latex_to_xml(lines[1])
        if len(lines) > 2:
            r.city = latex_to_xml(lines[2])
    return r
