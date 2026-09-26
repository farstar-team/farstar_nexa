from urllib.parse import parse_qs, urlsplit

from conftest import PASSWORD, sign_in
from fastapi.testclient import TestClient
from nexa.main import app
from nexa.models import Session, User
from nexa.security import digest
from sqlalchemy import select


def test_registration_login_logout(client, db):
    response = client.post(
        "/api/auth/register", json={"username": "newuser", "email": "new@example.com", "password": PASSWORD}
    )
    assert response.status_code == 201
    assert "password" not in response.text
    user = db.scalar(select(User).where(User.username == "newuser"))
    assert user.password_hash.startswith("$argon2id$")
    response = client.post("/api/auth/login", json={"username": "newuser", "password": PASSWORD})
    assert response.status_code == 200
    cookie = client.cookies["nexa_session"]
    session = db.scalar(select(Session).where(Session.user_id == user.id))
    assert session.token_hash == digest(cookie)
    client.headers["X-CSRF-Token"] = client.cookies["nexa_csrf"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Cookie": "nexa_session=" + cookie}).status_code == 401


def test_google_login_is_explicitly_unavailable_without_provider_credentials(client):
    response = client.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?google=unavailable&auth=1"


def test_google_oauth_creates_user_and_session(client, db, monkeypatch):
    import nexa.routes.auth as auth_routes
    from nexa.config import settings

    monkeypatch.setattr(settings(), "base_url", "http://localhost:8080")
    monkeypatch.setattr(settings(), "google_client_id", "client-id")
    monkeypatch.setattr(settings(), "google_client_secret", "client-secret")

    class OAuthRedis:
        values = {}

        @classmethod
        def from_url(cls, *args, **kwargs):
            return cls()

        def set(self, key, value, **kwargs):
            self.values[key] = value
            return True

        def get(self, key):
            return self.values.get(key)

        def delete(self, key):
            self.values.pop(key, None)

        def close(self):
            pass

    class OAuthResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class OAuthClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return OAuthResponse({"access_token": "provider-token"})

        def get(self, *args, **kwargs):
            return OAuthResponse({"sub": "google-123", "email": "google@example.com", "email_verified": True})

    monkeypatch.setattr(auth_routes, "Redis", OAuthRedis)
    monkeypatch.setattr(auth_routes.httpx, "Client", OAuthClient)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/auth/google/callback?code=authorization-code&state=" + state,
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert "google=success" in callback.headers["location"]
    assert client.get("/api/auth/me").status_code == 200
    user = db.scalar(select(User).where(User.email == "google@example.com"))
    assert user is not None and user.google_sub == "google-123"


def test_weak_password_never_echoed(client):
    response = client.post(
        "/api/auth/register",
        json={"username": "newuser", "email": "new@example.com", "password": "weak-secret"},
    )
    assert response.status_code == 422
    assert "weak-secret" not in response.text


def test_csrf_and_cross_origin(signed):
    assert (
        signed.post("/api/accounts/mock", json={"name": "x"}, headers={"X-CSRF-Token": "invalid"}).status_code
        == 403
    )
    assert (
        signed.post(
            "/api/accounts/mock", json={"name": "x"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_rate_limit(client):
    for _ in range(10):
        assert (
            client.post("/api/auth/login", json={"username": "missing", "password": PASSWORD}).status_code
            == 401
        )
    assert (
        client.post("/api/auth/login", json={"username": "missing", "password": PASSWORD}).status_code == 429
    )


def test_rbac(signed):
    for path in ["/admin/users", "/admin/status", "/admin/audit", "/admin/backups", "/admin/operations"]:
        assert signed.get("/api" + path).status_code == 403


def test_admin_cannot_manage_system(client):
    sign_in(client, "manager", "ADMIN")
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/api/admin/backups").status_code == 403


def test_disabled_user_sessions_revoked(owner, db):
    with TestClient(app) as other:
        identity = sign_in(other, "other")
        assert (
            owner.patch("/api/admin/users/" + identity, json={"role": "USER", "active": False}).status_code
            == 200
        )
        assert other.get("/api/auth/me").status_code == 401
    assert db.scalar(select(Session).where(Session.user_id == identity)) is None


def test_owner_self_protection(owner):
    identity = owner.get("/api/auth/me").json()["id"]
    assert (
        owner.patch("/api/admin/users/" + identity, json={"role": "USER", "active": False}).status_code == 400
    )


def test_password_change_invalidates_all_sessions(signed):
    result = signed.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD + "new"}
    )
    assert result.status_code == 200
    assert signed.get("/api/auth/me").status_code == 401
