"""Хто може користуватися ботом: адміністратори з ADMIN_IDS і схвалені ними люди."""

from __future__ import annotations

from typing import Any, Literal

from .catalog import utc_now_iso
from .storage import Storage

Status = Literal["admin", "approved", "pending", "rejected", "unknown"]


class AccessControl:
    def __init__(self, storage: Storage, admin_ids: frozenset[int], preapproved: frozenset[int] = frozenset()):
        self.storage = storage
        self.admin_ids = admin_ids
        self.preapproved = preapproved
        self.users: dict[int, dict[str, Any]] = storage.load_users()

    def status(self, user_id: int) -> Status:
        if user_id in self.admin_ids:
            return "admin"
        if user_id in self.preapproved:
            return "approved"
        return self.users.get(user_id, {}).get("status", "unknown")

    def is_allowed(self, user_id: int) -> bool:
        return self.status(user_id) in ("admin", "approved")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def _set(self, user_id: int, status: str, **info: Any) -> dict[str, Any]:
        entry = self.users.setdefault(user_id, {})
        entry.update({k: v for k, v in info.items() if v is not None})
        entry["status"] = status
        entry["changed_at"] = utc_now_iso()
        self.storage.save_users(self.users)
        return entry

    def request(self, user_id: int, name: str | None, username: str | None) -> bool:
        """Створює запит на доступ. True, якщо запит новий (треба повідомити адмінів)."""
        if self.status(user_id) != "unknown":
            return False
        self._set(user_id, "pending", name=name, username=username)
        return True

    def approve(self, user_id: int) -> None:
        self._set(user_id, "approved")

    def reject(self, user_id: int) -> None:
        self._set(user_id, "rejected")

    def label(self, user_id: int) -> str:
        info = self.users.get(user_id, {})
        name = info.get("name") or str(user_id)
        return f"{name} (@{info['username']})" if info.get("username") else name

    def listed(self, status: str) -> list[int]:
        return sorted(uid for uid, info in self.users.items() if info.get("status") == status)
