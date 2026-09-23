from alembic import context
from sqlalchemy import create_engine

from nexa import models  # noqa: F401
from nexa.config import settings
from nexa.db import Base

target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(url=settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(settings().database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
