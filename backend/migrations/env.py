"""Migration configuration uses the same DATABASE_URL as the application."""

from alembic import context

from app.database import Base, engine
from app.models.account_tokens import AccountToken  # noqa: F401 -- register table metadata
from app.models.audit import AuditEvent  # noqa: F401 -- register table metadata
from app.models.claims import Claim  # noqa: F401 -- register table metadata
from app.models.items import Item  # noqa: F401 -- register table metadata
from app.models.media import ItemPhoto  # noqa: F401 -- register table metadata
from app.models.notifications import Notification  # noqa: F401 -- register table metadata
from app.models.users import User  # noqa: F401 -- register table metadata

if context.is_offline_mode():
    context.configure(
        url=engine.url,
        target_metadata=Base.metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
            render_as_batch=engine.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
