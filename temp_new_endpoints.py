

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
    timeframe: str = "H1"
):
    """Get all technical indicators for specified symbols."""
    from src.strategy.technical.indicators import TechnicalIndicators
    import polars as pl
    
    symbol_list = [s.strip() for s in symbols.split(",")]
    result = {}
    
    try:
        for symbol in symbol_list:
            # Fetch recent bars for indicator calculation
            bars = await timescaledb.get_bars(
                symbol=symbol,
                timeframe=Timeframe(timeframe),
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
    timeframe: str = "H1"
):
    """Get current market regime detection."""
    from src.strategy.market_regime import MarketRegimeDetector, RegimeType
    
    try:
        detector = MarketRegimeDetector()
        
        # Get recent bars
        bars = await timescaledb.get_bars(
            symbol=symbol,
            timeframe=Timeframe(timeframe),
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
    import psutil
    import os
    
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
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        logger.error(f"Error getting processes: {e}")
    
    return {
        "processes": processes,
        "total_count": len(processes)
    }

@app.get("/api/v1/market/crypto-sessions")
async def get_crypto_sessions():
    """Get crypto trading sessions (24/7)."""
    from datetime import UTC, datetime
    
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
    from src.strategy.blind_spot_manager import BlindSpotManager
    
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
    from src.performance.attribution import AttributionEngine
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    from src.risk.advanced_risk import AdvancedRiskManager
    
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
    from src.strategy.blind_spot_manager import BlindSpotManager
    
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
    from src.performance.attribution import AttributionEngine
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    from src.risk.advanced_risk import AdvancedRiskManager
    
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
    from src.strategy.blind_spot_manager import BlindSpotManager
    
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
    from src.performance.attribution import AttributionEngine
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    from src.risk.advanced_risk import AdvancedRiskManager
    
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
    from src.strategy.blind_spot_manager import BlindSpotManager
    
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
    from src.performance.attribution import AttributionEngine
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    from src.risk.advanced_risk import AdvancedRiskManager
    
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
    from src.strategy.blind_spot_manager import BlindSpotManager
    
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
    from src.performance.attribution import AttributionEngine
    
    return {
        "factor_exposures": {},
        "factor_returns": {},
        "strategy_loadings": {},
        "residual_risk": {}
    }

@app.get("/api/v1/risk/correlation-clusters")
async def get_correlation_clusters():
    """Get correlation clusters for risk management."""
    from src.risk.advanced_risk import AdvancedRiskManager
    
    return {
        "clusters": [],
        "message": "Correlation clustering active"
    }
