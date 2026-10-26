from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..keyboards import BTN_ADD, BTN_LIST, BTN_REFRESH, BTN_USERS, main_menu

router = Router()

HELP = (
    "Надішліть мені <b>артикул</b> товару, і я знайду його в каталогах постачальників: "
    "назва, дроп-ціна, наявність по розмірах і посилання на МійДроп. "
    "Якщо в постачальника немає артикулів, надішліть ID товару (число з посилання "
    "<code>.../p/5566217</code>) або саме посилання на товар.\n\n"
    f"{BTN_ADD}: надішліть будь-яке посилання на магазин постачальника "
    "(наприклад, <code>https://mydrop.com.ua/segeda_shop</code>) або виберіть зі списку.\n"
    f"{BTN_LIST}: список доданих постачальників і видалення.\n"
    f"{BTN_REFRESH}: оновити каталоги вручну (вони й так оновлюються автоматично)."
)
ADMIN_HELP = f"\n{BTN_USERS}: хто має доступ до бота, запити на доступ."


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, is_admin: bool) -> None:
    user_id = message.from_user.id if message.from_user else "?"
    text = f"👋 Привіт!\n\n{HELP}"
    if is_admin:
        text += ADMIN_HELP
    await message.answer(f"{text}\n\n🆔 Ваш Telegram ID: <code>{user_id}</code>", reply_markup=main_menu(is_admin))
