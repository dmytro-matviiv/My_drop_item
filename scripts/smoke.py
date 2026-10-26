"""Smoke-тест на реальних ключах з .env: python -m scripts.smoke [артикул]

Перевіряє токен бота, список постачальників МійДроп і пошук артикулу
в каталогах усіх підключених постачальників. Нічого не записує на диск.
"""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot

from bot.catalog import SearchIndex
from bot.config import load_config
from bot.mydrop import MyDropClient, product_url
from bot.storage import VendorRecord


async def main(sku: str) -> int:
    config = load_config()

    bot = Bot(config.bot_token)
    try:
        me = await bot.get_me()
        print(f"Telegram: бот @{me.username} OK")
    finally:
        await bot.session.close()

    client = MyDropClient(config.mydrop_api_key)
    try:
        remote = await client.get_vendors()
        print(f"МійДроп: підключено постачальників: {len(remote)}")
        vendors, catalogs = {}, {}
        for v in remote:
            print(f"  {v.link_id:>8}  {v.name}  ({v.public_url}), skuPrefix={v.sku_prefix!r}")
            products = await client.get_catalog(v.link_id)
            print(f"           каталог: {len(products)} товарів")
            vendors[v.link_id] = VendorRecord(v.link_id, v.vendor_id, v.name, v.public_url, v.sku_prefix)
            catalogs[v.link_id] = products
    finally:
        await client.close()

    result = SearchIndex(vendors, catalogs).search(sku)
    print(f"Пошук '{sku}': {result.kind}")
    for m in result.matches:
        print(f"  {m.product.get('title')} | {m.vendor.name} | {product_url(m.vendor.public_url, m.product['id'])}")
    return 0 if result.kind in ("product", "size") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "art1.01")))
