"""Зберігання списку постачальників і кешу каталогів у DATA_DIR."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class VendorRecord:
    link_id: int
    vendor_id: int
    name: str
    public_url: str
    sku_prefix: str | None = None
    added_at: str | None = None
    updated_at: str | None = None  # ISO-час останнього успішного оновлення каталогу


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.catalog_dir = self.data_dir / "catalogs"
        self.vendors_path = self.data_dir / "vendors.json"
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

    def load_vendors(self) -> list[VendorRecord]:
        if not self.vendors_path.exists():
            return []
        try:
            raw = json.loads(self.vendors_path.read_text(encoding="utf-8"))
            return [VendorRecord(**item) for item in raw]
        except Exception:
            log.exception("Не вдалося прочитати %s", self.vendors_path)
            return []

    def save_vendors(self, vendors: list[VendorRecord]) -> None:
        atomic_write_json(self.vendors_path, [asdict(v) for v in vendors])

    def _catalog_path(self, link_id: int) -> Path:
        return self.catalog_dir / f"{int(link_id)}.json"

    def load_catalog(self, link_id: int) -> list[dict[str, Any]] | None:
        path = self._catalog_path(link_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))["products"]
        except Exception:
            log.exception("Пошкоджений кеш каталогу %s", path)
            return None

    def save_catalog(self, link_id: int, products: list[dict[str, Any]]) -> None:
        atomic_write_json(self._catalog_path(link_id), {"products": products})

    def delete_catalog(self, link_id: int) -> None:
        try:
            self._catalog_path(link_id).unlink()
        except FileNotFoundError:
            pass
