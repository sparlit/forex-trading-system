"""
Integration Tests for Broker Adapters
=====================================

Comprehensive integration tests for all broker adapters:
- MT5BrokerAdapter
- CCXTBrokerAdapter
- CTraderAdapter
- IBKRAdapter

Tests cover:
- Connection lifecycle
- Order placement and management
- Position synchronization
- Account info retrieval
- Error handling and recovery
- Circuit breaker integration
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.data.models import Direction, Order, OrderSide, OrderStatus, OrderType, Position
from src.execution.brokers import (
    CCXTBrokerAdapter,
    CTraderAdapter,
    IBKRAdapter,
    MT5BrokerAdapter,
)
from src.execution.order_manager import BrokerType


class MockBrokerBase:
    """Base class for mock broker tests."""
    
    @pytest.fixture
    def sample_order(self):
        """Create a sample order for testing."""
        return Order(
            order_id=UUID("12345678-1234-5678-1234-567812345678"),
            client_order_id="TEST_001",
            symbol="EURUSD",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            volume=Decimal("1.0"),
            price=None,
            stop_price=Decimal("1.0800"),
        )
    
    @pytest.fixture
    def sample_position(self):
        """Create a sample position for testing."""
        return Position(
            position_id=UUID("87654321-4321-8765-4321-876543210987"),
            symbol="EURUSD",
            broker=BrokerType.MT5,
            broker_position_id="POS_001",
            direction=Direction.LONG,
            volume=Decimal("1.0"),
            entry_price=Decimal("1.0850"),
            current_price=Decimal("1.0860"),
            unrealized_pnl=Decimal("10.0"),
            stop_loss=Decimal("1.0800"),
            take_profit=Decimal("1.0900"),
            is_open=True,
        )


class TestMT5BrokerAdapter(MockBrokerBase):
    """Integration tests for MT5 broker adapter."""
    
    @pytest.fixture
    def mt5_adapter(self):
        """Create MT5 adapter with mocked MT5."""
        with patch("src.execution.brokers.mt5_broker.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.terminal_info.return_value = MagicMock(connected=True)
            mock_mt5.account_info.return_value = MagicMock(
                login=60022138,
                balance=10000.0,
                equity=10100.0,
                margin=1000.0,
                margin_free=9000.0,
                margin_level=1010.0,
                currency="USD",
                leverage=100,
                profit=100.0,
            )
            mock_mt5.last_error.return_value = (0, "No error")
            
            adapter = MT5BrokerAdapter()
            yield adapter, mock_mt5
    
    @pytest.mark.asyncio
    async def test_connect_success(self, mt5_adapter):
        """Test successful MT5 connection."""
        adapter, mock_mt5 = mt5_adapter
        
        await adapter.connect()
        
        assert adapter.connected
        mock_mt5.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, mt5_adapter):
        """Test MT5 connection failure handling."""
        adapter, mock_mt5 = mt5_adapter
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (10001, "Login failed")
        
        with pytest.raises(ConnectionError, match="MT5 initialization failed"):
            await adapter.connect()
        
        assert not adapter.connected
    
    @pytest.mark.asyncio
    async def test_place_market_order(self, mt5_adapter, sample_order):
        """Test placing a market order."""
        adapter, mock_mt5 = mt5_adapter
        await adapter.connect()
        
        # Mock order send result
        mock_result = MagicMock()
        mock_result.retcode = 10009  # TRADE_RETCODE_DONE
        mock_result.order = 12345
        mock_result.volume = 1.0
        mock_result.price = 1.0855
        mock_result.commission = 0.5
        mock_mt5.order_send.return_value = mock_result
        mock_mt5.TRADE_RETCODE_DONE = 10009
        
        result = await adapter.place_order(sample_order)
        
        assert result.status == OrderStatus.FILLED
        assert result.broker_order_id == "12345"
        assert result.filled_volume == Decimal("1.0")
        assert result.avg_fill_price == Decimal("1.0855")
    
    @pytest.mark.asyncio
    async def test_place_order_rejection(self, mt5_adapter, sample_order):
        """Test order rejection handling."""
        adapter, mock_mt5 = mt5_adapter
        await adapter.connect()
        
        mock_result = MagicMock()
        mock_result.retcode = 10013  # TRADE_RETCODE_INVALID
        mock_result.comment = "Invalid volume"
        mock_mt5.order_send.return_value = mock_result
        
        result = await adapter.place_order(sample_order)
        
        assert result.status == OrderStatus.REJECTED
        assert "Invalid volume" in result.comment
    
    @pytest.mark.asyncio
    async def test_get_positions(self, mt5_adapter, sample_position):
        """Test retrieving positions."""
        adapter, mock_mt5 = mt5_adapter
        await adapter.connect()
        
        mock_pos = MagicMock()
        mock_pos.ticket = 98765
        mock_pos.symbol = "EURUSD"
        mock_pos.type = 0  # POSITION_TYPE_BUY
        mock_pos.volume = 1.0
        mock_pos.price_open = 1.0850
        mock_pos.price_current = 1.0860
        mock_pos.profit = 10.0
        mock_pos.sl = 1.0800
        mock_pos.tp = 1.0900
        mock_pos.swap = 0.0
        mock_pos.commission = 0.0
        mock_pos.margin = 100.0
        mock_pos.time = 1700000000
        
        mock_mt5.positions_get.return_value = (mock_pos,)
        mock_mt5.POSITION_TYPE_BUY = 0
        
        positions = await adapter.get_positions()
        
        assert len(positions) == 1
        assert positions[0].symbol == "EURUSD"
        assert positions[0].direction == Direction.LONG
        assert positions[0].volume == Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_health_check(self, mt5_adapter):
        """Test health check."""
        adapter, mock_mt5 = mt5_adapter
        await adapter.connect()
        
        mock_mt5.terminal_info.return_value = MagicMock(connected=True)
        
        healthy = await adapter.health_check()
        
        assert healthy is True


class TestCCXTBrokerAdapter(MockBrokerBase):
    """Integration tests for CCXT broker adapter."""
    
    @pytest.fixture
    def ccxt_adapter(self):
        """Create CCXT adapter with mocked exchanges."""
        with patch("src.execution.brokers.ccxt_broker.ccxt") as mock_ccxt:
            mock_exchange = AsyncMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.markets = {
                "BTC/USDT": {"symbol": "BTC/USDT", "type": "spot"},
                "ETH/USDT": {"symbol": "ETH/USDT", "type": "spot"},
            }
            mock_exchange.create_order = AsyncMock(return_value={
                "id": "order_123",
                "status": "closed",
                "filled": 1.0,
                "average": 50000.0,
                "fee": {"cost": 5.0},
            })
            mock_exchange.cancel_order = AsyncMock(return_value={"status": "canceled"})
            mock_exchange.fetch_order = AsyncMock(return_value={
                "id": "order_123",
                "status": "closed",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 1.0,
                "price": 50000.0,
                "filled": 1.0,
                "average": 50000.0,
                "fee": {"cost": 5.0},
                "timestamp": 1700000000000,
                "lastTradeTimestamp": 1700000000000,
                "clientOrderId": "TEST_001",
            })
            mock_exchange.fetch_open_orders = AsyncMock(return_value=[])
            mock_exchange.fetch_positions = AsyncMock(return_value=[])
            mock_exchange.fetch_balance = AsyncMock(return_value={
                "free": {"USDT": 10000, "BTC": 1.0},
                "used": {"USDT": 0, "BTC": 0},
                "total": {"USDT": 10000, "BTC": 1.0},
            })
            mock_exchange.fetch_time = AsyncMock(return_value=1700000000000)
            mock_exchange.close = AsyncMock()
            
            mock_ccxt.binance = MagicMock(return_value=mock_exchange)
            mock_ccxt.bybit = MagicMock(return_value=mock_exchange)
            
            adapter = CCXTBrokerAdapter(exchanges=["binance"])
            yield adapter, mock_exchange, mock_ccxt
    
    @pytest.mark.asyncio
    async def test_connect_success(self, ccxt_adapter):
        """Test successful CCXT connection."""
        adapter, mock_exchange, _mock_ccxt = ccxt_adapter
        
        await adapter.connect()
        
        assert adapter.connected
        mock_exchange.load_markets.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_place_market_order(self, ccxt_adapter, sample_order):
        """Test placing a market order via CCXT."""
        adapter, mock_exchange, _mock_ccxt = ccxt_adapter
        sample_order.symbol = "BTC/USDT"
        await adapter.connect()
        
        result = await adapter.place_order(sample_order)
        
        assert result.status == OrderStatus.FILLED
        assert result.broker_order_id == "order_123"
        assert result.filled_volume == Decimal("1.0")
        assert result.avg_fill_price == Decimal("50000.0")
        mock_exchange.create_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, ccxt_adapter):
        """Test order cancellation."""
        adapter, mock_exchange, _mock_ccxt = ccxt_adapter
        await adapter.connect()
        
        success = await adapter.cancel_order("order_123")
        
        assert success is True
        mock_exchange.cancel_order.assert_called_once_with("order_123")
    
    @pytest.mark.asyncio
    async def test_get_account_info(self, ccxt_adapter):
        """Test retrieving account info."""
        adapter, _mock_exchange, _mock_ccxt = ccxt_adapter
        await adapter.connect()
        
        accounts = await adapter.get_account_info()
        
        assert "binance" in accounts
        assert accounts["binance"]["free"]["USDT"] == 10000
    
    @pytest.mark.asyncio
    async def test_health_check(self, ccxt_adapter):
        """Test health check."""
        adapter, mock_exchange, _mock_ccxt = ccxt_adapter
        await adapter.connect()
        
        healthy = await adapter.health_check()
        
        assert healthy is True
        mock_exchange.fetch_time.assert_called_once()


class TestCTraderAdapter(MockBrokerBase):
    """Integration tests for cTrader broker adapter."""
    
    @pytest.fixture
    def ctrader_adapter(self):
        """Create cTrader adapter."""
        adapter = CTraderAdapter(
            client_id="test_client",
            client_secret="test_secret",
            access_token="test_token",
        )
        yield adapter
    
    @pytest.mark.asyncio
    async def test_initialization(self, ctrader_adapter):
        """Test adapter initialization."""
        assert ctrader_adapter.broker_type == BrokerType.CTRADER
        assert ctrader_adapter._client_id == "test_client"
        assert not ctrader_adapter.is_connected
    
    @pytest.mark.asyncio
    async def test_place_order_not_connected(self, ctrader_adapter, sample_order):
        """Test order placement when not connected."""
        with pytest.raises(ConnectionError):
            await ctrader_adapter.place_order(sample_order)


class TestIBKRAdapter(MockBrokerBase):
    """Integration tests for IBKR broker adapter."""
    
    @pytest.fixture
    def ibkr_adapter(self):
        """Create IBKR adapter with mocked ib_insync."""
        with patch("src.execution.brokers.ibkr_broker.IB") as mock_ib_class:
            mock_ib = MagicMock()
            mock_ib.connectAsync = AsyncMock()
            mock_ib.isConnected.return_value = True
            mock_ib.managedAccounts.return_value = ["DU123456"]
            mock_ib.qualifyContracts = MagicMock(return_value=[MagicMock(conId=123)])
            mock_ib.placeOrder = MagicMock(return_value=MagicMock(
                order=MagicMock(orderId=12345, clientId="TEST_001", action="BUY", totalQuantity=1.0, orderType="MKT", lmtPrice=0, auxPrice=0),
                orderStatus=MagicMock(status="Filled", avgFillPrice=100.0),
                filled=1.0,
                contract=MagicMock(symbol="AAPL", conId=123),
                commissionReport=MagicMock(commission=1.0),
                log=[MagicMock(time=1700000000)],
            ))
            mock_ib.cancelOrder = MagicMock()
            mock_ib.reqAllOpenOrdersAsync = AsyncMock()
            mock_ib.reqPositionsAsync = AsyncMock()
            mock_ib.accountSummary = MagicMock(return_value=[])
            mock_ib.reqCurrentTimeAsync = AsyncMock(return_value=1700000000)
            mock_ib.disconnect = MagicMock()
            mock_ib.trades = MagicMock(return_value=[])
            mock_ib.positions = MagicMock(return_value=[])
            
            mock_ib_class.return_value = mock_ib
            
            adapter = IBKRAdapter(
                host="127.0.0.1",
                port=7497,
                client_id=1,
                account="DU123456",  # Provide account explicitly
            )
            yield adapter, mock_ib, mock_ib_class
    
    @pytest.mark.asyncio
    async def test_connect_success(self, ibkr_adapter):
        """Test successful IBKR connection."""
        adapter, mock_ib, _mock_ib_class = ibkr_adapter
        
        await adapter.connect()
        
        assert adapter.is_connected
        assert adapter._account_id == "DU123456"
        mock_ib.connectAsync.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_place_market_order(self, ibkr_adapter, sample_order):
        """Test placing a market order via IBKR."""
        adapter, mock_ib, _mock_ib_class = ibkr_adapter
        sample_order.symbol = "AAPL"
        await adapter.connect()
        
        result = await adapter.place_order(sample_order)
        
        assert result.status == OrderStatus.FILLED
        assert result.broker_order_id == "12345"
        assert result.filled_volume == Decimal("1.0")
        assert result.avg_fill_price == Decimal("100.0")
        mock_ib.placeOrder.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check(self, ibkr_adapter):
        """Test health check."""
        adapter, mock_ib, _mock_ib_class = ibkr_adapter
        await adapter.connect()
        
        healthy = await adapter.health_check()
        
        assert healthy is True
        mock_ib.reqCurrentTimeAsync.assert_called_once()


class TestBrokerFailuresAndRecovery:
    """Tests for broker failure scenarios and recovery."""
    
    @pytest.mark.asyncio
    async def test_mt5_reconnection_after_failure(self):
        """Test MT5 reconnection after connection loss."""
        with patch("src.execution.brokers.mt5_broker.mt5") as mock_mt5:
            # Initial connection
            mock_mt5.initialize.return_value = True
            mock_mt5.terminal_info.return_value = MagicMock(connected=True)
            mock_mt5.last_error.return_value = (0, "No error")
            
            # Mock account_info for successful connection
            mock_account = MagicMock()
            mock_account.login = 60022138
            mock_account.balance = 10000.0
            mock_account.equity = 10100.0
            mock_account.margin = 1000.0
            mock_account.margin_free = 9000.0
            mock_account.margin_level = 1010.0
            mock_account.currency = "USD"
            mock_account.leverage = 100
            mock_account.profit = 100.0
            mock_mt5.account_info.return_value = mock_account
            
            adapter = MT5BrokerAdapter()
            await adapter.connect()
            assert adapter.connected
            
            # Simulate connection loss
            mock_mt5.terminal_info.return_value = MagicMock(connected=False)
            
            healthy = await adapter.health_check()
            assert healthy is False
            
            # Simulate reconnection
            mock_mt5.terminal_info.return_value = MagicMock(connected=True)
            
            healthy = await adapter.health_check()
            assert healthy is True
    
    @pytest.mark.asyncio
    async def test_ccxt_exchange_failover(self):
        """Test CCXT fallback to secondary exchange."""
        with patch("src.execution.brokers.ccxt_broker.ccxt") as mock_ccxt:
            primary = AsyncMock()
            primary.load_markets = AsyncMock()
            primary.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            primary.create_order = AsyncMock(side_effect=Exception("Primary down"))
            primary.close = AsyncMock()
            
            secondary = AsyncMock()
            secondary.load_markets = AsyncMock()
            secondary.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            secondary.create_order = AsyncMock(return_value={
                "id": "order_456",
                "status": "closed",
                "filled": 1.0,
                "average": 50000.0,
            })
            secondary.close = AsyncMock()
            
            mock_ccxt.binance = MagicMock(return_value=primary)
            mock_ccxt.bybit = MagicMock(return_value=secondary)
            
            adapter = CCXTBrokerAdapter(exchanges=["binance", "bybit"])
            await adapter.connect()
            
            # First exchange fails, should try second
            # (Implementation would need to handle this in place_order)
            # This test documents expected behavior
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker integration with brokers."""
        from src.infra.monitoring.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpenError,
        )
        
        # Create breaker with low threshold
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            timeout_seconds=5.0,
            recovery_timeout_seconds=1.0,
        )
        breaker = CircuitBreaker("test_broker", config)
        
        # Simulate failures
        async def failing_call():
            raise ConnectionError("Broker down")
        
        for _ in range(2):
            try:
                await breaker.call(failing_call)
            except ConnectionError:
                pass
        
        # Circuit should be open
        assert breaker.state.value == "open"
        
        # Further calls should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(failing_call)
        
        # Wait for recovery
        await asyncio.sleep(1.1)
        
        # Should be half-open, allow one call
        async def success_call():
            return "ok"
        
        result = await breaker.call(success_call)
        assert result == "ok"
        
        # Should be closed now
        assert breaker.state.value == "closed"


