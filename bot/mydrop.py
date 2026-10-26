"""Клієнт API МійДроп (версія для дропшиперів)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

BASE_URL = "https://backend.mydrop.com.ua"
SITE_URL = "https://mydrop.com.ua"

RETRIES = 3
RETRY_PAUSE = 5  # секунд, множиться на номер спроби
MAX_PAGES = 100


class MyDropError(Exception):
    """Будь-яка помилка API: мережа, 5xx, некоректна відповідь."""


class MyDropAuthError(MyDropError):
    """401: невалідний ключ, закінчилась підписка тощо."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RemoteVendor:
    link_id: int  # id зв'язки дропшипер ↔ постачальник, потрібен для каталогу
    vendor_id: int
    name: str
    public_url: str
    sku_prefix: str | None


def product_url(public_url: str, product_id: int | str) -> str:
    return f"{SITE_URL}/{public_url}/p/{product_id}"


def parse_vendor(item: dict[str, Any]) -> RemoteVendor | None:
    vendor = item.get("vendor") or {}
    try:
        return RemoteVendor(
            link_id=int(item["id"]),
            vendor_id=int(vendor.get("id") or 0),
            name=str(vendor.get("name") or vendor.get("publicUrl") or item["id"]),
            public_url=str(vendor.get("publicUrl") or "").strip(),
            sku_prefix=item.get("skuPrefix") or None,
        )
    except (KeyError, TypeError, ValueError):
        log.warning("Пропускаю постачальника з неочікуваним форматом: %r", item)
        return None


class MyDropClient:
    def __init__(self, api_key: str, timeout: float = 60):
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=BASE_URL,
                timeout=self._timeout,
                headers={"X-API-KEY": self._api_key, "Accept": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        session = await self._get_session()
        last_error: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                async with session.get(path, params=params) as resp:
                    if resp.status == 401:
                        raise await _auth_error(resp)
                    if 400 <= resp.status < 500:
                        # повтор тут не допоможе
                        text = (await resp.text())[:300]
                        raise _NoRetry(f"МійДроп відповів {resp.status}: {text}")
                    if resp.status >= 500:
                        raise MyDropError(f"Сервер МійДроп відповів {resp.status}")
                    return await resp.json(content_type=None)
            except MyDropAuthError:
                raise
            except _NoRetry as e:
                raise MyDropError(str(e)) from None
            except (aiohttp.ClientError, asyncio.TimeoutError, MyDropError, ValueError) as e:
                last_error = e
                log.warning("GET %s: спроба %d/%d не вдалася: %r", path, attempt, RETRIES, e)
                if attempt < RETRIES:
                    await asyncio.sleep(RETRY_PAUSE * attempt)
        raise MyDropError(f"Не вдалося отримати {path}: {last_error!r}")

    async def get_vendors(self) -> list[RemoteVendor]:
        """Усі підключені постачальники (з урахуванням сторінок)."""
        vendors: list[RemoteVendor] = []
        page = 1
        while page <= MAX_PAGES:
            data = await self._get_json("/dropshipper/api/dropshipper_vendors", params={"page": page})
            if not isinstance(data, dict):
                raise MyDropError("Неочікувана відповідь списку постачальників")
            results = data.get("results") or []
            for item in results:
                vendor = parse_vendor(item)
                if vendor is not None:
                    vendors.append(vendor)
            meta = data.get("meta") or {}
            try:
                current = int(meta.get("currentPage") or page)
                total = int(meta.get("totalPages") or 1)
            except (TypeError, ValueError):
                break
            if not results or current >= total:
                break
            page = current + 1
        # на випадок, якщо API ігнорує параметр page і віддає те саме
        unique = {v.link_id: v for v in vendors}
        return list(unique.values())

    async def get_catalog(self, link_id: int) -> list[dict[str, Any]]:
        data = await self._get_json(f"/dropshipper/api/export/dropshipper_vendors/{link_id}/products/json")
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise MyDropError(f"Неочікуваний формат каталогу {link_id}")
        return data["products"]


class _NoRetry(Exception):
    pass


async def _auth_error(resp: aiohttp.ClientResponse) -> MyDropAuthError:
    code, message = "unauthorized", "Невалідний API-ключ"
    try:
        body = await resp.json(content_type=None)
        code = body.get("code") or code
        message = body.get("message_ua") or body.get("message") or message
    except Exception:
        pass
    return MyDropAuthError(code, message)
