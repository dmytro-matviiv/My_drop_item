from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..keyboards import BTN_ADD, BTN_LIST, BTN_REFRESH, main_menu

router = Router()

HELP = (
    "Надішліть мені <b>артикул</b> товару, і я знайду його в каталогах ваших постачальників: "
    "назва, дроп-ціна, наявність по розмірах і посилання на МійДроп.\n\n"
    f"{BTN_ADD}: надішліть будь-яке посилання на магазин постачальника "
    "(наприклад, <code>https://mydrop.com.ua/segeda_shop</code>) або виберіть зі списку.\n"
    f"{BTN_LIST}: список доданих постачальників і видалення.\n"
    f"{BTN_REFRESH}: оновити каталоги вручну (вони й так оновлюються автоматично)."
)


@router.message(CommandStart())
async def cmd_start(message: Message, is_allowed: bool) -> None:
    user_id = message.from_user.id if message.from_user else "?"
    id_line = f"🆔 Ваш Telegram ID: <code>{user_id}</code>"
    if not is_allowed:
        await message.answer(
            "👋 Привіт! Це бот пошуку товарів за артикулом у постачальників МійДроп.\n\n"
            f"{id_line}\n\n"
            "⛔ Немає доступу. Щоб користуватися ботом, додайте цей ID у змінну ALLOWED_USERS."
        )
        return
    await message.answer(f"👋 Привіт!\n\n{HELP}\n\n{id_line}", reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())
