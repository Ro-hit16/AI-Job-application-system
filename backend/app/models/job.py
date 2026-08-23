from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        Index("ix_jobs_portal_status", "portal", "status"),
        Index("ix_jobs_url_hash", "url_hash", unique=True),
        Index("ix_jobs_scraped_at", "scraped_at"),
        Index("ix_jobs_last_seen_at", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    company: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    salary: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    experience_required: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    portal: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    url_hash: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True
    )

    required_skills: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True
    )

    job_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    embedding_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="new",
        index=True
    )

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # AI ranking (populated by job_match agent against the active resume)
    match_score: Mapped[Optional[float]] = mapped_column(
        nullable=True
    )

    match_reasons: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Scheduled sync bookkeeping — updated every time a refresh run sees this
    # job again; used to detect/expire postings that have disappeared upstream.
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title='{self.title}' portal={self.portal}>"