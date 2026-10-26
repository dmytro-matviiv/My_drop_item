"""Пошук товару за артикулом."""

from __future__ import annotations

import logging
from html import escape

import aiohttp
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..catalog import CatalogManager, Match
from ..config import Config
from ..keyboards import CB_SHOW, inline, short
from ..report import build_report, first_image, visible_length

log = logging.getLogger(__name__)
router = Router()

CAPTION_LIMIT = 1024
MAX_REPORTS = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024


async def _download(url: str) -> bytes | None:
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.content.read(MAX_IMAGE_BYTES + 1)
                return data if 0 < len(data) <= MAX_IMAGE_BYTES else None
    except Exception:
        log.warning("Не вдалося завантажити фото %s", url, exc_info=True)
        return None


async def send_report(message: Message, match: Match, tz: str) -> None:
    text = build_report(match, tz)
    photo_url = first_image(match.product)
    if photo_url:
        caption = text if visible_length(text) <= CAPTION_LIMIT else None
        sent = False
        try:
            await message.answer_photo(photo_url, caption=caption)
            sent = True
        except TelegramAPIError:
            # Telegram не зміг сам забрати фото: завантажуємо й надсилаємо файлом
            data = await _download(photo_url)
            if data:
                try:
                    await message.answer_photo(BufferedInputFile(data, "photo.jpg"), caption=caption)
                    sent = True
                except TelegramAPIError:
                    log.warning("Telegram не прийняв фото %s", photo_url, exc_info=True)
        if sent and caption is not None:
            return
    await message.answer(text)


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer("Невідома команда. Надішліть артикул або скористайтеся меню.")


@router.message(F.text)
async def search(message: Message, manager: CatalogManager, config: Config) -> None:
    query = (message.text or "").strip()
    if not manager.vendors:
        await message.answer("Ви ще не додали жодного постачальника. Натисніть «➕ Додати постачальника».")
        return

    result = manager.search(query)
    if result.kind == "none":
        await message.answer(f"❌ Артикул <code>{escape(query)}</code> не знайдено у ваших постачальників.")
        return

    if result.kind == "partial":
        rows = []
        for m in result.matches:
            size_id = m.size_id or 0
            label = f"{m.product.get('sku') or '—'} · {m.product.get('title') or ''} · {m.vendor.name}"
            rows.append([(short(label, 60), f"{CB_SHOW}{m.vendor.link_id}:{m.product.get('id')}:{size_id}")])
        more = f" (показано {len(result.matches)} з {result.total})" if result.total > len(result.matches) else ""
        await message.answer(
            f"🔍 Точного збігу для <code>{escape(query)}</code> немає. Схожі товари{more}:",
            reply_markup=inline(rows),
        )
        return

    for match in result.matches[:MAX_REPORTS]:
        await send_report(message, match, config.timezone)
    if len(result.matches) > MAX_REPORTS:
        await message.answer(f"…і ще {len(result.matches) - MAX_REPORTS} товарів з таким артикулом.")


@router.callback_query(F.data.startswith(CB_SHOW))
async def show_partial(call: CallbackQuery, manager: CatalogManager, config: Config) -> None:
    try:
        link_id, product_id, size_id = (int(x) for x in call.data.removeprefix(CB_SHOW).split(":"))
    except ValueError:
        await call.answer()
        return
    match = manager.index.get(link_id, product_id, size_id or None)
    if match is None:
        await call.answer("Цього товару вже немає в каталозі.", show_alert=True)
        return
    await call.answer()
    await send_report(call.message, match, config.timezone)
