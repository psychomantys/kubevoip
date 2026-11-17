"""Add shared Asterisk callee destination store for multi-replica Kamailio."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _tables()
    if "kubevoip_asterisk_callee" not in existing:
        op.create_table(
            "kubevoip_asterisk_callee",
            sa.Column("namespace", sa.String(length=63), primary_key=True, nullable=False),
            sa.Column("gateway_name", sa.String(length=63), primary_key=True, nullable=False),
            sa.Column("call_id", sa.String(length=255), primary_key=True, nullable=False),
            sa.Column("destination", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
    existing_indexes = _indexes("kubevoip_asterisk_callee")
    if "kubevoip_asterisk_callee_expires_idx" not in existing_indexes:
        op.create_index(
            "kubevoip_asterisk_callee_expires_idx",
            "kubevoip_asterisk_callee",
            ["expires_at"],
        )
    op.execute("INSERT INTO kubevoip_schema_migrations(version) VALUES (7) ON CONFLICT (version) DO NOTHING")


def downgrade() -> None:
    existing = _tables()
    if "kubevoip_asterisk_callee" in existing:
        existing_indexes = _indexes("kubevoip_asterisk_callee")
        if "kubevoip_asterisk_callee_expires_idx" in existing_indexes:
            op.drop_index("kubevoip_asterisk_callee_expires_idx", table_name="kubevoip_asterisk_callee")
        op.drop_table("kubevoip_asterisk_callee")
    op.execute("DELETE FROM kubevoip_schema_migrations WHERE version = 7")
