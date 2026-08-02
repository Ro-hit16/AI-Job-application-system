"""
services/pdf_service.py — Resume PDF Parsing
"""

import io
import os
from pathlib import Path
from typing import Optional

import pdfplumber

from app.config import get_settings
from app.core.exceptions import ResumeParseException
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class PDFService:
    def extract_text(self, file_path: str) -> str:
        try:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            full_text = "\n".join(text_parts).strip()
            if not full_text:
                raise ResumeParseException(file_path, "No text could be extracted — possibly a scanned PDF")
            logger.info("PDF extracted", extra={"file": file_path, "chars": len(full_text)})
            return full_text
        except ResumeParseException:
            raise
        except Exception as e:
            raise ResumeParseException(os.path.basename(file_path), str(e))

    def extract_from_bytes(self, content: bytes, filename: str) -> str:
        try:
            text_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            full_text = "\n".join(text_parts).strip()
            if not full_text:
                raise ResumeParseException(filename, "No text could be extracted")
            return full_text
        except ResumeParseException:
            raise
        except Exception as e:
            raise ResumeParseException(filename, str(e))

    def save_upload(self, content: bytes, filename: str, user_id: str) -> str:
        upload_dir = Path(settings.UPLOAD_DIR) / user_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        file_path = upload_dir / safe_name
        file_path.write_bytes(content)
        logger.info("Resume saved", extra={"path": str(file_path)})
        return str(file_path)

    def get_page_count(self, file_path: str) -> int:
        try:
            with pdfplumber.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0


_instance: Optional[PDFService] = None


def get_pdf_service() -> PDFService:
    global _instance
    if _instance is None:
        _instance = PDFService()
    return _instance