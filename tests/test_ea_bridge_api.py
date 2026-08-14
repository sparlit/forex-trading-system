"""Contract tests for the MT5 EA HTTP bridge endpoints."""

import pytest
from fastapi import HTTPException

from src.api.main import ea_bridge, get_ea_commands, get_ea_status, receive_ea_data


def setup_function() -> None:
    ea_bridge.latest_market_data.clear()
    while not ea_bridge._command_queue.empty():
        ea_bridge._command_queue.get_nowait()


@pytest.mark.asyncio
async def test_ea_data_requires_message_type() -> None:
    with pytest.raises(HTTPException, match="requires a non-empty") as exc_info:
        await receive_ea_data({})
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_ea_market_data_is_accepted_and_reported() -> None:
    payload = {
        "type": "market_data",
        "symbol": "EURUSD",
        "bid": 1.1,
        "ask": 1.1002,
        "last": 1.1001,
        "volume": 100,
        "time": 1,
        "time_msc": 1000,
        "flags": 0,
        "volume_real": 1.0,
    }
    assert await receive_ea_data(payload) == {"status": "ok"}
    status = await get_ea_status()
    assert status["market_data_symbols"] == 1
    assert ea_bridge.get_latest_market_data("EURUSD").bid == 1.1


@pytest.mark.asyncio
async def test_ea_commands_are_returned_once() -> None:
    ea_bridge.send_command({"type": "order", "symbol": "EURUSD", "action": "buy"})
    assert len(await get_ea_commands()) == 1
    assert await get_ea_commands() == []
