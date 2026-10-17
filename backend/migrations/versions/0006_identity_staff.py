"""Add verified identities, account recovery tokens, and moderation history."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(10), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify','reset')", name="ck_account_token_purpose"
        ),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_account_tokens_user_purpose_created",
        "account_tokens",
        ["user_id", "purpose", "created_at"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("claim_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_audit_events_created_id", "audit_events", ["created_at", "id"])


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("account_tokens")
    op.drop_column("users", "token_version")
    op.drop_column("users", "is_active")
    op.drop_column("users", "email_verified")
