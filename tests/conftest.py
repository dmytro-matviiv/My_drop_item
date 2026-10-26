import json
from pathlib import Path

import pytest

from bot.catalog import SearchIndex
from bot.storage import VendorRecord

FIXTURES = Path(__file__).parent / "fixtures"

SEGEDA = VendorRecord(522473, 33899, "Segeda_shop", "segeda_shop", updated_at="2026-10-26T12:42:00+00:00")
DOFF = VendorRecord(522501, 5108, "DoFF TEAM", "doff_team", updated_at="2026-10-26T12:40:00+00:00")


def load_products(name: str) -> list[dict]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))["products"]


@pytest.fixture
def catalogs():
    return {SEGEDA.link_id: load_products("segeda_shop"), DOFF.link_id: load_products("doff_team")}


@pytest.fixture
def index(catalogs):
    return SearchIndex({SEGEDA.link_id: SEGEDA, DOFF.link_id: DOFF}, catalogs)
