"""
Elite Autonomous Quantum Trading System - Order Book / DOM (Depth of Market)
Real-time Level 2 data, Order Flow Footprint, Volume Bubbles
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class OrderBookLevel:
    """Single price level in order book."""
    price: float
    size: float
    order_count: int = 1
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OrderBookSnapshot:
    """Complete order book snapshot."""
    symbol: str
    timestamp: datetime
    bids: list[OrderBookLevel] = field(default_factory=list)  # Sorted descending
    asks: list[OrderBookLevel] = field(default_factory=list)  # Sorted ascending
    spread: float = 0.0
    mid_price: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    imbalance: float = 0.0
    
    def __post_init__(self):
        if self.bids and self.asks:
            self.spread = self.asks[0].price - self.bids[0].price
            self.mid_price = (self.asks[0].price + self.bids[0].price) / 2
            self.bid_volume = sum(b.size for b in self.bids)
            self.ask_volume = sum(a.size for a in self.asks)
            total = self.bid_volume + self.ask_volume
            self.imbalance = (self.bid_volume - self.ask_volume) / total if total > 0 else 0


@dataclass
class TradeEvent:
    """Individual trade event."""
    symbol: str
    price: float
    size: float
    side: OrderSide
    timestamp: datetime
    trade_id: str = ""
    aggressive: bool = True  # True if market order (aggressor)


@dataclass
class FootprintBar:
    """Footprint (volume profile) for a single bar."""
    symbol: str
    timestamp: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    price_levels: dict[float, dict[str, float]] = field(default_factory=dict)  # price -> {buy_vol, sell_vol, delta}
    total_buy_volume: float = 0.0
    total_sell_volume: float = 0.0
    delta: float = 0.0
    poc_price: float = 0.0  # Point of Control (highest volume price)
    
    def __post_init__(self):
        for price, vols in self.price_levels.items():
            self.total_buy_volume += vols.get('buy', 0)
            self.total_sell_volume += vols.get('sell', 0)
        self.delta = self.total_buy_volume - self.total_sell_volume
        
        # Find POC
        if self.price_levels:
            self.poc_price = max(self.price_levels.keys(), 
                               key=lambda p: self.price_levels[p].get('buy', 0) + self.price_levels[p].get('sell', 0))


@dataclass
class VolumeBubble:
    """Volume bubble for visualization."""
    price: float
    size: float
    buy_volume: float
    sell_volume: float
    timestamp: datetime
    color: str = "#58a6ff"  # Default blue


class OrderBookManager:
    """
    Real-time Order Book / DOM Manager.
    
    Features:
    - Level 2 order book aggregation
    - Real-time bid/ask updates
    - Order flow footprint bars
    - Volume bubbles (large order detection)
    - Market depth visualization
    - Imbalance tracking
    - Spread analysis
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.max_levels = self.config.get("max_levels", 50)
        self.footprint_timeframe = self.config.get("footprint_timeframe", "1m")
        self.volume_bubble_threshold = self.config.get("volume_bubble_threshold", 10000)  # Min size for bubble
        
        # Order books per symbol
        self.order_books: dict[str, OrderBookSnapshot] = {}
        self.order_book_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Footprint data
        self.footprint_bars: dict[str, FootprintBar] = {}
        self.footprint_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        
        # Trade events
        self.recent_trades: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Volume bubbles
        self.volume_bubbles: dict[str, list[VolumeBubble]] = defaultdict(list)
        
        # Callbacks
        self.on_book_update: list[callable] = []
        self.on_footprint_update: list[callable] = []
        self.on_trade: list[callable] = []
        self.on_bubble: list[callable] = []
        
        logger.info("OrderBookManager initialized")
    
    def update_level2(
        self,
        symbol: str,
        bids: list[tuple[float, float]],  # (price, size)
        asks: list[tuple[float, float]],
        timestamp: datetime | None = None
    ) -> OrderBookSnapshot:
        """Update order book from Level 2 data."""
        if timestamp is None:
            timestamp = datetime.now(UTC)
        
        # Convert to OrderBookLevel objects
        bid_levels = [OrderBookLevel(price=p, size=s, timestamp=timestamp) for p, s in bids[:self.max_levels]]
        ask_levels = [OrderBookLevel(price=p, size=s, timestamp=timestamp) for p, s in asks[:self.max_levels]]
        
        # Sort: bids descending, asks ascending
        bid_levels.sort(key=lambda x: x.price, reverse=True)
        ask_levels.sort(key=lambda x: x.price)
        
        snapshot = OrderBookSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            bids=bid_levels,
            asks=ask_levels
        )
        
        self.order_books[symbol] = snapshot
        self.order_book_history[symbol].append(snapshot)
        
        # Trigger callbacks
        for callback in self.on_book_update:
            try:
                callback(snapshot)
            except Exception as e:
                logger.error(f"Book update callback error: {e}")
        
        return snapshot
    
    def update_from_feed(self, symbol: str, feed_data: dict[str, Any]) -> OrderBookSnapshot | None:
        """Update from various feed formats (MT5, CCXT, etc.)."""
        try:
            # MT5 format
            if "bids" in feed_data and "asks" in feed_data:
                bids = [(float(b[0]), float(b[1])) for b in feed_data["bids"]]
                asks = [(float(a[0]), float(a[1])) for a in feed_data["asks"]]
                ts = feed_data.get("timestamp", datetime.now(UTC))
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return self.update_level2(symbol, bids, asks, ts)
            
            # CCXT format
            if "bid" in feed_data and "ask" in feed_data:
                # Only top of book
                bids = [(float(feed_data["bid"]), float(feed_data.get("bid_volume", 1)))]
                asks = [(float(feed_data["ask"]), float(feed_data.get("ask_volume", 1)))]
                ts = feed_data.get("timestamp", datetime.now(UTC))
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts / 1000, UTC)
                return self.update_level2(symbol, bids, asks, ts)
            
        except Exception as e:
            logger.error(f"Feed update error for {symbol}: {e}")
        
        return None
    
    def add_trade(self, trade: TradeEvent) -> FootprintBar | None:
        """Add trade event and update footprint."""
        self.recent_trades[trade.symbol].append(trade)
        
        # Get or create current footprint bar
        bar_key = f"{trade.symbol}_{trade.timestamp.strftime('%Y%m%d_%H%M')}"  # 1-min bars
        
        if bar_key not in self.footprint_bars:
            # Create new bar
            recent = list(self.recent_trades[trade.symbol])[-100:]
            if recent:
                prices = [t.price for t in recent]
                self.footprint_bars[bar_key] = FootprintBar(
                    symbol=trade.symbol,
                    timestamp=trade.timestamp.replace(second=0, microsecond=0),
                    timeframe=self.footprint_timeframe,
                    open=prices[0] if prices else trade.price,
                    high=max(prices) if prices else trade.price,
                    low=min(prices) if prices else trade.price,
                    close=trade.price
                )
        
        bar = self.footprint_bars.get(bar_key)
        if bar:
            # Update bar
            bar.high = max(bar.high, trade.price)
            bar.low = min(bar.low, trade.price)
            bar.close = trade.price
            
            # Round price to tick size (simplified)
            tick_size = self._get_tick_size(trade.symbol)
            price_level = round(trade.price / tick_size) * tick_size
            
            if price_level not in bar.price_levels:
                bar.price_levels[price_level] = {"buy": 0.0, "sell": 0.0, "delta": 0.0}
            
            if trade.side == OrderSide.BUY:
                bar.price_levels[price_level]["buy"] += trade.size
            else:
                bar.price_levels[price_level]["sell"] += trade.size
            
            bar.price_levels[price_level]["delta"] = (
                bar.price_levels[price_level]["buy"] - bar.price_levels[price_level]["sell"]
            )
            
            # Check for volume bubble
            total_vol = (bar.price_levels[price_level]["buy"] + 
                        bar.price_levels[price_level]["sell"])
            if total_vol >= self.volume_bubble_threshold:
                bubble = VolumeBubble(
                    price=price_level,
                    size=total_vol,
                    buy_volume=bar.price_levels[price_level]["buy"],
                    sell_volume=bar.price_levels[price_level]["sell"],
                    timestamp=trade.timestamp,
                    color="#3fb950" if bar.price_levels[price_level]["buy"] > bar.price_levels[price_level]["sell"] else "#f85149"
                )
                self.volume_bubbles[trade.symbol].append(bubble)
                
                for callback in self.on_bubble:
                    try:
                        callback(bubble)
                    except Exception:
                        logging.getLogger(__name__).exception('Suppressed exception')
            
            # Trigger callbacks
            for callback in self.on_footprint_update:
                try:
                    callback(bar)
                except Exception as e:
                    logger.error(f"Footprint update callback error: {e}")
        
        # Trigger trade callbacks
        for callback in self.on_trade:
            try:
                callback(trade)
            except Exception as e:
                logger.error(f"Trade callback error: {e}")
        
        return bar
    
    def _get_tick_size(self, symbol: str) -> float:
        """Get tick size for symbol."""
        # Simplified - in reality would be symbol-specific
        if "JPY" in symbol or "XAU" in symbol or "XAG" in symbol or "BTC" in symbol or "ETH" in symbol:
            return 0.01
        else:
            return 0.00001
    
    def get_book(self, symbol: str) -> OrderBookSnapshot | None:
        """Get current order book snapshot."""
        return self.order_books.get(symbol)
    
    def get_footprint(self, symbol: str, bars_back: int = 0) -> FootprintBar | None:
        """Get current or historical footprint bar."""
        if not self.footprint_bars:
            return None
        
        bars = list(self.footprint_bars.values())
        if not bars:
            return None
        
        # Filter by symbol
        symbol_bars = [b for b in bars if b.symbol == symbol]
        if not symbol_bars:
            return None
        
        # Sort by timestamp
        symbol_bars.sort(key=lambda x: x.timestamp, reverse=True)
        
        if bars_back < len(symbol_bars):
            return symbol_bars[bars_back]
        return None
    
    def get_recent_trades(self, symbol: str, count: int = 100) -> list[TradeEvent]:
        """Get recent trades."""
        trades = list(self.recent_trades.get(symbol, []))
        return trades[-count:] if trades else []
    
    def get_volume_bubbles(self, symbol: str, count: int = 50) -> list[VolumeBubble]:
        """Get recent volume bubbles."""
        bubbles = self.volume_bubbles.get(symbol, [])
        return bubbles[-count:] if bubbles else []
    
    def get_market_depth(self, symbol: str, levels: int = 10) -> dict[str, Any]:
        """Get formatted market depth for visualization."""
        book = self.get_book(symbol)
        if not book:
            return {"bids": [], "asks": [], "spread": 0, "mid": 0, "imbalance": 0}
        
        return {
            "bids": [
                {"price": b.price, "size": b.size, "orders": b.order_count}
                for b in book.bids[:levels]
            ],
            "asks": [
                {"price": a.price, "size": a.size, "orders": a.order_count}
                for a in book.asks[:levels]
            ],
            "spread": book.spread,
            "mid": book.mid_price,
            "imbalance": book.imbalance,
            "bid_volume": book.bid_volume,
            "ask_volume": book.ask_volume,
            "timestamp": book.timestamp.isoformat()
        }
    
    def get_order_flow_metrics(self, symbol: str, lookback_bars: int = 20) -> dict[str, float]:
        """Calculate order flow metrics."""
        bars = list(self.footprint_history.get(symbol, []))[-lookback_bars:]
        if not bars:
            bars = [b for b in self.footprint_bars.values() if b.symbol == symbol][-lookback_bars:]
        
        if not bars:
            return {}
        
        total_delta = sum(b.delta for b in bars)
        total_volume = sum(b.total_buy_volume + b.total_sell_volume for b in bars)
        buy_volume = sum(b.total_buy_volume for b in bars)
        sell_volume = sum(b.total_sell_volume for b in bars)
        
        # Cumulative delta
        cumulative_delta = 0
        delta_series = []
        for b in bars:
            cumulative_delta += b.delta
            delta_series.append(cumulative_delta)
        
        return {
            "cumulative_delta": cumulative_delta,
            "total_delta": total_delta,
            "total_volume": total_volume,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "buy_ratio": buy_volume / total_volume if total_volume > 0 else 0,
            "sell_ratio": sell_volume / total_volume if total_volume > 0 else 0,
            "delta_series": delta_series,
            "avg_delta_per_bar": total_delta / len(bars) if bars else 0,
            "max_delta": max(delta_series) if delta_series else 0,
            "min_delta": min(delta_series) if delta_series else 0
        }
    
    def get_vwap(self, symbol: str, lookback_bars: int = 20) -> float:
        """Calculate VWAP from footprint data."""
        bars = list(self.footprint_history.get(symbol, []))[-lookback_bars:]
        if not bars:
            bars = [b for b in self.footprint_bars.values() if b.symbol == symbol][-lookback_bars:]
        
        if not bars:
            return 0.0
        
        total_pv = 0.0  # Price * Volume
        total_vol = 0.0
        
        for bar in bars:
            for price, vols in bar.price_levels.items():
                vol = vols.get('buy', 0) + vols.get('sell', 0)
                total_pv += price * vol
                total_vol += vol
        
        return total_pv / total_vol if total_vol > 0 else 0.0
    
    def get_poc_levels(self, symbol: str, lookback_bars: int = 20) -> list[float]:
        """Get Point of Control (POC) levels from recent bars."""
        bars = list(self.footprint_history.get(symbol, []))[-lookback_bars:]
        if not bars:
            bars = [b for b in self.footprint_bars.values() if b.symbol == symbol][-lookback_bars:]
        
        return [b.poc_price for b in bars if b.poc_price > 0]


