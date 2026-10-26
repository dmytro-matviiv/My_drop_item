"""Налаштування бота зі змінних середовища."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv потрібен лише для локального запуску
    load_dotenv = None

log = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    mydrop_api_key: str
    admin_ids: frozenset[int]      # адміністратори: схвалюють доступ, отримують сповіщення
    allowed_users: frozenset[int]  # заздалегідь дозволені користувачі (необов'язково)
    data_dir: Path
    refresh_minutes: int
    timezone: str


def _parse_users(name: str) -> frozenset[int]:
    users = set()
    for part in os.getenv(name, "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            users.add(int(part))
        except ValueError:
            raise ConfigError(f"{name}: '{part}' не схоже на Telegram ID") from None
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
        admin_ids=_parse_users("ADMIN_IDS"),
        allowed_users=_parse_users("ALLOWED_USERS"),
        data_dir=_data_dir(),
        refresh_minutes=max(1, refresh),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv").strip() or "Europe/Kyiv",
    )


def _data_dir() -> Path:
    """DATA_DIR, але на Railway дані завжди мають лежати на примонтованому Volume.

    Railway сам задає RAILWAY_VOLUME_MOUNT_PATH, коли до сервісу підключено Volume.
    Якщо DATA_DIR не задано або він вказує поза Volume, файли зникали б після редеплою.
    """
    raw = os.getenv("DATA_DIR", "").strip()
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if volume:
        volume_path = Path(volume).resolve()
        if not raw:
            return volume_path
        data_path = Path(raw).resolve()
        if data_path != volume_path and volume_path not in data_path.parents:
            log.warning("DATA_DIR=%s поза Volume %s: після редеплою дані зникли б, тож використовую Volume",
                        raw, volume)
            return volume_path
        return data_path
    return Path(raw or "./data")
