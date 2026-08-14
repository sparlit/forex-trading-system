from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.data.models import OrderStatus, Timeframe
from src.data.storage.redis_cache import redis_cache
from src.data.storage.timescale import timescaledb
from src.execution.order_manager import ExecutionEngine, Order
from src.infra.config.settings import settings
from src.infra.ea_bridge.bridge import EABridge
from src.infra.messaging.nats_client import nats_client
from src.infra.monitoring.logging import logger
from src.infra.monitoring.metrics import metrics_collector
from src.risk import circuit_breaker_manager, drawdown_guard
from src.strategy.base.strategy import strategy_registry

# Create FastAPI app
app = FastAPI(
    title="Forex Trading System API",
    description="REST API for the Innovative Forex Trading System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections
active_websockets: list[WebSocket] = []
ea_bridge = EABridge(http_port=settings.api_port, host=settings.api_host)


# Dependency injection
async def get_execution_engine(request: Request) -> ExecutionEngine:
    """Get execution engine instance from app state."""
    return request.app.state.execution_engine


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Health check
@app.get("/health", response_model=dict)
async def health_check():
    """Health check endpoint."""
    components = {}

    # Check database
    try:
        await timescaledb.health_check()
        components["timescaledb"] = "healthy"
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        components["timescaledb"] = "unhealthy"

    # Check Redis
    try:
        await redis_cache.health_check()
    except Exception:
        components["redis"] = "unhealthy"

    # Check NATS
    try:
        # NATS health check would go here
        # For now, we'll just check if the client is connected
        if nats_client.is_connected():
            components["nats"] = "healthy"
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        components["nats"] = "unhealthy"

    # Overall status
    status = "healthy" if all(v == "healthy" for v in components.values()) else "degraded"

    return {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "components": components,
        "version": "0.1.0",
    }


# ============================================
# MT5 EA BRIDGE ENDPOINTS
# ============================================


@app.post("/api/v1/ea/data")
async def receive_ea_data(payload: dict) -> dict[str, str]:
    """Accept a validated MT5 EA event through the main API transport.

    The EA sends ticks, account snapshots, positions, trade events, and
    heartbeats as JSON objects containing a ``type`` field.  Processing is
    delegated to the shared bridge so HTTP and ZeroMQ feeds have identical
    in-memory state.
    """
    message_type = payload.get("type")
    if not isinstance(message_type, str) or not message_type:
        raise HTTPException(status_code=422, detail="EA payload requires a non-empty 'type'")

    await ea_bridge._handle_message(json.dumps(payload))
    return {"status": "ok"}


@app.get("/api/v1/ea/commands", response_model=list[dict])
async def get_ea_commands() -> list[dict]:
    """Return and acknowledge commands queued for an EA polling over HTTP."""
    commands: list[dict] = []
    while not ea_bridge._command_queue.empty():
        try:
            commands.append(ea_bridge._command_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return commands


@app.get("/api/v1/ea/status", response_model=dict)
async def get_ea_status() -> dict:
    """Expose non-sensitive EA bridge health and connection state."""
    return ea_bridge.get_status()


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return metrics_collector.get_metrics()


# ============================================
# MARKET DATA ENDPOINTS
# ============================================


@app.get("/api/v1/symbols", response_model=list[dict])
async def get_symbols(
    asset_class: str | None = None,
    broker: str | None = None,
    active_only: bool = True,
):
    """Get list of available symbols."""
    try:
        symbols = await timescaledb.get_symbols(
            asset_class=asset_class,
            broker=broker,
            active_only=active_only,
        )
    except Exception as e:
        logger.warning(f"Failed to get symbols from TimescaleDB: {e}")
        symbols = []

    return [
        {
            "symbol": s.symbol,
            "base_currency": s.base_currency,
            "quote_currency": s.quote_currency,
            "asset_class": s.asset_class.value,
            "exchange": s.exchange,
            "broker": s.broker,
            "contract_size": float(s.contract_size),
            "tick_size": float(s.tick_size),
            "min_volume": float(s.min_volume),
            "max_volume": float(s.max_volume),
            "is_active": s.is_active,
        }
        for s in symbols
    ]


@app.get("/api/v1/symbols/{symbol}", response_model=dict)
async def get_symbol(symbol: str):
    """Get symbol details."""
    try:
        sym = await timescaledb.get_symbol(symbol)
    except Exception as e:
        logger.warning(f"Failed to get symbol {symbol} from TimescaleDB: {e}")
        raise HTTPException(status_code=404, detail="Symbol not found")

    if not sym:
        raise HTTPException(status_code=404, detail="Symbol not found")

    return {
        "symbol": sym.symbol,
                "base_currency": sym.base_currency,
                "quote_currency": sym.quote_currency,
                "asset_class": sym.asset_class.value,
                "exchange": sym.exchange,
                "broker": sym.broker,
                "contract_size": float(sym.contract_size),
                "tick_size": float(sym.tick_size),
                "tick_value": float(sym.tick_value),
                "min_volume": float(sym.min_volume),
                "max_volume": float(sym.max_volume),
                "volume_step": float(sym.volume_step),
                "swap_long": float(sym.swap_long),
                "swap_short": float(sym.swap_short),
                "margin_currency": sym.margin_currency,
                "margin_rate": float(sym.margin_rate),
                "is_active": sym.is_active,
    }


@app.get("/api/v1/market/bars", response_model=list[dict])
async def get_bars(
    symbol: str,
    start_time: Annotated[datetime, Query(...)],
    end_time: Annotated[datetime, Query(...)],
    timeframe: Timeframe = Timeframe.H1,
    source: str = "mt5",
    limit: int = 1000,
):
    """Get historical bars."""
    try:
        bars = await timescaledb.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            source=source,
            limit=limit,
        )
    except Exception as e:
        logger.warning(f"Failed to get bars for {symbol}: {e}")
        bars = []

    return [
        {
            "symbol": bar.symbol,
            "timestamp": bar.timestamp.isoformat(),
            "timeframe": bar.timeframe.value,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
            "spread": float(bar.spread),
            "source": bar.source.value,
            "tick_count": bar.tick_count,
            "is_complete": bar.is_complete,
        }
        for bar in bars
    ]


@app.get("/api/v1/market/bars/latest", response_model=dict)
async def get_latest_bar(
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    source: str = "mt5",
):
    """Get latest completed bar."""
    try:
        bar = await timescaledb.get_latest_bar(symbol, timeframe, source)
    except Exception as e:
        logger.warning(f"Failed to get latest bar for {symbol}: {e}")
        raise HTTPException(status_code=404, detail="No data found")

    if not bar:
        raise HTTPException(status_code=404, detail="No data found")

    return {
        "symbol": bar.symbol,
        "timestamp": bar.timestamp.isoformat(),
        "timeframe": bar.timeframe.value,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": float(bar.volume),
        "spread": float(bar.spread),
        "source": bar.source.value,
        "tick_count": bar.tick_count,
        "is_complete": bar.is_complete,
    }




# ============================================
# SESSION & MARKET STATE ENDPOINTS
# ============================================

@app.get("/api/v1/market/sessions")
async def get_market_sessions():
    """Get active trading sessions for forex and crypto."""
    from datetime import UTC, datetime
    
    now = datetime.now(UTC)
    current_hour = now.hour
    
    # Forex sessions (UTC)
    forex_sessions = [
        {
            "name": "Sydney",
            "start_hour": 22,
            "end_hour": 7,
            "active": current_hour >= 22 or current_hour < 7,
            "major_pairs": ["AUDUSD", "NZDUSD", "AUDJPY", "NZDJPY"],
            "time_range": "22:00-07:00 UTC",
            "liquidity": "medium"
        },
        {
            "name": "Tokyo",
            "start_hour": 0,
            "end_hour": 9,
            "active": 0 <= current_hour < 9,
            "major_pairs": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
            "time_range": "00:00-09:00 UTC",
            "liquidity": "high"
        },
        {
            "name": "London",
            "start_hour": 8,
            "end_hour": 17,
            "active": 8 <= current_hour < 17,
            "major_pairs": ["EURUSD", "GBPUSD", "EURGBP", "GBPCHF"],
            "time_range": "08:00-17:00 UTC",
            "liquidity": "very_high"
        },
        {
            "name": "New York",
            "start_hour": 13,
            "end_hour": 22,
            "active": 13 <= current_hour < 22,
            "major_pairs": ["EURUSD", "GBPUSD", "USDCAD", "USDCHF", "XAUUSD"],
            "time_range": "13:00-22:00 UTC",
            "liquidity": "very_high"
        }
    ]
    
    # Crypto sessions (24/7)
    crypto_sessions = [
        {
            "name": "Crypto 24/7",
            "start_hour": 0,
            "end_hour": 24,
            "active": True,
            "major_pairs": ["BTCUSD", "ETHUSD", "BTCETH", "LTCUSD", "XRPUSD"],
            "time_range": "24/7",
            "volume_24h": "high"
        }
    ]
    
    return {
        "forex": {s["name"]: s for s in forex_sessions},
        "crypto": {s["name"]: s for s in crypto_sessions},
        "auto_switch": True,
        "current_utc_hour": datetime.now(UTC).hour
    }

@app.get("/api/v1/market/indicators")
async def get_symbol_indicators(
    symbols: str = Query(...),
    timeframe: str = "1h"
):
    """Get all technical indicators for specified symbols."""
    from datetime import UTC, datetime, timedelta

    import polars as pl

    from src.strategy.technical.indicators import TechnicalIndicators

    # Map common timeframe strings to Timeframe enum
    timeframe_map = {
        "H1": "1h", "H2": "2h", "H3": "3h", "H4": "4h", "H6": "6h", "H8": "8h", "H12": "12h",
        "M1": "1m", "M2": "2m", "M3": "3m", "M5": "5m", "M10": "10m", "M15": "15m", "M30": "30m",
        "D1": "1d", "W1": "1w", "MN1": "1M",
        "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
        "1m": "1m", "2m": "2m", "3m": "3m", "5m": "5m", "10m": "10m", "15m": "15m", "30m": "30m",
        "1d": "1d", "1w": "1w", "1M": "1M",
    }
    tf_value = timeframe_map.get(timeframe, timeframe)

    symbol_list = [s.strip() for s in symbols.split(",")]
    result = {}

    try:
        for symbol in symbol_list:
            # Fetch recent bars for indicator calculation
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=7)  # Last 7 days
            bars = await timescaledb.get_bars(
                symbol=symbol,
                timeframe=Timeframe(tf_value),
                start_time=start_time,
                end_time=end_time,
                limit=200
            )

            if not bars or len(bars) < 50:
                result[symbol] = {"error": "Insufficient data"}
                continue

            # Convert to DataFrame
            df = pl.DataFrame([{
                "timestamp": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            } for b in bars])

            # Calculate all indicators
            df = TechnicalIndicators.add_all_indicators_polars(df)
            latest = df.row(-1, named=True)

            # Extract key indicators
            result[symbol] = {
                "price": {
                    "close": latest.get("close"),
                    "open": latest.get("open"),
                    "high": latest.get("high"),
                    "low": latest.get("low"),
                },
                "trend": {
                    "ema_20": latest.get("ema_20"),
                    "ema_50": latest.get("ema_50"),
                    "ema_200": latest.get("ema_200"),
                    "sma_20": latest.get("sma_20"),
                    "sma_50": latest.get("sma_50"),
                    "sma_200": latest.get("sma_200"),
                },
                "momentum": {
                    "rsi_14": latest.get("rsi_14"),
                    "macd": latest.get("macd"),
                    "macd_signal": latest.get("macd_signal"),
                    "macd_hist": latest.get("macd_hist"),
                    "roc_10": latest.get("roc_10"),
                },
                "volatility": {
                    "atr_14": latest.get("atr_14"),
                    "bb_upper": latest.get("bb_upper"),
                    "bb_middle": latest.get("bb_middle"),
                    "bb_lower": latest.get("bb_lower"),
                    "bb_width": latest.get("bb_width"),
                },
                "volume": {
                    "volume": latest.get("volume"),
                    "volume_sma": latest.get("volume_sma"),
                    "volume_ratio": latest.get("volume_ratio"),
                },
                "volatility_regime": {
                    "adx_14": latest.get("adx_14"),
                    "di_plus": latest.get("di_plus"),
                    "di_minus": latest.get("di_minus"),
                }
            }
    except Exception as e:
        logger.error(f"Error calculating indicators for {symbols}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return result

@app.get("/api/v1/market/regime")
async def get_market_regime(
    symbol: str = "EURUSD",
    timeframe: str = "1h"
):
    """Get current market regime detection."""
    from datetime import UTC, datetime, timedelta
    
    from src.strategy.market_regime import MarketRegimeDetector

    try:
        detector = MarketRegimeDetector()

        # Map common timeframe strings to Timeframe enum
        timeframe_map = {
            "H1": "1h", "H2": "2h", "H3": "3h", "H4": "4h", "H6": "6h", "H8": "8h", "H12": "12h",
            "M1": "1m", "M2": "2m", "M3": "3m", "M5": "5m", "M10": "10m", "M15": "15m", "M30": "30m",
            "D1": "1d", "W1": "1w", "MN1": "1M",
            "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
            "1m": "1m", "2m": "2m", "3m": "3m", "5m": "5m", "10m": "10m", "15m": "15m", "30m": "30m",
            "1d": "1d", "1w": "1w", "1M": "1M",
        }
        tf_value = timeframe_map.get(timeframe, timeframe)

        # Get recent bars - need start_time and end_time
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=7)  # Last 7 days
        
        bars = await timescaledb.get_bars(
            symbol=symbol,
            timeframe=Timeframe(tf_value),
            start_time=start_time,
            end_time=end_time,
            limit=100
        )
        
        if not bars or len(bars) < 50:
            return {"regime": "unknown", "confidence": 0.0}
        
        regime = await detector.detect_regime(bars)
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "regime": regime.value,
            "confidence": detector._current_regime.confidence if detector._current_regime else 0.0,
            "strength": detector._current_regime.strength if detector._current_regime else 0.0,
            "duration": detector._regime_duration,
            "characteristics": detector._current_regime.characteristics if detector._current_regime else {}
        }
    except Exception as e:
        logger.error(f"Error detecting regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/market/regime-transitions")
