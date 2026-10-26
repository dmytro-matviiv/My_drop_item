"""Налаштування бота зі змінних середовища."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv потрібен лише для локального запуску
    load_dotenv = None


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    mydrop_api_key: str
    allowed_users: frozenset[int]
    data_dir: Path
    refresh_minutes: int
    timezone: str


def _parse_users(raw: str) -> frozenset[int]:
    users = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            users.add(int(part))
        except ValueError:
            raise ConfigError(f"ALLOWED_USERS: '{part}' не схоже на Telegram ID") from None
    return frozenset(users)


def load_config() -> Config:
    if load_dotenv is not None:
        load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    api_key = os.getenv("MYDROP_API_KEY", "").strip()
    missing = [name for name, value in (("BOT_TOKEN", token), ("MYDROP_API_KEY", api_key)) if not value]
    if missing:
        raise ConfigError("Не задано змінні середовища: " + ", ".join(missing))

    try:
        refresh = int(os.getenv("REFRESH_MINUTES", "15").strip() or 15)
    except ValueError:
        raise ConfigError("REFRESH_MINUTES має бути цілим числом") from None

    return Config(
        bot_token=token,
        mydrop_api_key=api_key,
        allowed_users=_parse_users(os.getenv("ALLOWED_USERS", "")),
        data_dir=Path(os.getenv("DATA_DIR", "./data").strip() or "./data"),
        refresh_minutes=max(1, refresh),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv").strip() or "Europe/Kyiv",
    )
