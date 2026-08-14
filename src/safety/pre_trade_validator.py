# safety/pre_trade_validator.py
"""Pre‑Trade Order Validator.
Provides granular validation functions that can be called individually or via ``validate``.
All checks are pure Python (no external services) and mirror the safety concerns defined
in the V2.1 spec sections 51 and 52.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# A minimal representation of market / broker state used by the checks.
# In production this would be injected from the appropriate services.
@dataclass(slots=True)
class MarketInfo:
    symbol: str
    last_price: float | None = None
    spread: float | None = None
    is_market_open: bool = True
    data_freshness_seconds: int | None = None
    liquidity_score: float | None = None  # 0..1 where 1 is excellent liquidity


@dataclass(slots=True)
class BrokerInfo:
    connected: bool = True
    health_ok: bool = True
    max_order_size_pct: float = 0.05  # maximum of equity per order


@dataclass(slots=True)
class RiskContext:
    portfolio_equity: float
    gross_leverage: float = 1.0
    net_leverage: float = 1.0
    max_allowed_leverage: float = 5.0
    max_position_pct: float = 0.20  # max % of equity per position


@dataclass(slots=True)
class PreTradeValidator:
    """Collection of pre‑trade checks.

    The public ``validate`` method aggregates all checks and returns a tuple
    ``(approved, reasons)`` similar to the SafetyKernel.
    """

    market: MarketInfo
    broker: BrokerInfo
    risk: RiskContext

    # ---------------------------------------------------------------------
    # Individual check implementations – each returns ``bool``.
    # ---------------------------------------------------------------------
    def check_symbol_valid(self, symbol: str | None) -> bool:
        if not symbol:
            return False
        # Symbol whitelist – could be read from a config.
        allowed = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"}
        return symbol.upper() in allowed

    def check_volume_valid(self, volume: float | None, symbol: str | None) -> bool:
        if volume is None or volume <= 0:
            return False
        # Use risk context limits; here we enforce a max volume per symbol.
        max_volumes = {
            "EURUSD": 5_000_000,
            "GBPUSD": 3_000_000,
            "USDJPY": 6_000_000,
        }
        max_allowed = max_volumes.get(symbol.upper() if symbol else None, 1_000_000)
        return volume <= max_allowed

    def check_price_valid(self, price: float | None, market: MarketInfo) -> bool:
        if price is None or price <= 0:
            return False
        if market.last_price is None:
            return True
        # Accept price within ±20% of last price.
        return abs(price - market.last_price) / market.last_price <= 0.20

    def check_sl_valid(self, price: float | None, sl: float | None, side: str | None) -> bool:
        if price is None or side not in {"long", "short"}:
            return False
        if sl is None:
            return True  # optional stop loss
        if side == "long":
            return sl < price
        else:
            return sl > price

    def check_tp_valid(self, price: float | None, tp: float | None, side: str | None) -> bool:
        if price is None or side not in {"long", "short"}:
            return False
        if tp is None:
            return True
        if side == "long":
            return tp > price
        else:
            return tp < price

    def check_stop_distance_valid(self, price: float | None, sl: float | None) -> bool:
        if price is None or sl is None:
            return True
        # Minimum distance of 0.5% of price to avoid accidental fills.
        return abs(price - sl) / price >= 0.005

    def check_margin_valid(self, margin: float | None) -> bool:
        if margin is None:
            return False
        return 0.0 <= margin <= 1.0

    def check_market_open(self, market: MarketInfo) -> bool:
        return market.is_market_open

    def check_order_type_valid(self, order_type: str | None) -> bool:
        return order_type in {"market", "limit", "stop", "stop_limit"}

    def check_broker_rules_valid(self, volume: float | None) -> bool:
        if volume is None:
            return False
        # Ensure the order size does not exceed the broker's % limit of equity.
        max_size = self.risk.portfolio_equity * self.broker.max_order_size_pct
        return volume <= max_size

    def check_risk_valid(self, volume: float | None, price: float | None) -> bool:
        if volume is None or price is None:
            return False
        # Simple exposure check: position market value must stay within allowed leverage.
        exposure = volume * price
        if self.risk.gross_leverage > self.risk.max_allowed_leverage:
            return False
        return exposure <= self.risk.portfolio_equity * self.risk.max_position_pct

    def check_safety_valid(self, market: MarketInfo) -> bool:
        # Ensure spread is reasonable and data is fresh.
        if market.spread is not None and market.last_price is not None:
            if market.spread / market.last_price > 0.005:
                return False
        if market.data_freshness_seconds is not None:
            if market.data_freshness_seconds > 30:
                return False
        return True

    # ---------------------------------------------------------------------
    # Aggregate validation
    # ---------------------------------------------------------------------
    def validate(self, intent: dict[str, Any]) -> tuple[bool, list[str]]:
        """Run all pre‑trade checks on a trading intent.

        Returns ``(approved, reasons)`` where ``reasons`` is a list of failure messages.
        """
        approved = True
        reasons: list[str] = []

        symbol = intent.get("symbol")
        price = intent.get("price")
        volume = intent.get("volume")
        side = intent.get("order_side")
        sl = intent.get("stop_loss")
        tp = intent.get("take_profit")
        order_type = intent.get("order_type")
        margin = intent.get("margin_required")

        if not self.check_symbol_valid(symbol):
            approved = False
            reasons.append("Invalid or unsupported symbol")
        if not self.check_price_valid(price, self.market):
            approved = False
            reasons.append("Price invalid or out of range")
        if not self.check_volume_valid(volume, symbol):
            approved = False
            reasons.append("Volume invalid or exceeds symbol limits")
        if not self.check_order_type_valid(order_type):
            approved = False
            reasons.append("Order type not supported")
        if not self.check_sl_valid(price, sl, side):
            approved = False
            reasons.append("Stop‑loss configuration invalid")
        if not self.check_tp_valid(price, tp, side):
            approved = False
            reasons.append("Take‑profit configuration invalid")
        if not self.check_stop_distance_valid(price, sl):
            approved = False
            reasons.append("Stop distance too tight")
        if not self.check_margin_valid(margin):
            approved = False
            reasons.append("Margin requirement out of bounds")
        if not self.check_market_open(self.market):
            approved = False
            reasons.append("Market is closed for the symbol")
        if not self.check_broker_rules_valid(volume):
            approved = False
            reasons.append("Broker rules violated for order size")
        if not self.check_risk_valid(volume, price):
            approved = False
            reasons.append("Risk limits would be breached")
        if not self.check_safety_valid(self.market):
            approved = False
            reasons.append("Spread or data freshness outside safety limits")

        return approved, reasons
