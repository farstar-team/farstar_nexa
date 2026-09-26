import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from conftest import sign_in
from nexa import pricing
from nexa.automation import matches, normalize
from nexa.commerce_schema import ProductInput
from nexa.config import settings
from nexa.db import now_utc, utcnow
from nexa.flows import ingest_comment, run_flow
from nexa.models import (
    Account,
    ActionExecution,
    Automation,
    Execution,
    InstagramMedia,
    Job,
    Lead,
    Message,
    Product,
)
from nexa.pricing import ExchangeRate, PricingUnavailable, TgjuSanaProvider, calculate
from nexa.providers import DeliveryUnknown, InstagramProvider, RateLimited, Receipt
from nexa.routes.commerce import product_values
from nexa.security import encrypt
from nexa.templates import render, validate_template
from nexa.worker import recover_stale
from sqlalchemy import func, select

PRODUCT = {
    "name": "محصول نمونه",
    "slug": "sample-product",
    "base_price": "12.50",
    "base_currency": "USD",
    "output_currency": "TOMAN",
    "manual_rate": "60000",
    "pricing": {"percentage": "10", "discount_type": "PERCENTAGE", "discount_value": "5", "rounding": "1000"},
}


@pytest.fixture
def product(signed):
    response = signed.post("/api/products", json=PRODUCT)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def media(signed, account, product):
    response = signed.post("/api/media/sync", json={"account_id": account["id"]})
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert (
        signed.put(
            "/api/media/product", json={"media_ids": [row["id"]], "product_id": product["id"]}
        ).status_code
        == 200
    )
    return row


@pytest.fixture
def flow(signed, account, product, media):
    payload = {
        "account_id": account["id"],
        "name": "کامنت قیمت",
        "trigger_type": "instagram.comment",
        "keywords": ["قیمت"],
        "match_mode": "contains",
        "product_id": product["id"],
        "scope": "PRODUCT_MEDIA",
        "flow": {
            "actions": [
                {"type": "CREATE_OR_UPDATE_LEAD"},
                {"type": "ADD_TAG", "value": "علاقه‌مند"},
                {
                    "type": "SEND_PRICE",
                    "template": "سلام {{customer.name}}؛ {{product.name}}: {{product.price}} {{product.currency}}",
                },
                {"type": "INTERNAL_NOTE", "value": "قیمت ارسال شد"},
            ]
        },
    }
    response = signed.post("/api/automations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def dry(signed, account, media, flow, **overrides):
    payload = {
        "account_id": account["id"],
        "media_id": media["id"],
        "sender": "customer-1",
        "display_name": "علی",
        "text": "قیمت لطفاً",
        "event_id": "sample-1",
        **overrides,
    }
    response = signed.post(f"/api/automations/{flow['id']}/dry-run", json=payload)
    assert response.status_code == 200, response.text
    detail = signed.get("/api/executions/" + response.json()["execution_id"])
    assert detail.status_code == 200
    return response.json(), detail.json()


def test_decimal_preview_nonmutating(signed, db):
    before = db.scalar(select(func.count()).select_from(Product))
    result = signed.post("/api/products/preview", json=PRODUCT)
    assert result.status_code == 200, result.text
    assert result.json()["final_price"] == "784000.00"
    assert result.json()["rate"] == "60000"
    assert db.scalar(select(func.count()).select_from(Product)) == before


@pytest.mark.parametrize(
    "base,quote,expected", [("IRR", "TOMAN", "0.1"), ("TOMAN", "IRR", "10"), ("EUR", "EUR", "1")]
)
def test_currency_units(base, quote, expected):
    p = Product(
        **product_values(
            ProductInput.model_validate({**PRODUCT, "base_currency": base, "output_currency": quote})
        )
    )
    assert Decimal(calculate(None, p)["rate"]) == Decimal(expected)


@pytest.mark.parametrize(
    "mode,final", [("LIVE", "712500.00"), ("LIVE_WITH_ADJUSTMENT", "783750.00"), ("MANUAL", "783750.00")]
)
def test_pricing_modes(monkeypatch, mode, final):
    class Rates:
        def get_rate(self, base, quote):
            return ExchangeRate(
                base, quote, Decimal(60000), "test", now_utc(), now_utc() + timedelta(hours=1)
            )

    monkeypatch.setitem(pricing.PROVIDERS, "open_er_api", Rates())
    p = Product(
        **product_values(
            ProductInput.model_validate(
                {**PRODUCT, "pricing_mode": mode, "pricing": {**PRODUCT["pricing"], "rounding": "0"}}
            )
        )
    )
    assert calculate(None, p)["final_price"] == final


def test_direct_price_disables_conversion_and_adjustment():
    p = Product(
        **product_values(
            ProductInput.model_validate(
                {
                    **PRODUCT,
                    "base_currency": "TOMAN",
                    "output_currency": "TOMAN",
                    "base_price": "125000",
                    "manual_rate": None,
                    "pricing": {"direct_price": True, "percentage": "25", "fixed": "5000"},
                }
            )
        )
    )
    result = calculate(None, p)
    assert result["source"] == "direct_price"
    assert result["final_price"] == "125000.00"
    assert result["adjustment"] == "0"


def test_explicit_adjustment_toggle_overrides_legacy_mode():
    p = Product(
        **product_values(
            ProductInput.model_validate(
                {
                    **PRODUCT,
                    "pricing_mode": "LIVE",
                    "pricing": {"percentage": "10", "adjustment_enabled": True},
                }
            )
        )
    )
    result = calculate(None, p, sample_rate=Decimal("60000"))
    assert result["final_price"] == "825000.00"


def test_tgju_sana_parser_accepts_p_fields(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"id": "sana_sell_usd", "p": "600,000"},
                    {"id": "sana_sell_eur", "p": "650000"},
                    {"id": "sana_sell_aed", "p": "163500"},
                ]
            }

    monkeypatch.setattr(pricing.httpx, "get", lambda *args, **kwargs: Response())
    data = TgjuSanaProvider()._fetch(now_utc())
    assert data["rates"]["USD"] == "600000"
    assert data["rates"]["EUR"] == "650000"


