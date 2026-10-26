"""Доступ лише для ALLOWED_USERS."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

log = logging.getLogger(__name__)

NO_ACCESS = "⛔ Немає доступу."


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_users: frozenset[int]):
        self.allowed_users = allowed_users

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        allowed = user is not None and user.id in self.allowed_users
        data["is_allowed"] = allowed
        if allowed:
            return await handler(event, data)

        # /start показуємо всім, щоб людина могла дізнатися свій ID
        if isinstance(event, Message) and (event.text or "").startswith("/start"):
            return await handler(event, data)

        log.info("Відмовлено в доступі користувачу %s", user.id if user else None)
        if isinstance(event, Message):
            await event.answer(NO_ACCESS)
        elif isinstance(event, CallbackQuery):
            await event.answer(NO_ACCESS, show_alert=True)
        return None
