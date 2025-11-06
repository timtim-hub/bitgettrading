"""Configuration for Bitget trading system."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingConfig(BaseSettings):
    """Trading configuration with type validation."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Bitget API Credentials
    bitget_api_key: str = Field(default="", alias="BITGET_API_KEY")
    bitget_api_secret: str = Field(default="", alias="BITGET_API_SECRET")
    bitget_passphrase: str = Field(default="", alias="BITGET_PASSPHRASE")

    # Trading Parameters
    symbol: str = Field(default="BTCUSDT", alias="SYMBOL")
    product_type: str = Field(default="USDT-FUTURES")
    leverage: int = Field(default=5, ge=1, le=125, alias="LEVERAGE")
    max_position_usd: float = Field(default=1000.0, gt=0)
    
    # Risk Management
    daily_loss_limit: float = Field(default=0.10, gt=0, lt=1)
    max_drawdown_pct: float = Field(default=0.15, gt=0, lt=1)
    kill_switch_spread_bps: float = Field(default=20.0, gt=0)
    kill_switch_depth_usd: float = Field(default=5000.0, gt=0)
    
    # Model Parameters
    prediction_horizon_sec: int = Field(default=10, ge=5, le=60)
    label_threshold_bps: float = Field(default=1.0, gt=0)  # 0.01% = 1bp
    feature_window_sec: int = Field(default=30, ge=10)
    
    # LightGBM
    lgbm_n_estimators: int = Field(default=100, ge=10)
    lgbm_max_depth: int = Field(default=5, ge=3, le=10)
    lgbm_learning_rate: float = Field(default=0.1, gt=0, le=1)
    
    # Signal Thresholds
    signal_long_threshold: float = Field(default=0.6, gt=0.5, lt=1.0)
    signal_short_threshold: float = Field(default=0.6, gt=0.5, lt=1.0)
    signal_margin: float = Field(default=0.1, ge=0, lt=0.5)
    
    # Data Collection
    orderbook_levels: int = Field(default=5, ge=1, le=20)
    feature_interval_ms: int = Field(default=1000, ge=100, le=5000)
    
    # Exchange Parameters
    taker_fee: float = Field(default=0.0006)  # 0.06% Bitget taker
    maker_fee: float = Field(default=0.0002)  # 0.02% Bitget maker
    slippage_bps: float = Field(default=2.0)  # 2 basis points
    
    # System
    sandbox: bool = Field(default=True, alias="SANDBOX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    model_path: str = Field(default="models/lgbm_model.txt")
    data_path: str = Field(default="data/market_data.csv")

    def validate_credentials(self) -> bool:
        """Check if API credentials are set."""
        return bool(
            self.bitget_api_key and self.bitget_api_secret and self.bitget_passphrase
        )


def get_config() -> TradingConfig:
    """Get validated trading configuration."""
    return TradingConfig()

