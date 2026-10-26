import pytest

from bot.catalog import loose_sku, normalize_sku, sku_variants

from .conftest import DOFF, SEGEDA


@pytest.mark.parametrize("raw, expected", [
    ("art1.01", "art1.01"),
    ("  ART1.01  ", "art1.01"),
    ("Art 1.01", "art1.01"),
    ("DT\t500", "dt500"),
    ("CAP-77", "cap-77"),
    (None, ""),
    (12345, "12345"),
])
def test_normalize(raw, expected):
    assert normalize_sku(raw) == expected


def test_dot_is_significant():
    assert normalize_sku("art1.01") != normalize_sku("art101")
    assert loose_sku("art1.01") == loose_sku("art101") == "art101"


def test_sku_variants_with_prefix():
    assert sku_variants("ab-123", "AB-") == {"ab-123", "123"}
    assert sku_variants("123", "ab-") == {"123", "ab-123"}
    assert sku_variants("", "ab-") == set()


def test_exact_product(index):
    result = index.search(" ART1.01 ")
    assert result.kind == "product"
    assert len(result.matches) == 1
    m = result.matches[0]
    assert m.product["title"] == "SI Зіп Худі Stone island чорний"
    assert m.vendor is SEGEDA
    assert m.size_id is None


def test_dot_not_ignored_in_exact(index):
    result = index.search("art101")
    assert result.kind == "product"
    assert [m.product["id"] for m in result.matches] == [4374200]


def test_spaces_inside_ignored(index):
    result = index.search("dt500")
    assert result.kind == "product"
    assert result.matches[0].vendor is DOFF


def test_exact_size(index):
    result = index.search("pants-1-m")
    assert result.kind == "size"
    assert result.matches[0].product["id"] == 4374400
    assert result.matches[0].size_id == 3002


def test_product_sku_beats_size_sku(index):
    result = index.search("PANTS-1")
    assert result.kind == "product"
    assert result.matches[0].size_id is None


def test_duplicates_in_different_vendors(index):
    result = index.search("DUP-1")
    assert result.kind == "product"
    assert {m.vendor.link_id for m in result.matches} == {SEGEDA.link_id, DOFF.link_id}


def test_partial(index):
    result = index.search("pants")
    assert result.kind == "partial"
    # товар і обидва розміри ведуть на той самий товар: показуємо один раз
    assert [m.product["id"] for m in result.matches] == [4374400]


def test_partial_loose_match(index):
    result = index.search("cap77")
    assert result.kind == "partial"
    assert result.matches[0].product["id"] == 4374300


def test_partial_limit(index):
    result = index.search("a")  # є в багатьох артикулах
    assert result.kind == "partial"
    assert len(result.matches) <= 5
    assert result.total >= len(result.matches)


def test_not_found(index):
    assert index.search("nope-999").kind == "none"
    assert index.search("   ").kind == "none"


def test_get(index):
    m = index.get(SEGEDA.link_id, 4374400, 3001)
    assert m.product["sku"] == "PANTS-1" and m.size_id == 3001
    assert index.get(SEGEDA.link_id, 1) is None


def test_search_by_product_id(index):
    result = index.search(" 9000002 ")
    assert result.kind == "product"
    assert result.matches[0].product["sku"] == "DT 500"
    # ID не підказується частковим збігом
    assert index.search("900000").kind == "none"
