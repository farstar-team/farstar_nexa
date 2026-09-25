import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Protocol

import httpx
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from nexa.commerce_schema import PricingRule, aware
from nexa.config import settings
from nexa.models import WorkspaceRate


class PricingUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class ExchangeRate:
    base: str
    quote: str
    rate: Decimal
    provider: str
    fetched_at: datetime
    expires_at: datetime

    def as_dict(self):
        return dict(
            base_currency=self.base,
            quote_currency=self.quote,
            rate=str(self.rate),
            provider=self.provider,
            fetched_at=self.fetched_at.isoformat(),
            expires_at=self.expires_at.isoformat(),
            stale=self.expires_at <= datetime.now(UTC),
        )


class ExchangeRateProvider(Protocol):
    def get_rate(self, base: str, quote: str) -> ExchangeRate: ...
    def health(self) -> dict: ...


class OpenExchangeProvider:
    """Public daily indicative rates. Fixed host; callers cannot supply URLs."""

    name = "open_er_api"

    def health(self):
        try:
            with Redis.from_url(settings().redis_url, socket_timeout=2, socket_connect_timeout=2) as client:
                return {"provider": self.name, "status": client.get("fx:health") or b"not_checked"}
        except RedisError:
            return {"provider": self.name, "status": "cache_unavailable"}

    def get_rate(self, base: str, quote: str) -> ExchangeRate:
        actual_base, actual_quote = (
            ("IRR" if base == "TOMAN" else base),
            ("IRR" if quote == "TOMAN" else quote),
        )
        now = datetime.now(UTC)
        if actual_base == actual_quote:
            rate = Decimal(10 if base == "TOMAN" else 1) / Decimal(10 if quote == "TOMAN" else 1)
            return ExchangeRate(base, quote, rate, "fixed_conversion", now, now + timedelta(days=1))
        try:
            with Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2) as client:
                key = "fx:open_er_api:" + actual_base
                raw = client.get(key)
                data = json.loads(raw, parse_float=Decimal) if raw else None
                if not data or float(data["expires_at"]) <= now.timestamp():
                    # One request per base per hour across workers, including provider failures.
                    if not client.set(key + ":fetch", "1", nx=True, ex=3600):
                        raise PricingUnavailable("exchange_rate_unavailable")
                    try:
                        response = httpx.get("https://open.er-api.com/v6/latest/" + actual_base, timeout=8)
                        response.raise_for_status()
                        data = json.loads(response.text, parse_float=Decimal)
                        if data.get("result") != "success" or data.get("base_code") != actual_base:
                            raise ValueError()
                        updated = float(data["time_last_update_unix"])
                        expires = min(
                            float(data["time_next_update_unix"]) + 300,
                            now.timestamp() + settings().exchange_cache_ttl,
                        )
                        if (
                            updated > now.timestamp() + 300
                            or expires <= now.timestamp()
                            or now.timestamp() - updated > 172800
                        ):
                            raise ValueError()
                        data["expires_at"] = expires
                        client.set(key, json.dumps(data, default=str), ex=172800)
                        client.set("fx:health", "healthy", ex=86400)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        client.set("fx:health", "unavailable", ex=3600)
                        raise PricingUnavailable("exchange_rate_unavailable") from None
                rate = Decimal(str(data["rates"][actual_quote]))
                rate = rate * (10 if base == "TOMAN" else 1) / (10 if quote == "TOMAN" else 1)
                if not rate.is_finite() or rate <= 0:
                    raise ValueError()
                return ExchangeRate(
                    base,
                    quote,
                    rate,
                    self.name,
                    datetime.fromtimestamp(float(data["time_last_update_unix"]), UTC),
                    datetime.fromtimestamp(float(data["expires_at"]), UTC),
                )
        except (RedisError, KeyError, TypeError, ValueError):
            raise PricingUnavailable("exchange_rate_unavailable") from None


PROVIDERS: dict[str, ExchangeRateProvider] = {"open_er_api": OpenExchangeProvider()}


def format_price(value: Decimal) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def calculate(db, product, *, sample_rate=None, now=None):
    now = now or datetime.now(UTC)
    rule = PricingRule.model_validate(product.pricing or {})
    manual = product.manual_rate
    rate_updated = getattr(product, "updated_at", None) or now
    if manual is None and db is not None:
        row = db.scalar(
            select(WorkspaceRate).where(
                WorkspaceRate.workspace_id == product.workspace_id,
                WorkspaceRate.base_currency == product.base_currency,
                WorkspaceRate.quote_currency == product.output_currency,
            )
        )
        manual = row.rate if row else None
        if row:
            rate_updated = row.updated_at
    source = "manual"
    rate = manual
    fixed_conversion = product.base_currency == product.output_currency or {
        product.base_currency,
        product.output_currency,
    } <= {"IRR", "TOMAN"}
    if fixed_conversion:
        rate = (
            Decimal(10 if product.base_currency == "TOMAN" else 1)
            / Decimal(10 if product.output_currency == "TOMAN" else 1)
            if product.base_currency != product.output_currency
            else Decimal(1)
        )
        source = "fixed_conversion"
    elif sample_rate is not None:
        rate, source = Decimal(str(sample_rate)), "sample"
    exchange = None
    if product.pricing_mode != "MANUAL" and source not in {"sample", "fixed_conversion"}:
        try:
            exchange = PROVIDERS[settings().exchange_provider].get_rate(
                product.base_currency, product.output_currency
            )
            if exchange.expires_at <= now:
                raise PricingUnavailable("exchange_rate_stale")
            rate, source = exchange.rate, exchange.provider
        except (PricingUnavailable, KeyError):
            if rule.fallback != "MANUAL" or manual is None:
                raise PricingUnavailable("exchange_rate_unavailable") from None
            rate, source = manual, "manual_fallback"
    if rate is None or not rate.is_finite() or rate <= 0:
        raise PricingUnavailable("manual_rate_required")
    with localcontext() as ctx:
        ctx.prec = 50
        converted = Decimal(product.base_price) * rate
        adjusted = converted
        if product.pricing_mode != "LIVE":
            adjusted = converted * (1 + rule.percentage / 100) + rule.fixed
        original = max(Decimal(0), adjusted)
        discount_active = (not rule.discount_start or now >= rule.discount_start) and (
            not rule.discount_end or now < rule.discount_end
        )
        discount = Decimal(0)
        if discount_active:
            if rule.discount_type == "PERCENTAGE":
                discount = original * rule.discount_value / 100
            elif rule.discount_type == "FIXED":
                discount = rule.discount_value
        final = max(Decimal(0), original - discount)
        if rule.rounding:
            final = (final / rule.rounding).quantize(Decimal(1), rounding=ROUND_HALF_UP) * rule.rounding
        if rule.minimum is not None:
            final = max(rule.minimum, final)
        if rule.maximum is not None:
            final = min(rule.maximum, final)
        final = final.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    result = dict(
        base_price=str(product.base_price),
        base_currency=product.base_currency,
        converted_price=str(converted),
        original_price=str(original),
        discount=str(discount),
        final_price=str(final),
        formatted_price=format_price(final),
        currency=product.output_currency,
        adjustment=str(adjusted - converted),
        rate=str(rate),
        source=source,
        stale=False,
        updated_at=(exchange.fetched_at if exchange else aware(rate_updated)).isoformat(),
        expires_at=exchange.expires_at.isoformat() if exchange else None,
        warning="manual_fallback"
        if source == "manual_fallback"
        else ("indicative_daily_rate" if exchange else ""),
    )
    return result
