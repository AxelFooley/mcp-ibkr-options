"""Configuration management for MCP IBKR Options server."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MCP Server settings
    host: str = Field(default="0.0.0.0", description="MCP server host")
    port: int = Field(default=8000, description="MCP server port")
    log_level: str = Field(default="INFO", description="Logging level")

    # IBKR connection settings
    ibkr_host: str = Field(default="127.0.0.1", description="IB Gateway/TWS host")
    ibkr_port: int = Field(default=7496, description="IB Gateway/TWS port")
    ibkr_client_id: int = Field(default=1, description="IB client ID")
    ibkr_timeout: int = Field(default=30, description="IB connection timeout in seconds")

    # Session management
    session_timeout_minutes: int = Field(
        default=5, description="Session timeout in minutes"
    )
    session_cleanup_interval_seconds: int = Field(
        default=60, description="How often to check for stale sessions"
    )

    # Market data settings
    market_data_type: int = Field(
        default=4,
        description="Market data type: 1=live, 2=frozen, 3=delayed, 4=delayed frozen",
    )

    # Default option chain settings
    default_strike_count: int = Field(
        default=20, description="Default number of strikes above/below current price"
    )
    default_strike_range_pct: float = Field(
        default=20.0, description="Default percentage range for strikes"
    )

    def __repr__(self) -> str:
        """Safe representation without sensitive data."""
        return (
            f"Settings(host={self.host}, port={self.port}, "
            f"ibkr_host={self.ibkr_host}, ibkr_port={self.ibkr_port})"
        )


# Global settings instance
settings = Settings()
