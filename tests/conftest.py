import os
import secrets
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

TEST_DIR = Path(tempfile.mkdtemp(prefix="nexa-tests-"))
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite:///{TEST_DIR / 'test.sqlite'}"),
    SECRET_KEY=secrets.token_hex(32),
    ENCRYPTION_KEYS=Fernet.generate_key().decode(),
    COOKIE_SECURE="false",
    MOCK_MODE="true",
    BASE_URL="http://testserver",
    OPERATIONS_DIR=str(TEST_DIR / "operations"),
    BACKUP_DIR=str(TEST_DIR / "backups"),
    META_APP_SECRET=secrets.token_hex(24),
    META_VERIFY_TOKEN=secrets.token_hex(24),
    TELEGRAM_WEBHOOK_SECRET=secrets.token_urlsafe(32),
)
(TEST_DIR / "operations").mkdir()
(TEST_DIR / "backups").mkdir()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from nexa import security  # noqa: E402
from nexa.db import Base, SessionLocal, engine  # noqa: E402
from nexa.main import app  # noqa: E402
from nexa.routes.auth import Register, create_user  # noqa: E402

PASSWORD = "Test-only-safe-passphrase-472!"


class FakeRedis:
    counts = {}

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def eval(self, script, keys, key, seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def close(self):
        pass


@pytest.fixture(scope="session", autouse=True)
def migrate_database():
    config = Config(str(Path(__file__).resolve().parents[1] / "backend/alembic.ini"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate(monkeypatch, migrate_database):
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    FakeRedis.counts.clear()
    monkeypatch.setattr(security, "Redis", FakeRedis)


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def db():
    with SessionLocal() as db:
        yield db


def sign_in(client, username="alice", role="USER"):
    with SessionLocal() as db:
        user = create_user(
            db, Register(username=username, email=f"{username}@example.com", password=PASSWORD), role
        )
        db.commit()
        identity = user.id
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies["nexa_csrf"]
    return identity


@pytest.fixture
def signed(client):
    sign_in(client)
    return client


@pytest.fixture
def owner(client):
    sign_in(client, "owner", "SUPER_ADMIN")
    return client


@pytest.fixture
def account(signed):
    result = signed.post("/api/accounts/mock", json={"name": "Test Instagram"})
    assert result.status_code == 201
    return result.json()


@pytest.fixture
def rule(signed, account):
    result = signed.post(
        "/api/automations",
        json={
            "account_id": account["id"],
            "name": "Price reply",
            "keywords": ["قیمت"],
            "response": "سلام، کدام محصول؟",
            "cooldown_seconds": 60,
        },
    )
    assert result.status_code == 201
    return result.json()
