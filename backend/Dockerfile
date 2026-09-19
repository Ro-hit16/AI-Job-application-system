FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system deps for pdfplumber and playwright, plus a LaTeX
# toolchain for compiling tailored resumes (app/services/latex_resume.py
# shells out to `pdflatex`). resume_template.tex needs geometry, enumitem,
# hyperref, titlesec and tabularx, which live in texlive-latex-recommended
# and texlive-latex-extra.
RUN apt-get update && apt-get install -y \
    gcc libpq-dev curl wget gnupg \
    texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]