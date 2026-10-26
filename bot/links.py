"""Розбір посилань на магазини МійДроп."""

from __future__ import annotations

import re

# службові перші сегменти шляху, які не є slug магазину
_RESERVED = {"join", "p", "c", "api", "dropshipper", "vendor", "login", "register", "auth", "static"}

_LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?mydrop\.com\.ua(/[^\s?#]*)?", re.IGNORECASE)
_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-.]+$")


def is_mydrop_link(text: str) -> bool:
    return bool(_LINK_RE.search(text or ""))


def extract_slug(text: str) -> str | None:
    """Slug магазину з будь-якого посилання МійДроп або None.

    https://mydrop.com.ua/segeda_shop/c/145367 -> segeda_shop
    https://mydrop.com.ua/join/segeda_shop     -> segeda_shop
    """
    m = _LINK_RE.search(text or "")
    if not m or not m.group(1):
        return None
    parts = [p for p in m.group(1).split("/") if p]
    if parts and parts[0].lower() == "join":
        parts = parts[1:]
    if not parts:
        return None
    slug = parts[0]
    if slug.lower() in _RESERVED or not _SLUG_RE.match(slug):
        return None
    return slug.lower()
