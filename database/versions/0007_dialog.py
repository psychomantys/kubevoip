"""Add shared dialog store for multi-replica in-dialog validation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _tables()
    if "kubevoip_dialog" not in existing:
        op.create_table(
            "kubevoip_dialog",
            sa.Column("namespace", sa.String(length=63), primary_key=True, nullable=False),
            sa.Column("gateway_name", sa.String(length=63), primary_key=True, nullable=False),
            sa.Column("call_id", sa.String(length=255), primary_key=True, nullable=False),
            sa.Column("from_tag", sa.String(length=128), nullable=False),
            sa.Column("to_tag", sa.String(length=128), nullable=True),
            sa.Column("downstream_uri", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
    existing_indexes = _indexes("kubevoip_dialog")
    if "kubevoip_dialog_expires_idx" not in existing_indexes:
        op.create_index(
            "kubevoip_dialog_expires_idx",
            "kubevoip_dialog",
            ["expires_at"],
        )
    op.execute("INSERT INTO kubevoip_schema_migrations(version) VALUES (8) ON CONFLICT (version) DO NOTHING")


def downgrade() -> None:
    existing = _tables()
    if "kubevoip_dialog" in existing:
        existing_indexes = _indexes("kubevoip_dialog")
        if "kubevoip_dialog_expires_idx" in existing_indexes:
            op.drop_index("kubevoip_dialog_expires_idx", table_name="kubevoip_dialog")
        op.drop_table("kubevoip_dialog")
    op.execute("DELETE FROM kubevoip_schema_migrations WHERE version = 8")
