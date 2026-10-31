"""Керування постачальниками та ручне оновлення каталогів."""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from ..catalog import CatalogManager
from ..config import Config
from ..keyboards import (
    BTN_ADD,
    BTN_LIST,
    BTN_REFRESH,
    CB_ADD,
    CB_DEL,
    CB_DEL_OK,
    CB_LIST,
    CB_PICK,
    inline,
    plural_products,
    short,
)
from ..links import extract_product_id, extract_slug, is_mydrop_link
from ..mydrop import MyDropAuthError, MyDropClient, MyDropError, RemoteVendor
from ..report import format_updated
from ..sheets import is_sheet_link, parse_sheet_link
from .search import send_report

log = logging.getLogger(__name__)
router = Router()


async def _fetch_remote(client: MyDropClient) -> tuple[list[RemoteVendor] | None, str | None]:
    """Список підключених постачальників або текст помилки для користувача."""
    try:
        return await client.get_vendors(), None
    except MyDropAuthError as e:
        return None, f"❌ МійДроп відхилив API-ключ: {escape(e.message)}"
    except MyDropError:
        log.exception("Не вдалося отримати список постачальників")
        return None, "❌ Не вдалося зв'язатися з МійДроп. Спробуйте трохи пізніше."


async def _add(manager: CatalogManager, remote: RemoteVendor, status: Message) -> bool:
    await status.edit_text(f"⏳ Додаю {escape(remote.name)}, завантажую каталог…")
    result = await manager.add_vendor(remote)
    if result.ok:
        await status.edit_text(f"✅ Додано {escape(remote.name)} — {plural_products(result.count)}")
    else:
        await status.edit_text(
            f"⚠️ Додано {escape(remote.name)}, але каталог поки не завантажився "
            f"({escape(result.error or 'помилка')}). Спробую ще раз під час наступного оновлення."
        )
    return result.ok


async def _show_product(message: Message, manager: CatalogManager, config: Config,
                        link_id: int, product_id: int) -> None:
    match = manager.index.get(link_id, product_id)
    if match is None:
        await message.answer("❌ Цього товару немає в каталозі постачальника (можливо, його вже прибрали).")
        return
    await send_report(message, match, config.timezone)


# ---------- додавання ----------

@router.message(F.text == BTN_ADD)
async def add_prompt(message: Message) -> None:
    await message.answer(
        "Надішліть посилання на магазин постачальника на МійДроп, наприклад:\n"
        "<code>https://mydrop.com.ua/segeda_shop</code>\n"
        "Підійде будь-яке посилання: на магазин, категорію чи товар.\n\n"
        "📄 Або посилання на Google-таблицю постачальника з колонкою «Код» / «Артикул». "
        "Таблиця має бути відкрита для всіх, хто має посилання.",
        reply_markup=inline([[("📃 Вибрати зі списку підключених", CB_PICK)]]),
    )


@router.message(F.text.func(is_sheet_link))
async def add_sheet(message: Message, manager: CatalogManager) -> None:
    sheet_id, gid = parse_sheet_link(message.text or "")
    existing = manager.find_sheet(sheet_id, gid)
    if existing:
        await message.answer(f"ℹ️ Таблиця {escape(existing.name)} вже додана.")
        return
    status = await message.answer("⏳ Читаю таблицю…")
    title = await manager.sheets.get_title(sheet_id) or "Google-таблиця"
    result = await manager.add_sheet(sheet_id, gid, title)
    if result.ok:
        await status.edit_text(f"✅ Додано 📄 {escape(title)} — {plural_products(result.count)}")
    else:
        await status.edit_text(f"❌ Не вдалося додати таблицю: {escape(result.error or 'помилка')}")


@router.message(F.text.func(is_mydrop_link))
async def add_by_link(message: Message, manager: CatalogManager, client: MyDropClient, config: Config) -> None:
    slug = extract_slug(message.text or "")
    if not slug:
        await message.answer(
            "🤔 Не вдалося розпізнати магазин у посиланні. Надішліть посилання виду "
            "<code>https://mydrop.com.ua/назва_магазину</code>."
        )
        return
    product_id = extract_product_id(message.text or "")

    existing = manager.find_by_slug(slug)
    if existing:
        if product_id is not None:
            await _show_product(message, manager, config, existing.link_id, product_id)
        else:
            await message.answer(f"ℹ️ Постачальник {escape(existing.name)} вже доданий.")
        return

    status = await message.answer("⏳ Шукаю постачальника…")
    remote_list, error = await _fetch_remote(client)
    if error:
        await status.edit_text(error)
        return
    remote = next((v for v in remote_list if v.public_url.lower() == slug), None)
    if remote is None:
        await status.edit_text(
            f"❌ Ви не підключені до постачальника <code>{escape(slug)}</code> у МійДроп.\n"
            "Спершу підключіться до нього в кабінеті МійДроп, потім надішліть посилання ще раз."
        )
        return
    if remote.link_id in manager.vendors:
        await status.edit_text(f"ℹ️ Постачальник {escape(remote.name)} вже доданий.")
        return
    if await _add(manager, remote, status) and product_id is not None:
        await _show_product(message, manager, config, remote.link_id, product_id)


