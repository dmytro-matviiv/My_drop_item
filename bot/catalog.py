"""Кеш каталогів у пам'яті, індекс пошуку за артикулом і фонове оновлення."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .mydrop import MyDropAuthError, MyDropClient, MyDropError, RemoteVendor
from .storage import Storage, VendorRecord

log = logging.getLogger(__name__)

PARTIAL_LIMIT = 5
PAUSE_BETWEEN_VENDORS = 2  # секунд

_LOOSE_RE = re.compile(r"[.\-_/]")


def normalize_sku(value: Any) -> str:
    """Регістр і пробіли не важливі; крапки, дефіси тощо зберігаються."""
    if value is None:
        return ""
    return "".join(str(value).split()).lower()


def loose_sku(value: Any) -> str:
    """Ще м'якша форма лише для часткового пошуку: без . - _ /"""
    return _LOOSE_RE.sub("", normalize_sku(value))


def sku_variants(sku: Any, prefix: str | None) -> set[str]:
    """Нормалізований sku і варіанти з/без префікса постачальника."""
    norm = normalize_sku(sku)
    if not norm:
        return set()
    variants = {norm}
    p = normalize_sku(prefix)
    if p:
        if norm.startswith(p) and len(norm) > len(p):
            variants.add(norm[len(p):])
        else:
            variants.add(p + norm)
    return variants


@dataclass(frozen=True)
class Ref:
    link_id: int
    product_id: int
    size_id: int | None = None


@dataclass
class Match:
    vendor: VendorRecord
    product: dict[str, Any]
    size_id: int | None = None  # розмір, чий артикул збігся


@dataclass
class SearchResult:
    kind: Literal["product", "size", "partial", "none"]
    query: str
    matches: list[Match] = field(default_factory=list)
    total: int = 0  # для часткового пошуку: скільки всього знайшлося


