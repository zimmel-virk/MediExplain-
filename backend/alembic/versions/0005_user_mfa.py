"""Add local multi-factor authentication fields to users."""

from alembic import op
import sqlalchemy as sa


revision = "0005_user_mfa"
down_revision = "0004_assistant_support"
branch_labels = None
depends_on = None


def _user_columns():
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("users")}


def upgrade():
    existing = _user_columns()

    with op.batch_alter_table("users") as batch:
        if "mfa_enabled" not in existing:
            batch.add_column(
                sa.Column(
                    "mfa_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

        if "mfa_secret_encrypted" not in existing:
            batch.add_column(
                sa.Column(
                    "mfa_secret_encrypted",
                    sa.String(512),
                    nullable=True,
                )
            )


def downgrade():
    existing = _user_columns()

    with op.batch_alter_table("users") as batch:
        if "mfa_secret_encrypted" in existing:
            batch.drop_column("mfa_secret_encrypted")

        if "mfa_enabled" in existing:
            batch.drop_column("mfa_enabled")
