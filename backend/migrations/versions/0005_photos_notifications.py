"""Add report photos and recipient-scoped notifications without rebuilding reports."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "items",
        sa.Column("photo_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "item_photos",
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("length(data) BETWEEN 1 AND 1048576", name="ck_photo_size"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recipient_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_id",
            sa.Integer(),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("message", sa.String(240), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_notifications_recipient_read_id",
        "notifications",
        ["recipient_id", "is_read", "id"],
    )


def downgrade():
    op.drop_table("notifications")
    op.drop_table("item_photos")
    op.drop_column("items", "photo_version")
