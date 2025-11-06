"""Configuration management using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingConfig(BaseSettings):
    """Trading configuration with type validation."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # API Credentials
    bitget_api_key: str = Field(default="", alias="BITGET_API_KEY")
    bitget_api_secret: str = Field(default="", alias="BITGET_API_SECRET")
    bitget_passphrase: str = Field(default="", alias="BITGET_PASSPHRASE")

    # Trading Parameters
    symbol: str = Field(default="SOL/USDT:USDT", alias="SYMBOL")
    timeframe: str = Field(default="1m", alias="TIMEFRAME")
    leverage: int = Field(default=50, ge=1, le=125, alias="LEVERAGE")
    risk_per_trade: float = Field(default=0.008, gt=0, lt=1, alias="RISK_PER_TRADE")
    max_position_pct: float = Field(default=0.5, gt=0, le=1, alias="MAX_POSITION_PCT")
    daily_loss_limit: float = Field(default=0.10, gt=0, lt=1, alias="DAILY_LOSS_LIMIT")

    # Model Parameters
    seq_len: int = Field(default=60, ge=10)
    batch_size: int = Field(default=64, ge=1)
    n_features: int = Field(default=47)
    lstm_hidden: int = Field(default=178)
    gru_hidden: int = Field(default=92)
    dropout: float = Field(default=0.31, ge=0, le=1)

    # Exchange Parameters
    fee: float = Field(default=0.0006, ge=0)
    slippage: float = Field(default=0.0005, ge=0)
    sandbox: bool = Field(default=True, alias="SANDBOX")

    # System
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    model_path: str = Field(default="models/sol_model_2025.pth")

    def validate_credentials(self) -> bool:
        """Check if API credentials are set."""
        return bool(
            self.bitget_api_key and self.bitget_api_secret and self.bitget_passphrase
        )


def get_config() -> TradingConfig:
    """Get validated trading configuration."""
    return TradingConfig()