@router.callback_query(F.data == CB_PICK)
async def pick_list(call: CallbackQuery, manager: CatalogManager, client: MyDropClient) -> None:
    await call.answer()
    remote_list, error = await _fetch_remote(client)
    if error:
        await call.message.answer(error)
        return
    candidates = [v for v in remote_list if v.link_id not in manager.vendors]
    if not remote_list:
        await call.message.answer("У вашому кабінеті МійДроп немає підключених постачальників.")
        return
    if not candidates:
        await call.message.answer("✅ Усі підключені в МійДроп постачальники вже додані в бота.")
        return
    candidates.sort(key=lambda v: v.name.lower())
    rows = [[(short(v.name, 50), f"{CB_ADD}{v.link_id}")] for v in candidates[:90]]
    await call.message.answer("Виберіть постачальника, щоб додати:", reply_markup=inline(rows))


@router.callback_query(F.data.startswith(CB_ADD))
async def add_from_list(call: CallbackQuery, manager: CatalogManager, client: MyDropClient) -> None:
    link_id = int(call.data.removeprefix(CB_ADD))
    await call.answer()
    if link_id in manager.vendors:
        await call.message.answer(f"ℹ️ Постачальник {escape(manager.vendors[link_id].name)} вже доданий.")
        return
    status = await call.message.answer("⏳ Додаю…")
    remote_list, error = await _fetch_remote(client)
    if error:
        await status.edit_text(error)
        return
    remote = next((v for v in remote_list if v.link_id == link_id), None)
    if remote is None:
        await status.edit_text("❌ Цього постачальника вже немає серед підключених у МійДроп.")
        return
    await _add(manager, remote, status)


# ---------- список і видалення ----------

def _vendors_view(manager: CatalogManager, config: Config):
    if not manager.vendors:
        return (
            "У боті ще немає постачальників. Натисніть «➕ Додати постачальника».",
            inline([[("📃 Вибрати зі списку підключених", CB_PICK)]]),
        )
    vendors = sorted(manager.vendors.values(), key=lambda v: v.name.lower())
    lines = ["📋 <b>Мої постачальники:</b>", ""]
    for v in vendors:
        lines.append(
            f"• {'📄 ' if v.is_sheet else ''}<b>{escape(v.name)}</b> — "
            f"{plural_products(manager.product_count(v.link_id))}, "
            f"оновлено: {format_updated(v.updated_at, config.timezone)}"
        )
    rows = [[(f"🗑 Видалити {short(v.name, 40)}", f"{CB_DEL}{v.link_id}")] for v in vendors]
    rows.append([("➕ Додати зі списку", CB_PICK)])
    return "\n".join(lines), inline(rows)


@router.message(F.text == BTN_LIST)
async def list_vendors(message: Message, manager: CatalogManager, config: Config) -> None:
    text, markup = _vendors_view(manager, config)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == CB_LIST)
async def list_vendors_cb(call: CallbackQuery, manager: CatalogManager, config: Config) -> None:
    await call.answer()
    text, markup = _vendors_view(manager, config)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(CB_DEL_OK))
async def delete_confirmed(call: CallbackQuery, manager: CatalogManager) -> None:
    link_id = int(call.data.removeprefix(CB_DEL_OK))
    record = manager.remove_vendor(link_id)
    await call.answer()
    text = f"🗑 Постачальника {escape(record.name)} видалено." if record else "Цього постачальника вже немає."
    try:
        await call.message.edit_text(text, reply_markup=inline([[("📋 Мої постачальники", CB_LIST)]]))
    except TelegramBadRequest:
        await call.message.answer(text)


@router.callback_query(F.data.startswith(CB_DEL))
async def delete_ask(call: CallbackQuery, manager: CatalogManager) -> None:
    link_id = int(call.data.removeprefix(CB_DEL))
    record = manager.vendors.get(link_id)
    await call.answer()
    if record is None:
        await call.message.answer("Цього постачальника вже немає.")
        return
    await call.message.edit_text(
        f"Видалити постачальника <b>{escape(record.name)}</b>? Його товари більше не шукатимуться.",
        reply_markup=inline([[("✅ Так, видалити", f"{CB_DEL_OK}{link_id}"), ("↩️ Скасувати", CB_LIST)]]),
    )


# ---------- оновлення ----------

@router.message(F.text == BTN_REFRESH)
async def refresh(message: Message, manager: CatalogManager) -> None:
    if not manager.vendors:
        await message.answer("Спершу додайте постачальника.")
        return
    if manager.refreshing:
        await message.answer("⏳ Оновлення вже триває, зачекайте трохи.")
        return
    status = await message.answer("⏳ Оновлюю каталоги…")
    results = await manager.refresh_all()
    lines = ["🔄 <b>Оновлення завершено:</b>", ""]
    for r in results:
        if r.ok:
            lines.append(f"✅ {escape(r.vendor.name)} — {plural_products(r.count)}")
        else:
            lines.append(f"❌ {escape(r.vendor.name)}: {escape(short(r.error or 'помилка', 150))}")
    if len(results) < len(manager.vendors):
        lines.append("⚠️ Решту пропущено через помилку ключа.")
    await status.edit_text("\n".join(lines))