def test_discount_window_and_price_bounds():
    now = now_utc()
    config = {
        "percentage": "-10",
        "fixed": "-2",
        "discount_type": "FIXED",
        "discount_value": "10",
        "discount_start": (now + timedelta(hours=1)).isoformat(),
        "minimum": "8",
        "maximum": "9",
    }
    p = Product(
        **product_values(
            ProductInput.model_validate(
                {**PRODUCT, "base_currency": "USD", "output_currency": "USD", "pricing": config}
            )
        )
    )
    assert calculate(None, p, now=now)["final_price"] == "9.00"
    assert calculate(None, p, now=now + timedelta(hours=2))["final_price"] == "8.00"


def test_stale_rate_fails_closed_and_explicit_fallback(monkeypatch):
    class Stale:
        def get_rate(self, base, quote):
            return ExchangeRate(
                base,
                quote,
                Decimal(1),
                "stale",
                now_utc() - timedelta(days=2),
                now_utc() - timedelta(seconds=1),
            )

    monkeypatch.setitem(pricing.PROVIDERS, "open_er_api", Stale())
    p = Product(**product_values(ProductInput.model_validate({**PRODUCT, "pricing_mode": "LIVE"})))
    with pytest.raises(PricingUnavailable):
        calculate(None, p)
    p.pricing = {"fallback": "MANUAL"}
    assert calculate(None, p)["source"] == "manual_fallback"


def test_live_exchange_rate_is_cached_with_provider_timestamps(monkeypatch):
    now = now_utc()
    cache = {}
    requests = []

    class FakeRedis:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, key):
            return cache.get(key)

        def set(self, key, value, nx=False, ex=None):
            if nx and key in cache:
                return False
            cache[key] = value
            return True

    def fetch(url, timeout):
        requests.append((url, timeout))
        payload = {
            "result": "success",
            "base_code": "USD",
            "time_last_update_unix": int(now.timestamp()),
            "time_next_update_unix": int((now + timedelta(hours=12)).timestamp()),
            "rates": {"EUR": 0.85},
        }
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(pricing.Redis, "from_url", lambda *args, **kwargs: FakeRedis())
    monkeypatch.setattr(pricing.httpx, "get", fetch)
    provider = pricing.OpenExchangeProvider()
    first = provider.get_rate("USD", "EUR")
    second = provider.get_rate("USD", "EUR")

    assert first.rate == second.rate == Decimal("0.85")
    assert first.fetched_at == second.fetched_at
    assert first.expires_at == second.expires_at
    assert len(requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"base_price": "NaN"},
        {"manual_rate": "0"},
        {"base_currency": "BTC"},
        {"pricing": {"discount_value": "101", "discount_type": "PERCENTAGE"}},
        {"url": "javascript:alert(1)"},
        {"pricing": {"minimum": "20", "maximum": "10"}},
    ],
)
def test_invalid_product_rejected(signed, change):
    assert signed.post("/api/products", json={**PRODUCT, **change}).status_code == 422


