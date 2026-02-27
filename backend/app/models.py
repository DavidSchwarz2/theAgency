from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PipelineStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    done = "done"
    failed = "failed"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(100), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PipelineStatus] = mapped_column(Enum(PipelineStatus), nullable=False, default=PipelineStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    steps: Mapped[list["Step"]] = relationship(
        "Step", back_populates="pipeline", cascade="all, delete-orphan", order_by="Step.order_index"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="pipeline", cascade="all, delete-orphan"
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipelines.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus), nullable=False, default=StepStatus.pending)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="steps")
    handoffs: Mapped[list["Handoff"]] = relationship("Handoff", back_populates="step", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship("Approval", back_populates="step", cascade="all, delete-orphan")
    audit_events: Mapped[list["AuditEvent"]] = relationship("AuditEvent", back_populates="step")


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(Integer, ForeignKey("steps.id"), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    step: Mapped["Step"] = relationship("Step", back_populates="handoffs")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipelines.id"), nullable=False)
    step_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("steps.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="audit_events")
    step: Mapped["Step | None"] = relationship("Step", back_populates="audit_events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(Integer, ForeignKey("steps.id"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.pending)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    step: Mapped["Step"] = relationship("Step", back_populates="approvals")
