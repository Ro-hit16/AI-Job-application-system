"""
migrate_tex_to_pdf.py
---------------------
Converts every application in the database to have a validated PDF resume
using auto_ensure_application_pdf and ReportLab.
"""
import asyncio
from pathlib import Path


async def migrate():
    from app.database import get_db_context
    from app.models.application import Application
    from app.services.instant_tailor import auto_ensure_application_pdf
    from app.services.resume_edit import validate_pdf
    from sqlalchemy import select

    async with get_db_context() as db:
        result = await db.execute(select(Application))
        apps = result.scalars().all()

    converted, skipped, failed = 0, 0, 0

    print(f"Starting PDF migration for {len(apps)} applications...")

    for app in apps:
        if app.tailored_resume_path:
            p = Path(app.tailored_resume_path)
            if p.suffix.lower() == ".pdf" and p.is_file() and validate_pdf(p) is None:
                skipped += 1
                continue

        try:
            async with get_db_context() as db:
                pdf_path, media = await auto_ensure_application_pdf(app.id, app.user_id, db)
                print(f"  OK App {app.id}: -> {pdf_path.name} ({pdf_path.stat().st_size} bytes)")
                converted += 1
        except Exception as e:
            print(f"  FAIL App {app.id}: {e}")
            failed += 1

    print(f"\nMigration Complete! Converted: {converted} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(migrate())