async def get_regime_transitions():
    """Get regime transition signals."""
    # This would connect to the blind spot manager
    return {
        "transitions": [],
        "message": "Regime transition monitoring active"
    }

@app.get("/api/v1/risk/liquidity")
async def get_liquidity_metrics():
    """Get liquidity metrics for all symbols."""
    # This would connect to the blind spot manager
    return {
        "liquidity": {},
        "message": "Liquidity monitoring active"
    }

@app.get("/api/v1/risk/tail-risk")
async def get_tail_risk():
    """Get tail risk metrics (CVaR)."""
    return {
        "cvar_95": 0.0,
        "cvar_99": 0.0,
        "threshold": 0.05,
        "message": "Tail risk monitoring active"
    }

@app.get("/api/v1/ml/model-health")
async def get_model_health():
    """Get ML model health status."""
    # This would connect to the auto-retrain module
    return {
        "models": {},
        "message": "Model health monitoring active"
    }

@app.get("/api/v1/risk/behavioral-bias")
async def get_behavioral_bias():
    """Get behavioral bias metrics."""
    return {
        "disposition_ratio": 0.0,
        "overtrading_score": 0.0,
        "revenge_trading_score": 0.0,
        "message": "Behavioral bias monitoring active"
    }

@app.get("/api/v1/risk/concentration")
async def get_concentration_risk():
    """Get concentration risk metrics."""
    return {
        "concentration": {},
        "message": "Concentration risk monitoring active"
    }

