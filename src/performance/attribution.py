"""
Performance Attribution
=======================

Aggregates realised P&L from closed trades and computes simple
performance metrics per strategy, per symbol and overall.

The engine is intentionally lightweight – it stores trades in memory and
exposes helpers to query the aggregated data.  In production the same
data would be persisted to TimescaleDB.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger


@dataclass
class ClosedTrade:
    """A fully closed trade."""

    trade_id: str
    strategy_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    volume: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: datetime
    closed_at: datetime
    pnl: Decimal = field(init=False)

    def __post_init__(self) -> None:
        # Simple directional P&L – ignores fees / commissions for brevity
        diff = self.exit_price - self.entry_price
        if self.direction.upper() == "SHORT":
            diff = -diff
        self.pnl = diff * self.volume


@dataclass
class StrategyAttribution:
    strategy_id: str
    total_pnl: Decimal = Decimal(0)
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: Decimal = Decimal(0)
    max_drawdown: Decimal = Decimal(0)
    sharpe_ratio: float = 0.0


class AttributionEngine:
    """In‑memory performance attribution engine."""

    def __init__(self) -> None:
        self._trades: list[ClosedTrade] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record_trade(self, trade: ClosedTrade) -> None:
        """Add a closed trade to the dataset."""
        self._trades.append(trade)
        logger.debug(
            "Trade recorded",
            trade_id=trade.trade_id,
            pnl=str(trade.pnl),
        )

    def add_trades(self, trades: Iterable[ClosedTrade]) -> None:
        """Bulk add trades."""
        for t in trades:
            self.record_trade(t)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    @property
    def trades(self) -> list[ClosedTrade]:
        return list(self._trades)

    def compute_attribution(self) -> dict[str, StrategyAttribution]:
        """Return a mapping ``strategy_id -> StrategyAttribution``."""
        per_strategy: dict[str, list[ClosedTrade]] = defaultdict(list)
        for t in self._trades:
            per_strategy[t.strategy_id].append(t)

        results: dict[str, StrategyAttribution] = {}
        for sid, trades in per_strategy.items():
            total_pnl = sum((t.pnl for t in trades), Decimal(0))
            winning = sum(1 for t in trades if t.pnl > 0)
            losing = sum(1 for t in trades if t.pnl < 0)
            avg = total_pnl / len(trades) if trades else Decimal(0)
            win_rate = winning / len(trades) if trades else 0.0

            # Drawdown – compute running cumulative P&L
            cum = Decimal(0)
            peak = Decimal(0)
            max_dd = Decimal(0)
            for t in trades:
                cum += t.pnl
                peak = max(peak, cum)
                dd = peak - cum
                max_dd = max(max_dd, dd)

            # Sharpe – assumes zero risk‑free rate; uses sample std‑dev
            if len(trades) > 1:
                pnls = [float(t.pnl) for t in trades]
                mean = sum(pnls) / len(pnls)
                variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
                std = math.sqrt(variance) if variance > 0 else 0.0
                sharpe = mean / std if std > 0 else 0.0
            else:
                sharpe = 0.0

            results[sid] = StrategyAttribution(
                strategy_id=sid,
                total_pnl=total_pnl,
                trade_count=len(trades),
                winning_trades=winning,
                losing_trades=losing,
                win_rate=win_rate,
                avg_pnl=avg,
                max_drawdown=max_dd,
                sharpe_ratio=sharpe,
            )
        return results

    def total_pnl(self) -> Decimal:
        return sum((t.pnl for t in self._trades), Decimal(0))


# Singleton accessor ---------------------------------------------------------
_default_engine: AttributionEngine | None = None


def get_attribution_engine() -> AttributionEngine:
    """Return a process‑wide :class:`AttributionEngine`."""
    global _default_engine
    if _default_engine is None:
        _default_engine = AttributionEngine()
    return _default_engine
