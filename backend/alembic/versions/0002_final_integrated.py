"""Final integrated safety, medication, scheduling and evaluation schema."""
from alembic import op
import sqlalchemy as sa

revision = "0002_final_integrated"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("consultations") as b:
        b.add_column(sa.Column("verified_transcript", sa.Text(), nullable=True))
        b.add_column(sa.Column("translation_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("pipeline_error", sa.Text(), nullable=True))
        b.add_column(sa.Column("model_metadata", sa.JSON(), nullable=True))
        b.alter_column("tts_backend", existing_type=sa.String(16), type_=sa.String(32))

    with op.batch_alter_table("cross_checks") as b:
        b.add_column(sa.Column("requester_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("request_status", sa.String(24), nullable=False, server_default="pending"))
        b.add_column(sa.Column("reason", sa.Text(), nullable=True))
        b.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE users SET is_verified = 1")
    op.execute(
        "UPDATE cross_checks SET request_status = "
        "CASE WHEN verdict = 'pending' THEN 'pending' ELSE 'completed' END"
    )
    op.execute(
        "UPDATE cross_checks SET completed_at = created_at "
        "WHERE verdict <> 'pending' AND completed_at IS NULL"
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patient_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("method", sa.String(32), nullable=False, server_default="verbal"),
        sa.Column("consent_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("withdrawn_at", sa.DateTime()),
        sa.Column("withdrawn_by_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_consent_records_consultation_id", "consent_records", ["consultation_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text_raw", sa.Text(), nullable=False),
        sa.Column("text_reviewed", sa.Text()),
        sa.Column("language", sa.String(16)),
        sa.Column("language_confidence", sa.Float()),
        sa.Column("avg_logprob", sa.Float()),
        sa.Column("no_speech_prob", sa.Float()),
        sa.Column("confidence", sa.Float()),
        sa.Column("speaker_label", sa.String(32)),
        sa.Column("diarization_confidence", sa.Float()),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("consultation_id", "segment_index", name="uq_transcript_segment"),
    )
    op.create_index("ix_transcript_segments_consultation_id", "transcript_segments", ["consultation_id"])

    op.create_table(
        "summary_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="ai"),
        sa.Column("model_name", sa.String(128)),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("consultation_id", "kind", "version", name="uq_summary_version"),
    )
    op.create_index("ix_summary_versions_consultation_id", "summary_versions", ["consultation_id"])

    op.create_table(
        "safety_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("statement", sa.Text()),
        sa.Column("evidence", sa.Text()),
        sa.Column("score", sa.Float()),
        sa.Column("details", sa.JSON()),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_safety_checks_consultation_id", "safety_checks", ["consultation_id"])

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("image_path", sa.String(512)),
        sa.Column("raw_ocr_text", sa.Text()),
        sa.Column("corrected_ocr_text", sa.Text()),
        sa.Column("ocr_engine", sa.String(32)),
        sa.Column("ocr_confidence", sa.Float()),
        sa.Column("structured_data", sa.JSON()),
        sa.Column("doctor_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_prescriptions_consultation_id", "prescriptions", ["consultation_id"])

    op.create_table(
        "medication_concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("tty", sa.String(16)),
        sa.Column("generic_name", sa.String(512)),
        sa.Column("brand_name", sa.String(512)),
        sa.Column("strength", sa.String(128)),
        sa.Column("dosage_form", sa.String(128)),
        sa.Column("route", sa.String(128)),
        sa.Column("active_ingredient", sa.String(512)),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("country", sa.String(64)),
        sa.Column("metadata_json", sa.JSON()),
        sa.UniqueConstraint("source", "source_id", "display_name", name="uq_medication_concept_source_display"),
    )
    op.create_index("ix_medication_concepts_source", "medication_concepts", ["source"])
    op.create_index("ix_medication_concepts_source_id", "medication_concepts", ["source_id"])
    op.create_index("ix_medication_concepts_display_name", "medication_concepts", ["display_name"])
    op.create_index("ix_medication_concepts_normalized_name", "medication_concepts", ["normalized_name"])

    op.create_table(
        "medication_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("medication_concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(512), nullable=False),
        sa.Column("normalized_alias", sa.String(512), nullable=False),
        sa.Column("alias_type", sa.String(32), nullable=False, server_default="synonym"),
        sa.UniqueConstraint("concept_id", "normalized_alias", name="uq_med_alias"),
    )
    op.create_index("ix_medication_aliases_concept_id", "medication_aliases", ["concept_id"])
    op.create_index("ix_medication_aliases_normalized_alias", "medication_aliases", ["normalized_alias"])

    op.create_table(
        "consultation_medications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="transcript"),
        sa.Column("source_index", sa.Integer()),
        sa.Column("raw_name", sa.String(512)),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("medication_concepts.id")),
        sa.Column("canonical_name", sa.String(512)),
        sa.Column("generic_name", sa.String(512)),
        sa.Column("brand_name", sa.String(512)),
        sa.Column("strength", sa.String(128)),
        sa.Column("dose", sa.String(128)),
        sa.Column("dose_unit", sa.String(64)),
        sa.Column("dosage_form", sa.String(128)),
        sa.Column("route", sa.String(128)),
        sa.Column("frequency", sa.String(128)),
        sa.Column("timing", sa.String(128)),
        sa.Column("food_instruction", sa.String(128)),
        sa.Column("duration", sa.String(128)),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("as_needed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("indication", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("extraction_confidence", sa.Float()),
        sa.Column("match_confidence", sa.Float()),
        sa.Column("doctor_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("discrepancy_status", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_consultation_medications_consultation_id", "consultation_medications", ["consultation_id"])

    op.create_table(
        "medication_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consultation_medication_id", sa.Integer(), sa.ForeignKey("consultation_medications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Karachi"),
        sa.Column("instructions", sa.Text()),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_medication_schedules_consultation_id", "medication_schedules", ["consultation_id"])
    op.create_index("ix_medication_schedules_consultation_medication_id", "medication_schedules", ["consultation_medication_id"])
    op.create_index("ix_medication_schedules_patient_id", "medication_schedules", ["patient_id"])

    op.create_table(
        "medication_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("medication_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("action_at", sa.DateTime()),
        sa.Column("snoozed_until", sa.DateTime()),
        sa.Column("reminder_audio_path", sa.String(512)),
    )
    op.create_index("ix_medication_events_schedule_id", "medication_events", ["schedule_id"])
    op.create_index("ix_medication_events_scheduled_at", "medication_events", ["scheduled_at"])

    op.create_table(
        "translation_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("back_translation", sa.Text()),
        sa.Column("numeric_preserved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("medication_preserved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("script_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("semantic_status", sa.String(16), nullable=False, server_default="unavailable"),
        sa.Column("semantic_score", sa.Float()),
        sa.Column("model_name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_translation_records_consultation_id", "translation_records", ["consultation_id"])

def downgrade():
    for table in [
        "translation_records", "medication_events", "medication_schedules",
        "consultation_medications", "medication_aliases", "medication_concepts",
        "prescriptions", "safety_checks", "summary_versions", "transcript_segments",
        "consent_records",
    ]:
        op.drop_table(table)

    with op.batch_alter_table("cross_checks") as b:
        b.drop_column("updated_at")
        b.drop_column("completed_at")
        b.drop_column("reason")
        b.drop_column("request_status")
        b.drop_column("requester_id")

    with op.batch_alter_table("consultations") as b:
        b.drop_column("model_metadata")
        b.drop_column("pipeline_error")
        b.drop_column("translation_verified")
        b.drop_column("verified_transcript")

    with op.batch_alter_table("users") as b:
        b.drop_column("last_login_at")
        b.drop_column("is_verified")