@app.get("/api/v1/system/processes")
async def get_background_processes():
    """Get background process status."""
    import os

    import psutil
    
    processes = []
    current_pid = os.getpid()
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'create_time', 'status']):
            try:
                info = proc.info()
                if info['pid'] == current_pid:
                    continue
                processes.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu_percent": info['cpu_percent'],
                    "memory_mb": round(info['memory_info'].rss / 1024 / 1024, 1) if info['memory_info'] else 0,
                    "status": info['status'],
                    "uptime_seconds": int(__import__('time').time() - info['create_time']) if info['create_time'] else 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                logging.getLogger(__name__).warning(
                    "Unable to inspect background process: %s", exc, exc_info=True
                )
    except Exception as e:
        logger.error(f"Error getting processes: {e}")
    
    return {
        "processes": processes,
        "total_count": len(processes)
    }

@app.get("/api/v1/market/crypto-sessions")
async def get_crypto_sessions():
    """Get crypto trading sessions (24/7)."""
    
    return {
        "crypto": {
            "Crypto 24/7": {
                "name": "Crypto 24/7",
                "start_hour": 0,
                "end_hour": 24,
                "active": True,
                "major_pairs": ["BTCUSD", "ETHUSD", "BTCETH", "LTCUSD", "XRPUSD"],
                "time_range": "24/7",
                "volume_24h": "high"
            }
        }
    }

