from bot.access import AccessControl
from bot.storage import Storage

ADMIN = 100


def test_access_flow(tmp_path):
    access = AccessControl(Storage(tmp_path), frozenset({ADMIN}), frozenset({300}))
    assert access.is_allowed(ADMIN) and access.is_admin(ADMIN)
    assert access.is_allowed(300) and not access.is_admin(300)

    assert not access.is_allowed(200)
    assert access.request(200, "Оля", "olya") is True
    assert access.request(200, "Оля", "olya") is False  # повторно адміна не смикаємо
    assert access.status(200) == "pending" and not access.is_allowed(200)
    assert access.listed("pending") == [200]
    assert access.label(200) == "Оля (@olya)"

    access.approve(200)
    assert access.is_allowed(200)

    # після перезапуску стан зберігся
    restarted = AccessControl(Storage(tmp_path), frozenset({ADMIN}))
    assert restarted.is_allowed(200)
    restarted.reject(200)
    assert not restarted.is_allowed(200)
    assert restarted.request(200, "Оля", None) is False  # відхилений не створює нових запитів
    assert AccessControl(Storage(tmp_path), frozenset({ADMIN})).status(200) == "rejected"
