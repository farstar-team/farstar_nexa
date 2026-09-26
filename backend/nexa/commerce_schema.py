from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Currency = Literal["USD", "EUR", "AED", "IRR", "TOMAN"]
Amount = Annotated[Decimal, Field(ge=0, le=Decimal("999999999999"), decimal_places=6, allow_inf_nan=False)]
Rate = Annotated[Decimal, Field(gt=0, le=Decimal("999999999999"), decimal_places=10, allow_inf_nan=False)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PricingRule(StrictInput):
    # Explicit controls are optional so records created before v0.3 keep their
    # historical pricing behaviour.
    direct_price: bool = False
    adjustment_enabled: bool | None = None
    rate_source: Literal["tgju_sana", "bonbast", "open_er_api"] | None = None
    percentage: Decimal = Field(default=Decimal(0), ge=-100, le=10000, allow_inf_nan=False)
    fixed: Decimal = Field(default=Decimal(0), ge=-999999999999, le=999999999999, allow_inf_nan=False)
    rounding: Amount = Decimal(0)
    minimum: Amount | None = None
    maximum: Amount | None = None
    discount_type: Literal["NONE", "PERCENTAGE", "FIXED"] = "NONE"
    discount_value: Amount = Decimal(0)
    discount_start: AwareDatetime | None = None
    discount_end: AwareDatetime | None = None
    fallback: Literal["STOP", "MANUAL"] = "STOP"

    @model_validator(mode="after")
    def valid_range(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("invalid_price_range")
        if self.discount_type == "PERCENTAGE" and self.discount_value > 100:
            raise ValueError("invalid_discount")
        if self.discount_start and self.discount_end and self.discount_start >= self.discount_end:
            raise ValueError("invalid_discount_window")
        return self


class ProductInput(StrictInput):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    description: str = Field(default="", max_length=4000)
    sku: str = Field(default="", max_length=80)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    availability: Literal["IN_STOCK", "OUT_OF_STOCK", "LIMITED", "ON_REQUEST"] = "IN_STOCK"
    base_price: Amount
    base_currency: Currency
    output_currency: Currency
    pricing_mode: Literal["LIVE", "MANUAL", "LIVE_WITH_ADJUSTMENT"] = "MANUAL"
    manual_rate: Rate | None = None
    pricing: PricingRule = Field(default_factory=PricingRule)
    url: str = Field(default="", max_length=2048)
    custom_fields: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def validate_direct_price(self):
        if self.pricing.direct_price and self.base_currency != self.output_currency:
            raise ValueError("direct_price_currency_mismatch")
        return self

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value:
            p = urlsplit(value)
            if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
                raise ValueError("invalid_url")
        return value

    @field_validator("custom_fields")
    @classmethod
    def bounded_fields(cls, value):
        if any(len(k) > 60 or len(v) > 500 for k, v in value.items()):
            raise ValueError("invalid_custom_fields")
        return value


class ActionInput(StrictInput):
    type: Literal[
        "SEND_DM", "SEND_PRODUCT", "SEND_PRICE", "ADD_TAG", "CREATE_OR_UPDATE_LEAD", "DELAY", "INTERNAL_NOTE"
    ]
    template: str = Field(default="", max_length=1000)
    value: str = Field(default="", max_length=500)
    seconds: int = Field(default=0, ge=0, le=86400)

    @model_validator(mode="after")
    def validate_action(self):
        from nexa.templates import validate_template

        if self.type.startswith("SEND_"):
            validate_template(self.template)
            if not self.template.strip():
                raise ValueError("template_required")
        if self.type in {"ADD_TAG", "INTERNAL_NOTE"} and not self.value.strip():
            raise ValueError("action_value_required")
        if self.type == "ADD_TAG" and len(self.value) > 60:
            raise ValueError("tag_too_long")
        return self


class FlowInput(StrictInput):
    version: Literal[2] = 2
    actions: list[ActionInput] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def one_reply(self):
        # A second message requires a new inbound messaging event and its own flow.
        if sum(a.type.startswith("SEND_") for a in self.actions) > 1:
            raise ValueError("one_message_per_trigger")
        return self


class CommentInput(StrictInput):
    account_id: str
    media_id: str
    sender: str = Field(default="sample-customer", min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    event_id: str = Field(min_length=1, max_length=100)
    occurred_at: AwareDatetime | None = None
    sample_rate: Rate | None = None


def aware(value: datetime) -> datetime:
    from datetime import UTC

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