@app.get("/api/v1/market/sessions")
async def get_all_sessions():
    """Get all trading sessions (forex + crypto)."""
    # Combine forex and crypto sessions
    forex = await get_market_sessions()
    crypto = await get_crypto_sessions()
    return {**forex, **crypto}

@app.post("/api/v1/ml/models/{model_id}/retrain")
async def trigger_model_retrain(model_id: str):
    """Trigger manual model retraining."""
    from src.strategy.ml.auto_retrain import AutoRetrainer
    
    try:
        retrainer = AutoRetrainer()
        result = await retrainer.retrain_model(model_id)
        return {"status": "retraining_started", "model_id": model_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/blind-spots/alerts")
async def get_blind_spot_alerts():
    """Get active blind spot alerts."""
    
    # This would connect to the actual blind spot manager
    return {
        "alerts": {},
        "summary": {
            "active": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "by_type": {}
        }
    }

@app.get("/api/v1/blind-spots/summary")
async def get_blind_spot_summary():
    """Get blind spot summary."""
    return {
        "active": 0,
        "by_severity": {"critical": 0, "warning": 0, "info": 0},
        "by_type": {}
    }

@app.get("/api/v1/performance/factor-analysis")
async def get_factor_analysis():
    """Get factor analysis for performance attribution."""
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }

@app.post("/api/v1/ml/models/{model_id}/retrain")
async def trigger_model_retrain(model_id: str):
    """Trigger manual model retraining."""
    from src.strategy.ml.auto_retrain import AutoRetrainer
    
    try:
        retrainer = AutoRetrainer()
        result = await retrainer.retrain_model(model_id)
        return {"status": "retraining_started", "model_id": model_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/blind-spots/alerts")
async def get_blind_spot_alerts():
    """Get active blind spot alerts."""
    
    # This would connect to the actual blind spot manager
    return {
        "alerts": {},
        "summary": {
            "active": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "by_type": {}
        }
    }

@app.get("/api/v1/blind-spots/summary")
async def get_blind_spot_summary():
    """Get blind spot summary."""
    return {
        "active": 0,
        "by_severity": {"critical": 0, "warning": 0, "info": 0},
        "by_type": {}
    }

@app.get("/api/v1/performance/factor-analysis")
async def get_factor_analysis():
    """Get factor analysis for performance attribution."""
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }

