-- TimescaleDB Initialization Script
-- Run on first database creation

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Set search path
ALTER DATABASE market_data SET search_path = market_data, trading, analytics, public;

-- ============================================
-- MARKET DATA TABLES
-- ============================================

-- Symbols reference table
CREATE TABLE IF NOT EXISTS market_data.symbols (
    symbol_id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL UNIQUE,
    base_currency VARCHAR(10) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    asset_class VARCHAR(20) NOT NULL,
    sector VARCHAR(50),
    exchange VARCHAR(50),
    broker VARCHAR(50),
    contract_size DECIMAL(20, 8) DEFAULT 1.0,
    tick_size DECIMAL(20, 8) DEFAULT 0.00001,
    tick_value DECIMAL(20, 8) DEFAULT 1.0,
    min_volume DECIMAL(20, 8) DEFAULT 0.01,
    max_volume DECIMAL(20, 8) DEFAULT 100.0,
    volume_step DECIMAL(20, 8) DEFAULT 0.01,
    swap_long DECIMAL(10, 4) DEFAULT 0.0,
    swap_short DECIMAL(10, 4) DEFAULT 0.0,
    margin_currency VARCHAR(10) DEFAULT 'USD',
    margin_rate DECIMAL(10, 4) DEFAULT 0.01,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_symbols_asset_class ON market_data.symbols(asset_class);
CREATE INDEX IF NOT EXISTS idx_symbols_broker ON market_data.symbols(broker);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON market_data.symbols(is_active);

-- Tick data hypertable
CREATE TABLE IF NOT EXISTS market_data.ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    bid DECIMAL(20, 8) NOT NULL,
    ask DECIMAL(20, 8) NOT NULL,
    last DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    flags INTEGER DEFAULT 0,
    source VARCHAR(20) NOT NULL
);

SELECT create_hypertable('market_data.ticks', 'time', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON market_data.ticks (symbol_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_ticks_source ON market_data.ticks (source);

-- Add compression policy for older ticks
ALTER TABLE market_data.ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol_id'
);

SELECT add_compression_policy('market_data.ticks', INTERVAL '7 days', if_not_exists => TRUE);

-- OHLCV Bars hypertable (multiple timeframes)
CREATE TABLE IF NOT EXISTS market_data.bars (
    time TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    timeframe VARCHAR(10) NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    spread DECIMAL(20, 8) DEFAULT 0,
    tick_count INTEGER DEFAULT 0,
    source VARCHAR(20) NOT NULL,
    is_complete BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (time, symbol_id, timeframe)
);

SELECT create_hypertable('market_data.bars', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS idx_bars_symbol_timeframe_time ON market_data.bars (symbol_id, timeframe, time DESC);
CREATE INDEX IF NOT EXISTS idx_bars_source ON market_data.bars (source);
CREATE INDEX IF NOT EXISTS idx_bars_complete ON market_data.bars (is_complete);

-- Compress older bars
ALTER TABLE market_data.bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol_id, timeframe'
);

SELECT add_compression_policy('market_data.bars', INTERVAL '30 days', if_not_exists => TRUE);

-- Continuous aggregates for common timeframes
-- 1-minute bars from ticks
CREATE MATERIALIZED VIEW IF NOT EXISTS market_data.bars_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    symbol_id,
    '1m' AS timeframe,
    FIRST(bid, time) AS open,
    MAX(bid) AS high,
    MIN(bid) AS low,
    LAST(bid, time) AS close,
    SUM(volume) AS volume,
    AVG(ask - bid) AS spread,
    COUNT(*) AS tick_count,
    'mt5' AS source,
    TRUE AS is_complete
FROM market_data.ticks
GROUP BY bucket, symbol_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('market_data.bars_1m',
    start_offset => INTERVAL '3 minutes',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- 5-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS market_data.bars_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minute', bucket) AS bucket,
    symbol_id,
    '5m' AS timeframe,
    FIRST(open, bucket) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, bucket) AS close,
    SUM(volume) AS volume,
    AVG(spread) AS spread,
    SUM(tick_count) AS tick_count,
    source,
    TRUE AS is_complete
FROM market_data.bars_1m
GROUP BY bucket, symbol_id, source
WITH NO DATA;

SELECT add_continuous_aggregate_policy('market_data.bars_5m',
    start_offset => INTERVAL '10 minutes',
    end_offset => INTERVAL '5 minute',
    schedule_interval => INTERVAL '5 minute',
    if_not_exists => TRUE
);

-- 1-hour bars
CREATE MATERIALIZED VIEW IF NOT EXISTS market_data.bars_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', bucket) AS bucket,
    symbol_id,
    '1h' AS timeframe,
    FIRST(open, bucket) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, bucket) AS close,
    SUM(volume) AS volume,
    AVG(spread) AS spread,
    SUM(tick_count) AS tick_count,
    source,
    TRUE AS is_complete
