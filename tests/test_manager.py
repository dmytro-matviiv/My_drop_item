"""Додавання, видалення, оновлення й збереження без мережі (фейковий клієнт)."""

import asyncio

from bot.catalog import CatalogManager
from bot.mydrop import MyDropAuthError, MyDropError, RemoteVendor
from bot.storage import Storage

from .conftest import load_products

SEGEDA = RemoteVendor(522473, 33899, "Segeda_shop", "segeda_shop", None)
DOFF = RemoteVendor(522501, 5108, "DoFF TEAM", "doff_team", None)


class FakeClient:
    def __init__(self):
        self.catalogs = {SEGEDA.link_id: load_products("segeda_shop"), DOFF.link_id: load_products("doff_team")}
        self.fail: Exception | None = None

    async def get_catalog(self, link_id):
        if self.fail:
            raise self.fail
        return [dict(p) for p in self.catalogs[link_id]]


def make(tmp_path, client=None, notes=None):
    async def on_auth(e):
        notes.append(e.code)
    return CatalogManager(Storage(tmp_path), client or FakeClient(), on_auth if notes is not None else None)


def test_add_search_remove(tmp_path):
    async def scenario():
        manager = make(tmp_path)
        result = await manager.add_vendor(SEGEDA)
        assert result.ok and result.count == 6
        assert manager.search("art1.01").kind == "product"
        assert manager.find_by_slug("SEGEDA_SHOP").link_id == SEGEDA.link_id

        await manager.add_vendor(DOFF)
        assert len(manager.search("dup-1").matches) == 2

        manager.remove_vendor(SEGEDA.link_id)
        assert manager.search("art1.01").kind == "none"
        assert len(manager.search("dup-1").matches) == 1
    asyncio.run(scenario())


def test_persistence_after_restart(tmp_path):
    async def scenario():
        manager = make(tmp_path)
        await manager.add_vendor(SEGEDA)
        await manager.add_vendor(DOFF)
        manager.remove_vendor(DOFF.link_id)
    asyncio.run(scenario())

    restarted = make(tmp_path)
    restarted.load_from_disk()
    assert list(restarted.vendors) == [SEGEDA.link_id]
    assert restarted.vendors[SEGEDA.link_id].updated_at
    assert restarted.search("art1.01").kind == "product"
    assert not (tmp_path / "catalogs" / f"{DOFF.link_id}.json").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_refresh_picks_up_new_products(tmp_path):
    async def scenario():
        client = FakeClient()
        manager = make(tmp_path, client)
        await manager.add_vendor(SEGEDA)
        assert manager.search("NEW-1").kind == "none"
        client.catalogs[SEGEDA.link_id].append({"id": 1, "title": "Новинка", "sku": "NEW-1", "sizes": []})
        results = await manager.refresh_all()
        assert results[0].ok and results[0].count == 7
        assert manager.search("NEW-1").kind == "product"
    asyncio.run(scenario())


def test_failed_refresh_keeps_old_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.catalog.PAUSE_BETWEEN_VENDORS", 0)

    async def scenario():
        client = FakeClient()
        notes = []
        manager = make(tmp_path, client, notes)
        await manager.add_vendor(SEGEDA)
        await manager.add_vendor(DOFF)

        client.fail = MyDropError("503")
        results = await manager.refresh_all()
        assert [r.ok for r in results] == [False, False]
        assert manager.search("art1.01").kind == "product"

        client.fail = MyDropAuthError("api_key_invalid", "Ключ невалідний")
        results = await manager.refresh_all()
        await manager.refresh_all()
        assert len(results) == 1  # після 401 решту не смикаємо
        assert notes == ["api_key_invalid"]  # повідомили один раз
        assert manager.search("art1.01").kind == "product"

        client.fail = None
        await manager.refresh_all()
        client.fail = MyDropAuthError("subscription_expired", "Підписка закінчилась")
        await manager.refresh_all()
        assert notes == ["api_key_invalid", "subscription_expired"]
    asyncio.run(scenario())
