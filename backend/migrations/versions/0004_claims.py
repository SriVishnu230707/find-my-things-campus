"""Add private claims and report archival without rebuilding existing tables."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "items",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "claimant_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','withdrawn','completed')",
            name="ck_claims_status",
        ),
        sa.CheckConstraint(
            "length(evidence) BETWEEN 10 AND 2000", name="ck_claims_evidence"
        ),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_claims_item_id", "claims", ["item_id"])
    op.create_index("ix_claims_claimant_id", "claims", ["claimant_id"])
    for name, columns, predicate in [
        (
            "uq_claims_active_student",
            ["item_id", "claimant_id"],
            "status IN ('pending','approved')",
        ),
        ("uq_claims_winner", ["item_id"], "status IN ('approved','completed')"),
    ]:
        op.create_index(
            name,
            "claims",
            columns,
            unique=True,
            sqlite_where=sa.text(predicate),
            postgresql_where=sa.text(predicate),
        )


def downgrade():
    op.drop_table("claims")
    op.drop_column("items", "archived")
