from urllib.parse import parse_qs, urlsplit

import pytest
from nexa.config import Settings, settings


@pytest.mark.parametrize("base", ["https://first.example", "https://replacement.example"])
def test_domain_change_updates_owner_urls_and_oauth(owner, monkeypatch, base):
    monkeypatch.setattr(settings(), "base_url", base)
    monkeypatch.setattr(settings(), "meta_app_id", "test-app")
    result = owner.get("/api/admin/integrations")
    assert result.status_code == 200
    urls = result.json()["public_urls"]
    assert urls == {
        "base_url": base,
        "instagram_callback": base + "/api/instagram/callback",
        "meta_webhook": base + "/webhooks/meta",
        "telegram_webhook": base + "/webhooks/telegram",
    }
    authorized = owner.post("/api/instagram/authorize")
    assert authorized.status_code == 200
    query = parse_qs(urlsplit(authorized.json()["url"]).query)
    assert query["redirect_uri"] == [urls["instagram_callback"]]
    assert settings().meta_app_secret not in result.text
    assert settings().meta_verify_token not in result.text


def test_missing_meta_credentials_is_explicit(signed, monkeypatch):
    monkeypatch.setattr(settings(), "meta_app_id", "")
    monkeypatch.setattr(settings(), "meta_app_secret", "")
    response = signed.post("/api/instagram/authorize")
    assert response.status_code == 503
    assert response.json() == {"detail": "meta_not_configured"}
    assert signed.get("/api/admin/integrations").status_code == 403


def test_base_url_normalizes_trailing_slash():
    assert Settings(base_url="https://panel.example/").base_url == "https://panel.example"


@pytest.mark.parametrize(
    "value",
    [
        "https://",
        "ftp://panel.example",
        "https://user:secret@panel.example",
        "https://panel.example/path",
        "https://panel.example?query=1",
        "https://panel.example#fragment",
        "https://panel.example:99999",
    ],
)
def test_base_url_rejects_ambiguous_origins(value):
    with pytest.raises(ValueError):
        Settings(base_url=value)


def test_production_cookies_and_logout_invalidate_session(client, monkeypatch):
    from conftest import PASSWORD, sign_in

    sign_in(client)
    monkeypatch.setattr(settings(), "cookie_secure", True)
    client.base_url = "https://testserver"
    response = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert all("Secure" in value and "SameSite=lax" in value for value in cookies)
    assert "HttpOnly" in next(value for value in cookies if value.startswith("nexa_session="))
    session = client.cookies["nexa_session"]
    client.headers["X-CSRF-Token"] = client.cookies["nexa_csrf"]
    assert client.get("/api/dashboard").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/dashboard", headers={"Cookie": "nexa_session=" + session}).status_code == 401