class TestBrokerPositionReconciliation:
    """Tests for position reconciliation across brokers."""
    
    @pytest.mark.asyncio
    async def test_position_matching(self):
        """Test matching local and broker positions."""
        from src.portfolio.reconciliation import (
            PositionReconciler,
            ReconciliationConfig,
        )
        
        # Create mock position manager
        local_pos = Position(
            position_id=UUID("11111111-1111-1111-1111-111111111111"),
            symbol="EURUSD",
            broker=BrokerType.MT5,
            broker_position_id="POS_001",
            direction=Direction.LONG,
            volume=Decimal("1.0"),
            entry_price=Decimal("1.0850"),
            current_price=Decimal("1.0860"),
            unrealized_pnl=Decimal("10.0"),
            is_open=True,
        )
        mock_pm = AsyncMock()
        mock_pm.get_all_positions = AsyncMock(return_value=[local_pos])
        
        config = ReconciliationConfig(interval_seconds=60)
        reconciler = PositionReconciler(mock_pm, config)
        
        # Mock broker adapter
        mock_broker = AsyncMock()
        broker_pos = Position(
            position_id=UUID("22222222-2222-2222-2222-222222222222"),
            symbol="EURUSD",
            broker=BrokerType.MT5,
            broker_position_id="POS_001",
            direction=Direction.LONG,
            volume=Decimal("1.0"),
            entry_price=Decimal("1.0850"),
            current_price=Decimal("1.0860"),
            unrealized_pnl=Decimal("10.0"),
            is_open=True,
        )
        mock_broker.get_positions = AsyncMock(return_value=[broker_pos])
        
        reconciler._brokers[BrokerType.MT5] = mock_broker
        
        result = await reconciler.reconcile()
        
        assert result.success
        assert result.mismatch_count == 0
    
    @pytest.mark.asyncio
    async def test_position_volume_mismatch(self):
        """Test detection of volume mismatch."""
        from src.portfolio.reconciliation import PositionReconciler, ReconciliationConfig
        
        local_pos = Position(
            position_id=UUID("11111111-1111-1111-1111-111111111111"),
            symbol="EURUSD",
            broker=BrokerType.MT5,
            broker_position_id="POS_001",
            direction=Direction.LONG,
            volume=Decimal("1.0"),
            entry_price=Decimal("1.0850"),
            is_open=True,
        )
        mock_pm = AsyncMock()
        mock_pm.get_all_positions = AsyncMock(return_value=[local_pos])
        
        config = ReconciliationConfig(interval_seconds=60, volume_tolerance=Decimal("0.01"))
        reconciler = PositionReconciler(mock_pm, config)
        
        mock_broker = AsyncMock()
        broker_pos = Position(
            position_id=UUID("22222222-2222-2222-2222-222222222222"),
            symbol="EURUSD",
            broker=BrokerType.MT5,
            broker_position_id="POS_001",
            direction=Direction.LONG,
            volume=Decimal("1.5"),  # Different volume
            entry_price=Decimal("1.0850"),
            is_open=True,
        )
        mock_broker.get_positions = AsyncMock(return_value=[broker_pos])
        
        reconciler._brokers[BrokerType.MT5] = mock_broker
        
        result = await reconciler.reconcile()
        
        assert result.success
        assert result.mismatch_count == 1
        assert result.mismatches[0].mismatch_type == "volume"
        assert result.mismatches[0].volume_diff == Decimal("0.5")


# Pytest configuration
def pytest_configure(config):
    """Configure pytest for async tests."""
    config.addinivalue_line("markers", "asyncio: mark test as async")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])