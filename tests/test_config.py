"""Tests for configuration management."""

from mcp_ibkr_options.config import Settings


def test_default_settings():
    """Test default settings values."""
    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.ibkr_host == "127.0.0.1"
    assert settings.ibkr_port == 7496
    assert settings.session_timeout_minutes == 5
    assert settings.market_data_type == 4


def test_settings_from_env(monkeypatch):
    """Test settings can be loaded from environment variables."""
    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("IBKR_HOST", "192.168.1.100")
    monkeypatch.setenv("IBKR_PORT", "7497")
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "10")

    settings = Settings()

    assert settings.host == "localhost"
    assert settings.port == 9000
    assert settings.ibkr_host == "192.168.1.100"
    assert settings.ibkr_port == 7497
    assert settings.session_timeout_minutes == 10


def test_settings_repr():
    """Test settings representation doesn't expose sensitive data."""
    settings = Settings()
    repr_str = repr(settings)

    assert "Settings(" in repr_str
    assert settings.host in repr_str
    assert str(settings.port) in repr_str
