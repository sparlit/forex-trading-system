"""Trading-style selection based on explicit market and account constraints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class TradingStyle(StrEnum):
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING = "swing"
    POSITION = "position"
    NO_TRADE = "no_trade"


class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True, slots=True)
class MarketConditions:
    """Normalized observations used for a style decision.

    ``volatility`` is annualized volatility as a decimal (for example, 0.18
    means 18%). ``liquidity`` is normalized to the inclusive 0..1 range.
    """

    volatility: float
    liquidity: float
    active_session: bool
    session_overlap: bool = False
    spread_bps: float = 0.0
    event_risk: bool = False

    def __post_init__(self) -> None:
        if self.volatility < 0:
            raise ValueError("volatility cannot be negative")
        if not 0.0 <= self.liquidity <= 1.0:
            raise ValueError("liquidity must be between 0 and 1")
        if self.spread_bps < 0:
            raise ValueError("spread_bps cannot be negative")


@dataclass(frozen=True, slots=True)
class AccountProfile:
    equity: float
    risk_tolerance: RiskTolerance
    available_minutes: int

    def __post_init__(self) -> None:
        if self.equity <= 0:
            raise ValueError("equity must be positive")
        if self.available_minutes < 0:
            raise ValueError("available_minutes cannot be negative")


@dataclass(frozen=True, slots=True)
class StyleDecision:
    style: TradingStyle
    confidence: float
    reasons: tuple[str, ...]
    switched: bool


class StyleSelector:
    """Choose a style conservatively and retain the selected style as state.

    The selector refuses short-horizon trading outside liquid sessions or when
    market-event risk is elevated.  This deliberately makes ``NO_TRADE`` a
    first-class outcome rather than forcing every condition into a trade.
    """

    _MIN_EQUITY: ClassVar[dict[TradingStyle, float]] = {
        TradingStyle.SCALPING: 5_000.0,
        TradingStyle.DAY_TRADING: 2_000.0,
        TradingStyle.SWING: 500.0,
        TradingStyle.POSITION: 500.0,
    }

    def __init__(self) -> None:
        self._current_style = TradingStyle.NO_TRADE

    @property
    def current_style(self) -> TradingStyle:
        return self._current_style

    def select(self, market: MarketConditions, account: AccountProfile) -> StyleDecision:
        """Return the best permissible style for current conditions."""
        reasons: list[str] = []
        if not market.active_session:
            return self._commit(TradingStyle.NO_TRADE, 1.0, ("No active trading session.",))
        if market.event_risk:
            return self._commit(TradingStyle.NO_TRADE, 0.95, ("Elevated scheduled-event risk.",))
        if market.liquidity < 0.25 or market.spread_bps > 15:
            return self._commit(TradingStyle.NO_TRADE, 0.9, ("Liquidity or spread is unsuitable.",))

        if (
            account.available_minutes >= 120
            and account.equity >= self._MIN_EQUITY[TradingStyle.SCALPING]
            and market.liquidity >= 0.75
            and market.spread_bps <= 3
            and market.session_overlap
            and market.volatility <= 0.35
            and account.risk_tolerance is not RiskTolerance.CONSERVATIVE
        ):
            reasons.append("Liquid overlap and tight spread support scalping.")
            return self._commit(TradingStyle.SCALPING, 0.85, tuple(reasons))

        if account.available_minutes >= 60 and market.volatility <= 0.50:
            if account.equity >= self._MIN_EQUITY[TradingStyle.DAY_TRADING]:
                reasons.append("Active session and available monitoring time support day trading.")
                return self._commit(TradingStyle.DAY_TRADING, 0.78, tuple(reasons))

        if account.available_minutes >= 15 and market.volatility <= 0.70:
            reasons.append("Conditions favour a managed multi-day swing trade.")
            return self._commit(TradingStyle.SWING, 0.72, tuple(reasons))

        reasons.append("Limited monitoring time or elevated volatility favours longer holding periods.")
        return self._commit(TradingStyle.POSITION, 0.65, tuple(reasons))

    def _commit(
        self, style: TradingStyle, confidence: float, reasons: tuple[str, ...]
    ) -> StyleDecision:
        switched = style is not self._current_style
        self._current_style = style
        return StyleDecision(style=style, confidence=confidence, reasons=reasons, switched=switched)
