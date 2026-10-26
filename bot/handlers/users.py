"""Керування доступом (лише для адміністраторів)."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from ..access import AccessControl
from ..keyboards import BTN_USERS, CB_APPROVE, CB_REJECT, inline, main_menu, short

log = logging.getLogger(__name__)
router = Router()


class IsAdmin(Filter):
    async def __call__(self, event, is_admin: bool = False) -> bool:
        return is_admin


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _users_view(access: AccessControl):
    lines = ["👥 <b>Користувачі</b>", ""]
    rows = []
    sections = (
        ("approved", "✅ Мають доступ:", "🚫 Забрати: {}", CB_REJECT),
        ("pending", "⏳ Чекають на схвалення:", "✅ Дозволити: {}", CB_APPROVE),
        ("rejected", "⛔ Відхилені:", "✅ Дозволити: {}", CB_APPROVE),
    )
    for status, title, button, prefix in sections:
        ids = access.listed(status)
        if not ids:
            continue
        lines.append(title)
        for uid in ids:
            lines.append(f"• {escape(access.label(uid))}, <code>{uid}</code>")
            rows.append([(button.format(short(access.label(uid), 35)), f"{prefix}{uid}")])
        lines.append("")
    if not rows:
        lines.append("Поки що ніхто не просив доступу. Перешліть людині посилання на бота: "
                     "після /start вам прийде запит із кнопками.")
    if access.preapproved:
        lines.append("Також доступ мають ID зі змінної ALLOWED_USERS: "
                     + ", ".join(f"<code>{uid}</code>" for uid in sorted(access.preapproved)))
    return "\n".join(lines).strip(), (inline(rows) if rows else None)


@router.message(F.text == BTN_USERS)
async def list_users(message: Message, access: AccessControl) -> None:
    text, markup = _users_view(access)
    await message.answer(text, reply_markup=markup)


async def _tell_user(bot: Bot, user_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(user_id, text, **kwargs)
    except Exception:
        log.warning("Не вдалося написати користувачу %s", user_id)


@router.callback_query(F.data.startswith(CB_APPROVE))
async def approve(call: CallbackQuery, access: AccessControl, bot: Bot) -> None:
    user_id = int(call.data.removeprefix(CB_APPROVE))
    was = access.status(user_id)
    access.approve(user_id)
    await call.answer("Доступ надано")
    if was != "approved":
        await _tell_user(bot, user_id, "✅ Вам надали доступ до бота. Надішліть артикул, щоб знайти товар.",
                         reply_markup=main_menu(access.is_admin(user_id)))
    await _refresh(call, access, f"✅ Доступ надано: {escape(access.label(user_id))}")


@router.callback_query(F.data.startswith(CB_REJECT))
async def reject(call: CallbackQuery, access: AccessControl, bot: Bot) -> None:
    user_id = int(call.data.removeprefix(CB_REJECT))
    if access.is_admin(user_id):
        await call.answer("Адміністратора не можна заблокувати", show_alert=True)
        return
    was = access.status(user_id)
    access.reject(user_id)
    await call.answer("Готово")
    if was == "approved":
        await _tell_user(bot, user_id, "⛔ Ваш доступ до бота скасовано.")
    await _refresh(call, access, f"⛔ Без доступу: {escape(access.label(user_id))}")


async def _refresh(call: CallbackQuery, access: AccessControl, note: str) -> None:
    """Запит від нового користувача: змінюємо сам запит; список: перемальовуємо список."""
    if call.message is None:
        return
    is_request = "Запит на доступ" in (call.message.text or "")
    if is_request:
        text, markup = note, None
    else:
        text, markup = _users_view(access)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass
