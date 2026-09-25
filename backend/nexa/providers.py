import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from nexa.config import settings
from nexa.models import Account
from nexa.security import decrypt


class DeliveryUnknown(Exception):
    """The remote service may have accepted the message; never retry automatically."""


class DeliveryRejected(Exception):
    pass


class RateLimited(DeliveryRejected):
    def __init__(self, retry_after=60):
        self.retry_after = min(max(int(retry_after), 1), 3600)
        super().__init__("rate_limited")


@dataclass(frozen=True)
class Receipt:
    message_id: str


class Provider(Protocol):
    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt: ...
    def private_reply(self, account: Account, comment_id: str, text: str, key: str) -> Receipt: ...


class MockInstagramProvider:
    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt:
        if not settings().mock_mode:
            raise DeliveryRejected("mock_disabled")
        return Receipt("mock:" + key)

    def private_reply(self, account, comment_id, text, key):
        return self.send(account, comment_id, text, key)


class InstagramProvider:
    def read(self, account, path, params):
        if not account.credential:
            raise DeliveryRejected("credentials_missing")
        if not re.fullmatch(r"[0-9]+(?:/media)?", path):
            raise DeliveryRejected("invalid_provider_id")
        try:
            response = httpx.get(
                f"https://graph.instagram.com/{settings().meta_api_version}/{path}",
                headers={"Authorization": "Bearer " + decrypt(account.credential)},
                params=params,
                timeout=15,
            )
            if response.status_code == 429:
                raise RateLimited()
            if not response.is_success:
                code = response.json().get("error", {}).get("code")
                raise DeliveryRejected(
                    "reconnect_required"
                    if code == 190
                    else "permission_required"
                    if code in {10, 200}
                    else "provider_unavailable"
                )
            return response.json()
        except (httpx.HTTPError, ValueError, AttributeError):
            raise DeliveryRejected("provider_unavailable") from None

    def list_media(self, account, cursor=None):
        params = {
            "fields": "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp",
            "limit": 25,
        }
        if cursor:
            params["after"] = cursor
        return self.read(account, account.external_id + "/media", params)

    def comment(self, account, comment_id):
        data = self.read(account, comment_id, {"fields": "id,timestamp,media,from"})
        try:
            data["occurred_at"] = datetime.fromisoformat(data["timestamp"])
            return data
        except (KeyError, ValueError, TypeError):
            raise DeliveryRejected("comment_timestamp_unavailable") from None

    def send(self, account: Account, recipient: str, text: str, key: str) -> Receipt:
        return self._send(account, {"id": recipient}, text)

    def private_reply(self, account: Account, comment_id: str, text: str, key: str) -> Receipt:
        return self._send(account, {"comment_id": comment_id}, text)

    def _send(self, account, recipient, text):
        if not account.credential:
            raise DeliveryRejected("credentials_missing")
        try:
            response = httpx.post(
                f"https://graph.instagram.com/{settings().meta_api_version}/{account.external_id}/messages",
                headers={"Authorization": "Bearer " + decrypt(account.credential)},
                json={"recipient": recipient, "message": {"text": text}},
                timeout=15,
            )
        except httpx.HTTPError:
            raise DeliveryUnknown("delivery_unknown") from None
        if response.status_code >= 500:
            raise DeliveryUnknown("delivery_unknown")
        if not response.is_success:
            try:
                code = response.json().get("error", {}).get("code")
            except (ValueError, AttributeError):
                code = None
            if response.status_code == 429 or code in {4, 17, 32, 613, 80002}:
                delay = response.headers.get("Retry-After", "60")
                raise RateLimited(int(delay) if delay.isdigit() else 60)
            if code == 190:
                raise DeliveryRejected("reconnect_required")
            if code in {10, 200}:
                raise DeliveryRejected("permission_required")
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
