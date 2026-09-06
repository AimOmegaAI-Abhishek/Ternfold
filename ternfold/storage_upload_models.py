"""Durable direct-upload intentions; import this module before running migrations."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now_utc


class UploadIntent(Base):
    __tablename__ = 'upload_intents'
    __table_args__ = (UniqueConstraint('case_id', 'request_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'))
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(40))
    storage_key: Mapped[str] = mapped_column(String(255))
    validity_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    document_id: Mapped[str | None] = mapped_column(ForeignKey('source_documents.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
