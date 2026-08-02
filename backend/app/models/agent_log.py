import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    run_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="running",
        index=True
    )

    input_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True
    )

    output_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<AgentLog agent={self.agent_name} run={self.run_id} status={self.status}>"
