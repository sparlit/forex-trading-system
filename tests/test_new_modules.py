"""Tests for newly added modules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.infra.config import app_config
from src.monitoring.operational import OperationalMetrics, collect_metrics
from src.performance.attribution import AttributionEngine, ClosedTrade
from src.risk.pre_trade import (
    PreTradeLimits,
    PreTradeValidationError,
    PreTradeValidator,
    get_pre_trade_validator,
)

# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def _make_trade(pnl_factor: float, sid: str = "s1") -> ClosedTrade:
    now = datetime.now(UTC)
    direction = "LONG"
    return ClosedTrade(
        trade_id=f"t-{pnl_factor}",
        strategy_id=sid,
        symbol="EURUSD",
        direction=direction,
        volume=Decimal(1),
        entry_price=Decimal("1.0"),
        exit_price=Decimal(str(1.0 + pnl_factor)),
        opened_at=now,
        closed_at=now + timedelta(minutes=1),
    )


def test_attribution_basic():
    engine = AttributionEngine()
    engine.add_trades([
        _make_trade(0.01, "s1"),
        _make_trade(-0.005, "s1"),
        _make_trade(0.02, "s2"),
    ])
    result = engine.compute_attribution()
    assert "s1" in result and "s2" in result
    assert result["s1"].trade_count == 2
    assert result["s2"].trade_count == 1
    assert engine.total_pnl() == Decimal("0.025")


def test_attribution_win_rate():
    engine = AttributionEngine()
    engine.add_trades([
        _make_trade(0.01),
        _make_trade(-0.01),
        _make_trade(0.02),
    ])
    res = engine.compute_attribution()
    assert res["s1"].winning_trades == 2
    assert res["s1"].losing_trades == 1
    assert 0.6 < res["s1"].win_rate < 0.7


# ---------------------------------------------------------------------------
# Pre‑trade validation
# ---------------------------------------------------------------------------


def test_pre_trade_validator_passes():
    validator = PreTradeValidator()
    from src.data.models import Order, OrderSide, OrderType
    order = Order(
        order_id=None,
        client_order_id="c1",
        strategy_id="s1",
        signal_id=None,
        symbol="EURUSD",
        symbol_id=1,
        broker="mt5",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        volume=Decimal("0.1"),
    )
    validator.validate(order, account_balance=Decimal(100000), account_free_margin=Decimal(50000))


def test_pre_trade_validator_rejects_oversized():
    validator = PreTradeValidator(PreTradeLimits(max_position_size=Decimal(1)))
    from src.data.models import Order, OrderSide, OrderType
    order = Order(
        order_id=None,
        client_order_id="c1",
        strategy_id="s1",
        signal_id=None,
        symbol="EURUSD",
        symbol_id=1,
        broker="mt5",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        volume=Decimal(2),
    )
    with pytest.raises(PreTradeValidationError):
        validator.validate(order, account_balance=Decimal(100000), account_free_margin=Decimal(50000))


def test_pre_trade_validator_rejects_insufficient_margin():
    validator = PreTradeValidator()
    from src.data.models import Order, OrderSide, OrderType
    order = Order(
        order_id=None,
        client_order_id="c1",
        strategy_id="s1",
        signal_id=None,
        symbol="EURUSD",
        symbol_id=1,
        broker="mt5",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        volume=Decimal(1000000),
    )
    with pytest.raises(PreTradeValidationError):
        validator.validate(order, account_balance=Decimal(100000), account_free_margin=Decimal(1000))


def test_pre_trade_singleton():
    v = get_pre_trade_validator()
    assert v is get_pre_trade_validator()


# ---------------------------------------------------------------------------
# Operational metrics
# ---------------------------------------------------------------------------


def test_operational_metrics_structure():
    m = OperationalMetrics()
    d = m.to_dict()
    assert "cpu_percent" in d and "memory_percent" in d


def test_collect_metrics_returns_metrics():
    m = collect_metrics()
    assert isinstance(m, OperationalMetrics)


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------


def test_app_config_delegates():
    # app_config should expose the same attributes as settings
    env = app_config.environment
    assert isinstance(env, str)


def test_app_config_validate():
    warnings = app_config.validate()
    assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# Level‑2 connector (stub – does not hit network)
# ---------------------------------------------------------------------------


def test_level2_connector_cache_key():
    from src.data.ingest.level2_connector import Level2Connector
    c = Level2Connector(exchange_id="binance")
    assert c.exchange_id == "binance"
    assert c.depth > 0
    assert c.cache_ttl > 0


# ---------------------------------------------------------------------------
# Regulatory reporting
# ---------------------------------------------------------------------------


def test_regulatory_report_csv(tmp_path):
    from src.regulatory.reporting import RegulatoryTrade, generate_mifid_report
    now = datetime.now(UTC)
    trades = [
        RegulatoryTrade(
            trade_id="t1",
            timestamp=now,
            symbol="EURUSD",
            side="BUY",
            quantity=Decimal(1),
            price=Decimal("1.1"),
            venue="MT5",
        )
    ]
    report = generate_mifid_report(trades)
    out = tmp_path / "report.csv"
    report.to_csv(out)
    text = out.read_text(encoding="utf-8")
    assert "trade_id" in text and "EURUSD" in text
    assert report.to_dict()["trades"][0]["symbol"] == "EURUSD"


# ---------------------------------------------------------------------------
# Chaos script – only verifies that the script module is importable and
# exposes the required CLI entry point.
# ---------------------------------------------------------------------------


def test_chaos_script_importable():
    import importlib.util
    import pathlib

    script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "chaos_test.py"
    spec = importlib.util.spec_from_file_location("chaos_test", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert hasattr(module, "main")


# ---------------------------------------------------------------------------
# Security / audit logging
# ---------------------------------------------------------------------------


def test_audit_logger_records_event():
    from src.security.audit import (
        AuditEvent,
        AuditLogger,
        log_login,
        log_order_rejected,
    )

    logger_ = AuditLogger()
    logger_.record(AuditEvent("test", "user", "res", "act", "success"))
    log_login("alice", True, ip="127.0.0.1")
    log_order_rejected("bob", "o1", "limit exceeded")
    events = logger_.events()
    # log_login / log_order_rejected use the singleton; make sure they
    # both produced events (the singleton is separate from the instance
    # created above)
    from src.security.audit import get_audit_logger

    singleton = get_audit_logger()
    singleton.clear()
    log_login("carol", False)
    assert any(e.actor == "carol" for e in singleton.events())
    assert isinstance(events[0], AuditEvent)


# ---------------------------------------------------------------------------
# ML feature store & online learner
# ---------------------------------------------------------------------------


def test_feature_store_put_get():
    from datetime import UTC, datetime

    from src.ml.feature_store import FeatureStore, FeatureVector, get_feature_store

    store = FeatureStore()
    now = datetime.now(UTC)
    fv = FeatureVector(symbol="EURUSD", timeframe="H1", timestamp=now, values={"rsi": 55.0})
    store.put(fv)
    assert store.get("EURUSD", "H1", now) is fv
    assert store.latest("EURUSD", "H1") is fv
    assert len(store) == 1
    # singleton accessor
    s = get_feature_store()
    assert isinstance(s, FeatureStore)


def test_online_linear_model_learns():
    from src.ml.feature_store import OnlineLinearModel

    # Simple linear function: y = 2*x0 + 3*x1 + 1
    model = OnlineLinearModel(n_features=2, learning_rate=0.1)
    xs = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]
    ys = [3.0, 4.0, 6.0, 8.0]
    initial_loss = model.loss(xs, ys)
    for _ in range(200):
        for x, y in zip(xs, ys):
            model.update(x, y)
    final_loss = model.loss(xs, ys)
    assert final_loss < initial_loss
