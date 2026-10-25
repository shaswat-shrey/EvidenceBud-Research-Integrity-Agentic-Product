import uuid
from datetime import datetime
from sqlalchemy import (
    DateTime, 
    String,
    func, 
    text,
    ForeignKey
    )
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column
from app.models.Base import Base

class OrganisationMember(Base):
    __tablename__ = "organisation_members"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'member'"),
    )
    joined_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )