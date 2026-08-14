#!/usr/bin/env python
"""
Bloomberg-Style Trading Terminal (TUI)
Real-time trading terminal with Textual TUI framework
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import redis.asyncio as redis
from loguru import logger
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    RichLog,
    Sparkline,
    Static,
)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.storage.redis_cache import redis_cache
from src.data.storage.timescale import timescaledb
from src.infra.config.settings import settings


class PriceWidget(Static):
    """Real-time price display widget"""

    symbol: reactive[str] = ""
    bid: reactive[float] = 0.0
    ask: reactive[float] = 0.0
    change: reactive[float] = 0.0
    change_pct: reactive[float] = 0.0

    def watch_bid(self, bid: float) -> None:
        self.refresh()

    def watch_ask(self, ask: float) -> None:
        self.refresh()

    def watch_change(self, change: float) -> None:
        self.refresh()

    def watch_change_pct(self, pct: float) -> None:
        self.refresh()

    def render(self) -> str:
        color = "green" if self.change >= 0 else "red"
        change_str = f"{self.change:+.5f} ({self.change_pct:+.2f}%)"
        return f"[bold]{self.symbol}[/bold]\n[bid:{self.bid:.5f}] [ask:{self.ask:.5f}]\n[{color}]{change_str}[/]"


class PositionsTable(DataTable):
    """Positions table with live updates"""

    def on_mount(self) -> None:
        self.add_columns("Symbol", "Side", "Volume", "Entry", "Current", "Unrealized P&L", "Status")
        self.cursor_type = "row"
        self.zebra_stripes = True


class OrdersTable(DataTable):
    """Orders table with live updates"""

    def on_mount(self) -> None:
        self.add_columns("ID", "Symbol", "Side", "Type", "Volume", "Price", "Status", "Filled")
        self.cursor_type = "row"
        self.zebra_stripes = True


class MarketWatchPanel(Static):
    """Market watch panel with live prices"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prices_data = {}

    def compose(self) -> ComposeResult:
        self.log("DEBUG: MarketWatchPanel.compose")
        yield DataTable(id="market-table")

    def on_mount(self) -> None:
        self.log("DEBUG: MarketWatchPanel.on_mount")
        self.table = self.query_one("#market-table", DataTable)
        self.log(f"DEBUG: Got table from query: {self.table}")
        if self.table:
            self.log("DEBUG: Table exists in on_mount")
            self.table.add_columns("Symbol", "Bid", "Ask", "Change", "Change %", "Spread", "Timeframe", "Time")
            self.table.cursor_type = "row"
            self.table.zebra_stripes = True
            self.table.add_row("TEST", "1.00000", "1.00001", "+0.00001", "+0.01%", "0.00001", "TICK", "12:00:00")
            self.log(f"DEBUG: Test row added in on_mount, row_count: {self.table.row_count}")
        else:
            self.log("ERROR: Table is None in on_mount")
        
        # Also test calling update_prices directly
        self.log("DEBUG: Testing update_prices directly")
        self.update_prices({
            "EURUSD": {"bid": 1.15063, "ask": 1.15073, "change": 0.0002, "change_pct": 0.017, "time": "now", "timeframe": "1m"}
        })

    def update_prices(self, prices: dict) -> None:
        """Direct method to update prices"""
        self.log(f"DEBUG: MarketWatchPanel.update_prices called with {len(prices)} symbols")
        self.prices_data = prices
        if self.table:
            self.log("DEBUG: Table exists, clearing and adding rows")
            self.table.clear()
            for symbol, data in sorted(prices.items()):
                spread = data.get('ask', 0) - data.get('bid', 0)
                change = data.get('change', 0)
                change_pct = data.get('change_pct', 0)
                color = "green" if change >= 0 else "red"
                tf = data.get('timeframe', 'TICK')
                bid_val = data.get('bid', 0)
                ask_val = data.get('ask', 0)
                self.log(f"DEBUG: Adding row for {symbol}: bid={bid_val}, ask={ask_val}, tf={tf}")
                self.table.add_row(
                    symbol,
                    f"{bid_val:.5f}",
                    f"{ask_val:.5f}",
                    f"[{color}]{change:+.5f}[/]",
                    f"[{color}]{change_pct:+.2f}%[/]",
                    f"{spread:.5f}",
                    tf,
                    datetime.now(UTC).strftime("%H:%M:%S"),
                )
            self.log(f"DEBUG: Rows added, row count: {self.table.row_count}")


class AccountSummaryPanel(Static):
    """Account summary with live updates"""

    balance: reactive[float] = 0.0
    equity: reactive[float] = 0.0
    margin_used: reactive[float] = 0.0
    free_margin: reactive[float] = 0.0
    margin_level: reactive[float] = 0.0
    unrealized_pnl: reactive[float] = 0.0
    daily_pnl: reactive[float] = 0.0

    def render(self) -> str:
        pnl_color = "green" if self.daily_pnl >= 0 else "red"
        return f"""
[bold]ACCOUNT SUMMARY[/bold]
┌─────────────────────────────────────┐
│ Balance:      ${self.balance:>12,.2f} │
│ Equity:       ${self.equity:>12,.2f} │
│ Unrealized P&L: ${self.unrealized_pnl:>+8,.2f} │
│ Daily P&L:    [{pnl_color}]${self.daily_pnl:>+8,.2f}[/] │
├─────────────────────────────────────┤
│ Margin Used:  ${self.margin_used:>12,.2f} │
│ Free Margin:  ${self.free_margin:>12,.2f} │
│ Margin Level: {self.margin_level:>12.1f}% │
└─────────────────────────────────────┘
"""


class EquityChart(Static):
    """Sparkline equity chart"""

    data: reactive[list[float]] = reactive(list)

    def render(self) -> str:
        if not self.data:
            return "[dim]No equity data[/dim]"

        # Simple text-based sparkline
        spark = Sparkline(self.data, width=80, height=10)
        return str(spark)


class NewsPanel(RichLog):
    """News feed panel"""

    def on_mount(self) -> None:
        self.write("[bold cyan]NEWS FEED[/bold cyan]")
        self.write("─" * 50)


class RiskPanel(Static):
    """Risk monitoring panel"""

    var_95: reactive[float] = 0.0
    var_99: reactive[float] = 0.0
    max_drawdown: reactive[float] = 0.0
    current_drawdown: reactive[float] = 0.0
    max_correlation: reactive[float] = 0.0
    leverage: reactive[float] = 0.0

    def render(self) -> str:
        dd_color = "red" if self.current_drawdown > 5 else "yellow" if self.current_drawdown > 2 else "green"
        return f"""
[bold red]RISK MONITOR[/bold red]
┌─────────────────────────────────────┐
│ VaR (95%):     ${self.var_95:>12,.2f} │
│ VaR (99%):     ${self.var_99:>12,.2f} │
│ Max DD:        {self.max_drawdown:>12.2f}% │
│ Current DD:    [{dd_color}]{self.current_drawdown:>12.2f}%[/] │
│ Max Corr:      {self.max_correlation:>12.2f} │
│ Leverage:      {self.leverage:>12.2f}x │
└─────────────────────────────────────┘
"""