class DOMVisualizer:
    """Helper for DOM visualization in dashboard."""
    
    @staticmethod
    def create_dom_html(symbol: str, depth: dict[str, Any], height: int = 400) -> str:
        """Create HTML for DOM visualization."""
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])
        spread = depth.get("spread", 0)
        mid = depth.get("mid", 0)
        imbalance = depth.get("imbalance", 0)
        
        max_size = max(
            max((b["size"] for b in bids), default=1),
            max((a["size"] for a in asks), default=1)
        )
        
        html = f"""
        <div style="font-family: monospace; font-size: 12px; background: #0e1117; color: #e0e0e0; padding: 10px; height: {height}px; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding: 5px; background: #161b22; border-radius: 4px;">
                <span style="color: #3fb950;">BID</span>
                <span style="color: #8b949e;">{symbol}</span>
                <span style="color: #f85149;">ASK</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 11px; color: #8b949e;">
                <span>Spread: {spread:.5f}</span>
                <span>Mid: {mid:.5f}</span>
                <span>Imbalance: {imbalance:.2%}</span>
            </div>
        """
        
        # ASKS (top, red)
        for i, ask in enumerate(asks[:15]):
            bar_width = min(100, (ask["size"] / max_size) * 100) if max_size > 0 else 0
            html += f"""
            <div style="display: flex; align-items: center; margin: 1px 0; opacity: {1 - i*0.03:.2f};">
                <div style="width: {bar_width}%; height: 20px; background: linear-gradient(90deg, #f85149, #ff6b6b); border-radius: 0 4px 4px 0;"></div>
                <span style="width: 80px; text-align: right; padding-right: 10px; color: #f85149;">{ask["price"]:.5f}</span>
                <span style="width: 60px; text-align: right; color: #8b949e;">{ask["size"]:.2f}</span>
            </div>
            """
        
        # Spread line
        html += """
        <div style="height: 2px; background: #30363d; margin: 5px 0; border: 1px dashed #58a6ff;"></div>
        """
        
        # BIDS (bottom, green)
        for i, bid in enumerate(bids[:15]):
            bar_width = min(100, (bid["size"] / max_size) * 100) if max_size > 0 else 0
            html += f"""
            <div style="display: flex; align-items: center; margin: 1px 0; opacity: {1 - i*0.03:.2f};">
                <span style="width: 80px; text-align: right; padding-right: 10px; color: #3fb950;">{bid["price"]:.5f}</span>
                <div style="width: {bar_width}%; height: 20px; background: linear-gradient(90deg, #3fb950, #5de68a); border-radius: 4px 0 0 4px;"></div>
                <span style="width: 60px; text-align: right; color: #8b949e;">{bid["size"]:.2f}</span>
            </div>
            """
        
        html += "</div>"
        return html
    
    @staticmethod
    def create_footprint_html(footprint: FootprintBar, height: int = 300) -> str:
        """Create HTML for footprint chart."""
        if not footprint.price_levels:
            return "<div>No footprint data</div>"
        
        max_vol = max(
            vols.get('buy', 0) + vols.get('sell', 0) 
            for vols in footprint.price_levels.values()
        )
        
        # Sort price levels descending
        sorted_levels = sorted(footprint.price_levels.items(), key=lambda x: x[0], reverse=True)
        
        html = f"""
        <div style="font-family: monospace; font-size: 10px; background: #0e1117; color: #e0e0e0; padding: 10px; height: {height}px; overflow-y: auto;">
            <div style="margin-bottom: 10px;">
                <span style="color: #58a6ff;">{footprint.symbol}</span> | 
                <span>O:{footprint.open:.5f} H:{footprint.high:.5f} L:{footprint.low:.5f} C:{footprint.close:.5f}</span> | 
                <span style="color: #3fb950;">Δ{footprint.delta:.2f}</span> | 
                <span>POC: {footprint.poc_price:.5f}</span>
            </div>
        """
        
        for price, vols in sorted_levels:
            buy_vol = vols.get('buy', 0)
            sell_vol = vols.get('sell', 0)
            total_vol = buy_vol + sell_vol
            delta = vols.get('delta', 0)
            
            buy_width = min(100, (buy_vol / max_vol) * 100) if max_vol > 0 else 0
            sell_width = min(100, (sell_vol / max_vol) * 100) if max_vol > 0 else 0
            
            delta_color = "#3fb950" if delta > 0 else "#f85149" if delta < 0 else "#8b949e"
            
            html += f"""
            <div style="display: flex; align-items: center; margin: 1px 0;">
                <span style="width: 80px; text-align: right; padding-right: 5px;">{price:.5f}</span>
                <div style="width: {sell_width}%; height: 16px; background: #f85149; border-radius: 0 4px 4px 0;"></div>
                <div style="width: {buy_width}%; height: 16px; background: #3fb950; border-radius: 4px 0 0 4px;"></div>
                <span style="width: 50px; text-align: right; padding-left: 5px; color: {delta_color};">{delta:+.2f}</span>
            </div>
            """
        
        html += "</div>"
        return html


# Global instance
order_book_manager = OrderBookManager()


async def get_order_book_manager(config: dict | None = None) -> OrderBookManager:
    """Get or create global order book manager."""
    global order_book_manager
    if config:
        order_book_manager = OrderBookManager(config)
    return order_book_manager