def test_crud_and_reference_guard(signed, product, media):
    assert signed.post("/api/products", json=PRODUCT).status_code == 409
    assert (
        signed.put("/api/products/" + product["id"], json={**PRODUCT, "status": "INACTIVE"}).status_code
        == 200
    )
    assert signed.delete("/api/products/" + product["id"]).status_code == 409
    signed.put("/api/media/product", json={"media_ids": [media["id"]], "product_id": None})
    assert signed.delete("/api/products/" + product["id"]).status_code == 200


def test_product_list_includes_usage_counts(signed, product, media, flow):
    row = signed.get("/api/products").json()[0]
    assert row["id"] == product["id"]
    assert row["media_count"] == 1
    assert row["automation_count"] == 1
    assert row["updated_at"]


def test_workspace_isolation(signed, product, account, media, flow):
    _, execution = dry(signed, account, media, flow)
    sign_in(signed, "bob")
    assert signed.get("/api/products").json() == []
    assert signed.put("/api/products/" + product["id"], json=PRODUCT).status_code == 404
    assert signed.get("/api/media", params={"account_id": account["id"]}).status_code == 404
    assert (
        signed.put(
            "/api/media/product", json={"media_ids": [media["id"]], "product_id": product["id"]}
        ).status_code
        == 404
    )
    assert signed.get("/api/executions/" + execution["id"]).status_code == 404
    assert (
        signed.post(
            "/api/automations",
            json={"account_id": account["id"], "name": "x", "keywords": ["x"], "response": "x"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "text,keyword,mode,expected",
    [
        ("قِيمت", "قیمت", "exact", True),
        ("مي خواهم", "می‌خواهم", "exact", True),
        (" قیمت امروز ", "قیمت", "starts_with", True),
        ("گرانقیمت", "قیمت", "keyword_set", False),
        ("قیمت؟", "قیمت", "keyword_set", True),
        ("سلام", "قیمت", "contains", False),
    ],
)
def test_persian_triggers(text, keyword, mode, expected):
    assert matches(text, [keyword], mode) is expected
    assert normalize(normalize(text)) == normalize(text)


@pytest.mark.parametrize(
    "template",
    [
        "{{__import__('os')}}",
        "{{customer.__class__}}",
        "{% for x in a %}",
        "{{product.secret}}",
        "{{product.price",
    ],
)
def test_unsafe_templates_rejected(template):
    with pytest.raises(ValueError):
        validate_template(template)


def test_render_requires_all_variables():
    with pytest.raises(ValueError):
        render("{{product.price}}", {})
    assert render("سلام {{customer.name}}", {"customer": {"name": "علی"}}) == "سلام علی"


def test_dry_run_pipeline_duplicate_no_side_effects(signed, account, media, flow, db, monkeypatch):
    monkeypatch.setattr(InstagramProvider, "private_reply", lambda *a: pytest.fail("dry-run sent a message"))
    result, detail = dry(signed, account, media, flow)
    assert detail["status"] == "simulated"
    assert "784,000" in detail["actions"][2]["result"]["rendered_text"]
    assert detail["actions"][2]["result"]["pricing"]["source"] == "manual"
    again, _ = dry(signed, account, media, flow)
    assert again["duplicate"] and again["execution_id"] == result["execution_id"]
    assert db.scalar(select(func.count()).select_from(Lead)) == 0
    assert db.scalar(select(func.count()).select_from(Message).where(Message.direction == "out")) == 0
    history = signed.get("/api/executions").json()[0]
    assert history["automation_name"] == "کامنت قیمت"
    assert history["product_name"] == "محصول نمونه"
    assert history["media_caption"]
    assert history["actions"] == ["CREATE_OR_UPDATE_LEAD", "ADD_TAG", "SEND_PRICE", "INTERNAL_NOTE"]


def test_cooldown_inactive_no_match(signed, account, product, media, flow):
    dry(signed, account, media, flow)
    assert dry(signed, account, media, flow, event_id="sample2")[1]["status"] == "cooldown"
    assert dry(signed, account, media, flow, event_id="sample3", text="سلام")[1]["status"] == "skipped"
    signed.put("/api/products/" + product["id"], json={**PRODUCT, "status": "INACTIVE"})
    assert (
        dry(signed, account, media, flow, event_id="sample4", sender="other")[1]["detail"]
        == "product_inactive"
    )


def test_sample_dryrun_production_mode(signed, monkeypatch):
    monkeypatch.setattr(settings(), "mock_mode", False)
    assert signed.post("/api/accounts/mock", json={"name": "نمونه"}).status_code == 403
    account = signed.post("/api/accounts/mock", json={"name": "نمونه", "dry_run_only": True}).json()
    data = {
        "name": "draft",
        "account_id": account["id"],
        "trigger_type": "instagram.comment",
        "match_mode": "any",
        "status": "DRAFT",
        "flow": {"actions": [{"type": "SEND_DM", "template": "سلام"}]},
    }
    response = signed.post("/api/automations", json=data)
    assert response.status_code == 201, response.text
    assert (
        signed.patch("/api/automations/" + response.json()["id"], json={"enabled": True}).status_code == 422
    )


def test_flow_validations(signed, account):
    base = {
        "account_id": account["id"],
        "name": "flow",
        "trigger_type": "instagram.comment",
        "match_mode": "any",
    }
    assert (
        signed.post(
            "/api/automations", json={**base, "flow": {"actions": [{"type": "SEND_DM", "template": "a"}] * 2}}
        ).status_code
        == 422
    )
    assert (
        signed.post(
            "/api/automations",
            json={
                **base,
                "scope": "SPECIFIC_MEDIA",
                "flow": {"actions": [{"type": "SEND_DM", "template": "a"}]},
            },
        ).status_code
        == 422
    )


def real_job(db, account, media, flow):
    account = db.get(Account, account["id"])
    account.provider, account.external_id, account.credential = "instagram", "111", encrypt("test-token-only")
    row = db.get(InstagramMedia, media["id"])
    row.external_id = "222"
    job = Job(
        key="meta-comment:" + account.id + ":333",
        kind="incoming",
        payload={
            "account_id": account.id,
            "event_type": "comment",
            "event_id": "333",
            "sender": "444",
            "display_name": "علی",
            "text": "قیمت",
            "media_external_id": "222",
        },
    )
    db.add(job)
    db.commit()
    ingest_comment(db, job)
    db.commit()
    return db.scalar(select(Job).where(Job.kind == "flow")), db.scalar(select(Execution))


@pytest.fixture
def comment_contract(monkeypatch):
    monkeypatch.setattr(
        InstagramProvider,
        "comment",
        lambda *a: {
            "occurred_at": now_utc(),
            "media": {"id": "222", "media_product_type": "FEED"},
            "from": {"id": "444"},
        },
    )


def test_real_pipeline_leads_and_delivery(db, account, media, flow, comment_contract, monkeypatch):
    calls = []
    monkeypatch.setattr(InstagramProvider, "private_reply", lambda *a: calls.append(a) or Receipt("receipt"))
    job, execution = real_job(db, account, media, flow)
    run_flow(db, job)
    run_flow(db, job)
    assert execution.status == "complete" and len(calls) == 1
    assert calls[0][2] == "333"
    lead = db.scalar(select(Lead))
    assert lead.tags == ["علاقه‌مند"] and len(lead.notes) == 1


def test_rate_limit_retries_are_bounded(db, account, media, flow, comment_contract, monkeypatch):
    monkeypatch.setattr(InstagramProvider, "private_reply", lambda *a: (_ for _ in ()).throw(RateLimited(2)))
    job, execution = real_job(db, account, media, flow)
    for attempt in range(5):
        run_flow(db, job)
        if attempt < 4:
            assert execution.status == "waiting" and job.available_at > utcnow()
    assert execution.status == "failed" and execution.detail == "rate_limit_exhausted"


def test_uncertain_send_never_retried(db, account, media, flow, comment_contract, monkeypatch):
    calls = []

    def timeout(*a):
        calls.append(1)
        raise DeliveryUnknown()

    monkeypatch.setattr(InstagramProvider, "private_reply", timeout)
    job, execution = real_job(db, account, media, flow)
    run_flow(db, job)
    run_flow(db, job)
    assert execution.status == "unknown" and len(calls) == 1


def test_expired_comment_blocks_delivery(db, account, media, flow, monkeypatch):
    monkeypatch.setattr(
        InstagramProvider,
        "comment",
        lambda *a: {
            "occurred_at": now_utc() - timedelta(days=8),
            "media": {"id": "222", "media_product_type": "FEED"},
            "from": {"id": "444"},
        },
    )
    monkeypatch.setattr(InstagramProvider, "private_reply", lambda *a: pytest.fail("expired comment sent"))
    job, execution = real_job(db, account, media, flow)
    run_flow(db, job)
    assert execution.detail == "private_reply_window_expired"


def test_delayed_execution_rechecks_product(db, account, media, flow, product):
    row = db.get(Automation, flow["id"])
    row.flow = {"version": 2, "actions": [{"type": "DELAY", "seconds": 60}, *row.flow["actions"]]}
    db.commit()
    job, execution = real_job(db, account, media, flow)
    run_flow(db, job)
    assert execution.status == "waiting" and job.status == "pending"
    db.get(Product, product["id"]).status = "INACTIVE"
    db.commit()
    run_flow(db, job)
    assert execution.status == "cancelled"


def test_recover_sending_flow_quarantines(db, account, media, flow):
    job, execution = real_job(db, account, media, flow)
    job.status, job.locked_at = "running", utcnow() - timedelta(minutes=6)
    action = db.scalar(
        select(ActionExecution).where(
            ActionExecution.execution_id == execution.id, ActionExecution.kind == "SEND_PRICE"
        )
    )
    action.status = "sending"
    db.commit()
    recover_stale(db)
    assert execution.status == action.status == job.status == "unknown"


@pytest.mark.parametrize("direct", [False, True])
def test_signed_comment_webhook_formats_and_dedup(signed, db, account, media, flow, direct):
    row = db.get(Account, account["id"])
    row.provider, row.external_id = "instagram", "111"
    db.commit()
    change = {
        "field": "comments",
        "value": {
            "id": "333",
            "from": {"id": "444", "username": "sample"},
            "text": "قیمت",
            "media": {"id": "222", "media_product_type": "FEED"},
        },
    }
    entry = {"id": "111", **(change if direct else {"changes": [change]})}
    body = json.dumps({"object": "instagram", "entry": [entry]}).encode()
    signature = "sha256=" + hmac.new(settings().meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    for _ in range(2):
        assert (
            signed.post(
                "/webhooks/meta", content=body, headers={"x-hub-signature-256": signature}
            ).status_code
            == 200
        )
    assert db.scalar(select(func.count()).select_from(Job)) == 1
    assert (
        signed.post("/webhooks/meta", content=body, headers={"x-hub-signature-256": "invalid"}).status_code
        == 403
    )


def test_meta_private_reply_contract(db, account, monkeypatch):
    account = db.get(Account, account["id"])
    account.external_id, account.credential = "111", encrypt("test-token-only")

    def post(url, **kw):
        assert url.endswith("/111/messages") and url.startswith("https://graph.instagram.com/")
        assert kw["json"] == {"recipient": {"comment_id": "333"}, "message": {"text": "سلام"}}
        assert "access_token" not in url
        return httpx.Response(200, json={"message_id": "receipt", "recipient_id": "444"})

    monkeypatch.setattr("nexa.providers.httpx.post", post)
    assert InstagramProvider().private_reply(account, "333", "سلام", "key").message_id == "receipt"


def test_manual_workspace_rate_used(signed):
    signed.put(
        "/api/exchange-rates", json={"base_currency": "USD", "quote_currency": "TOMAN", "rate": "50000"}
    )
    response = signed.post("/api/products/preview", json={**PRODUCT, "manual_rate": None})
    assert response.status_code == 200 and Decimal(response.json()["rate"]) == Decimal(50000)