class BloombergTerminal(App):
    """Main Bloomberg-style trading terminal"""

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #e0e0e0;
    }

    .panel {
        border: solid #333;
        padding: 1;
        margin: 1;
        background: #121212;
    }

    .panel-title {
        text-style: bold;
        color: #00d4aa;
        background: #1a1a1a;
        padding: 0 1;
    }

    DataTable {
        background: #121212;
        color: #e0e0e0;
    }

    DataTable > .datatable--header {
        background: #1a1a1a;
        color: #00d4aa;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #003333;
    }

    Button {
        background: #003333;
        color: #00d4aa;
        border: solid #005555;
    }

    Button:hover {
        background: #005555;
    }

    Button:focus {
        background: #007777;
    }

    TabbedContent {
        background: #121212;
    }

    Tabs {
        background: #1a1a1a;
    }

    Tab {
        color: #888;
        padding: 0 2;
    }

    Tab.-active {
        color: #00d4aa;
        background: #121212;
        text-style: bold;
    }

    RichLog {
        background: #121212;
        border: solid #333;
    }

    Static {
        background: #121212;
    }

    Sparkline {
        color: #00d4aa;
    }

    Footer {
        background: #1a1a1a;
        color: #888;
    }

    Header {
        background: #0a0a0a;
        color: #00d4aa;
        text-style: bold;
    }

    #market-watch {
        width: 100%;
        height: 1fr;
    }

    #positions {
        width: 1fr;
        height: 1fr;
    }

    #orders {
        width: 1fr;
        height: 1fr;
    }

    #account {
        width: 40;
        height: 1fr;
    }

    #risk {
        width: 40;
        height: 1fr;
    }

    #news {
        width: 60;
        height: 1fr;
    }

    #chart {
        width: 1fr;
        height: 1fr;
    }

    .left-pane {
        width: 70%;
    }

    .right-pane {
        width: 30%;
    }

    .top-pane {
        height: 60%;
    }

    .bottom-pane {
        height: 40%;
    }
    """

    BINDINGS = (
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("t", "toggle_theme", "Theme", show=True),
        Binding("f1", "help", "Help", show=True),
        Binding("ctrl+p", "positions", "Positions", show=False),
        Binding("ctrl+o", "orders", "Orders", show=False),
        Binding("ctrl+n", "news", "News", show=False),
        Binding("ctrl+r", "risk", "Risk", show=False),
        Binding("ctrl+a", "account", "Account", show=False),
    )

    # Reactive data
    market_data: reactive[dict]  # type: ignore
    positions_data: reactive[list]  # type: ignore
    orders_data: reactive[list]  # type: ignore
    account_data: reactive[dict]  # type: ignore
    risk_data: reactive[dict]  # type: ignore
    news_data: reactive[list]  # type: ignore
    equity_data: reactive[list]  # type: ignore

    def __init__(self):
        super().__init__()
        self.redis_client = None
        self.db_pool = None
        self.running = True

    async def on_mount(self) -> None:
        """Initialize connections and start data streams"""
        self.log("DEBUG: on_mount started")
        self.title = "BLOOMBERG TERMINAL - FOREX TRADING SYSTEM"
        self.sub_title = f"MT5: {settings.mt5_login}@{settings.mt5_server} | CCXT: {len(settings.ccxt_exchanges)} exchanges"

        # Initialize connections
        await self.init_connections()
        self.log("DEBUG: init_connections completed")

        # Start data refresh tasks
        self.set_interval(1.0, self.refresh_market_data)
        self.set_interval(2.0, self.refresh_positions)
        self.set_interval(3.0, self.refresh_orders)
        self.set_interval(5.0, self.refresh_account)
        self.set_interval(10.0, self.refresh_risk)
        self.set_interval(30.0, self.refresh_news)
        self.log("DEBUG: on_mount completed")

        # Initial data load - use call_later to ensure UI is mounted
        self.call_later(self.refresh_all)

    async def init_connections(self) -> None:
            """Initialize database and Redis connections"""
            try:
                # Redis
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    max_connections=settings.redis_max_connections,
                    decode_responses=settings.redis_decode_responses,
                )
                await self.redis_client.ping()
                self.log(f"Redis connected to {settings.redis_url}")
            
                # Test reading data
                test_keys = await self.redis_client.keys("*")
                self.log(f"DEBUG: Redis keys found: {len(test_keys)}")
                for k in test_keys[:5]:
                    val = await self.redis_client.get(k)
                    self.log(f"DEBUG: Redis key {k}: {val[:100] if val else 'None'}")
            
                # TimescaleDB
                await timescaledb.connect()
                self.log("TimescaleDB connected")
            
                # Redis cache
                await redis_cache.connect()
                self.log("Redis cache connected")
            
                # Start data refresh tasks
                self.set_interval(1.0, self.refresh_market_data)
                self.set_interval(2.0, self.refresh_positions)
                self.set_interval(3.0, self.refresh_orders)
                self.set_interval(5.0, self.refresh_account)
                self.set_interval(10.0, self.refresh_risk)
                self.set_interval(30.0, self.refresh_news)
            
                # Initial data load
                self.log("DEBUG: Calling refresh_all()")
                await self.refresh_all()
                self.log("DEBUG: refresh_all() completed")
            
            except Exception as e:
                self.log(f"Connection error: {e}")
                import traceback
                self.log(f"Traceback: {traceback.format_exc()}")

    async def refresh_all(self) -> None:
        """Refresh all data"""
        self.log("DEBUG: refresh_all started")
        try:
            await asyncio.gather(
                self.refresh_market_data(),
                self.refresh_positions(),
                self.refresh_orders(),
                self.refresh_account(),
                self.refresh_risk(),
                self.refresh_news(),
                return_exceptions=True,
            )
            self.log("DEBUG: refresh_all completed")
        except Exception as e:
            self.log(f"ERROR in refresh_all: {e}")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}")

    async def refresh_market_data(self) -> None:
        """Fetch latest market data from Redis for multiple timeframes"""
        self.log("DEBUG: refresh_market_data called")
        try:
            self.log(f"DEBUG: refresh_market_data called, redis_client={self.redis_client is not None}")
            if not self.redis_client:
                self.log("ERROR: redis_client is None")
                return

            # Get all symbols from MT5
            symbols = [
                "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"
            ]

            # Timeframes to fetch
            _timeframes = ["TICK", "1m", "5m", "15m", "1h", "4h", "1d"]

            prices = {}
            timeframe_data = {}

            for symbol in symbols:
                _symbol_prices = {}
                tf_data = {}

                # TICK data from Redis
                tick_key = f"tick:{symbol}"
                tick_data = await self.redis_client.get(tick_key)
                self.log(f"DEBUG: tick_key={tick_key}, data={tick_data[:100] if tick_data else 'None'}")
                if tick_data:
                    tick = json.loads(tick_data)
                    _bid = tick.get("bid", 0)
                    _ask = tick.get("ask", 0)
                    _spread = tick.get("spread", 0)
                    _volume = tick.get("volume", 0)

                    # Calculate change from previous close (would need previous close from DB)
                    # For now, use last price if available
                    last = tick.get("last", 0)
                    prev_close = await self.get_previous_close(symbol)
                    change = last - prev_close if prev_close else 0
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    tf_data["TICK"] = {
                        "bid": tick.get("bid", 0),
                        "ask": tick.get("ask", 0),
                        "last": last,
                        "volume": tick.get("volume", 0),
                        "spread": tick.get("spread", 0),
                        "change": change,
                        "change_pct": change_pct,
                        "time": tick.get("timestamp", ""),
                    }
                else:
                    self.log(f"DEBUG: No tick data for {symbol}, checking bar data")

                # Also check bar data from Redis as fallback
                bar_key = f"bar:{symbol}:1m"
                bar_data = await self.redis_client.get(bar_key)
                self.log(f"DEBUG: bar_key={bar_key}, data={bar_data[:100] if bar_data else 'None'}")
                if bar_data:
                    bar = json.loads(bar_data)
                    if "TICK" not in tf_data:
                        tf_data["TICK"] = {
                            "bid": bar.get("close", 0),
                            "ask": bar.get("close", 0),
                            "last": bar.get("close", 0),
                            "volume": bar.get("volume", 0),
                            "spread": bar.get("spread", 0),
                            "change": 0,
                            "change_pct": 0,
                            "time": bar.get("timestamp", ""),
                        }

                # Fetch bar data for each timeframe from TimescaleDB
                async with timescaledb.acquire() as conn:
                    for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                        row = await conn.fetchrow("""
                            SELECT close, open, high, low, volume
                            FROM market_data.bars
                            WHERE symbol_id = (SELECT symbol_id FROM market_data.symbols WHERE symbol = $1)
                              AND timeframe = $2
                              AND is_complete = TRUE
                            ORDER BY time DESC
                            LIMIT 2
                        """, symbol, tf)

                        if row:
                            current = row
                            prev_close = row["close"] if row else 0

                            # Get previous bar for change calculation
                            prev_row = await conn.fetchrow("""
                                SELECT close
                                FROM market_data.bars
                                WHERE symbol_id = (SELECT symbol_id FROM market_data.symbols WHERE symbol = $1)
                                  AND timeframe = $2
                                  AND is_complete = TRUE
                                ORDER BY time DESC
                                LIMIT 1 OFFSET 1
                            """, symbol, tf)

                            prev_close_val = prev_row["close"] if prev_row else current["close"]
                            change = current["close"] - prev_close_val
                            change_pct = (change / prev_close_val * 100) if prev_close_val else 0

                            tf_data[tf] = {
                                "bid": current["close"],
                                "ask": current["close"],
                                "last": current["close"],
                                "open": current["open"],
                                "high": current["high"],
                                "low": current["low"],
                                "volume": current["volume"],
                                "spread": 0,
                                "change": change,
                                "change_pct": change_pct,
                                "time": datetime.now(UTC).isoformat(),
                            }

                if tf_data:
                    # Use latest available timeframe as main price
                    main_tf = "TICK" if "TICK" in tf_data else "1m"
                    main = tf_data.get(main_tf, {})
                    prices[symbol] = {
                        "bid": main.get("bid", 0),
                        "ask": main.get("ask", 0),
                        "last": main.get("last", 0),
                        "volume": main.get("volume", 0),
                        "spread": main.get("spread", 0),
                        "change": main.get("change", 0),
                        "change_pct": main.get("change_pct", 0),
                        "time": main.get("time", ""),
                        "timeframe": main_tf,
                    }

                    timeframe_data[symbol] = tf_data

            self.log(f"DEBUG: prices={prices}")
            self.market_data = prices
            self.timeframes = timeframe_data

            # Update market watch panel
            try:
                self.log("DEBUG: Looking for market-watch panel")
                panel = self.query_one("#market-watch", expect_type=MarketWatchPanel)
                self.log("DEBUG: Found market-watch panel, setting prices")
                self.log(f"DEBUG: panel type: {type(panel)}, has table: {hasattr(panel, 'table')}")
                if hasattr(panel, 'table'):
                    self.log(f"DEBUG: panel.table: {panel.table}")
                    self.log(f"DEBUG: panel.table.row_count before: {panel.table.row_count}")
                self.log("DEBUG: Calling panel.update_prices")
                panel.update_prices(prices)
                self.log("DEBUG: panel.update_prices returned")
                panel.timeframes = timeframe_data
                self.log("DEBUG: prices set on panel")
                if hasattr(panel, 'table'):
                    self.log(f"DEBUG: panel.table.row_count after: {panel.table.row_count}")
            except Exception as e:
                self.log(f"ERROR: Failed to update market-watch panel: {e}")
                import traceback
                self.log(f"Traceback: {traceback.format_exc()}")

        except Exception as e:
            self.log(f"Market data error: {e}")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}")

    async def get_previous_close(self, symbol: str) -> float:
        """Get previous day's close price for a symbol"""
        try:
            async with timescaledb.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT close
                    FROM market_data.bars
                    WHERE symbol_id = (SELECT symbol_id FROM market_data.symbols WHERE symbol = $1)
                      AND timeframe = '1d'
                      AND is_complete = TRUE
                    ORDER BY time DESC
                    LIMIT 1 OFFSET 1
                """, symbol)
                return row["close"] if row else 0
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return 0

    async def refresh_positions(self) -> None:
        """Fetch positions from TimescaleDB"""
        try:
            async with timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT p.*, s.symbol
                    FROM trading.positions p
                    JOIN market_data.symbols s ON p.symbol_id = s.symbol_id
                    WHERE p.is_open = TRUE
                    ORDER BY p.opened_at DESC
                """)

                positions = [dict(row) for row in rows]
                self.positions_data = positions

                # Update positions table
                table = self.query_one("#positions-table", expect_type=PositionsTable)
                table.clear()
                for pos in positions:
                    pnl = pos.get("unrealized_pnl", 0) or 0
                    pnl_color = "green" if pnl >= 0 else "red"
                    table.add_row(
                        pos["symbol"],
                        pos.get("direction", "FLAT"),
                        f"{pos.get('volume', 0):.2f}",
                        f"{pos.get('entry_price', 0):.5f}",
                        f"{pos.get('current_price', 0):.5f}",
                        f"[{pnl_color}]${pnl:+,.2f}[/]",
                        "OPEN" if pos.get("is_open") else "CLOSED",
                    )

        except Exception as e:
            self.log(f"Positions error: {e}")

    async def refresh_orders(self) -> None:
        """Fetch orders from TimescaleDB"""
        try:
            async with timescaledb.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT o.*, s.symbol
                    FROM trading.orders o
                    JOIN market_data.symbols s ON o.symbol_id = s.symbol_id
                    ORDER BY o.created_at DESC
                    LIMIT 50
                """)

                orders = [dict(row) for row in rows]
                self.orders_data = orders

                table = self.query_one("#orders-table", expect_type=OrdersTable)
                table.clear()
                for order in orders:
                    status = order.get("status", "PENDING")
                    status_color = {
                        "FILLED": "green",
                        "PARTIAL": "yellow",
                        "PENDING": "blue",
                        "SUBMITTED": "cyan",
                        "CANCELLED": "gray",
                        "REJECTED": "red",
                    }.get(status, "white")

                    table.add_row(
                        str(order["order_id"])[:8],
                        order["symbol"],
                        order.get("side", ""),
                        order.get("order_type", ""),
                        f"{order.get('volume', 0):.2f}",
                        f"{order.get('price', 0):.5f}" if order.get("price") else "MARKET",
                        f"[{status_color}]{status}[/]",
                        f"{order.get('filled_volume', 0):.2f}",
                    )

        except Exception as e:
            self.log(f"Orders error: {e}")

    async def refresh_account(self) -> None:
        """Fetch account summary"""
        try:
            async with timescaledb.acquire() as conn:
                # Get latest equity curve point
                row = await conn.fetchrow("""
                    SELECT equity, balance, unrealized_pnl, margin_used, free_margin, margin_level
                    FROM analytics.equity_curve
                    ORDER BY time DESC
                    LIMIT 1
                """)

                if row:
                    self.account_data = dict(row)
                    panel = self.query_one("#account-summary", expect_type=AccountSummaryPanel)
                    panel.balance = row.get("balance", 0)
                    panel.equity = row.get("equity", 0)
                    panel.unrealized_pnl = row.get("unrealized_pnl", 0)
                    panel.margin_used = row.get("margin_used", 0)
                    panel.free_margin = row.get("free_margin", 0)
                    panel.margin_level = row.get("margin_level", 0)

                # Get daily P&L
                row = await conn.fetchrow("""
                    SELECT daily_pnl FROM analytics.performance_metrics
                    ORDER BY date DESC LIMIT 1
                """)
                if row:
                    self.daily_pnl = row.get("daily_pnl", 0)
                    panel = self.query_one("#account-summary", expect_type=AccountSummaryPanel)
                    panel.daily_pnl = row.get("daily_pnl", 0)

        except Exception as e:
            self.log(f"Account error: {e}")

    async def refresh_risk(self) -> None:
        """Fetch risk metrics"""
        try:
            async with timescaledb.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT portfolio_var_95, portfolio_var_99, portfolio_es_95, portfolio_es_99,
                           max_position_var, correlation_risk, concentration_risk, leverage
                    FROM analytics.risk_metrics
                    ORDER BY time DESC
                    LIMIT 1
                """)

                if row:
                    self.risk_data = dict(row)
                    panel = self.query_one("#risk-panel", expect_type=RiskPanel)
                    panel.var_95 = row.get("portfolio_var_95", 0)
                    panel.var_99 = row.get("portfolio_var_99", 0)
                    panel.max_drawdown = row.get("correlation_risk", 0)
                    panel.current_drawdown = row.get("concentration_risk", 0)
                    panel.max_correlation = row.get("correlation_risk", 0)
                    panel.leverage = row.get("leverage", 0)

        except Exception as e:
            self.log(f"Risk error: {e}")

    async def refresh_news(self) -> None:
        """Fetch news from Redis"""
        try:
            if not self.redis_client:
                return

            # Get latest news from Redis
            news_key = "news:latest"
            data = await self.redis_client.lrange(news_key, 0, 19)
            if data:
                self.news_data = [json.loads(item) for item in data]
                panel = self.query_one("#news-panel", expect_type=NewsPanel)
                panel.clear()
                panel.write("[bold cyan]NEWS FEED[/bold cyan]")
                panel.write("─" * 50)
                for item in self.news_data[:10]:
                    time_str = item.get("timestamp", "")[:19]
                    title = item.get("title", "No title")
                    source = item.get("source", "Unknown")
                    panel.write(f"[dim]{time_str}[/dim] [bold]{title}[/bold] ({source})")

        except Exception as e:
            self.log(f"News error: {e}")

    def compose(self) -> ComposeResult:
        """Compose the terminal layout"""
        yield Header()
        yield Footer()

        with Container(id="main"):
            # Top section - Market Watch
            with Horizontal(id="top-section"):
                yield MarketWatchPanel(id="market-watch", classes="panel")

            # Middle section - Left: Charts, Right: Account & Risk
            with Horizontal(id="middle-section"):
                # Left pane - Charts
                with Vertical(id="left-pane", classes="left-pane panel"):
                    yield EquityChart(id="equity-chart", classes="panel")

                # Right pane - Account & Risk
                with Vertical(id="right-pane", classes="right-pane panel"):
                    yield AccountSummaryPanel(id="account-summary", classes="panel")
                    yield RiskPanel(id="risk-panel", classes="panel")

            # Bottom section - Positions, Orders, News
            with Horizontal(id="bottom-section"):
                # Positions
                with VerticalScroll(id="positions-section", classes="panel"):
                    yield Label("[bold]POSITIONS[/bold]", classes="panel-title")
                    yield PositionsTable(id="positions-table", classes="panel")

                # Orders
                with VerticalScroll(id="orders-section", classes="panel"):
                    yield Label("[bold]ORDERS[/bold]", classes="panel-title")
                    yield OrdersTable(id="orders-table", classes="panel")

                # News
                with VerticalScroll(id="news-section", classes="panel"):
                    yield Label("[bold]NEWS[/bold]", classes="panel-title")
                    yield NewsPanel(id="news-panel", classes="panel", markup=True)

    async def action_quit(self) -> None:
        """Quit the application"""
        self.running = False
        if self.redis_client:
            await self.redis_client.close()
        await timescaledb.disconnect()
        await redis_cache.disconnect()
        self.exit()

    async def action_refresh(self) -> None:
        """Manual refresh"""
        await self.refresh_all()
        self.notify("Data refreshed")

    async def action_toggle_theme(self) -> None:
        """Toggle theme"""
        self.dark = not self.dark

    async def action_positions(self) -> None:
        """Focus positions tab"""
        self.query_one("#positions-table").focus()

    async def action_orders(self) -> None:
        """Focus orders tab"""
        self.query_one("#orders-table").focus()

    async def action_news(self) -> None:
        """Focus news panel"""
        self.query_one("#news-panel").focus()

    async def action_risk(self) -> None:
        """Focus risk panel"""
        self.query_one("#risk-panel").focus()

    async def action_account(self) -> None:
        """Focus account panel"""
        self.query_one("#account-summary").focus()

    async def action_help(self) -> None:
        """Show help"""
        self.notify(
            "Keys: q=Quit | r=Refresh | t=Theme | F1=Help | "
            "Ctrl+P=Positions | Ctrl+O=Orders | Ctrl+N=News | "
            "Ctrl+R=Risk | Ctrl+A=Account",
            timeout=10,
        )


async def main():
    """Main entry point"""
    app = BloombergTerminal()
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())