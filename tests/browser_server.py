"""Disposable, loopback-only browser test fixture; never used by deployment."""

import threading
import time

from conftest import PASSWORD, FakeRedis
from nexa import security
from nexa.config import settings
from nexa.db import SessionLocal
from nexa.routes.auth import Register, create_user
from nexa.worker import run_one

security.Redis = FakeRedis
settings().base_url = "http://127.0.0.1:8080"


def main():
    from pathlib import Path

    import uvicorn
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "backend/alembic.ini")), "head")
    with SessionLocal() as db:
        create_user(
            db,
            Register(username="preview_owner", email="preview@example.com", password=PASSWORD),
            "SUPER_ADMIN",
        )
        db.commit()

    def worker():
        while True:
            if not run_one():
                time.sleep(0.3)

    threading.Thread(target=worker, daemon=True).start()
    uvicorn.run("nexa.main:app", host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__":
    main()
