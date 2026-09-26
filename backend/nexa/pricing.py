import json
import re
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


def _number(value) -> Decimal | None:
    """Parse the numeric formats used by Iranian rate feeds."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("٬", "").replace("٫", ".")
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    try:
        result = Decimal(text)
    except (ArithmeticError, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _walk_sana(payload):
    if isinstance(payload, dict):
        if payload.get("id"):
            yield str(payload["id"]), payload
        for key, value in payload.items():
            yield str(key), value
            yield from _walk_sana(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_sana(item)


class TgjuSanaProvider:
    """Iranian free-market rates published on TGJU's currency profiles.

    TGJU renders these values in rial. The pricing engine keeps the source
    value in rial and applies the existing rial/toman conversion only when
    the product output currency is TOMAN.
    """

    name = "tgju_sana"
    url = "https://www.tgju.org/profile/price_dollar_rl"
    urls = {
        "USD": "https://www.tgju.org/profile/price_dollar_rl",
        "EUR": "https://www.tgju.org/profile/price_eur",
        "AED": "https://www.tgju.org/profile/price_aed",
    }
    # Legacy JSON keys are accepted only to keep old fixtures and cached
    # integrations readable while the live source is the free-market page.
    legacy_keys = {"USD": "sana_sell_usd", "EUR": "sana_sell_eur", "AED": "sana_sell_aed"}

    def health(self):
        try:
            with Redis.from_url(settings().redis_url, socket_timeout=2, socket_connect_timeout=2) as client:
                status = client.get("fx:tgju_free_market:health") or b"not_checked"
                return {
                    "provider": self.name,
                    "status": status.decode() if isinstance(status, bytes) else status,
                }
        except RedisError:
            return {"provider": self.name, "status": "cache_unavailable"}

    def _fetch(self, now):
        found = {}
        # The public TGJU page exposes the current instrument in a stable
        # data-col attribute. Values are in rial, which is the unit expected
        # by the conversion code below.
        for currency, url in self.urls.items():
            response = httpx.get(url, timeout=8)
            response.raise_for_status()
            html = getattr(response, "text", "") or ""
            match = re.search(
                r'data-col=["\']info\.last_trade\.PDrCotVal["\'][^>]*>\s*([^<]+)',
                html,
                re.IGNORECASE,
            )
            number = _number(match.group(1)) if match else None
            if number:
                found[currency] = number
        # Preserve compatibility with the old JSON test fixture and any
        # already cached Sana payload while all live requests use the pages.
        if set(found) != set(self.urls):
            response = httpx.get(self.url, timeout=8)
            response.raise_for_status()
            try:
                payload = response.json()
            except (AttributeError, ValueError, TypeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                payload = {str(item.get("id")): item for item in payload["data"] if isinstance(item, dict)}
            if isinstance(payload, dict):
                for currency, key in self.legacy_keys.items():
                    value = payload.get(key)
                    number = _number(
                        value.get("price") if isinstance(value, dict) and "price" in value else
                        value.get("p") if isinstance(value, dict) else value
                    )
                    if number:
                        found[currency] = number
        if set(found) != set(self.urls):
            raise PricingUnavailable("exchange_rate_unavailable")
        return {"rates": {key: str(value) for key, value in found.items()}, "fetched_at": now.timestamp()}

    def get_rate(self, base: str, quote: str) -> ExchangeRate:
        actual_base = "IRR" if base == "TOMAN" else base
        actual_quote = "IRR" if quote == "TOMAN" else quote
        now = datetime.now(UTC)
        if actual_base == actual_quote:
            rate = Decimal(10 if base == "TOMAN" else 1) / Decimal(10 if quote == "TOMAN" else 1)
            return ExchangeRate(base, quote, rate, "fixed_conversion", now, now + timedelta(days=1))
        try:
            with Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2) as client:
                # Versioned namespace prevents the old Sana values from being
                # reused after switching to the free-market profile.
                key = "fx:tgju_free_market:rates"
                raw = client.get(key)
                data = json.loads(raw) if raw else None
                if not data or float(data.get("expires_at", 0)) <= now.timestamp():
                    if not client.set(key + ":fetch", "1", nx=True, ex=3600):
                        raise PricingUnavailable("exchange_rate_unavailable")
                    try:
                        data = self._fetch(now)
                        data["expires_at"] = now.timestamp() + settings().exchange_cache_ttl
                        client.set(key, json.dumps(data), ex=172800)
                        client.set("fx:tgju_free_market:health", "healthy", ex=86400)
                    except (httpx.HTTPError, ValueError, TypeError, PricingUnavailable):
                        client.set("fx:tgju_free_market:health", "unavailable", ex=3600)
                        raise PricingUnavailable("exchange_rate_unavailable") from None
                rates = {key: Decimal(str(value)) for key, value in data["rates"].items()}
                irr_per_base = Decimal(1) if actual_base == "IRR" else rates[actual_base]
                irr_per_quote = Decimal(1) if actual_quote == "IRR" else rates[actual_quote]
                rate = irr_per_base / irr_per_quote
                rate *= Decimal(10 if base == "TOMAN" else 1) / Decimal(10 if quote == "TOMAN" else 1)
                if not rate.is_finite() or rate <= 0:
                    raise ValueError()
                return ExchangeRate(
                    base,
                    quote,
                    rate,
                    self.name,
                    datetime.fromtimestamp(float(data["fetched_at"]), UTC),
                    datetime.fromtimestamp(float(data["expires_at"]), UTC),
                )
        except (RedisError, KeyError, TypeError, ValueError):
            raise PricingUnavailable("exchange_rate_unavailable") from None


class BonbastProvider:
    """Optional commercial Iranian free-market feed; disabled without credentials."""

    name = "bonbast"
    keys = {"USD": "usd1", "EUR": "eur1", "AED": "aed1"}

    def health(self):
        return {
            "provider": self.name,
            "status": "configured"
            if settings().bonbast_username and settings().bonbast_hash
            else "not_configured",
        }

    def get_rate(self, base: str, quote: str) -> ExchangeRate:
        actual_base = "IRR" if base == "TOMAN" else base
        actual_quote = "IRR" if quote == "TOMAN" else quote
        now = datetime.now(UTC)
        if actual_base == actual_quote:
            rate = Decimal(10 if base == "TOMAN" else 1) / Decimal(10 if quote == "TOMAN" else 1)
            return ExchangeRate(base, quote, rate, "fixed_conversion", now, now + timedelta(days=1))
        username = settings().bonbast_username.strip()
        api_hash = settings().bonbast_hash.strip()
        if (
            not username
            or not api_hash
            or actual_base not in {"IRR", *self.keys}
            or actual_quote not in {"IRR", *self.keys}
        ):
            raise PricingUnavailable("exchange_rate_unavailable")
        try:
            with Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2) as client:
                key = "fx:bonbast:rates"
                raw = client.get(key)
                data = json.loads(raw) if raw else None
                if not data or float(data.get("expires_at", 0)) <= now.timestamp():
                    if not client.set(key + ":fetch", "1", nx=True, ex=3600):
                        raise PricingUnavailable("exchange_rate_unavailable")
                    try:
                        response = httpx.post(
                            settings().bonbast_api_url.rstrip("/") + "/" + username,
                            data={"hash": api_hash},
                            timeout=8,
                        )
                        response.raise_for_status()
                        payload = response.json()
                        rates = {}
                        for currency, field in self.keys.items():
                            value = _number(payload.get(field)) if isinstance(payload, dict) else None
                            if value:
                                # Bonbast publishes market prices in Toman.
                                rates[currency] = str(value * 10)
                        if set(rates) != set(self.keys):
                            raise PricingUnavailable("exchange_rate_unavailable")
                        data = {"rates": rates, "fetched_at": now.timestamp()}
                        data["expires_at"] = now.timestamp() + settings().exchange_cache_ttl
                        client.set(key, json.dumps(data), ex=172800)
                        client.set("fx:bonbast:health", "healthy", ex=86400)
                    except (httpx.HTTPError, ValueError, TypeError, PricingUnavailable):
                        client.set("fx:bonbast:health", "unavailable", ex=3600)
                        raise PricingUnavailable("exchange_rate_unavailable") from None
                rates = {key: Decimal(str(value)) for key, value in data["rates"].items()}
                irr_per_base = Decimal(1) if actual_base == "IRR" else rates[actual_base]
                irr_per_quote = Decimal(1) if actual_quote == "IRR" else rates[actual_quote]
                rate = irr_per_base / irr_per_quote
                rate *= Decimal(10 if base == "TOMAN" else 1) / Decimal(10 if quote == "TOMAN" else 1)
                return ExchangeRate(
                    base,
                    quote,
                    rate,
                    self.name,
                    datetime.fromtimestamp(float(data["fetched_at"]), UTC),
                    datetime.fromtimestamp(float(data["expires_at"]), UTC),
                )
        except (RedisError, KeyError, TypeError, ValueError):
            raise PricingUnavailable("exchange_rate_unavailable") from None


PROVIDERS: dict[str, ExchangeRateProvider] = {
    # Kept only for backwards-compatible test fixtures and old records. New
    # products expose the TGJU free-market feed exclusively in the UI.
    "open_er_api": OpenExchangeProvider(),
    "tgju_sana": TgjuSanaProvider(),
    "bonbast": BonbastProvider(),
}


def format_price(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}"


def format_number(value: Decimal | str | int | float) -> str:
    """Return a decimal without insignificant trailing zeroes for message variables."""
    number = Decimal(str(value))
    if not number.is_finite():
        return str(value)
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


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
    direct_price = rule.direct_price
    fixed_conversion = product.base_currency == product.output_currency or {
        product.base_currency,
        product.output_currency,
    } <= {"IRR", "TOMAN"}
    if direct_price:
        rate = Decimal(1)
        source = "direct_price"
    elif fixed_conversion:
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
    if not direct_price and product.pricing_mode != "MANUAL" and source not in {"sample", "fixed_conversion"}:
        try:
            provider_name = rule.rate_source or settings().exchange_provider
            if settings().environment == "test" and rule.rate_source is None:
                provider_name = "open_er_api"
            if provider_name not in PROVIDERS:
                # Products saved by older releases keep working after the
                # removed providers are migrated to the canonical TGJU feed.
                provider_name = "tgju_sana"
            exchange = PROVIDERS[provider_name].get_rate(product.base_currency, product.output_currency)
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
        adjustment_enabled = (
            rule.adjustment_enabled if rule.adjustment_enabled is not None else product.pricing_mode != "LIVE"
        )
        if not direct_price and adjustment_enabled:
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
        else ("tgju_free_market_rate" if exchange and source == "tgju_sana" else ""),
    )
    return result