class SearchIndex:
    def __init__(self, vendors: dict[int, VendorRecord], catalogs: dict[int, list[dict[str, Any]]]):
        self.vendors = vendors
        self.products: dict[tuple[int, int], dict[str, Any]] = {}
        self.by_product: dict[str, list[Ref]] = {}
        self.by_size: dict[str, list[Ref]] = {}

        for link_id, vendor in vendors.items():
            for product in catalogs.get(link_id) or []:
                try:
                    pid = int(product["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                self.products[(link_id, pid)] = product
                for key in sku_variants(product.get("sku"), vendor.sku_prefix):
                    self.by_product.setdefault(key, []).append(Ref(link_id, pid))
                for size in product.get("sizes") or []:
                    if not size.get("sku") or size.get("id") is None:
                        continue
                    ref = Ref(link_id, pid, int(size["id"]))
                    for key in sku_variants(size["sku"], vendor.sku_prefix):
                        self.by_size.setdefault(key, []).append(ref)

    def _to_matches(self, refs: list[Ref]) -> list[Match]:
        seen: set[tuple[int, int]] = set()
        matches = []
        for ref in refs:
            key = (ref.link_id, ref.product_id)
            if key in seen or key not in self.products:
                continue
            seen.add(key)
            matches.append(Match(self.vendors[ref.link_id], self.products[key], ref.size_id))
        return matches

    def get(self, link_id: int, product_id: int, size_id: int | None = None) -> Match | None:
        product = self.products.get((link_id, product_id))
        if product is None:
            return None
        return Match(self.vendors[link_id], product, size_id)

    def search(self, query: str) -> SearchResult:
        q = normalize_sku(query)
        if not q:
            return SearchResult("none", query)

        if q in self.by_product:
            return SearchResult("product", query, self._to_matches(self.by_product[q]))
        if q in self.by_size:
            return SearchResult("size", query, self._to_matches(self.by_size[q]))

        q_loose = loose_sku(q)
        found: list[tuple[int, str, Ref]] = []
        for index in (self.by_product, self.by_size):
            for key, refs in index.items():
                if q in key or (q_loose and q_loose in loose_sku(key)):
                    found.extend((len(key), key, ref) for ref in refs)
        found.sort(key=lambda item: (item[0], item[1]))
        matches = self._to_matches([ref for _, _, ref in found])
        if not matches:
            return SearchResult("none", query)
        return SearchResult("partial", query, matches[:PARTIAL_LIMIT], total=len(matches))


@dataclass
class RefreshResult:
    vendor: VendorRecord
    ok: bool
    count: int = 0
    error: str | None = None
    auth_error: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CatalogManager:
    def __init__(
        self,
        storage: Storage,
        client: MyDropClient,
        on_auth_error: Callable[[MyDropAuthError], Awaitable[None]] | None = None,
    ):
        self.storage = storage
        self.client = client
        self.on_auth_error = on_auth_error
        self.vendors: dict[int, VendorRecord] = {}
        self.catalogs: dict[int, list[dict[str, Any]]] = {}
        self.index = SearchIndex({}, {})
        self._refresh_lock = asyncio.Lock()
        self._auth_notified = False

    # ---------- стан ----------

    def load_from_disk(self) -> None:
        for vendor in self.storage.load_vendors():
            self.vendors[vendor.link_id] = vendor
            products = self.storage.load_catalog(vendor.link_id)
            if products is not None:
                self.catalogs[vendor.link_id] = products
        self._rebuild()
        log.info("З диска завантажено %d постачальників, %d товарів",
                 len(self.vendors), sum(len(p) for p in self.catalogs.values()))

    def _rebuild(self) -> None:
        self.index = SearchIndex(dict(self.vendors), dict(self.catalogs))

    def _save_vendors(self) -> None:
        self.storage.save_vendors(list(self.vendors.values()))

    def product_count(self, link_id: int) -> int:
        return len(self.catalogs.get(link_id) or [])

    def search(self, query: str) -> SearchResult:
        return self.index.search(query)

    def find_by_slug(self, slug: str) -> VendorRecord | None:
        slug = slug.lower()
        return next((v for v in self.vendors.values() if v.public_url.lower() == slug), None)

    # ---------- додавання / видалення ----------

    async def add_vendor(self, remote: RemoteVendor) -> RefreshResult:
        record = VendorRecord(
            link_id=remote.link_id,
            vendor_id=remote.vendor_id,
            name=remote.name,
            public_url=remote.public_url,
            sku_prefix=remote.sku_prefix,
            added_at=utc_now_iso(),
        )
        self.vendors[record.link_id] = record
        self._save_vendors()
        result = await self.refresh_vendor(record)
        if not result.ok:
            self._rebuild()
        return result

    def remove_vendor(self, link_id: int) -> VendorRecord | None:
        record = self.vendors.pop(link_id, None)
        self.catalogs.pop(link_id, None)
        self._save_vendors()
        self.storage.delete_catalog(link_id)
        self._rebuild()
        return record

    # ---------- оновлення ----------

    async def refresh_vendor(self, record: VendorRecord) -> RefreshResult:
        try:
            products = await self.client.get_catalog(record.link_id)
        except MyDropAuthError as e:
            log.error("МійДроп відхилив ключ (%s): %s", e.code, e.message)
            await self._report_auth_error(e)
            return RefreshResult(record, False, error=e.message, auth_error=True)
        except MyDropError as e:
            log.error("Не вдалося оновити каталог %s: %s", record.name, e)
            return RefreshResult(record, False, error=str(e))

        self._auth_notified = False
        if record.link_id not in self.vendors:  # видалили, поки завантажували
            return RefreshResult(record, False, error="постачальника видалено")
        self.catalogs[record.link_id] = products
        record.updated_at = utc_now_iso()
        try:
            self.storage.save_catalog(record.link_id, products)
            self._save_vendors()
        except OSError:
            log.exception("Не вдалося зберегти каталог %s на диск", record.name)
        self._rebuild()
        log.info("Каталог %s оновлено: %d товарів", record.name, len(products))
        return RefreshResult(record, True, count=len(products))

    @property
    def refreshing(self) -> bool:
        return self._refresh_lock.locked()

    async def refresh_all(self) -> list[RefreshResult]:
        async with self._refresh_lock:
            results = []
            for i, record in enumerate(list(self.vendors.values())):
                if i:
                    await asyncio.sleep(PAUSE_BETWEEN_VENDORS)
                if record.link_id not in self.vendors:
                    continue
                result = await self.refresh_vendor(record)
                results.append(result)
                if result.auth_error:
                    break  # з невалідним ключем інші теж не завантажаться
            return results

    async def run_periodic(self, minutes: int) -> None:
        while True:
            try:
                await self.refresh_all()
            except Exception:
                log.exception("Помилка фонового оновлення")
            await asyncio.sleep(minutes * 60)

    async def _report_auth_error(self, error: MyDropAuthError) -> None:
        if self._auth_notified:
            return
        self._auth_notified = True
        if self.on_auth_error is not None:
            try:
                await self.on_auth_error(error)
            except Exception:
                log.exception("Не вдалося повідомити про помилку ключа")
