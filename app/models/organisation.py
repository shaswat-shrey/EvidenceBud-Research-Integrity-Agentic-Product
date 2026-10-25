import uuid
from datetime import datetime
from sqlalchemy import ( 
    DateTime, 
    String, 
    func, 
    )
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column

class Base(DeclarativeBase):
    pass


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
