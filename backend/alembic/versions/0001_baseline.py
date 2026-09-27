"""Original MediExplain+ prototype schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(18), nullable=False),
        sa.Column("preferred_language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("specialty", sa.String(120)),
        sa.Column("clinic", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "consultations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patient_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("audio_path", sa.String(512)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("raw_transcript", sa.Text()),
        sa.Column("transcript_normalised", sa.Text()),
        sa.Column("languages_detected", sa.JSON()),
        sa.Column("code_switched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stt_primary_language", sa.String(8)),
        sa.Column("stt_secondary_language", sa.String(8)),
        sa.Column("clinical_note", sa.Text()),
        sa.Column("patient_summary_en", sa.Text()),
        sa.Column("patient_summary_translated", sa.Text()),
        sa.Column("patient_language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("structured_data", sa.JSON()),
        sa.Column("translation_quality", sa.String(16)),
        sa.Column("dose_sentences_for_review", sa.JSON()),
        sa.Column("audio_summary_path", sa.String(512)),
        sa.Column("tts_backend", sa.String(16)),
        sa.Column("prescription_image_path", sa.String(512)),
        sa.Column("prescription_ocr_text", sa.Text()),
        sa.Column("prescription_ocr_confidence", sa.Float()),
        sa.Column("patient_phone", sa.String(32)),
        sa.Column("status", sa.String(32), nullable=False, server_default="recording"),
        sa.Column("doctor_edited_summary", sa.Text()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("released_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "cross_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("comments", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.Integer()),
        sa.Column("details", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )

def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("cross_checks")
    op.drop_table("consultations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
