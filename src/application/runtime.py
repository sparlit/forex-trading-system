"""Paper-safe EAQTS 2.4 runtime.

This is the rebuild's vertical slice.  It composes market state, capital/risk
controls, the canonical trade-admission boundary, paper execution, positions,
and immutable event provenance without relying on a live broker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from src.orch.event_bus import Event, EventStore
from src.orch.trading_control import (
    AdmissionContext,
    AdmissionDecision,
    CanonicalTradingIntent,
    SystemState,
    TradeControlChain,
)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    initial_equity: float = 100_000.0
    max_risk_per_trade: float = 1_000.0
    max_total_risk: float = 2_000.0
    max_spread_bps: float = 10.0
    slippage_bps: float = 1.0
    intent_ttl_seconds: int = 30
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    observed_at: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000 if self.mid else float("inf")


@dataclass(slots=True)
class PaperPosition:
    position_id: str
    intent_id: str
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    stop_price: float
    target_price: float
    opened_at: datetime
    current_price: float
    closed_at: datetime | None = None
    realised_pnl: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def unrealised_pnl(self) -> float:
        direction = 1.0 if self.direction == "long" else -1.0
        return (self.current_price - self.entry_price) * self.quantity * direction


class EAQTSRuntime:
    """Single-process runtime for shadow and paper release gates.

    Live execution is intentionally unsupported here.  A future venue adapter
    must be inserted after an admitted intent and independently verified fill.
    """

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        event_db: Path | str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.event_store = EventStore(event_db)
        self.system_state = SystemState.NORMAL
        self.quotes: dict[str, Quote] = {}
        self.positions: dict[str, PaperPosition] = {}
        self.equity = self.config.initial_equity
        self._admission = TradeControlChain(
            event_store=self.event_store,
            risk_verifier=self._verify_risk,
            clock=self._clock,
        )

    def ingest_quote(
        self, symbol: str, bid: float, ask: float, observed_at: datetime | None = None
    ) -> Quote:
        if not symbol or bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError("quote requires a symbol and positive bid <= ask")
        quote = Quote(
            symbol=symbol.upper(), bid=bid, ask=ask, observed_at=observed_at or self._clock()
        )
        self.quotes[quote.symbol] = quote
        self._record("MarketTickReceived", {"symbol": quote.symbol, "bid": bid, "ask": ask})
        self._mark_positions(quote)
        return quote

    def submit_intent(
        self,
        *,
        symbol: str,
        direction: str,
        strategy_id: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        quantity: float,
        risk_amount: float,
        capital_allocation: float,
        expected_value: float,
        probability: float,
        decision_snapshot_id: str,
        style: str = "systematic",
        timeframe: str = "H1",
    ) -> tuple[CanonicalTradingIntent, AdmissionDecision, tuple[str, ...]]:
        now = self._clock()
        intent = CanonicalTradingIntent(
            intent_id=str(uuid4()),
            symbol=symbol.upper(),
            direction=direction,
            strategy_id=strategy_id,
            style=style,
            timeframe=timeframe,
            probability=probability,
            expected_value=expected_value,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            position_size=quantity,
            risk_amount=risk_amount,
            capital_allocation=capital_allocation,
            decision_snapshot_id=decision_snapshot_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.config.intent_ttl_seconds),
        )
        outcome = self._admission.evaluate(intent, self._context_for(intent))
        if outcome.decision is AdmissionDecision.ADMIT:
            self._paper_execute(intent)
        return intent, outcome.decision, outcome.reasons

    def close_position(self, position_id: str, reason: str = "manual") -> PaperPosition:
        position = self.positions[position_id]
        if not position.is_open:
            return position
        quote = self.quotes.get(position.symbol)
        if quote is None:
            raise ValueError(f"no current quote for {position.symbol}")
        position.current_price = quote.bid if position.direction == "long" else quote.ask
        position.realised_pnl = position.unrealised_pnl
        position.closed_at = self._clock()
        self.equity += position.realised_pnl
        self._record(
            "PositionClosed",
            {"position_id": position_id, "reason": reason, "pnl": position.realised_pnl},
        )
        return position

    def snapshot(self) -> dict[str, object]:
        open_positions = [position for position in self.positions.values() if position.is_open]
        return {
            "mode": "paper",
            "system_state": self.system_state.value,
            "live_trading_enabled": self.config.live_trading_enabled,
            "equity": self.equity,
            "open_risk": sum(self._position_risk(position) for position in open_positions),
            "quotes": {symbol: asdict(quote) for symbol, quote in self.quotes.items()},
            "positions": [
                asdict(position) | {"unrealised_pnl": position.unrealised_pnl}
                for position in self.positions.values()
            ],
        }

    def _context_for(self, intent: CanonicalTradingIntent) -> AdmissionContext:
        quote = self.quotes.get(intent.symbol)
        quote_is_fresh = (
            quote is not None and (self._clock() - quote.observed_at).total_seconds() <= 5
        )
        spread_ok = quote is not None and quote.spread_bps <= self.config.max_spread_bps
        return AdmissionContext(
            system_state=self.system_state,
            legal_permitted=True,
            broker_permitted=True,
            data_valid=(quote.bid <= quote.ask if quote is not None else None),
            data_fresh=(quote_is_fresh if quote is not None else None),
            strategy_licensed=bool(intent.strategy_id),
            model_eligible=True,
            liquidity_adequate=(spread_ok if quote is not None else None),
            capacity_available=True,
            capital_reserved=intent.capital_allocation <= self.equity,
            risk_approved=True,
            safety_approved=not self.config.live_trading_enabled,
            compliance_approved=True,
            rate_limit_available=True,
            order_valid=True,
        )

    def _verify_risk(self, intent: CanonicalTradingIntent, _: AdmissionContext) -> tuple[bool, str]:
        if intent.risk_amount > self.config.max_risk_per_trade:
            return False, "per-trade risk limit exceeded"
        open_risk = sum(
            self._position_risk(position)
            for position in self.positions.values()
            if position.is_open
        )
        if open_risk + intent.risk_amount > self.config.max_total_risk:
            return False, "portfolio risk budget exceeded"
        return True, "approved"

    def _paper_execute(self, intent: CanonicalTradingIntent) -> PaperPosition:
        quote = self.quotes[intent.symbol]
        slippage = self.config.slippage_bps / 10_000
        fill = (
            quote.ask * (1 + slippage) if intent.direction == "long" else quote.bid * (1 - slippage)
        )
        position = PaperPosition(
            position_id=str(uuid4()),
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            direction=intent.direction,
            quantity=intent.position_size,
            entry_price=fill,
            stop_price=intent.stop_price,
            target_price=intent.target_price,
            opened_at=self._clock(),
            current_price=fill,
        )
        self.positions[position.position_id] = position
        self._record(
            "OrderFilled",
            {
                "intent_id": intent.intent_id,
                "position_id": position.position_id,
                "fill_price": fill,
            },
        )
        self._record(
            "PositionOpened", {"intent_id": intent.intent_id, "position_id": position.position_id}
        )
        return position

    def _mark_positions(self, quote: Quote) -> None:
        for position in self.positions.values():
            if position.is_open and position.symbol == quote.symbol:
                position.current_price = quote.bid if position.direction == "long" else quote.ask

    @staticmethod
    def _position_risk(position: PaperPosition) -> float:
        return abs(position.entry_price - position.stop_price) * position.quantity

    def _record(self, event_type: str, payload: dict[str, object]) -> None:
        self.event_store.append(
            Event(source="eaqts_runtime", event_type=event_type, payload=payload)
        )
