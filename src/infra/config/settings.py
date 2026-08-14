import os
from enum import Enum

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Timeframe(str, Enum):
    TICK = "tick"
    S1 = "1s"
    S5 = "5s"
    S15 = "15s"
    S30 = "30s"
    M1 = "1m"
    M2 = "2m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H3 = "3h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1M"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class DataSource(str, Enum):
    MT5 = "mt5"
    CTRADER = "ctrader"
    CCXT = "ccxt"
    REST = "rest"
    SYNTHETIC = "synthetic"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class BrokerType(str, Enum):
    MT5 = "mt5"
    CTRADER = "ctrader"
    CCXT = "ccxt"


class AssetClass(str, Enum):
    FOREX = "forex"
    METALS = "metals"
    CRYPTO = "crypto"
    INDICES = "indices"
    ENERGY = "energy"
    AGRICULTURE = "agriculture"


class SignalType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    REVERSE = "reverse"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"
    ADJUST_SL = "adjust_sl"
    ADJUST_TP = "adjust_tp"


from src.infra.config.secrets import (
    AzureKeyVaultProvider,
    EnvProvider,
    SecretManager,
    VaultProvider,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # App
    app_name: str = "forex-trading-system"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "json"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    api_reload: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # Database - TimescaleDB
    timescale_host: str = "localhost"
    timescale_port: int = 5432
    timescale_database: str = "market_data"
    timescale_user: str = "trader"
    timescale_password: str = ""
    timescale_pool_size: int = 20
    timescale_max_overflow: int = 10
    timescale_ssl_mode: str = "prefer"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_ssl: bool = False
    redis_max_connections: int = 50
    redis_decode_responses: bool = True

    # InfluxDB
    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "trading"
    influx_bucket: str = "metrics"
    influx_timeout: int = 10000

    # NATS
    nats_servers: list[str] = ["nats://localhost:4222"]
    nats_name: str = "forex-trading-system"
    nats_max_reconnect_attempts: int = -1
    nats_reconnect_time_wait: int = 2

    # MT5
    mt5_enabled: bool = True
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_path: str = ""
    mt5_timeout: int = 60000
    mt5_portable: bool = False

    # cTrader
    ctrader_enabled: bool = False
    ctrader_client_id: str = ""
    ctrader_client_secret: str = ""
    ctrader_access_token: str = ""
    ctrader_refresh_token: str = ""
    ctrader_host: str = "demo.ctraderapi.com"
    ctrader_port: int = 443

    # CCXT
    ccxt_enabled: bool = True
    ccxt_exchanges: list[str] = ["binance", "bybit", "kraken"]
    ccxt_api_keys: dict = {}
    ccxt_rate_limit: int = 1200
    ccxt_timeout: int = 30000
    ccxt_enable_rate_limit: bool = True
    ccxt_options: dict = {}

    # REST Data Providers
    twelve_data_api_key: str = ""
    alpha_vantage_api_key: str = ""
    polygon_api_key: str = ""
    finnhub_api_key: str = ""

    # Strategy
    strategy_ml_models_path: str = "./models"
    strategy_feature_lookback: int = 100
    strategy_prediction_horizon: int = 10
    strategy_ensemble_method: str = "weighted_average"
    strategy_min_confidence: float = 0.6
    strategy_max_concurrent_signals: int = 10
    strategy_signal_expiry_seconds: int = 300

    # Risk
    risk_max_portfolio_risk: float = 0.02
    risk_max_drawdown: float = 0.10
    risk_max_correlation: float = 0.7
    risk_max_leverage: float = 10.0
    risk_var_confidence: float = 0.99
    risk_var_horizon_days: int = 1
    risk_max_position_size_pct: float = 0.10
    risk_max_sector_exposure: float = 0.30
    risk_stop_out_level: float = 0.50
    risk_margin_call_level: float = 0.80
    risk_daily_loss_limit: float = 0.05
    risk_weekly_loss_limit: float = 0.10
    risk_monthly_loss_limit: float = 0.20

    # Trading Mode
    simulation_mode: bool = False  # False = live/demo trading, True = simulation
    demo_account: bool = True  # Use demo account when simulation_mode=False

    # Execution
    execution_default_algorithm: str = "adaptive"
    execution_max_slippage_bps: int = 5
    execution_partial_fill_timeout: int = 30
    execution_max_order_age_seconds: int = 300
    execution_retry_attempts: int = 3
    execution_retry_delay_seconds: int = 1
    execution_use_smart_routing: bool = True
    execution_min_order_size: float = 0.01
    execution_max_order_size: float = 100.0

    # Backtesting
    backtest_initial_capital: float = 100000.0
    backtest_commission_per_lot: float = 7.0
    backtest_spread_bps: int = 10
    backtest_slippage_bps: int = 2
    backtest_max_positions: int = 20
    backtest_allow_short: bool = True
    backtest_margin_requirement: float = 0.01

    # Monitoring
    monitoring_prometheus_port: int = 9090
    monitoring_grafana_dashboard: str = "forex-trading"
    monitoring_alert_webhook_telegram: str = ""
    monitoring_alert_webhook_discord: str = ""
    monitoring_alert_webhook_email: str = ""
    monitoring_health_check_interval: int = 30

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501
    dashboard_theme: str = "dark"
    dashboard_auto_refresh_seconds: int = 5

    # Secrets
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    api_key_header: str = "X-API-Key"

    # Secret Manager
    secret_manager: SecretManager | None = None

    @field_validator("ccxt_exchanges", mode="before")
    @classmethod
    def parse_exchanges(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v

    @field_validator("ccxt_api_keys", mode="before")
    @classmethod
    def parse_api_keys(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v or {}

    @property
    def timescale_dsn(self) -> str:
        return (
            f"postgresql://{self.timescale_user}:{self.timescale_password}"
            f"@{self.timescale_host}:{self.timescale_port}/{self.timescale_database}"
            f"?sslmode={self.timescale_ssl_mode}"
        )

    @property
    def redis_url(self) -> str:
        scheme = "rediss" if self.redis_ssl else "redis"
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def nats_url(self) -> str:
        return self.nats_servers[0] if self.nats_servers else "nats://localhost:4222"
    
    def get_secret_manager(self) -> SecretManager:
        """Get or create secret manager with configured providers."""
        if self.secret_manager is not None:
            return self.secret_manager
        
        # Initialize secret manager based on environment
        vault_url = os.environ.get("VAULT_URL")
        vault_token = os.environ.get("VAULT_TOKEN")
        vault_role_id = os.environ.get("VAULT_ROLE_ID")
        vault_secret_id = os.environ.get("VAULT_SECRET_ID")
        azure_vault_url = os.environ.get("AZURE_KEY_VAULT_URL")
        
        providers = []
        
        # Vault provider
        if vault_url:
            vault_provider = VaultProvider(
                url=vault_url,
                token=vault_token,
                role_id=vault_role_id,
                secret_id=vault_secret_id,
                mount_point=os.environ.get("VAULT_MOUNT", "secret"),
            )
            if vault_provider.health_check():
                providers.append(vault_provider)
        
        # Azure Key Vault provider
        if azure_vault_url:
            azure_provider = AzureKeyVaultProvider(vault_url=azure_vault_url)
            if azure_provider.health_check():
                providers.append(azure_provider)
        
        # Env provider (always as fallback)
        providers.append(EnvProvider(prefix="FOREX_"))
        
        self.secret_manager = SecretManager()
        self.secret_manager.providers = providers
        return self.secret_manager


settings = Settings()