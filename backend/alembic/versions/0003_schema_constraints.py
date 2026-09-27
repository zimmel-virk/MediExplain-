"""Align final SQLite constraints with SQLAlchemy metadata."""
from alembic import op

revision = "0003_schema_constraints"
down_revision = "0002_final_integrated"
branch_labels = None
depends_on = None


def upgrade():
    # Unique constraints already index these one-to-one consultation IDs.
    with op.batch_alter_table("consent_records") as batch:
        try:
            batch.drop_index("ix_consent_records_consultation_id")
        except Exception:
            pass
    with op.batch_alter_table("prescriptions") as batch:
        try:
            batch.drop_index("ix_prescriptions_consultation_id")
        except Exception:
            pass

    # requester_id was added during prototype migration; make referential
    # integrity explicit in the final schema.
    with op.batch_alter_table("cross_checks", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_cross_checks_requester_id_users",
            "users",
            ["requester_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("cross_checks", recreate="always") as batch:
        batch.drop_constraint("fk_cross_checks_requester_id_users", type_="foreignkey")
    op.create_index("ix_prescriptions_consultation_id", "prescriptions", ["consultation_id"])
    op.create_index("ix_consent_records_consultation_id", "consent_records", ["consultation_id"])
