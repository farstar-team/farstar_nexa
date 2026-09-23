"""Wait for PostgreSQL and apply the forward Alembic migrations."""

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from nexa.config import settings

log = logging.getLogger("nexa.migrate")
MAX_ATTEMPTS = 30
RETRY_SECONDS = 2


def wait_for_database() -> None:
    database_url = settings().database_url
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                raise
            log.warning(
                "Database is not ready; retrying (%s/%s): %s",
                attempt,
                MAX_ATTEMPTS,
                type(exc).__name__,
            )
            time.sleep(RETRY_SECONDS)
        finally:
            engine.dispose()
    if last_error is not None:
        raise last_error


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    wait_for_database()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
