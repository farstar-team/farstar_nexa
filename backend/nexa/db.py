from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from nexa.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().database_url, pool_pre_ping=True)
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
