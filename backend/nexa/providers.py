from dataclasses import dataclass
from typing import Protocol

import httpx

from nexa.config import settings
from nexa.models import Account
from nexa.security import decrypt


class DeliveryUnknown(Exception):
    """The remote service may have accepted the message; never retry automatically."""


class DeliveryRejected(Exception):
    pass


@dataclass(frozen=True)
class Receipt:
    message_id: str


class Provider(Protocol):
    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt: ...


class MockInstagramProvider:
    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt:
        if not settings().mock_mode:
            raise DeliveryRejected("mock_disabled")
        return Receipt("mock:" + key)


class InstagramProvider:
    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt:
        if not account.credential:
            raise DeliveryRejected("credentials_missing")
        try:
            response = httpx.post(
                f"https://graph.instagram.com/{settings().meta_api_version}/{account.external_id}/messages",
                headers={"Authorization": "Bearer " + decrypt(account.credential)},
                json={"recipient": {"id": recipient}, "message": {"text": text}},
                timeout=15,
            )
        except httpx.HTTPError:
            raise DeliveryUnknown("delivery_unknown") from None
        if response.status_code >= 500:
            raise DeliveryUnknown("delivery_unknown")
        if not response.is_success:
            raise DeliveryRejected("provider_rejected")
        try:
            return Receipt(str(response.json()["message_id"]))
        except (ValueError, KeyError):
            raise DeliveryUnknown("delivery_unknown") from None


PROVIDERS: dict[str, Provider] = {"instagram_mock": MockInstagramProvider(), "instagram": InstagramProvider()}


def provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise DeliveryRejected("provider_unsupported")
    return PROVIDERS[name]
