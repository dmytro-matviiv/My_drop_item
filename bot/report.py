"""Формування текстового звіту про товар (HTML parse mode)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from .catalog import Match
from .mydrop import product_url

IN_STOCK = "✅ В наявності"
OUT_OF_STOCK = "❌ Немає"
NOTHING_IN_STOCK = "❌ Немає в наявності"


def size_available(size: dict[str, Any]) -> bool:
    try:
        return float(size.get("real_count_dropshipper") or 0) > 0
    except (TypeError, ValueError):
        return False


def size_title(size: dict[str, Any]) -> str:
    return str(size.get("formatted") or size.get("title") or "—").strip()


def _children(product: dict[str, Any]) -> list[dict[str, Any]]:
    children = []
    for child in product.get("child_products") or []:
        if not isinstance(child, dict):
            continue
        # підстраховка: складова може бути вкладена в поле product
        inner = child.get("product")
        children.append(inner if isinstance(inner, dict) else child)
    return children


def product_available(product: dict[str, Any]) -> bool:
    sizes = product.get("sizes") or []
    if sizes:
        return any(size_available(s) for s in sizes)
    children = _children(product) if product.get("is_set") else []
    if children:
        # комплект доступний, якщо доступна кожна складова
        return all(product_available(c) for c in children)
    return bool(product.get("sizes_available"))


def format_price(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return escape(str(value))
    text = f"{number:.0f}" if number.is_integer() else f"{number:.2f}".rstrip("0")
    return f"{text} грн"


def format_updated(iso: str | None, tz: str, now: datetime | None = None) -> str:
    if not iso:
        return "—"
    try:
        zone = ZoneInfo(tz)
        moment = datetime.fromisoformat(iso).astimezone(zone)
    except Exception:
        return "—"
    now = (now or datetime.now(zone)).astimezone(zone)
    if moment.date() == now.date():
        return moment.strftime("%H:%M")
    return moment.strftime("%d.%m %H:%M")


def sizes_table(sizes: list[dict[str, Any]], highlight_id: int | None = None) -> str:
    titles = [size_title(s) for s in sizes]
    width = max(4, *(len(t) for t in titles)) + 1
    marker = highlight_id is not None
    lines = []
    for size, title in zip(sizes, titles):
        status = IN_STOCK if size_available(size) else OUT_OF_STOCK
        line = f"{title:<{width}}{status}"
        if marker:
            line = ("▶ " if size.get("id") == highlight_id else "  ") + line
        lines.append(line)
    return "<pre>" + escape("\n".join(lines)) + "</pre>"


def first_image(product: dict[str, Any]) -> str | None:
    for image in product.get("images") or []:
        if isinstance(image, dict) and image.get("full_url"):
            return str(image["full_url"])
    return None


def build_report(match: Match, tz: str = "Europe/Kyiv", now: datetime | None = None) -> str:
    product = match.product
    vendor = match.vendor
    available = product_available(product)
    sizes = product.get("sizes") or []
    children = _children(product) if product.get("is_set") else []

    lines = [
        f"{'✅' if available else '❌'} <b>{escape(str(product.get('title') or 'Без назви'))}</b>",
        f"🏪 {escape(vendor.name)}",
        f"🔖 Артикул: <code>{escape(str(product['sku']))}</code>" if product.get("sku")
        else f"🔖 Артикул: — (ID товару <code>{product.get('id')}</code>)",
        f"💰 Дроп. ціна: {format_price(product.get('drop_price'))}",
    ]

    if match.size_id is not None:
        size = next((s for s in sizes if s.get("id") == match.size_id), None)
        if size is not None:
            lines.append(f"📏 Розмір за артикулом: <b>{escape(size_title(size))}</b> "
                         f"(<code>{escape(str(size.get('sku')))}</code>)")

    lines.append("")
    if sizes:
        lines.append(sizes_table(sizes, match.size_id))
        if not available:
            lines.append(NOTHING_IN_STOCK)
    elif children:
        lines.append("🧩 Комплект:")
        for child in children:
            child_ok = product_available(child)
            lines.append(f"{'✅' if child_ok else '❌'} {escape(str(child.get('title') or 'Складова'))}")
            child_sizes = child.get("sizes") or []
            if child_sizes:
                lines.append(sizes_table(child_sizes))
        if not available:
            lines.append(NOTHING_IN_STOCK)
    else:
        lines.append(IN_STOCK if available else NOTHING_IN_STOCK)

    lines += [
        "",
        f"🔗 {product_url(vendor.public_url, product.get('id'))}",
        f"🕒 Дані оновлено: {format_updated(vendor.updated_at, tz, now)}",
    ]
    return "\n".join(lines)


_TAG_RE = re.compile(r"<[^>]+>")


def visible_length(html_text: str) -> int:
    """Приблизна довжина тексту після розбору HTML (для ліміту підпису 1024)."""
    text = _TAG_RE.sub("", html_text)
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#x27;"):
        text = text.replace(entity, "x")
    return len(text)
