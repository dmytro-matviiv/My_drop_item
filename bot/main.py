"""Точка входу: python -m bot.main"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from html import escape

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .access import AccessControl
from .catalog import CatalogManager
from .config import ConfigError, load_config
from .handlers import build_router
from .middlewares import AccessMiddleware
from .mydrop import MyDropAuthError, MyDropClient
from .sheets import SheetsClient
from .storage import Storage

log = logging.getLogger("bot")


async def run() -> None:
    config = load_config()
    if not config.admin_ids:
        log.warning("ADMIN_IDS порожній: нікому схвалювати запити на доступ. "
                    "Надішліть боту /start, щоб дізнатися свій ID")

    if os.getenv("RAILWAY_ENVIRONMENT") and not os.getenv("RAILWAY_VOLUME_MOUNT_PATH"):
        log.warning("До сервісу не підключено Volume: постачальники й користувачі зникнуть після редеплою")

    bot = Bot(
        config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    client = MyDropClient(config.mydrop_api_key)
    storage = Storage(config.data_dir)
    access = AccessControl(storage, config.admin_ids, config.allowed_users)

    async def notify_auth_error(error: MyDropAuthError) -> None:
        text = (
            "⚠️ МійДроп відхилив API-ключ, каталоги не оновлюються.\n"
            f"Причина: {escape(error.message)} (<code>{escape(error.code)}</code>)\n"
            "Перевірте MYDROP_API_KEY і підписку. Пошук працює по останніх збережених даних."
        )
        for user_id in config.admin_ids:
            try:
                await bot.send_message(user_id, text)
            except Exception:
                log.warning("Не вдалося надіслати сповіщення користувачу %s", user_id)

    sheets = SheetsClient()
    manager = CatalogManager(storage, client, on_auth_error=notify_auth_error, sheets=sheets)
    manager.load_from_disk()

    dp = Dispatcher(manager=manager, client=client, config=config, access=access)
    middleware = AccessMiddleware(access)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.include_router(build_router())

    refresh_task = asyncio.create_task(manager.run_periodic(config.refresh_minutes))
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Почати / мій ID"),
                                   BotCommand(command="help", description="Як користуватися")])
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("Бот запущено, оновлення каталогів кожні %d хв, DATA_DIR=%s",
                 config.refresh_minutes, config.data_dir.resolve())
        await dp.start_polling(bot)
    finally:
        refresh_task.cancel()
        await client.close()
        await sheets.close()
        await bot.session.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # кирилиця в логах на Windows
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run())
    except ConfigError as e:
        log.error("Помилка налаштувань: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