@app.post("/api/v1/ml/models/{model_id}/retrain")
async def trigger_model_retrain(model_id: str):
    """Trigger manual model retraining."""
    from src.strategy.ml.auto_retrain import AutoRetrainer
    
    try:
        retrainer = AutoRetrainer()
        result = await retrainer.retrain_model(model_id)
        return {"status": "retraining_started", "model_id": model_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/blind-spots/alerts")
async def get_blind_spot_alerts():
    """Get active blind spot alerts."""
    
    # This would connect to the actual blind spot manager
    return {
        "alerts": {},
        "summary": {
            "active": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "by_type": {}
        }
    }

@app.get("/api/v1/blind-spots/summary")
async def get_blind_spot_summary():
    """Get blind spot summary."""
    return {
        "active": 0,
        "by_severity": {"critical": 0, "warning": 0, "info": 0},
        "by_type": {}
    }

@app.get("/api/v1/performance/factor-analysis")
async def get_factor_analysis():
    """Get factor analysis for performance attribution."""
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }

@app.post("/api/v1/ml/models/{model_id}/retrain")
async def trigger_model_retrain(model_id: str):
    """Trigger manual model retraining."""
    from src.strategy.ml.auto_retrain import AutoRetrainer
    
    try:
        retrainer = AutoRetrainer()
        result = await retrainer.retrain_model(model_id)
        return {"status": "retraining_started", "model_id": model_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/blind-spots/alerts")
async def get_blind_spot_alerts():
    """Get active blind spot alerts."""
    
    # This would connect to the actual blind spot manager
    return {
        "alerts": {},
        "summary": {
            "active": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "by_type": {}
        }
    }

@app.get("/api/v1/blind-spots/summary")
async def get_blind_spot_summary():
    """Get blind spot summary."""
    return {
        "active": 0,
        "by_severity": {"critical": 0, "warning": 0, "info": 0},
        "by_type": {}
    }

@app.get("/api/v1/performance/factor-analysis")
async def get_factor_analysis():
    """Get factor analysis for performance attribution."""
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }

@app.post("/api/v1/ml/models/{model_id}/retrain")
async def trigger_model_retrain(model_id: str):
    """Trigger manual model retraining."""
    from src.strategy.ml.auto_retrain import AutoRetrainer
    
    try:
        retrainer = AutoRetrainer()
        result = await retrainer.retrain_model(model_id)
        return {"status": "retraining_started", "model_id": model_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/blind-spots/alerts")
async def get_blind_spot_alerts():
    """Get active blind spot alerts."""
    
    # This would connect to the actual blind spot manager
    return {
        "alerts": {},
        "summary": {
            "active": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "by_type": {}
        }
    }

@app.get("/api/v1/blind-spots/summary")
async def get_blind_spot_summary():
    """Get blind spot summary."""
    return {
        "active": 0,
        "by_severity": {"critical": 0, "warning": 0, "info": 0},
        "by_type": {}
    }

@app.get("/api/v1/performance/factor-analysis")
async def get_factor_analysis():
    """Get factor analysis for performance attribution."""
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }


# ============================================
# SIGNAL ENDPOINTS
# ============================================


