import pytest

from bot.links import extract_slug, is_mydrop_link


@pytest.mark.parametrize("url", [
    "https://mydrop.com.ua/segeda_shop/c/145367",
    "https://mydrop.com.ua/segeda_shop/p/4374148",
    "https://mydrop.com.ua/segeda_shop",
    "https://mydrop.com.ua/segeda_shop/",
    "https://mydrop.com.ua/join/segeda_shop",
    "http://www.mydrop.com.ua/Segeda_Shop?utm_source=ig",
    "mydrop.com.ua/segeda_shop/p/4374148#photo",
    "Ось магазин: https://mydrop.com.ua/segeda_shop/c/145367 дякую",
])
def test_extract_slug(url):
    assert is_mydrop_link(url)
    assert extract_slug(url) == "segeda_shop"


@pytest.mark.parametrize("url", [
    "https://mydrop.com.ua/",
    "https://mydrop.com.ua",
    "https://mydrop.com.ua/join/",
    "https://mydrop.com.ua/p/123",
])
def test_extract_slug_without_shop(url):
    assert extract_slug(url) is None


@pytest.mark.parametrize("text", ["art1.01", "https://example.com/segeda_shop", "mydrop"])
def test_not_a_link(text):
    assert not is_mydrop_link(text)
