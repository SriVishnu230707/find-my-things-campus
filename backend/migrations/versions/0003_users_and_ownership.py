"""Add accounts and nullable ownership without guessing legacy identities."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    sequence = None
    if connection.dialect.name == "sqlite":
        sequence = connection.execute(sa.text("SELECT seq FROM sqlite_sequence WHERE name='items'")).scalar()
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('student', 'staff')", name="ck_users_role"),
        sa.CheckConstraint("length(display_name) BETWEEN 2 AND 100", name="ck_users_display_name"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("items", table_kwargs={"sqlite_autoincrement": True}) as batch:
        batch.add_column(sa.Column("reporter_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_items_reporter_id_users", "users", ["reporter_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_items_reporter_id", ["reporter_id"])
    if sequence is not None:
        connection.execute(sa.text("UPDATE sqlite_sequence SET seq=max(seq,:seq) WHERE name='items'"), {"seq": sequence})


def downgrade():
    with op.batch_alter_table("items", table_kwargs={"sqlite_autoincrement": True}) as batch:
        batch.drop_index("ix_items_reporter_id")
        batch.drop_constraint("fk_items_reporter_id_users", type_="foreignkey")
        batch.drop_column("reporter_id")
    op.drop_table("users")
