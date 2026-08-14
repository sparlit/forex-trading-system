import pytest

from src.autonomous.style_selector import (
    AccountProfile,
    MarketConditions,
    RiskTolerance,
    StyleSelector,
    TradingStyle,
)


def test_selector_requires_an_active_session() -> None:
    decision = StyleSelector().select(
        MarketConditions(volatility=0.2, liquidity=0.9, active_session=False),
        AccountProfile(10_000, RiskTolerance.MODERATE, 120),
    )
    assert decision.style is TradingStyle.NO_TRADE


def test_selector_uses_scalping_only_for_liquid_overlap() -> None:
    selector = StyleSelector()
    decision = selector.select(
        MarketConditions(0.2, 0.9, True, session_overlap=True, spread_bps=1.5),
        AccountProfile(10_000, RiskTolerance.AGGRESSIVE, 180),
    )
    assert decision.style is TradingStyle.SCALPING
    assert decision.switched


def test_selector_switches_style_when_conditions_change() -> None:
    selector = StyleSelector()
    account = AccountProfile(10_000, RiskTolerance.MODERATE, 90)
    assert selector.select(MarketConditions(0.2, 0.8, True), account).style is TradingStyle.DAY_TRADING
    decision = selector.select(MarketConditions(0.8, 0.8, True), account)
    assert decision.style is TradingStyle.POSITION
    assert decision.switched


@pytest.mark.parametrize("liquidity", [-0.1, 1.1])
def test_market_conditions_validate_liquidity(liquidity: float) -> None:
    with pytest.raises(ValueError, match="liquidity"):
        MarketConditions(0.2, liquidity, True)
