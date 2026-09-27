"""Additive workflow models for assistant pre-review and in-app support.

These tables do not replace the original consultation/cross-check model.  They
add a delegated pre-review layer while keeping final doctor approval/release
unchanged.
"""
from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base

# This class stores the delegated assistant pre-review for a consultation.
# It records which assistant was assigned, who assigned the case, the current
# review status, checklist results and any notes added during the review.
# The checked fields make it possible to record when the assistant completed
# their part of the workflow without giving them final approval or release control.
class AssistantReview(Base):
    __tablename__ = "assistant_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    assistant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
# This class stores support requests submitted through the MediExplain+
# application. It keeps the user who raised the ticket, its category, subject,
# message, urgency and optional contact information. Privacy-related requests
# can also store their specific request type, while the status field is used
# to keep track of whether the ticket is still open or has been handled.

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    urgency: Mapped[str] = mapped_column(String(16), default="normal")
    privacy_request_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
