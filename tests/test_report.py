from datetime import datetime, timezone

from bot.catalog import Match
from bot.report import build_report, first_image, format_price, format_updated, visible_length

from .conftest import DOFF, SEGEDA

NOW = datetime(2026, 10, 26, 13, 0, tzinfo=timezone.utc)


def product(products, pid):
    return next(p for p in products if p["id"] == pid)


def test_report_in_stock(catalogs):
    p = product(catalogs[SEGEDA.link_id], 4374148)
    text = build_report(Match(SEGEDA, p), now=NOW)
    assert text.startswith("✅ <b>SI Зіп Худі Stone island чорний</b>")
    assert "🏪 Segeda_shop" in text
    assert "art1.01" in text
    assert "💰 Дроп. ціна: 1760 грн" in text
    assert "<pre>S    ✅ В наявності\nM    ✅ В наявності" in text
    assert "XXL  ✅ В наявності</pre>" in text
    assert "🔗 https://mydrop.com.ua/segeda_shop/p/4374148" in text
    assert "🕒 Дані оновлено: 14:42" in text  # Київ, UTC+2 наприкінці жовтня
    # точну кількість не показуємо
    assert "47" not in text and "28" not in text
    assert first_image(p).endswith("hoodie.jpeg")
    assert visible_length(text) < 1024


def test_report_out_of_stock_and_escaping(catalogs):
    p = product(catalogs[SEGEDA.link_id], 4374200)
    text = build_report(Match(SEGEDA, p), now=NOW)
    assert text.startswith("❌ <b>Футболка &lt;Basic&gt; &amp; Co</b>")
    assert "M    ❌ Немає" in text
    assert "❌ Немає в наявності" in text
    assert "https://mydrop.com.ua/segeda_shop/p/4374200" in text
    assert "450.5 грн" in text
    assert first_image(p) is None


def test_report_without_sizes(catalogs):
    p = product(catalogs[SEGEDA.link_id], 4374300)
    text = build_report(Match(SEGEDA, p), now=NOW)
    assert text.startswith("✅")
    assert "<pre>" not in text
    assert "\n✅ В наявності\n" in text

    p = product(catalogs[DOFF.link_id], 9000001)
    text = build_report(Match(DOFF, p), now=NOW)
    assert text.startswith("❌")
    assert "❌ Немає в наявності" in text
    assert "https://mydrop.com.ua/doff_team/p/9000001" in text


def test_report_size_highlight(catalogs):
    p = product(catalogs[SEGEDA.link_id], 4374400)
    text = build_report(Match(SEGEDA, p, size_id=3002), now=NOW)
    assert "📏 Розмір за артикулом: <b>M</b>" in text
    assert "▶ M" in text
    assert "  S    ❌ Немає" in text


def test_report_set(catalogs):
    p = product(catalogs[SEGEDA.link_id], 4374500)
    text = build_report(Match(SEGEDA, p), now=NOW)
    # штани в комплекті закінчились, тож комплект недоступний
    assert text.startswith("❌")
    assert "🧩 Комплект:" in text
    assert "✅ Худі" in text and "❌ Штани" in text
    assert "❌ Немає в наявності" in text


def test_format_helpers():
    assert format_price(1760) == "1760 грн"
    assert format_price(1760.0) == "1760 грн"
    assert format_price(None) == "—"
    assert format_updated(None, "Europe/Kyiv") == "—"
    assert format_updated("2026-10-20T10:00:00+00:00", "Europe/Kyiv", NOW) == "20.10 13:00"
