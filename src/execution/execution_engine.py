"""
Execution Engine - Smart order routing, TCA, multi-venue execution.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from src.data.models import Order, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class ExecutionAlgo(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    TWAP = "twap"
    VWAP = "vwap"
    POV = "pov"  # Percentage of Volume
    ICEBERG = "iceberg"
    SNIPER = "sniper"  # Aggressive limit


@dataclass
class VenueConfig:
    name: str
    broker_type: str  # "mt5", "binance", "bybit", "kraken"
    enabled: bool = True
    commission_bps: float = 0.0
    min_order_size: float = 0.01
    max_order_size: float = 100.0
    latency_ms: int = 50
    supports_iceberg: bool = False
    supports_twap: bool = False
    supports_vwap: bool = False


@dataclass
class ExecutionConfig:
    default_algo: ExecutionAlgo = ExecutionAlgo.MARKET
    twap_duration_minutes: int = 60
    vwap_participation_rate: float = 0.10  # 10% of volume
    pov_rate: float = 0.10  # 10% of volume
    iceberg_display_qty: float = 0.1  # 10% displayed
    sniper_limit_offset_bps: float = 5.0  # 5 bps from mid
    max_slippage_bps: float = 20.0  # 20 bps max slippage
    order_timeout_seconds: int = 300
    child_order_size_factor: float = 0.2  # 20% of parent per child
    venues: dict[str, VenueConfig] = field(default_factory=dict)


@dataclass
class Fill:
    fill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    venue: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    liquidity_flag: str = ""  # "maker", "taker"


@dataclass
class ExecutionReport:
    order_id: str
    status: OrderStatus
    fills: list[Fill] = field(default_factory=list)
    avg_fill_price: float = 0.0
    total_filled: float = 0.0
    remaining: float = 0.0
    commission: float = 0.0
    slippage_bps: float = 0.0
    market_impact_bps: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ExecutionAlgoBase(ABC):
    """Base class for execution algorithms."""

    def __init__(self, config: ExecutionConfig, venue: VenueConfig):
        self.config = config
        self.venue = venue

    @abstractmethod
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        """Execute order and return fills."""
        raise NotImplementedError("Subclass must implement execute()")

    def _calculate_child_size(self, parent_qty: float) -> float:
        """Calculate child order size."""
        return parent_qty * self.config.child_order_size_factor


class MarketOrderAlgo(ExecutionAlgoBase):
    """Simple market order execution"""
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        # Get current market price
        bid = market_data.get_bid(order.symbol)
        ask = market_data.get_ask(order.symbol)
        
        if order.side == OrderSide.BUY:
            fill_price = ask
        else:
            fill_price = bid
        
        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=fill_price * order.quantity * (self.venue.commission_bps / 10000),
            venue=self.venue.name,
            liquidity_flag="taker"
        )
        
        return [fill]


class LimitOrderAlgo(ExecutionAlgoBase):
    """Limit order with timeout and optional re-price"""
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        # Simplified - would actually place limit order and wait
        # For now, simulate immediate fill if price is favorable
        bid = market_data.get_bid(order.symbol)
        ask = market_data.get_ask(order.symbol)
        
        if order.side == OrderSide.BUY and order.price >= ask:
            fill_price = ask
        elif order.side == OrderSide.SELL and order.price <= bid:
            fill_price = bid
        else:
            # Would wait for fill - simplified to return empty
            return []
        
        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=fill_price * order.quantity * (self.venue.commission_bps / 10000),
            venue=self.venue.name,
            liquidity_flag="maker"
        )
        
        return [fill]


class TWAPAlgo(ExecutionAlgoBase):
    """Time-Weighted Average Price execution"""
    
    def __init__(self, config: ExecutionConfig, venue: VenueConfig):
        super().__init__(config, venue)
        self.duration = timedelta(minutes=config.twap_duration_minutes)
        self.interval = timedelta(minutes=5)  # Every 5 minutes
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        fills = []
        remaining = order.quantity
        start_time = datetime.now(UTC)
        end_time = start_time + self.duration
        
        while remaining > 0 and datetime.now(UTC) < end_time:
            child_size = min(self._calculate_child_size(order.quantity), remaining)
            
            # Place market child order
            child_order = Order(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                quantity=child_size,
                order_type=OrderType.MARKET,
                strategy_id=order.strategy_id,
                parent_order_id=order.order_id
            )
            
            market_algo = MarketOrderAlgo(self.config, self.venue)
            child_fills = await market_algo.execute(child_order, market_data)
            
            for fill in child_fills:
                fills.append(fill)
                remaining -= fill.quantity
            
            # Wait for next interval
            await asyncio.sleep(self.interval.total_seconds())
        
        return fills


class VWAPAlgo(ExecutionAlgoBase):
    """Volume-Weighted Average Price execution"""
    
    def __init__(self, config: ExecutionConfig, venue: VenueConfig):
        super().__init__(config, venue)
        self.participation_rate = config.vwap_participation_rate
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        fills = []
        remaining = order.quantity
        
        # Get volume profile for the day
        volume_profile = market_data.get_volume_profile(order.symbol)
        if not volume_profile:
            # Fallback to TWAP
            twap = TWAPAlgo(self.config, self.venue)
            return await twap.execute(order, market_data)
        
        # Execute proportionally to volume
        for expected_vol in volume_profile.values():
            if remaining <= 0:
                break
            
            # Target volume = participation_rate * expected_volume
            target_vol = expected_vol * self.participation_rate
            child_size = min(target_vol, remaining)
            
            if child_size < self.venue.min_order_size:
                continue
            
            child_order = Order(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                quantity=child_size,
                order_type=OrderType.MARKET,
                strategy_id=order.strategy_id,
                parent_order_id=order.order_id
            )
            
            market_algo = MarketOrderAlgo(self.config, self.venue)
            child_fills = await market_algo.execute(child_order, market_data)
            
            for fill in child_fills:
                fills.append(fill)
                remaining -= fill.quantity
            
            await asyncio.sleep(60)  # 1 minute intervals
        
        return fills


class IcebergAlgo(ExecutionAlgoBase):
    """Iceberg order - shows small display quantity"""
    
    def __init__(self, config: ExecutionConfig, venue: VenueConfig):
        super().__init__(config, venue)
        self.display_qty_pct = config.iceberg_display_qty
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        if not self.venue.supports_iceberg:
            # Fallback to limit
            limit_algo = LimitOrderAlgo(self.config, self.venue)
            return await limit_algo.execute(order, market_data)
        
        fills = []
        remaining = order.quantity
        display_qty = order.quantity * self.display_qty_pct
        
        while remaining > 0:
            current_display = min(display_qty, remaining)
            
            child_order = Order(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                quantity=current_display,
                order_type=OrderType.LIMIT,
                price=order.price,
                strategy_id=order.strategy_id,
                parent_order_id=order.order_id,
                iceberg=True,
                iceberg_qty=display_qty
            )
            
            limit_algo = LimitOrderAlgo(self.config, self.venue)
            child_fills = await limit_algo.execute(child_order, market_data)
            
            for fill in child_fills:
                fills.append(fill)
                remaining -= fill.quantity
            
            if remaining > 0:
                await asyncio.sleep(1)  # Brief pause between tranches
        
        return fills


class SniperAlgo(ExecutionAlgoBase):
    """Aggressive limit order - places limit slightly better than market"""
    
    def __init__(self, config: ExecutionConfig, venue: VenueConfig):
        super().__init__(config, venue)
        self.offset_bps = config.sniper_limit_offset_bps
    
    async def execute(self, order: Order, market_data: Any) -> list[Fill]:
        bid = market_data.get_bid(order.symbol)
        ask = market_data.get_ask(order.symbol)
        mid = (bid + ask) / 2
        
        # Place limit slightly better than market
        if order.side == OrderSide.BUY:
            limit_price = mid * (1 + self.offset_bps / 10000)
            if limit_price >= ask:
                limit_price = ask * 0.9999  # Just inside
        else:
            limit_price = mid * (1 - self.offset_bps / 10000)
            if limit_price <= bid:
                limit_price = bid * 1.0001
        
        limit_order = Order(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=OrderType.LIMIT,
            price=limit_price,
            strategy_id=order.strategy_id
        )
        
        limit_algo = LimitOrderAlgo(self.config, self.venue)
        return await limit_algo.execute(limit_order, market_data)


class SmartExecutionEngine:
    """Main execution engine with smart routing"""
    
    def __init__(self, config: ExecutionConfig, portfolio: Any = None):
        self.config = config
        self.portfolio = portfolio
        
        # Initialize venues
        self.venues: dict[str, VenueConfig] = config.venues
        self._init_default_venues()
        
        # Algorithm instances
        self.algorithms: dict[ExecutionAlgo, ExecutionAlgoBase] = {}
        
        # State
        self.active_orders: dict[str, Order] = {}
        self.order_history: list[ExecutionReport] = []
        self.pending_fills: dict[str, list[Fill]] = {}
        
        # Metrics
        self.total_volume = 0.0
        self.total_commission = 0.0
        self.total_slippage_bps = 0.0
        
        logger.info("SmartExecutionEngine initialized")
    
    def _init_default_venues(self):
        """Initialize default venue configurations"""
        if not self.config.venues:
            self.config.venues = {
                "mt5": VenueConfig(
                    name="mt5",
                    broker_type="mt5",
                    enabled=True,
                    commission_bps=0.0,  # Included in spread
                    min_order_size=0.01,
                    max_order_size=100.0,
                    latency_ms=10,
                ),
                "binance": VenueConfig(
                    name="binance",
                    broker_type="binance",
                    enabled=True,
                    commission_bps=1.0,  # 1 bps
                    min_order_size=0.001,
                    max_order_size=1000.0,
                    latency_ms=50,
                    supports_iceberg=True,
                    supports_twap=True,
                    supports_vwap=True,
                ),
                "bybit": VenueConfig(
                    name="bybit",
                    broker_type="bybit",
                    enabled=True,
                    commission_bps=1.0,
                    min_order_size=0.001,
                    max_order_size=1000.0,
                    latency_ms=80,
                    supports_iceberg=True,
                    supports_twap=True,
                ),
                "kraken": VenueConfig(
                    name="kraken",
                    broker_type="kraken",
                    enabled=True,
                    commission_bps=2.0,
                    min_order_size=0.01,
                    max_order_size=500.0,
                    latency_ms=100,
                ),
            }
    
    def _get_algorithm(self, algo: ExecutionAlgo, venue_name: str) -> ExecutionAlgoBase:
        """Get or create algorithm instance"""
        key = (algo, venue_name)
        if key not in self.algorithms:
            venue = self.config.venues.get(venue_name)
            if not venue:
                raise ValueError(f"Venue {venue_name} not configured")
            
            if algo == ExecutionAlgo.MARKET:
                self.algorithms[key] = MarketOrderAlgo(self.config, venue)
            elif algo == ExecutionAlgo.LIMIT:
                self.algorithms[key] = LimitOrderAlgo(self.config, venue)
            elif algo == ExecutionAlgo.TWAP:
                self.algorithms[key] = TWAPAlgo(self.config, venue)
            elif algo == ExecutionAlgo.VWAP:
                self.algorithms[key] = VWAPAlgo(self.config, venue)
            elif algo == ExecutionAlgo.POV:
                self.algorithms[key] = VWAPAlgo(self.config, venue)  # Similar
            elif algo == ExecutionAlgo.ICEBERG:
                self.algorithms[key] = IcebergAlgo(self.config, venue)
            elif algo == ExecutionAlgo.SNIPER:
                self.algorithms[key] = SniperAlgo(self.config, venue)
            else:
                raise ValueError(f"Unknown algorithm: {algo}")
        
        return self.algorithms[key]
    
    def _select_venue(self, order: Order) -> str:
        """Smart venue selection"""
        # For FX, use MT5
        if order.symbol in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD"]:
            return "mt5"
        
        # For crypto, use best venue based on liquidity
        crypto_venues = ["binance", "bybit", "kraken"]
        for v in crypto_venues:
            if v in self.config.venues and self.config.venues[v].enabled:
                return v
        
        return "mt5"  # Default
    
    def _select_algorithm(self, order: Order, market_data: Any) -> tuple[ExecutionAlgo, str]:
        """Smart algorithm selection based on order and market conditions"""
        _venue = self._select_venue(order)
        
        # Check spread
        bid = market_data.get_bid(order.symbol)
        ask = market_data.get_ask(order.symbol)
        spread_bps = ((ask - bid) / ((bid + ask) / 2)) * 10000 if bid > 0 else 0
        
        # Check volume
        volume = market_data.get_volume(order.symbol)
        avg_volume = market_data.get_avg_volume(order.symbol)
        _vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        # Large order relative to volume -> TWAP/VWAP
        order_size_pct = order.quantity / avg_volume if avg_volume > 0 else 0
        
        if order_size_pct > 0.05:  # >5% of avg volume
            if self.config.venues[self._select_venue(order)].supports_vwap:
                return ExecutionAlgo.VWAP, self._select_venue(order)
            return ExecutionAlgo.TWAP, self._select_venue(order)
        
        # Wide spread -> limit or sniper
        if spread_bps > 10:
            return ExecutionAlgo.SNIPER, self._select_venue(order)
        
        # Small spread, small order -> market or sniper
        if order_size_pct < 0.001:
            return ExecutionAlgo.SNIPER, self._select_venue(order)
        
        # Default: market
        return ExecutionAlgo.MARKET, self._select_venue(order)
    
    async def submit_order(self, order: Order, market_data: Any = None) -> ExecutionReport:
        """Submit order for execution"""
        if market_data is None:
            market_data = self._get_market_data()
        
        # Select algorithm and venue
        algo, venue = self._select_algorithm(order, market_data)
        _venue_config = self.config.venues[venue]
        
        # Get algorithm instance
        execution_algo = self._get_algorithm(algo, venue)
        
        # Track order
        self.active_orders[order.order_id] = order
        
        # Execute
        start_time = datetime.now(UTC)
        fills = await execution_algo.execute(order, market_data)
        
        # Calculate execution quality
        report = self._create_report(order, fills, start_time)
        
        # Store
        self.order_history.append(report)
        if order.order_id in self.active_orders:
            del self.active_orders[order.order_id]
        
        return report
    
    def _create_report(self, order: Order, fills: list[Fill], start_time: datetime) -> ExecutionReport:
        """Create execution report with quality metrics"""
        if not fills:
            return ExecutionReport(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                timestamp=datetime.now(UTC)
            )
        
        total_qty = sum(f.quantity for f in fills)
        avg_price = sum(f.price * f.quantity for f in fills) / total_qty
        total_commission = sum(f.commission for f in fills)
        
        # Slippage
        bid = self._get_market_data().get_bid(order.symbol)
        ask = self._get_market_data().get_ask(order.symbol)
        mid = (bid + ask) / 2
        
        if order.side == OrderSide.BUY:
            slippage = (avg_price - mid) / mid * 10000
        else:
            slippage = (mid - avg_price) / mid * 10000
        
        # Market impact (simplified)
        market_impact = slippage * 0.5  # Rough estimate
        
        status = OrderStatus.FILLED if total_qty >= order.quantity * 0.99 else OrderStatus.PARTIALLY_FILLED
        
        return ExecutionReport(
            order_id=order.order_id,
            status=status,
            fills=fills,
            avg_fill_price=avg_price,
            total_filled=total_qty,
            remaining=order.quantity - total_qty,
            commission=total_commission,
            slippage_bps=slippage,
            market_impact_bps=market_impact,
            timestamp=datetime.now(UTC)
        )
    
    def _get_market_data(self) -> Any:
            """Get market data - integrates with market data service."""
            from src.data.models import MarketData
            # Returns a MarketData instance for simulation
            return MarketData()


    class TCAAnalyzer:
        """Transaction Cost Analysis."""

        def __init__(self, timescaledb=None):
            self.timescaledb = timescaledb
    
    def analyze_order(self, report: ExecutionReport, market_data: Any) -> dict[str, Any]:
        """Analyze single order execution quality"""
        return {
            "order_id": report.order_id,
            "slippage_bps": report.slippage_bps,
            "market_impact_bps": report.market_impact_bps,
            "commission_bps": (report.commission / (report.avg_fill_price * report.total_filled)) * 10000 if report.total_filled > 0 else 0,
            "total_cost_bps": report.slippage_bps + report.market_impact_bps + (report.commission / (report.avg_fill_price * report.total_filled)) * 10000 if report.total_filled > 0 else 0,
            "fill_rate": report.total_filled / (report.total_filled + report.remaining) if (report.total_filled + report.remaining) > 0 else 0,
            "execution_time_seconds": 0,  # Would track actual time
        }
    
    def analyze_period(self, start: datetime, end: datetime) -> dict[str, Any]:
        """Analyze execution quality over period"""
        # Would query execution reports from DB
        return {
            "total_orders": 0,
            "avg_slippage_bps": 0.0,
            "avg_market_impact_bps": 0.0,
            "avg_commission_bps": 0.0,
            "fill_rate": 1.0,
            "by_venue": {},
            "by_algorithm": {},
            "by_symbol": {},
        }
    
    def generate_tca_report(self, start: datetime, end: datetime) -> str:
        """Generate TCA report"""
        analysis = self.analyze_period(start, end)
        return f"""
TCA Report: {start.date()} to {end.date()}
=====================================
Total Orders: {analysis['total_orders']}
Avg Slippage: {analysis['avg_slippage_bps']:.2f} bps
Avg Market Impact: {analysis['avg_market_impact_bps']:.2f} bps
Avg Commission: {analysis['avg_commission_bps']:.2f} bps
Fill Rate: {analysis['fill_rate']:.2%}

By Venue: {analysis['by_venue']}
By Algorithm: {analysis['by_algorithm']}
By Symbol: {analysis['by_symbol']}
"""