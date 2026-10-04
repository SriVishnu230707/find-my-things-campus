"""Create persistent reports independently of future model changes."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("location", sa.String(150), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("reported_by", sa.String(100), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('lost', 'found')", name="ck_items_type"),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_items_status"),
        sa.CheckConstraint("category IN ('electronics', 'clothing', 'documents', 'accessories', 'other')", name="ck_items_category"),
        sa.CheckConstraint("length(title) BETWEEN 3 AND 120", name="ck_items_title"),
        sa.CheckConstraint("length(description) BETWEEN 10 AND 2000", name="ck_items_description"),
        sa.CheckConstraint("length(location) BETWEEN 2 AND 150", name="ck_items_location"),
        sa.CheckConstraint("length(reported_by) BETWEEN 2 AND 100", name="ck_items_reporter"),
        sqlite_autoincrement=True,
    )

def downgrade():
    op.drop_table("items")
