"""Доступ: адміністратори та схвалені ними користувачі. Решта надсилає запит."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from .access import AccessControl
from .keyboards import CB_APPROVE, CB_REJECT, inline

log = logging.getLogger(__name__)

NO_ACCESS = "⛔ Немає доступу."


def user_name(user: User) -> str:
    return " ".join(p for p in (user.first_name, user.last_name) if p) or str(user.id)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, access: AccessControl):
        self.access = access

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            return None
        data["is_admin"] = self.access.is_admin(user.id)
        if self.access.is_allowed(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(NO_ACCESS, show_alert=True)
            return None
        if not isinstance(event, Message) or event.chat.type != "private":
            return None

        id_line = f"🆔 Ваш Telegram ID: <code>{user.id}</code>"
        status = self.access.status(user.id)
        if status == "rejected":
            await event.answer(f"{NO_ACCESS}\n\n{id_line}")
            return None
        if status == "pending":
            await event.answer(f"⏳ Ваш запит на доступ ще розглядається адміністратором.\n\n{id_line}")
            return None

        text = "👋 Привіт! Це бот пошуку товарів за артикулом у постачальників МійДроп.\n\n"
        if not self.access.admin_ids:
            text += ("Адміністратора ще не налаштовано. Якщо це ваш бот, впишіть ID нижче "
                     "у змінну ADMIN_IDS і перезапустіть бота.")
        else:
            self.access.request(user.id, user_name(user), user.username)
            log.info("Новий запит на доступ від %s", user.id)
            await self._notify_admins(data["bot"], user)
            text += "📨 Запит на доступ надіслано адміністратору. Я напишу, щойно його схвалять."
        await event.answer(f"{text}\n\n{id_line}")
        return None

    async def _notify_admins(self, bot: Bot, user: User) -> None:
        username = f" (@{escape(user.username)})" if user.username else ""
        text = (
            "🔔 <b>Запит на доступ</b>\n"
            f"{escape(user_name(user))}{username}\n"
            f"ID: <code>{user.id}</code>"
        )
        markup = inline([[("✅ Дозволити", f"{CB_APPROVE}{user.id}"), ("❌ Відхилити", f"{CB_REJECT}{user.id}")]])
        for admin_id in self.access.admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=markup)
            except Exception:
                log.warning("Не вдалося надіслати запит адміністратору %s", admin_id)
