"""Core trading loop engine.
Coordinates data ingestion, market‑state, opportunity ranking, portfolio allocation,
risk checking, trade admission, execution, position tracking and exit handling.
All components are wired together using the EventBus for decoupled communication.
"""

import logging
import threading
import time

from src.autonomous_evolution.engine import EvolutionEngine

# Import core engines (already implemented)
from src.event_bus.event_bus import Event, EventBus, EventType
from src.execution_core.engine import ExecutionCore
from src.macro_pipeline.economic_calendar import fetch_upcoming_events
from src.macro_pipeline.news_sentiment import fetch_sentiment
from src.market_state_engine.engine import MarketStateEngine
from src.monitoring.prometheus_client import (
    inc_trade_count,
    init_metrics,
    record_execution_latency,
    record_pnl,
    record_position,
)
from src.opportunity_engine.engine import OpportunityEngine
from src.portfolio_engine.engine import PortfolioEngine
from src.position_manager.engine import PositionManager
from src.regime_detection.detector import detect_regime
from src.risk_engine.engine import RiskEngine
from src.self_diagnostics.health import run_checks
from src.self_diagnostics.recovery import handle_failure
from src.trade_admission.engine import TradeAdmission

logger = logging.getLogger(__name__)

class TradingLoop:
    def __init__(self):
        # Core components
        self.bus = EventBus(start_immediately=False)
        self.bus.start()
        self.market_state = MarketStateEngine()
        self.opportunity = OpportunityEngine()
        self.portfolio = PortfolioEngine()
        self.risk = RiskEngine()
        self.admission = TradeAdmission()
        self.execution = ExecutionCore()
        self.positions = PositionManager()
        self.evolution = EvolutionEngine(window=5)  # Monitor performance and adapt if needed
        # Internal tick counter for periodic tasks (macro data fetch)
        self._tick_counter = 0
        # Subscribe to events
        self.bus.subscribe(EventType.MarketTickReceived, self.on_market_tick)
        self.bus.subscribe(EventType.OpportunityGenerated, self.on_opportunity)
        self.bus.subscribe(EventType.OrderExecuted, self.on_order_executed)
        self.bus.subscribe(EventType.PositionClosed, self.on_position_closed)

    # ---------------------------------------------------------------------
    # Event callbacks
    # ---------------------------------------------------------------------
    def on_market_tick(self, ev: Event) -> None:
        """Handle a new market tick.
        Pull the latest data via the unified FeedManager, update market state,
        and evaluate trading opportunities.
        """
        from src.data_ingestion.feed_manager import get_latest
        symbol = ev.payload.get("symbol")
        # Refresh data from configured source(s)
        data = get_latest(symbol)
        logger.debug("Market tick refreshed for %s: %s", symbol, data)
        self.market_state.update_feed(ev.event_type.name, data)
        state = self.market_state.get_state()
        # Detect market regime (trend, range, etc.)
        regime = detect_regime(state)
        logger.info("Market regime detected: %s", regime)
        decision = self.opportunity.evaluate(state)

        # Periodic macro & news data refresh (every 5 market ticks)
        self._tick_counter += 1
        if self._tick_counter % 5 == 0:
            macro_events = fetch_upcoming_events()
            self.market_state.add_macro_data(macro_events)
            news_sentiment = fetch_sentiment()
            self.market_state.update_feed('news_sentiment', news_sentiment)
            logger.debug("Macro and news data refreshed")

        # Publish opportunity for downstream components
        opp_event = Event(
            event_id="opp_" + ev.event_id,
            timestamp=ev.timestamp,
            source="TradingLoop",
            version="2.4",
            correlation_id=ev.event_id,
            causation_id=None,
            event_type=EventType.OpportunityGenerated,
            payload={"decision": decision.name, "symbol": symbol},
        )
        self.bus.publish(opp_event)

    def on_opportunity(self, ev: Event) -> None:
        """Process an opportunity – run through portfolio, risk, admission, then execute."""
        decision = ev.payload.get("decision")
        symbol = ev.payload.get("symbol")
        if decision != "BUY" and decision != "SELL":
            logger.info("No trade action for decision %s", decision)
            return
        # Simple allocation request (placeholder amount)
        allocation = self.portfolio.allocate(symbol, 0.01)  # 1% of capital placeholder
        if not self.risk.check_limits(allocation):
            logger.warning("Risk check failed for %s", symbol)
            return
        if not self.admission.validate(symbol, decision, allocation):
            logger.warning("Trade admission denied for %s %s", decision, symbol)
            return
        # Build order dict (simplified)
        order = {
            "symbol": symbol,
            "side": decision.lower(),
            "volume": allocation,
            "price": ev.payload.get("last"),
        }
        exec_result = self.execution.execute_order(order)
        # Publish execution result
        exec_event = Event(
            event_id="exec_" + ev.event_id,
            timestamp=ev.timestamp,
            source="TradingLoop",
            version="2.4",
            correlation_id=ev.event_id,
            causation_id=None,
            event_type=EventType.OrderExecuted,
            payload=exec_result,
        )
        self.bus.publish(exec_event)

    def on_order_executed(self, ev: Event) -> None:
        """Update position manager with a new filled order and record metrics."""
        order = ev.payload
        self.positions.add_position(order)
        # Record trade count and execution latency (placeholder latency 0.01s)
        inc_trade_count()
        record_execution_latency(0.01)
        # Update PnL metric if order provides pnl
        pnl = order.get("pnl")
        if pnl is not None:
            record_pnl(pnl)
        # Update live positions count
        record_position(len(self.positions.positions))
        # Possibly trigger exit evaluation (placeholder)
        exit_signal = self.exit_engine.evaluate_exit(order)
        if exit_signal:
            # In a real system we would send a close order here
            logger.info("Exit condition met for %s", order["symbol"])

    def on_position_closed(self, ev: Event) -> None:
        """Cleanup after a position is closed."""
        self.positions.remove_position(ev.payload["position_id"])

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def start(self) -> None:
        """Start the trading loop.
        Initializes Prometheus metrics endpoint (default port 8000) and then
        runs an infinite loop (in production this would be an async event loop).
        """
        # Start Prometheus exporter (no‑op if the library is missing)
        init_metrics(port=8000)
        logger.info("TradingLoop started – Prometheus metrics on :8000")
        # Launch background health‑monitoring thread
        def _health_loop():
            while True:
                checks = run_checks(self.bus, self.market_state)
                if not all(checks.values()):
                    handle_failure(self.bus, f"Health check failed: {checks}")
                time.sleep(60)
        health_thread = threading.Thread(target=_health_loop, daemon=True)
        health_thread.start()
        try:
            while True:
                # In production this would block on an async event queue.
                # For this skeleton we just sleep.
                time.sleep(1)
                # Record dummy performance metric (e.g., 1.0) for evolution engine
                self.evolution.record(1.0)
                if self.evolution.should_adapt():
                    logger.info("Evolution engine signaled adaptation – placeholder action.")

        except KeyboardInterrupt:
            logger.info("TradingLoop stopped by user")
        finally:
            self.bus.stop()


if __name__ == "__main__":
    loop = TradingLoop()
    loop.start()
