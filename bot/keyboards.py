"""Клавіатури та тексти кнопок."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_ADD = "➕ Додати постачальника"
BTN_LIST = "📋 Мої постачальники"
BTN_REFRESH = "🔄 Оновити каталоги"
BTN_USERS = "👥 Користувачі"

# callback_data
CB_PICK = "pick"            # показати список підключених у МійДроп
CB_ADD = "add:"             # add:<link_id>
CB_LIST = "list"            # мої постачальники
CB_DEL = "del:"             # del:<link_id> — запит підтвердження
CB_DEL_OK = "delok:"        # delok:<link_id>
CB_SHOW = "show:"           # show:<link_id>:<product_id>:<size_id|0>
CB_APPROVE = "uok:"         # uok:<user_id> — дозволити доступ
CB_REJECT = "uno:"          # uno:<user_id> — відхилити / забрати доступ


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    last_row = [KeyboardButton(text=BTN_REFRESH)]
    if is_admin:
        last_row.append(KeyboardButton(text=BTN_USERS))
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_LIST)],
            last_row,
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Введіть артикул…",
    )


def inline(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def short(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def plural_products(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "товар"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "товари"
    else:
        word = "товарів"
    return f"{n} {word}"
