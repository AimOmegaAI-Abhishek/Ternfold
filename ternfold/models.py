from __future__ import annotations
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid() -> str: return str(uuid.uuid4())
def now_utc() -> datetime: return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__="organizations"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    slug: Mapped[str]=mapped_column(String(80),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(180))
    min_contribution_pct: Mapped[Decimal]=mapped_column(Numeric(12,6),default=Decimal("12"))
    erosion_warning_pp: Mapped[Decimal]=mapped_column(Numeric(12,6),default=Decimal("3"))
    retention_source_days: Mapped[int]=mapped_column(Integer,default=30)
    retention_record_days: Mapped[int]=mapped_column(Integer,default=90)
    synthetic: Mapped[bool]=mapped_column(Boolean,default=False)

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    email: Mapped[str]=mapped_column(String(200),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(120))
    password_hash: Mapped[str]=mapped_column(Text)
    service_admin: Mapped[bool]=mapped_column(Boolean,default=False)
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class Membership(Base):
    __tablename__="memberships"; __table_args__=(UniqueConstraint("organization_id","user_id"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    role: Mapped[str]=mapped_column(String(30))
    title: Mapped[str|None]=mapped_column(String(80),nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class ReviewerAssignment(Base):
    __tablename__="reviewer_assignments"; __table_args__=(UniqueConstraint("organization_id","user_id"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class SessionToken(Base):
    __tablename__="sessions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    token_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    csrf_token: Mapped[str]=mapped_column(String(64))
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class Case(Base):
    __tablename__="cases"; __table_args__=(UniqueConstraint("organization_id","reference"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    reference: Mapped[str]=mapped_column(String(80))
    decision_owner_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    purchasing_contact: Mapped[str]=mapped_column(String(120))
    purchase_deadline: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    proposed_purchase_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    service_deadline: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    workflow_status: Mapped[str]=mapped_column(String(40),default="DRAFT")
    financial_status: Mapped[str]=mapped_column(String(40),default="NOT_EVALUATED")
    next_actor: Mapped[str]=mapped_column(String(120),default="Operations")
    working_revision: Mapped[int]=mapped_column(Integer,default=1)
    working_data: Mapped[dict]=mapped_column(JSON,default=dict)
    current_calculation_id: Mapped[str|None]=mapped_column(String(36),nullable=True)
    unsupported_reason: Mapped[str|None]=mapped_column(Text,nullable=True)
    synthetic: Mapped[bool]=mapped_column(Boolean,default=False)
    closed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,onupdate=now_utc)

class SourceDocument(Base):
    __tablename__="source_documents"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    category: Mapped[str]=mapped_column(String(40)); filename: Mapped[str]=mapped_column(String(255))
    content_type: Mapped[str]=mapped_column(String(100)); size_bytes: Mapped[int]=mapped_column(Integer)
    sha256: Mapped[str]=mapped_column(String(64)); storage_key: Mapped[str]=mapped_column(String(255))
    uploaded_by_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    validity_end: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    revision_added: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    deleted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class EvidenceReference(Base):
    __tablename__="evidence_references"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    source_document_id: Mapped[str|None]=mapped_column(ForeignKey("source_documents.id",ondelete="SET NULL"),nullable=True)
    field_key: Mapped[str]=mapped_column(String(120)); locator: Mapped[str]=mapped_column(String(120))
    excerpt: Mapped[str|None]=mapped_column(Text,nullable=True)
    attested_by_id: Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class ExtractionDraft(Base):
    __tablename__="extraction_drafts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    source_document_id: Mapped[str]=mapped_column(ForeignKey("source_documents.id",ondelete="CASCADE"),index=True)
    requested_by_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    provider: Mapped[str]=mapped_column(String(40)); model: Mapped[str]=mapped_column(String(120))
    status: Mapped[str]=mapped_column(String(30),default="SUCCEEDED")
    proposals: Mapped[dict]=mapped_column(JSON,default=dict)
    error: Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class InputQuestion(Base):
    __tablename__="input_questions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    revision: Mapped[int]=mapped_column(Integer); field_key: Mapped[str]=mapped_column(String(120))
    question: Mapped[str]=mapped_column(Text); assigned_to: Mapped[str]=mapped_column(String(120))
    resolved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    answer: Mapped[str|None]=mapped_column(Text,nullable=True)

class Review(Base):
    __tablename__="reviews"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    revision: Mapped[int]=mapped_column(Integer); reviewer_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    notes: Mapped[str|None]=mapped_column(Text,nullable=True)
    confirmed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class CalculationVersion(Base):
    __tablename__="calculation_versions"; __table_args__=(UniqueConstraint("case_id","version_number"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    version_number: Mapped[int]=mapped_column(Integer); working_revision: Mapped[int]=mapped_column(Integer)
    formula_version: Mapped[str]=mapped_column(String(30),default="1.0"); snapshot: Mapped[dict]=mapped_column(JSON)
    revenue: Mapped[Decimal]=mapped_column(Numeric(40,2)); original_cost: Mapped[Decimal]=mapped_column(Numeric(40,2))
    current_cost: Mapped[Decimal]=mapped_column(Numeric(40,2)); original_contribution: Mapped[Decimal]=mapped_column(Numeric(40,2))
    current_contribution: Mapped[Decimal]=mapped_column(Numeric(40,2))
    original_pct: Mapped[Decimal|None]=mapped_column(Numeric(24,12),nullable=True)
    current_pct: Mapped[Decimal|None]=mapped_column(Numeric(24,12),nullable=True)
    erosion_rupees: Mapped[Decimal]=mapped_column(Numeric(40,2)); erosion_pp: Mapped[Decimal|None]=mapped_column(Numeric(24,12),nullable=True)
    financial_status: Mapped[str]=mapped_column(String(40)); reviewer_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class Decision(Base):
    __tablename__="decisions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    calculation_id: Mapped[str]=mapped_column(ForeignKey("calculation_versions.id"),index=True)
    owner_id: Mapped[str]=mapped_column(ForeignKey("users.id")); choice: Mapped[str]=mapped_column(String(40))
    rationale: Mapped[str]=mapped_column(Text); purchasing_action: Mapped[str]=mapped_column(Text)
    recorded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class Outcome(Base):
    __tablename__="outcomes"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    decision_id: Mapped[str]=mapped_column(ForeignKey("decisions.id"),index=True)
    actual_goods: Mapped[Decimal]=mapped_column(Numeric(40,2)); actual_freight: Mapped[Decimal]=mapped_column(Numeric(40,2))
    actual_contribution: Mapped[Decimal]=mapped_column(Numeric(40,2)); actual_pct: Mapped[Decimal|None]=mapped_column(Numeric(24,12),nullable=True)
    notes: Mapped[str|None]=mapped_column(Text,nullable=True); recorded_by_id: Mapped[str]=mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class ReportArtifact(Base):
    __tablename__="report_artifacts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    calculation_id: Mapped[str]=mapped_column(ForeignKey("calculation_versions.id"),index=True)
    decision_id: Mapped[str]=mapped_column(ForeignKey("decisions.id"),index=True)
    storage_key: Mapped[str]=mapped_column(String(255)); content_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    case_id: Mapped[str|None]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),nullable=True,index=True)
    actor_id: Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    action: Mapped[str]=mapped_column(String(100)); detail: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

class IdempotencyRecord(Base):
    __tablename__="idempotency_records"; __table_args__=(UniqueConstraint("organization_id","operation","request_key"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"))
    operation: Mapped[str]=mapped_column(String(80)); request_key: Mapped[str]=mapped_column(String(100))
    payload_hash: Mapped[str]=mapped_column(String(64)); result_id: Mapped[str]=mapped_column(String(36))

class EffortEntry(Base):
    __tablename__="effort_entries"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id",ondelete="CASCADE"),index=True)
    actor_id: Mapped[str]=mapped_column(ForeignKey("users.id")); category: Mapped[str]=mapped_column(String(40))
    minutes: Mapped[int]=mapped_column(Integer); measurement: Mapped[str]=mapped_column(String(20))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)

from . import storage_upload_models  # noqa: E402,F401
