import csv
import io
from datetime import datetime, timezone

from bot.catalog import SearchIndex
from bot.report import build_report
from bot.sheets import cell_available, detect_columns, parse_images, parse_sheet_link, parse_title, rows_to_products
from bot.storage import VendorRecord

# формат як у реальному прайсі «Tip Top»
CSV = '''Код,Фото товару,Заміри устілок,ОПТ,35,36,37,38,39,40
Для замовлення пишіть Telegram: https://t.me/example,,,,,,,,,
11388,,"36-23
37-24
Розмір у розмір",1600,-,-,-,-,39 - 2,-
11389,,,1600,-,-,-,-,-,-
16651,,,1 830 грн,-,36 - 3,37 - 3,38 - 0,"39 - 1
1пара Михайлюк  17:05",-
,,,200,-,-,-,-,-,-
'''

HTML = (
    '<tr><th id="0R0"><div>1</div></th><td>Код</td></tr>'
    '<tr><th id="0R2"><div>3</div></th><td>11388</td><td><div><img src="https://lh3.googleusercontent.com/'
    'docsubipk/ABC=s100-w100-h20" style="x"/></div></td></tr>'
    '<tr><th id="0R3"><div>4</div></th><td>11389</td><td></td></tr>'
)

SHEET = VendorRecord(-1, 0, "Tip Top прайс", "", updated_at="2026-10-31T10:00:00+00:00",
                     kind="sheet", sheet_id="1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ", sheet_gid=0)


def rows():
    return list(csv.reader(io.StringIO(CSV)))


def test_parse_sheet_link():
    url = "https://docs.google.com/spreadsheets/d/1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ/edit?gid=0#gid=0"
    assert parse_sheet_link(url) == ("1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ", 0)
    assert parse_sheet_link("https://docs.google.com/spreadsheets/d/1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ/"
                            "edit#gid=12345")[1] == 12345
    assert parse_sheet_link("https://docs.google.com/spreadsheets/d/1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ")[1] == 0
    assert parse_sheet_link("art1.01") is None


def test_cell_available():
    assert cell_available("39 - 2")
    assert not cell_available("38 - 0")
    assert not cell_available("-")
    assert not cell_available("")
    assert cell_available("5")
    assert not cell_available("0")
    assert cell_available("+")
    assert cell_available("39 - 1\n1пара Михайлюк  17:05")
    assert not cell_available("немає")


def test_detect_columns():
    cols = detect_columns(rows())
    assert cols.code == 0 and cols.price == 3 and cols.price_label == "ОПТ"
    assert [label for _, label in cols.sizes] == ["35", "36", "37", "38", "39", "40"]
    assert [label for _, label in cols.notes] == ["Заміри устілок"]


def test_rows_to_products():
    products = rows_to_products(rows(), parse_images(HTML))
    # рядок-примітка й рядок без коду пропущені
    assert [p["sku"] for p in products] == ["11388", "11389", "16651"]
    first = products[0]
    assert first["id"] == 3  # номер рядка в таблиці
    assert first["drop_price"] == 1600
    assert [s["title"] for s in first["sizes"] if s["real_count_dropshipper"]] == ["39"]
    assert first["images"][0]["full_url"] == "https://lh3.googleusercontent.com/docsubipk/ABC=s1000"
    assert products[1]["images"] == []
    assert products[2]["drop_price"] == 1830
    assert [s["title"] for s in products[2]["sizes"] if s["real_count_dropshipper"]] == ["36", "37", "39"]


def test_search_and_report():
    products = rows_to_products(rows(), parse_images(HTML))
    index = SearchIndex({SHEET.link_id: SHEET}, {SHEET.link_id: products})
    result = index.search("11388")
    assert result.kind == "product"
    # номер рядка не має знаходитись як ID товару
    assert index.search("4").kind == "none"

    text = build_report(result.matches[0], now=datetime(2026, 10, 31, 12, tzinfo=timezone.utc))
    assert text.startswith("✅ <b>Товар 11388</b>")
    assert "🏪 Tip Top прайс" in text
    assert "💰 ОПТ: 1600 грн" in text
    assert "39   ✅ В наявності" in text and "35   ❌ Немає" in text
    assert "📐 Заміри устілок:\n36-23\n37-24" in text
    assert "🔗 https://docs.google.com/spreadsheets/d/1-4mGwlX3dxJfONy3RqsBIaP50zFqlvWoDq19ykZeugQ/edit#gid=0&range=A3" in text

    sold_out = build_report(index.search("11389").matches[0])
    assert sold_out.startswith("❌") and "❌ Немає в наявності" in sold_out


def test_parse_title():
    assert parse_title("<title>Tip Top прайс - Google Диск</title>") == "Tip Top прайс"
    assert parse_title("<title>Прайс &amp; залишки - Google Sheets</title>") == "Прайс & залишки"
