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
    
    # Backtesting
    backtest_enabled: bool = Field(default=True, alias="BACKTEST_ENABLED")
    backtest_interval_hours: int = Field(default=6, ge=1, alias="BACKTEST_INTERVAL_HOURS")
    backtest_lookback_days: int = Field(default=3, ge=1, alias="BACKTEST_LOOKBACK_DAYS")  # Reduced from 7 to 3 for speed
    backtest_min_trades: int = Field(default=5, ge=1, alias="BACKTEST_MIN_TRADES")  # Reduced from 10 to 5 for speed
    backtest_parallel_tokens: int = Field(default=50, ge=1, alias="BACKTEST_PARALLEL_TOKENS")  # Increased from 20 to 50 for speed
    
    # Filtering
    filter_losing_tokens: bool = Field(default=True, alias="FILTER_LOSING_TOKENS")
    filter_min_win_rate: float = Field(default=0.50, ge=0, le=1, alias="FILTER_MIN_WIN_RATE")
    filter_min_roi: float = Field(default=0.0, alias="FILTER_MIN_ROI")
    filter_min_sharpe: float = Field(default=0.5, ge=0, alias="FILTER_MIN_SHARPE")
    filter_min_profit_factor: float = Field(default=1.0, ge=0, alias="FILTER_MIN_PROFIT_FACTOR")
    
    # Dynamic Parameters
    dynamic_params_enabled: bool = Field(default=True, alias="DYNAMIC_PARAMS_ENABLED")
    trailing_tp_best_tokens: float = Field(default=0.06, ge=0, le=0.10, alias="TRAILING_TP_BEST_TOKENS")
    trailing_tp_good_tokens: float = Field(default=0.05, ge=0, le=0.10, alias="TRAILING_TP_GOOD_TOKENS")
    trailing_tp_average_tokens: float = Field(default=0.04, ge=0, le=0.10, alias="TRAILING_TP_AVERAGE_TOKENS")
    trailing_tp_poor_tokens: float = Field(default=0.03, ge=0, le=0.10, alias="TRAILING_TP_POOR_TOKENS")
    position_size_best_multiplier: float = Field(default=1.3, ge=0.5, le=2.0, alias="POSITION_SIZE_BEST_MULTIPLIER")
    position_size_good_multiplier: float = Field(default=1.15, ge=0.5, le=2.0, alias="POSITION_SIZE_GOOD_MULTIPLIER")
    position_size_poor_multiplier: float = Field(default=0.8, ge=0.5, le=2.0, alias="POSITION_SIZE_POOR_MULTIPLIER")

    def validate_credentials(self) -> bool:
        """Check if API credentials are set."""
        return bool(
            self.bitget_api_key and self.bitget_api_secret and self.bitget_passphrase
        )


def get_config() -> TradingConfig:
    """Get validated trading configuration."""
    return TradingConfig()

