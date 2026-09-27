"""Add delegated assistant pre-review and support-ticket tables.

Original MediExplain+ clinical, multilingual, medication, scheduling and
cross-check tables are intentionally untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_assistant_support"
down_revision = "0003_schema_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_reviews_consultation_id", "assistant_reviews", ["consultation_id"])
    op.create_index("ix_assistant_reviews_assistant_id", "assistant_reviews", ["assistant_id"])
    op.create_index("ix_assistant_reviews_status", "assistant_reviews", ["status"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("urgency", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_support_tickets_reporter_id", "support_tickets", ["reporter_id"])
    op.create_index("ix_support_tickets_category", "support_tickets", ["category"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])


def downgrade():
    op.drop_table("support_tickets")
    op.drop_table("assistant_reviews")
