"""Постачальники з Google-таблиць (для тих, хто не працює через МійДроп).

Таблиця має бути відкрита «Усі, хто має посилання». Дані беремо з CSV-експорту,
фото з HTML-перегляду. Колонки розпізнаємо за заголовками, тож формат може
відрізнятися між постачальниками: потрібна лише колонка з кодом/артикулом.
Рядки перетворюємо на словники у форматі каталогу МійДроп, щоб пошук і звіт
працювали однаково для всіх джерел.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

RETRIES = 3
RETRY_PAUSE = 5
HEADER_SCAN_ROWS = 15
MAX_CODE_LEN = 40

_SHEET_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})", re.IGNORECASE)
_GID_RE = re.compile(r"[#?&]gid=(\d+)")


class SheetError(Exception):
    pass


def is_sheet_link(text: str) -> bool:
    return bool(_SHEET_RE.search(text or ""))


def parse_sheet_link(text: str) -> tuple[str, int] | None:
    """(id таблиці, gid аркуша) з посилання; без gid береться перший аркуш (0)."""
    m = _SHEET_RE.search(text or "")
    if not m:
        return None
    gid = _GID_RE.search(text[m.end():])
    return m.group(1), int(gid.group(1)) if gid else 0


def sheet_row_url(sheet_id: str, gid: int, row: int) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={gid}&range=A{row}"


# ---------- розбір таблиці ----------

_CODE_WORDS = ("код", "артикул", "арт", "sku", "code")
_NAME_WORDS = ("назва", "найменування", "товар", "модель", "name")
_PRICE_WORDS = ("дроп", "опт", "ціна", "price", "вартість")  # у порядку пріоритету
_STOCK_WORDS = ("наявн", "залишок", "залишки", "кількість", "к-сть", "stock")
_NOTE_WORDS = ("замір", "опис", "примітк", "розмірна", "склад", "матеріал")

_LETTER_SIZES = {"xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl", "5xl",
                 "one size", "onesize", "os", "універсальний"}
_SIZE_RE = re.compile(r"^\d{1,3}([.,]5)?(\s*[-/]\s*\d{1,3}([.,]5)?)?$")
_EMPTY = {"", "-", "—", "–", "0", "x", "х", "ні", "нема", "немає", "нет", "no", "n/a"}
_YES = {"+", "є", "так", "yes", "в наявності", "наявність", "у наявності", "есть", "да"}


def _norm(value: str) -> str:
    return " ".join(str(value).split()).lower()


def is_size_header(value: str) -> bool:
    v = _norm(value)
    return bool(v) and (v in _LETTER_SIZES or bool(_SIZE_RE.match(v)))


def _matches(header: str, words: tuple[str, ...]) -> bool:
    h = _norm(header)
    return any(h == w or h.startswith(w) or f" {w}" in h for w in words)


def cell_available(value: str) -> bool:
    """«39 - 2» → є, «-» / «0» / порожньо → немає, «+» / «є» → є."""
    v = _norm(value)
    if v in _EMPTY:
        return False
    if v in _YES:
        return True
    dash = re.search(r"[-–—]\s*(\d+)", v)  # «39 - 2»: кількість після дефіса
    if dash:
        return int(dash.group(1)) > 0
    number = re.match(r"^(\d+(?:[.,]\d+)?)", v)
    if number:
        return float(number.group(1).replace(",", ".")) > 0
    return not any(word in v for word in ("немає", "нема", "закінч", "відсутн", "продано"))


def _parse_price(value: str) -> float | None:
    m = re.search(r"\d[\d\s]*(?:[.,]\d+)?", value or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


@dataclass
class Columns:
    header_row: int
    code: int
    name: int | None = None
    price: int | None = None
    price_label: str = "Ціна"
    stock: int | None = None
    sizes: list[tuple[int, str]] = field(default_factory=list)
    notes: list[tuple[int, str]] = field(default_factory=list)


def detect_columns(rows: list[list[str]]) -> Columns | None:
    for r, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        code = next((i for i, h in enumerate(row) if _matches(h, _CODE_WORDS)), None)
        if code is None:
            continue
        cols = Columns(header_row=r, code=code)
        for i, header in enumerate(row):
            if i == code or not header.strip():
                continue
            label = " ".join(header.split())
            if is_size_header(header):
                cols.sizes.append((i, label))
            elif cols.name is None and _matches(header, _NAME_WORDS) and "фото" not in _norm(header):
                cols.name = i
            elif cols.stock is None and _matches(header, _STOCK_WORDS):
                cols.stock = i
            elif _matches(header, _NOTE_WORDS):
                cols.notes.append((i, label))
        for word in _PRICE_WORDS:
            price = next((i for i, h in enumerate(row) if i != code and _matches(h, (word,))), None)
            if price is not None:
                cols.price, cols.price_label = price, " ".join(row[price].split())
                break
        return cols
    return None


def rows_to_products(rows: list[list[str]], images: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Рядки CSV → товари у форматі каталогу МійДроп. id товару = номер рядка в таблиці (з 1)."""
    cols = detect_columns(rows)
    if cols is None:
        raise SheetError("не знайдено колонку з кодом або артикулом (заголовок «Код» / «Артикул»)")
    images = images or {}

    def cell(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    products = []
    for r in range(cols.header_row + 1, len(rows)):
        row = rows[r]
        code = cell(row, cols.code)
        if not code or len(code) > MAX_CODE_LEN:
            continue
        name = cell(row, cols.name)
        price = cell(row, cols.price)
        sizes = [
            {"id": i, "title": label, "formatted": label, "sku": None,
             "real_count_dropshipper": 1 if cell_available(cell(row, i)) else 0}
            for i, label in cols.sizes
        ]
        stock = cell(row, cols.stock)
        if not (name or price or stock or any(cell(row, i) for i, _ in cols.sizes)):
            continue  # рядок-примітка на кшталт «Для замовлення пишіть…»

        product: dict[str, Any] = {
            "id": r + 1,
            "title": name or f"Товар {code}",
            "sku": code,
            "drop_price": _parse_price(price),
            "price_label": cols.price_label,
            "sizes": sizes,
            "sizes_available": cell_available(stock) if cols.stock is not None else any(
                s["real_count_dropshipper"] for s in sizes),
            "is_set": False,
            "child_products": [],
            "images": [{"full_url": images[r]}] if r in images else [],
            "notes": [(label, cell(row, i)) for i, label in cols.notes if cell(row, i)],
        }
        products.append(product)
    return products


_ROW_RE = re.compile(r'<th id="\d+R(\d+)"')
_IMG_RE = re.compile(r'<img[^>]+src="(https://[^"]+)"')


def parse_images(html: str) -> dict[int, str]:
    """Номер рядка (з 0) → перше фото в рядку, у повному розмірі."""
    images: dict[int, str] = {}
    marks = list(_ROW_RE.finditer(html))
    for n, mark in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else len(html)
        img = _IMG_RE.search(html, mark.end(), end)
        if img:
            url = unescape(img.group(1))
            images[int(mark.group(1))] = re.sub(r"=s\d+[^/]*$", "=s1000", url)
    return images


def parse_title(html: str) -> str | None:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m:
        return None
    title = unescape(m.group(1)).strip()
    title = re.sub(r"\s+-\s+Google\s+(Диск|Drive|Таблиці|Sheets|Таблицы)$", "", title)
    return title or None


# ---------- завантаження ----------

class SheetsClient:
    def __init__(self, timeout: float = 60):
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _get_text(self, url: str) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                async with self._session.get(url) as resp:
                    if resp.status in (401, 403, 404):
                        raise SheetError("таблиця недоступна: відкрийте доступ «Усі, хто має посилання» (перегляд)")
                    if resp.status >= 400:
                        raise aiohttp.ClientResponseError(resp.request_info, (), status=resp.status)
                    text = await resp.text(encoding="utf-8")
                    if "accounts.google.com" in str(resp.url):
                        raise SheetError("таблиця недоступна: відкрийте доступ «Усі, хто має посилання» (перегляд)")
                    return text
            except SheetError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last = e
                log.warning("GET %s: спроба %d/%d не вдалася: %r", url, attempt, RETRIES, e)
                if attempt < RETRIES:
                    await asyncio.sleep(RETRY_PAUSE * attempt)
        raise SheetError(f"не вдалося завантажити таблицю: {last!r}")

    async def get_title(self, sheet_id: str) -> str | None:
        try:
            html = await self._get_text(f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview")
        except SheetError:
            return None
        return parse_title(html)

    async def get_products(self, sheet_id: str, gid: int) -> list[dict[str, Any]]:
        base = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        text = await self._get_text(f"{base}/export?format=csv&gid={gid}")
        if text.lstrip().lower().startswith(("<!doctype", "<html")):
            raise SheetError("таблиця недоступна: відкрийте доступ «Усі, хто має посилання» (перегляд)")
        rows = list(csv.reader(io.StringIO(text)))
        try:
            html = await self._get_text(f"{base}/htmlview/sheet?headers=true&gid={gid}")
            images = parse_images(html)
        except SheetError as e:
            log.warning("Фото з таблиці %s не завантажено: %s", sheet_id, e)
            images = {}
        return rows_to_products(rows, images)