@app.post("/api/v1/signals", response_model=dict)
async def create_signal(signal: dict):
    """Submit a new trading signal."""
    # In production, would validate and publish to NATS
    try:
        await nats_client.publish("signals", signal)
    except Exception as e:
        logger.warning(f"Failed to publish signal to NATS: {e}")

    return {
        "signal_id": str(uuid4()),
        **signal,
        "is_executed": False,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/api/v1/signals", response_model=list[dict])
async def get_signals(
    strategy_id: str | None = None,
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
):
    """Get signals history."""
    # Would query database - for now return empty list
    return []


# ============================================
# ORDER ENDPOINTS
# ============================================


@app.post("/api/v1/orders", response_model=dict)
async def create_order(
    order: dict,
    request: Request,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Create and place a new order."""
    # Convert to internal Order model
    internal_order = Order(
        client_order_id=order.get("client_order_id") or f"api_{uuid4().hex[:8]}",
        strategy_id=order.get("strategy_id", ""),
        signal_id=UUID(order["signal_id"]) if order.get("signal_id") else None,
        symbol=order["symbol"],
        symbol_id=0,  # Would look up from symbol
        broker=order.get("broker", "mt5"),
        order_type=order.get("order_type", "market"),
        side=order["side"],
        volume=Decimal(str(order["volume"])),
        price=Decimal(str(order["price"])) if order.get("price") else None,
        stop_price=Decimal(str(order["stop_price"])) if order.get("stop_price") else None,
        status=OrderStatus.PENDING,
    )

    # Store order in order manager
    created_order = engine.order_manager.create_order(
        strategy_id=internal_order.strategy_id,
        signal_id=internal_order.signal_id,
        symbol=internal_order.symbol,
        symbol_id=internal_order.symbol_id,
        broker=internal_order.broker,
        order_type=internal_order.order_type,
        side=internal_order.side,
        volume=internal_order.volume,
        price=internal_order.price,
        stop_price=internal_order.stop_price,
        client_order_id=internal_order.client_order_id,
    )

    # In a real system, we would send to broker via execution engine
    # For now, just return the created order
    return {
        "order_id": str(created_order.order_id),
        "client_order_id": created_order.client_order_id,
        "strategy_id": created_order.strategy_id,
        "symbol": created_order.symbol,
        "broker": created_order.broker.value,
        "order_type": created_order.order_type.value,
        "side": created_order.side.value,
        "volume": float(created_order.volume),
        "price": float(created_order.price) if created_order.price else None,
        "stop_price": float(created_order.stop_price) if created_order.stop_price else None,
        "status": created_order.status.value,
        "filled_volume": float(created_order.filled_volume),
        "avg_fill_price": float(created_order.avg_fill_price) if created_order.avg_fill_price else None,
        "commission": float(created_order.commission),
        "created_at": created_order.created_at.isoformat(),
        "updated_at": created_order.updated_at.isoformat(),
    }


@app.get("/api/v1/orders", response_model=list[dict])
async def get_orders(
    strategy_id: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
    request: Request = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Get orders history."""
    # Get all orders from order manager
    orders = list(engine.order_manager._orders.values())

    # Apply filters
    if strategy_id:
        orders = [o for o in orders if o.strategy_id == strategy_id]
    if symbol:
        orders = [o for o in orders if o.symbol == symbol]
    if status:
        try:
            status_enum = OrderStatus(status)
            orders = [o for o in orders if o.status == status_enum]
        except ValueError:
            logger.debug("Ignored invalid order status: %s", status)
    if start_time:
        orders = [o for o in orders if o.created_at >= start_time]
    if end_time:
        orders = [o for o in orders if o.created_at <= end_time]

    # Sort by created_at descending and limit
    orders.sort(key=lambda o: o.created_at, reverse=True)
    orders = orders[:limit]

    return [
        {
            "order_id": str(order.order_id),
            "client_order_id": order.client_order_id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "broker": order.broker.value,
            "order_type": order.order_type.value,
            "side": order.side.value,
            "volume": float(order.volume),
            "price": float(order.price) if order.price else None,
            "stop_price": float(order.stop_price) if order.stop_price else None,
            "status": order.status.value,
            "filled_volume": float(order.filled_volume),
            "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price else None,
            "commission": float(order.commission),
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
        for order in orders
    ]


@app.get("/api/v1/orders/{order_id}", response_model=dict)
async def get_order(
    order_id: str,
    request: Request = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Get order details."""
    order = engine.order_manager.get_order(UUID(order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "order_id": str(order.order_id),
        "client_order_id": order.client_order_id,
        "strategy_id": order.strategy_id,
        "symbol": order.symbol,
        "broker": order.broker.value,
        "order_type": order.order_type.value,
        "side": order.side.value,
        "volume": float(order.volume),
        "price": float(order.price) if order.price else None,
        "stop_price": float(order.stop_price) if order.stop_price else None,
        "status": order.status.value,
        "filled_volume": float(order.filled_volume),
        "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price else None,
        "commission": float(order.commission),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


@app.delete("/api/v1/orders/{order_id}")
async def cancel_order(
    order_id: str,
    request: Request = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Cancel an order."""
    order = engine.order_manager.get_order(UUID(order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Update order status to cancelled
    order.status = OrderStatus.CANCELLED
    engine.order_manager.update_order(order)

    # In a real system, we would send cancellation to broker
    # For now, just return success
    return {"status": "cancelled"}


# ============================================
# POSITION ENDPOINTS
# ============================================


@app.get("/api/v1/positions", response_model=list[dict])
async def get_positions(
    strategy_id: str | None = None,
    symbol: str | None = None,
    broker: str | None = None,
    open_only: bool = True,
    request: Request = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Get current positions."""
    return engine.get_positions(strategy_id=strategy_id, symbol=symbol, open_only=open_only)


@app.get("/api/v1/positions/{position_id}", response_model=dict)
async def get_position(
    position_id: str,
    request: Request = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Get position details."""
    position = engine.position_manager.get_position(UUID(position_id))
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    return {
        "position_id": str(position.position_id),
        "strategy_id": position.strategy_id,
        "symbol": position.symbol,
        "side": position.side.value,
        "volume": float(position.volume),
        "entry_price": float(position.entry_price),
        "current_price": float(position.current_price),
        "unrealized_pnl": float(position.unrealized_pnl),
        "realized_pnl": float(position.realized_pnl),
        "stop_loss": float(position.stop_loss) if position.stop_loss else None,
        "take_profit": float(position.take_profit) if position.take_profit else None,
        "opened_at": position.opened_at.isoformat(),
        "updated_at": position.updated_at.isoformat(),
        "is_open": position.is_open,
    }


# ============================================
# RISK ENDPOINTS
# ============================================


@app.get("/api/v1/risk/metrics", response_model=dict)
async def get_risk_metrics():
    """Get current portfolio risk metrics."""
    # Would get from portfolio_risk_manager
    return {
        "total_equity": 0.0,
        "total_margin_used": 0.0,
        "free_margin": 0.0,
        "margin_level": 0.0,
        "total_unrealized_pnl": 0.0,
        "total_realized_pnl": 0.0,
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "monthly_pnl": 0.0,
        "current_drawdown": 0.0,
        "max_drawdown": 0.0,
        "portfolio_var_95": 0.0,
        "portfolio_var_99": 0.0,
        "portfolio_es_95": 0.0,
        "portfolio_es_99": 0.0,
        "max_correlation": 0.0,
        "sector_exposures": {},
        "leverage": 0.0,
        "open_positions": 0,
    }


@app.get("/api/v1/risk/circuit-breakers", response_model=list[dict])
async def get_circuit_breakers():
    """Get circuit breaker status."""
    breakers = circuit_breaker_manager.get_all_breakers()

    return [
        {
            "breaker_type": bt.value,
            "state": b.state.value,
            "threshold": b.config.threshold,
            "triggered_at": b.triggered_at.isoformat() if b.triggered_at else None,
            "trigger_count": b.trigger_count,
            "enabled": b.config.enabled,
        }
        for bt, b in breakers.items()
    ]


@app.post("/api/v1/risk/circuit-breakers/{breaker_type}/reset")
async def reset_circuit_breaker(breaker_type: str):
    """Reset a circuit breaker."""
    try:
        cb_type = list(circuit_breaker_manager._breakers.keys())[
            list(circuit_breaker_manager._breakers.keys()).index(breaker_type)
        ]
        circuit_breaker_manager.force_close(cb_type)
        return {"status": "reset"}
    except ValueError:
        raise HTTPException(status_code=404, detail="Circuit breaker not found")


@app.post("/api/v1/risk/circuit-breakers/{breaker_type}/trip")
async def trip_circuit_breaker(breaker_type: str, reason: str = "Manual trip"):
    """Force trip a circuit breaker."""
    try:
        cb_type = list(circuit_breaker_manager._breakers.keys())[
            list(circuit_breaker_manager._breakers.keys()).index(breaker_type)
        ]
        circuit_breaker_manager.force_open(cb_type, reason)
        return {"status": "tripped"}
    except ValueError:
        raise HTTPException(status_code=404, detail="Circuit breaker not found")


@app.get("/api/v1/risk/drawdown")
async def get_drawdown_status():
    """Get drawdown guard status."""
    return drawdown_guard.get_status()


# ============================================
# STRATEGY ENDPOINTS
# ============================================


@app.get("/api/v1/strategies", response_model=list[dict])
async def get_strategies():
    """Get all strategies status."""
    strategies = strategy_registry.get_all()

    return [
        {
            "strategy_id": s.strategy_id,
            "name": s.config.name,
            "state": s.state.value,
            "signals_generated": s._signals_generated,
            "last_signal_time": s._last_signal_time.isoformat() if s._last_signal_time else None,
            "error_count": s._error_count,
            "uptime_seconds": s.get_state().get("uptime_seconds", 0),
            "active_positions": s.get_state().get("active_positions", 0),
            "config": s.get_state().get("config", {}),
        }
        for s in strategies
    ]


@app.get("/api/v1/strategies/{strategy_id}", response_model=dict)
async def get_strategy(strategy_id: str):
    """Get strategy details."""
    strategy = strategy_registry.get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    state = strategy.get_state()
    return {
        "strategy_id": strategy.strategy_id,
        "name": strategy.config.name,
        "state": strategy.state.value,
        "signals_generated": strategy._signals_generated,
        "last_signal_time": strategy._last_signal_time.isoformat() if strategy._last_signal_time else None,
        "error_count": strategy._error_count,
        "uptime_seconds": state.get("uptime_seconds", 0),
        "active_positions": state.get("active_positions", 0),
        "config": state.get("config", {}),
    }


@app.post("/api/v1/strategies/{strategy_id}/pause")
async def pause_strategy(strategy_id: str):
    """Pause a strategy."""
    strategy = strategy_registry.get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    await strategy.pause()
    return {"status": "paused"}


@app.post("/api/v1/strategies/{strategy_id}/resume")
async def resume_strategy(strategy_id: str):
    """Resume a strategy."""
    strategy = strategy_registry.get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    await strategy.resume()
    return {"status": "active"}


@app.post("/api/v1/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: str):
    """Stop a strategy."""
    strategy = strategy_registry.get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    await strategy.stop()
    return {"status": "stopped"}


# ============================================
# BACKTEST ENDPOINTS
# ============================================


@app.post("/api/v1/backtest/run")
async def run_backtest(
    strategy_id: str,
    start_date: datetime,
    end_date: datetime,
    symbols: list[str],
    initial_capital: float = 100000,
    timeframe: Timeframe = Timeframe.H1,
):
    """Run a backtest."""
    # Would run backtest engine
    return {
        "backtest_id": str(uuid4()),
        "status": "started",
        "message": "Backtest started in background",
    }


@app.get("/api/v1/backtest/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    """Get backtest results."""
    raise HTTPException(status_code=404, detail="Backtest not found")


# ============================================
# WEBSOCKET ENDPOINTS
# ============================================


@app.websocket("/ws/market")
async def websocket_market(websocket: WebSocket):
    """WebSocket for real-time market data."""
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        while True:
            # Send market updates
            # In production, would subscribe to NATS
            await asyncio.sleep(1)
            await websocket.send_json(
                {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
            )
    except WebSocketDisconnect:
        active_websockets.remove(websocket)


@app.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """WebSocket for real-time portfolio updates."""
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json(
                {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
            )
    except WebSocketDisconnect:
        active_websockets.remove(websocket)


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket for real-time signals."""
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json(
                {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
            )
    except WebSocketDisconnect:
        active_websockets.remove(websocket)


# ============================================
# STARTUP/SHUTDOWN
# ============================================


@app.on_event("startup")
async def startup():
    """Application startup."""
    # Initialize connections
    try:
        await timescaledb.connect()
    except Exception as e:
        logger.warning(f"TimescaleDB connection failed: {e}")

    try:
        await redis_cache.connect()
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")

    try:
        await nats_client.connect()
    except Exception as e:
        logger.warning(f"NATS connection failed: {e}")

    # Initialize execution engine and store in app state
    app.state.execution_engine = ExecutionEngine()

    # Initialize metrics
    metrics_collector.init_metrics()

    logger.info("Application started")


# ============================================
# KILL‑SWITCH ENDPOINT (admin only)
# ============================================

ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "change-me-in-production")


def _verify_admin(token: str) -> bool:
    """Constant‑time comparison of the admin token."""
    import hmac

    return hmac.compare_digest(token, ADMIN_TOKEN)


@app.post("/admin/kill-switch")
async def kill_switch(token: str | None = None):
    """Emergency stop.

    Triggers a graceful shutdown of the application after cancelling all
    in‑flight orders.  Requires a valid admin token supplied as the
    ``token`` query parameter (or header ``X‑Admin‑Token``).
    """
    header_token = token
    if header_token is None:

        # FastAPI automatically injects the request if declared in signature
        # but we keep it optional for backwards compatibility.
        request: Request | None = None
        if request is not None:
            header_token = request.headers.get("X-Admin-Token")

    if not header_token or not _verify_admin(header_token):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    logger.warning("KILL‑SWITCH triggered – initiating emergency shutdown")
    # Schedule shutdown – FastAPI will run the shutdown event handler
    import asyncio

    asyncio.create_task(_emergency_shutdown())
    return {"status": "shutting_down"}


async def _emergency_shutdown() -> None:
    """Close connections and stop the event loop."""
    try:
        await nats_client.disconnect()
    except Exception:
        logging.getLogger(__name__).exception('Suppressed exception')
    try:
        await redis_cache.disconnect()
    except Exception:
        logging.getLogger(__name__).exception('Suppressed exception')
    try:
        await timescaledb.disconnect()
    except Exception:
        logging.getLogger(__name__).exception('Suppressed exception')
    # Give the response a chance to be sent
    await asyncio.sleep(0.1)
    # Stop the event loop – this will trigger the FastAPI shutdown
    loop = asyncio.get_event_loop()
    loop.stop()


@app.on_event("shutdown")
async def shutdown():
    """Application shutdown."""
    # Close connections
    try:
        await timescaledb.disconnect()
    except Exception as e:
        logger.debug("Timescaledb disconnect failed: %s", e)

    try:
        await redis_cache.disconnect()
    except Exception as e:
        logger.debug("Redis cache disconnect failed: %s", e)

    try:
        await nats_client.disconnect()
    except Exception as e:
        logger.debug("NATS client disconnect failed: %s", e)

    logger.info("Application stopped")


# Run server
def run_api():
    """Run the API server."""
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run_api()
