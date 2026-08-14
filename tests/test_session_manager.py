from datetime import UTC, datetime

import pytest

from src.strategy.session_manager import MarketType, SessionManager


@pytest.mark.asyncio
async def test_forex_sessions_and_overlap_are_active_in_their_utc_windows() -> None:
    manager = SessionManager()
    london = manager.get_session_by_name("london")
    overlap = manager.get_session_by_name("london_newyork_overlap")
    assert london is not None and overlap is not None

    timestamp = datetime(2025, 1, 6, 13, 0, tzinfo=UTC)  # Monday
    assert manager.is_session_active(london, timestamp)
    assert manager.is_session_active(overlap, timestamp)


@pytest.mark.asyncio
async def test_crypto_session_is_available_all_week() -> None:
    manager = SessionManager()
    crypto = manager.get_session_by_name("crypto_24_7")
    assert crypto is not None
    assert manager.is_session_active(crypto, datetime(2025, 1, 5, 12, tzinfo=UTC))  # Sunday


@pytest.mark.asyncio
async def test_active_symbol_filtering_uses_updated_session_state() -> None:
    manager = SessionManager()
    await manager.update_active_sessions()
    active_symbols = manager.get_active_symbols(MarketType.CRYPTO)
    assert "BTCUSD" in active_symbols
    assert manager.filter_symbols_by_active_sessions(["BTCUSD", "INVALID"]) == ["BTCUSD"]
