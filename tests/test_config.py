from pathlib import Path

from bot.config import _data_dir


def test_data_dir_default(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    assert _data_dir() == Path("./data")


def test_data_dir_uses_railway_volume(monkeypatch):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert _data_dir() == Path("/data").resolve()

    # DATA_DIR поза Volume (наприклад, ./data з .env.example) не має губити дані
    monkeypatch.setenv("DATA_DIR", "./data")
    assert _data_dir() == Path("/data").resolve()

    monkeypatch.setenv("DATA_DIR", "/data/bot")
    assert _data_dir() == Path("/data/bot").resolve()
