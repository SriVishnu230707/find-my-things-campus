"""Index chronological listing and combined report filters."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_items_created_id", "items", ["created_at", "id"])
    op.create_index(
        "ix_items_category_type_status_created_id",
        "items",
        ["category", "type", "status", "created_at", "id"],
    )


def downgrade():
    op.drop_index("ix_items_category_type_status_created_id", table_name="items")
    op.drop_index("ix_items_created_id", table_name="items")