FROM market_data.bars_5m
GROUP BY bucket, symbol_id, source
WITH NO DATA;

SELECT add_continuous_aggregate_policy('market_data.bars_1h',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================
-- TRADING TABLES
-- ============================================

-- Strategies
CREATE TABLE IF NOT EXISTS trading.strategies (
    strategy_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    version VARCHAR(20) DEFAULT '1.0.0',
    asset_classes VARCHAR(50)[] DEFAULT ARRAY['forex'],
    timeframes VARCHAR(10)[] DEFAULT ARRAY['1h'],
    parameters JSONB DEFAULT '{}',
    ml_model_path VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    is_paper BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Signals
CREATE TABLE IF NOT EXISTS trading.signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id VARCHAR(100) NOT NULL REFERENCES trading.strategies(strategy_id),
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    time TIMESTAMPTZ NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    strength DECIMAL(5, 4) NOT NULL,
    entry_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    metadata JSONB DEFAULT '{}',
    expires_at TIMESTAMPTZ,
    is_executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('trading.signals', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_signals_strategy_time ON trading.signals (strategy_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading.signals (symbol_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_executed ON trading.signals (is_executed);

-- Orders
CREATE TABLE IF NOT EXISTS trading.orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id VARCHAR(100) UNIQUE,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    signal_id UUID REFERENCES trading.signals(signal_id),
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    broker VARCHAR(20) NOT NULL,
    broker_order_id VARCHAR(100),
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    stop_price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filled_volume DECIMAL(20, 8) DEFAULT 0,
    avg_fill_price DECIMAL(20, 8),
    commission DECIMAL(20, 8) DEFAULT 0,
    swap DECIMAL(20, 8) DEFAULT 0,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ
);

SELECT create_hypertable('trading.orders', 'created_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_orders_client_id ON trading.orders (client_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_broker_id ON trading.orders (broker, broker_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_strategy_time ON trading.orders (strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_symbol_time ON trading.orders (symbol_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON trading.orders (status);

-- Positions
CREATE TABLE IF NOT EXISTS trading.positions (
    position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    broker VARCHAR(20) NOT NULL,
    broker_position_id VARCHAR(100),
    direction VARCHAR(10) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    swap DECIMAL(20, 8) DEFAULT 0,
    commission DECIMAL(20, 8) DEFAULT 0,
    margin_used DECIMAL(20, 8) DEFAULT 0,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_open BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_positions_strategy ON trading.positions (strategy_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON trading.positions (symbol_id);
CREATE INDEX IF NOT EXISTS idx_positions_broker ON trading.positions (broker);
CREATE INDEX IF NOT EXISTS idx_positions_open ON trading.positions (is_open);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON trading.positions (opened_at DESC);

-- Fills/Executions
CREATE TABLE IF NOT EXISTS trading.fills (
    fill_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES trading.orders(order_id),
    symbol_id INTEGER NOT NULL REFERENCES market_data.symbols(symbol_id),
    broker VARCHAR(20) NOT NULL,
    broker_fill_id VARCHAR(100),
    side VARCHAR(10) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    commission DECIMAL(20, 8) DEFAULT 0,
    time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('trading.fills', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_fills_order ON trading.fills (order_id);
CREATE INDEX IF NOT EXISTS idx_fills_symbol_time ON trading.fills (symbol_id, time DESC);

-- ============================================
-- ANALYTICS TABLES
-- ============================================

-- Portfolio equity curve
CREATE TABLE IF NOT EXISTS analytics.equity_curve (
    time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    broker VARCHAR(20),
    equity DECIMAL(20, 8) NOT NULL,
    balance DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    margin_used DECIMAL(20, 8) DEFAULT 0,
    free_margin DECIMAL(20, 8) DEFAULT 0,
    margin_level DECIMAL(10, 4),
    drawdown_pct DECIMAL(10, 4) DEFAULT 0,
    daily_pnl DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, strategy_id, broker)
);

SELECT create_hypertable('analytics.equity_curve', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_equity_strategy_time ON analytics.equity_curve (strategy_id, time DESC);

-- Performance metrics (daily snapshots)
CREATE TABLE IF NOT EXISTS analytics.performance_metrics (
    date DATE NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    broker VARCHAR(20),
    total_return DECIMAL(10, 6),
    daily_return DECIMAL(10, 6),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    calmar_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 6),
    current_drawdown DECIMAL(10, 6),
    win_rate DECIMAL(5, 4),
    profit_factor DECIMAL(10, 4),
    expectancy DECIMAL(20, 8),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    largest_win DECIMAL(20, 8),
    largest_loss DECIMAL(20, 8),
    avg_trade_duration INTERVAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, strategy_id, broker)
);

-- Risk metrics
CREATE TABLE IF NOT EXISTS analytics.risk_metrics (
    time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    portfolio_var_95 DECIMAL(20, 8),
    portfolio_var_99 DECIMAL(20, 8),
    portfolio_es_95 DECIMAL(20, 8),
    portfolio_es_99 DECIMAL(20, 8),
    max_position_var DECIMAL(20, 8),
    correlation_risk DECIMAL(5, 4),
    concentration_risk DECIMAL(5, 4),
    leverage DECIMAL(10, 4),
    margin_level DECIMAL(10, 4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, strategy_id)
);

SELECT create_hypertable('analytics.risk_metrics', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_symbols_updated_at BEFORE UPDATE ON market_data.symbols
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at BEFORE UPDATE ON trading.strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON trading.orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON trading.positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to get latest bar
CREATE OR REPLACE FUNCTION market_data.get_latest_bar(
    p_symbol_id INTEGER,
    p_timeframe VARCHAR(10),
    p_source VARCHAR(20) DEFAULT 'mt5'
)
RETURNS TABLE (
    time TIMESTAMPTZ,
    open DECIMAL(20, 8),
    high DECIMAL(20, 8),
    low DECIMAL(20, 8),
    close DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    spread DECIMAL(20, 8)
) AS $$
BEGIN
    RETURN QUERY
    SELECT b.time, b.open, b.high, b.low, b.close, b.volume, b.spread
    FROM market_data.bars b
    WHERE b.symbol_id = p_symbol_id
      AND b.timeframe = p_timeframe
      AND b.source = p_source
      AND b.is_complete = TRUE
    ORDER BY b.time DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get bars for backtesting
CREATE OR REPLACE FUNCTION market_data.get_bars_range(
    p_symbol_id INTEGER,
    p_timeframe VARCHAR(10),
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_source VARCHAR(20) DEFAULT 'mt5',
    p_limit INTEGER DEFAULT 100000
)
RETURNS TABLE (
    time TIMESTAMPTZ,
    open DECIMAL(20, 8),
    high DECIMAL(20, 8),
    low DECIMAL(20, 8),
    close DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    spread DECIMAL(20, 8)
) AS $$
BEGIN
    RETURN QUERY
    SELECT b.time, b.open, b.high, b.low, b.close, b.volume, b.spread
    FROM market_data.bars b
    WHERE b.symbol_id = p_symbol_id
      AND b.timeframe = p_timeframe
      AND b.source = p_source
      AND b.is_complete = TRUE
      AND b.time >= p_start_time
      AND b.time <= p_end_time
    ORDER BY b.time ASC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- RISK TABLES
-- ============================================

CREATE SCHEMA IF NOT EXISTS risk;

-- Risk alerts
CREATE TABLE IF NOT EXISTS risk.alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    symbol_id INTEGER REFERENCES market_data.symbols(symbol_id),
    current_value DECIMAL(20, 8),
    limit_value DECIMAL(20, 8),
    metadata JSONB DEFAULT '{}'
);

SELECT create_hypertable('risk.alerts', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_alerts_type_time ON risk.alerts (alert_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_strategy_time ON risk.alerts (strategy_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON risk.alerts (severity);

-- Circuit breaker events
CREATE TABLE IF NOT EXISTS risk.circuit_breaker_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    circuit_breaker_name VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    trigger_alert_type VARCHAR(50),
    trigger_value DECIMAL(20, 8),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

SELECT create_hypertable('risk.circuit_breaker_events', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_cb_events_name_time ON risk.circuit_breaker_events (circuit_breaker_name, timestamp DESC);

-- Risk metrics (detailed)
CREATE TABLE IF NOT EXISTS risk.risk_metrics (
    time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    broker VARCHAR(20),
    var_95_1d DECIMAL(20, 8),
    var_99_1d DECIMAL(20, 8),
    var_95_10d DECIMAL(20, 8),
    var_99_10d DECIMAL(20, 8),
    es_95_1d DECIMAL(20, 8),
    es_99_1d DECIMAL(20, 8),
    portfolio_volatility DECIMAL(20, 8),
    portfolio_beta DECIMAL(20, 8),
    max_drawdown DECIMAL(20, 8),
    current_drawdown DECIMAL(20, 8),
    gross_leverage DECIMAL(10, 4),
    net_leverage DECIMAL(10, 4),
    max_position_pct DECIMAL(10, 6),
    herfindahl_index DECIMAL(10, 6),
    effective_positions DECIMAL(10, 2),
    avg_correlation DECIMAL(10, 4),
    max_correlation DECIMAL(10, 4),
    skewness DECIMAL(10, 4),
    kurtosis DECIMAL(10, 4),
    stress_scenarios JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, strategy_id, broker)
);

SELECT create_hypertable('risk.risk_metrics', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_risk_metrics_strategy_time ON risk.risk_metrics (strategy_id, time DESC);

-- Portfolio returns for VaR calculation
CREATE TABLE IF NOT EXISTS risk.portfolio_returns (
    time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    broker VARCHAR(20),
    return_pct DECIMAL(20, 8) NOT NULL,
    equity DECIMAL(20, 8) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, strategy_id, broker)
);

SELECT create_hypertable('risk.portfolio_returns', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_returns_strategy_time ON risk.portfolio_returns (strategy_id, time DESC);

-- Drawdown tracking
CREATE TABLE IF NOT EXISTS risk.drawdown_tracking (
    time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(100) REFERENCES trading.strategies(strategy_id),
    broker VARCHAR(20),
    peak_equity DECIMAL(20, 8) NOT NULL,
    current_equity DECIMAL(20, 8) NOT NULL,
    drawdown_pct DECIMAL(10, 6) NOT NULL,
    is_new_peak BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, strategy_id, broker)
);

SELECT create_hypertable('risk.drawdown_tracking', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_drawdown_strategy_time ON risk.drawdown_tracking (strategy_id, time DESC);

-- Risk limits configuration (for audit trail)
CREATE TABLE IF NOT EXISTS risk.limits_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    limit_name VARCHAR(100) NOT NULL,
    old_value DECIMAL(20, 8),
    new_value DECIMAL(20, 8),
    changed_by VARCHAR(100),
    reason TEXT
);

-- Grant permissions
GRANT USAGE ON SCHEMA risk TO trader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA risk TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA risk TO trader;

-- ============================================
-- RISK FUNCTIONS
-- ============================================

-- Function to log circuit breaker event
CREATE OR REPLACE FUNCTION risk.log_circuit_breaker_event(
    p_circuit_breaker_name VARCHAR(100),
    p_action VARCHAR(100),
    p_trigger_alert_type VARCHAR(50),
    p_trigger_value DECIMAL(20, 8),
    p_success BOOLEAN,
    p_error_message TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO risk.circuit_breaker_events (
        circuit_breaker_name, action, trigger_alert_type,
        trigger_value, success, error_message, metadata
    ) VALUES (
        p_circuit_breaker_name, p_action, p_trigger_alert_type,
        p_trigger_value, p_success, p_error_message, p_metadata
    );
END;
$$ LANGUAGE plpgsql;

-- Function to update drawdown tracking
CREATE OR REPLACE FUNCTION risk.update_drawdown_tracking(
    p_strategy_id VARCHAR(100),
    p_broker VARCHAR(20),
    p_current_equity DECIMAL(20, 8)
)
RETURNS VOID AS $$
DECLARE
    v_peak_equity DECIMAL(20, 8);
    v_drawdown_pct DECIMAL(10, 6);
    v_is_new_peak BOOLEAN := FALSE;
BEGIN
    -- Get current peak
    SELECT peak_equity INTO v_peak_equity
    FROM risk.drawdown_tracking
    WHERE strategy_id = p_strategy_id AND broker = p_broker
    ORDER BY time DESC
    LIMIT 1;
    
    IF v_peak_equity IS NULL OR p_current_equity > v_peak_equity THEN
        v_peak_equity := p_current_equity;
        v_is_new_peak := TRUE;
    END IF;
    
    v_drawdown_pct := (v_peak_equity - p_current_equity) / v_peak_equity;
    
    INSERT INTO risk.drawdown_tracking (
        strategy_id, broker, peak_equity, current_equity, drawdown_pct, is_new_peak
    ) VALUES (
        p_strategy_id, p_broker, v_peak_equity, p_current_equity, v_drawdown_pct, v_is_new_peak
    );
END;
$$ LANGUAGE plpgsql;

-- Function to calculate portfolio returns
CREATE OR REPLACE FUNCTION risk.calculate_portfolio_returns(
    p_strategy_id VARCHAR(100),
    p_broker VARCHAR(20),
    p_time_window INTERVAL DEFAULT '24 hours'
)
RETURNS VOID AS $$
BEGIN
    -- This would calculate returns from equity curve
    -- Simplified for now
    INSERT INTO risk.portfolio_returns (strategy_id, broker, return_pct, equity)
    SELECT 
        p_strategy_id,
        p_broker,
        (equity - LAG(equity) OVER (ORDER BY time)) / LAG(equity) OVER (ORDER BY time) * 100,
        equity
    FROM analytics.equity_curve
    WHERE strategy_id = p_strategy_id 
      AND broker = p_broker
      AND time > NOW() - p_time_window
      AND equity IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- Grant execute on risk functions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA risk TO trader;

-- ============================================
-- END OF RISK TABLES
-- ============================================

-- Set default privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA market_data, trading, analytics
    GRANT ALL PRIVILEGES ON TABLES TO trader;
ALTER DEFAULT PRIVILEGES IN SCHEMA market_data, trading, analytics
    GRANT ALL PRIVILEGES ON SEQUENCES TO trader;
ALTER DEFAULT PRIVILEGES IN SCHEMA market_data, trading, analytics
    GRANT EXECUTE ON FUNCTIONS TO trader;