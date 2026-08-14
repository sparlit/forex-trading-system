#!/usr/bin/env python3
"""
Elite Autonomous Quantum Trading System - Native Dashboard
PyQt6-based native Windows application with real-time trading visualization.
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QTextCursor
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class MarketData:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    timestamp: datetime
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0

@dataclass
class Trade:
    symbol: str
    side: str
    volume: float
    entry: float
    current: float
    sl: float
    tp: float
    pnl: float
    time: datetime

@dataclass
class AccountInfo:
    equity: float
    balance: float
    profit: float
    daily_pnl: float
    margin: float
    free_margin: float
    margin_level: float

@dataclass
class SessionInfo:
    name: str
    market_type: str
    start_utc: str
    end_utc: str
    is_active: bool
    progress: float
    time_remaining: str
    liquidity: str
    volatility: str
    major_symbols: list[str]
    overlaps: list[str] = field(default_factory=list)


# =============================================================================
# WebSocket Client for Real-time Updates
# =============================================================================

class WebSocketClient(QObject):
    """WebSocket client for real-time dashboard updates."""
    
    message_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    
    def __init__(self, url: str = "ws://localhost:8765"):
        super().__init__()
        self.url = url
        self.websocket = None
        self.connected = False
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self.connect)
    
    async def connect(self):
        """Connect to WebSocket server."""
        try:
            import websockets
            self.websocket = await websockets.connect(self.url)
            self.connected = True
            self.connection_changed.emit(True)
            logger.info("WebSocket connected")
            
            # Listen for messages
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.message_received.emit(data)
                except json.JSONDecodeError:
                    raise NotImplementedError("Not implemented")
                    
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self.connected = False
            self.connection_changed.emit(False)
            # Reconnect after 5 seconds
            self.reconnect_timer.start(5000)
    
    def disconnect(self):
        """Disconnect from WebSocket."""
        self.reconnect_timer.stop()
        if self.websocket:
            asyncio.create_task(self.websocket.close())
        self.connected = False
        self.connection_changed.emit(False)


# =============================================================================
# Lightweight Charts HTML Generator
# =============================================================================

class ChartWidget(QWebEngineView):
    """TradingView Lightweight Charts widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(500)
        self.current_symbol = "EURUSD"
        self.channel = QWebChannel()
        self.page().setWebChannel(self.channel)
        self.load_chart()
    
    def load_chart(self):
        """Load the Lightweight Charts HTML."""
        html = self.generate_chart_html()
        self.setHtml(html, QUrl("about:blank"))
    
    def generate_chart_html(self) -> str:
        """Generate HTML with Lightweight Charts."""
        # Generate sample data
        end_time = datetime.now(timezone.utc)
        start_time = end_time - pd.Timedelta(hours=24)
        periods = 240
        times = pd.date_range(start=start_time, periods=periods, freq='5min', tz='UTC')
        
        np.random.seed(42)
        base_price = 1.0850
        returns = np.random.normal(0, 0.0002, periods)
        prices = base_price * np.exp(np.cumsum(returns))
        
        opens = prices
        highs = prices + np.abs(np.random.normal(0, 0.0001, periods))
        lows = prices - np.abs(np.random.normal(0, 0.0001, periods))
        closes = prices + np.random.normal(0, 0.00005, periods)
        volumes = np.random.randint(1000, 10000, periods)
        
        df = pd.DataFrame({
            'time': times,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
        
        df['ema_20'] = df['close'].ewm(span=20).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        
        # Convert to format for Lightweight Charts
        candlestick_data = []
        volume_data = []
        ema20_data = []
        ema50_data = []
        
        for _, row in df.iterrows():
            timestamp = int(row['time'].timestamp())
            candlestick_data.append({
                'time': timestamp,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close'])
            })
            volume_data.append({
                'time': timestamp,
                'value': float(row['volume']),
                'color': '#3fb950' if row['close'] >= row['open'] else '#f85149'
            })
            if not np.isnan(row['ema_20']):
                ema20_data.append({'time': timestamp, 'value': float(row['ema_20'])})
            if not np.isnan(row['ema_50']):
                ema50_data.append({'time': timestamp, 'value': float(row['ema_50'])})
        
        import json
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background: #0e1117;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }}
                #chart-container {{
                    width: 100%;
                    height: 500px;
                    position: relative;
                }}
                .chart-toolbar {{
                    position: absolute;
                    top: 10px;
                    left: 10px;
                    z-index: 100;
                    display: flex;
                    gap: 8px;
                    background: rgba(22, 27, 34, 0.95);
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 1px solid #30363d;
                }}
                .chart-toolbar button {{
                    background: transparent;
                    border: 1px solid #30363d;
                    color: #8b949e;
                    padding: 4px 10px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 12px;
                    transition: all 0.2s;
                }}
                .chart-toolbar button:hover {{
                    background: #238636;
                    border-color: #238636;
                    color: white;
                }}
                .chart-toolbar button.active {{
                    background: #238636;
                    border-color: #238636;
                    color: white;
                }}
                .symbol-title {{
                    position: absolute;
                    top: 10px;
                    right: 10px;
                    z-index: 100;
                    background: rgba(22, 27, 34, 0.95);
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 1px solid #30363d;
                    color: #e0e0e0;
                    font-weight: 600;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div id="chart-container">
                <div class="chart-toolbar" id="toolbar">
                    <button id="btn-1m" data-res="60">1m</button>
                    <button id="btn-5m" data-res="300" class="active">5m</button>
                    <button id="btn-15m" data-res="900">15m</button>
                    <button id="btn-1h" data-res="3600">1h</button>
                    <button id="btn-4h" data-res="14400">4h</button>
                    <button id="btn-1d" data-res="86400">1D</button>
                </div>
                <div class="symbol-title">{self.current_symbol}</div>
            </div>

            <script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
            <script>
                const candlestickData = {json.dumps(candlestick_data)};
                const volumeData = {json.dumps(volume_data)};
                const ema20Data = {json.dumps(ema20_data)};
                const ema50Data = {json.dumps(ema50_data)};

                const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {{
                    width: document.getElementById('chart-container').clientWidth,
                    height: 500,
                    layout: {{
                        background: {{ color: '#0e1117' }},
                        textColor: '#e0e0e0',
                        fontSize: 11,
                        fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
                    }},
                    grid: {{
                        vertLines: {{ color: '#21262d' }},
                        horzLines: {{ color: '#21262d' }},
                    }},
                    crosshair: {{
                        mode: LightweightCharts.CrosshairMode.Normal,
                        vertLine: {{ color: '#58a6ff', width: 1, style: LightweightCharts.LineStyle.Dashed }},
                        horzLine: {{ color: '#58a6ff', width: 1, style: LightweightCharts.LineStyle.Dashed }},
                    }},
                    rightPriceScale: {{
                        borderColor: '#30363d',
                        scaleMargins: {{
                            top: 0.2,
                            bottom: 0.25,
                        }},
                    }},
                    timeScale: {{
                        borderColor: '#30363d',
                        timeVisible: true,
                        secondsVisible: false,
                        tickMarkFormatter: (time) => {{
                            const date = new Date(time * 1000);
                            return date.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
                        }},
                    }},
                    watermark: {{
                        color: 'rgba(92, 166, 255, 0.1)',
                        text: '{self.current_symbol}',
                        fontSize: 48,
                    }},
                }});

                window.addEventListener('resize', () => {{
                    chart.resize(document.getElementById('chart-container').clientWidth, 500);
                }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: '#3fb950',
                    downColor: '#f85149',
                    borderUpColor: '#3fb950',
                    borderDownColor: '#f85149',
                    wickUpColor: '#3fb950',
                    wickDownColor: '#f85149',
                    priceFormat: {{
                        type: 'price',
                        precision: 5,
                        minMove: 0.00001,
                    }},
                }});
                candleSeries.setData(candlestickData);

                const ema20Series = chart.addLineSeries({{
                    color: '#58a6ff',
                    lineWidth: 1,
                    title: 'EMA 20',
                    priceLineVisible: false,
                    lastValueVisible: true,
                }});
                ema20Series.setData(ema20Data);

                const ema50Series = chart.addLineSeries({{
                    color: '#f97316',
                    lineWidth: 1,
                    title: 'EMA 50',
                    priceLineVisible: false,
                    lastValueVisible: true,
                }});
                ema50Series.setData(ema50Data);

                const volumeChart = LightweightCharts.createChart(document.getElementById('chart-container'), {{
                    width: document.getElementById('chart-container').clientWidth,
                    height: 150,
                    layout: {{
                        background: {{ color: '#0e1117' }},
                        textColor: '#e0e0e0',
                        fontSize: 11,
                        fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
                    }},
                    grid: {{
                        vertLines: {{ color: '#21262d' }},
                        horzLines: {{ color: '#21262d' }},
                    }},
                    rightPriceScale: {{
                        borderColor: '#30363d',
                        visible: false,
                    }},
                    timeScale: {{
                        borderColor: '#30363d',
                        visible: false,
                    }},
                }});

                const volumeSeries = volumeChart.addHistogramSeries({{
                    color: '#58a6ff',
                    priceFormat: {{
                        type: 'volume',
                    }},
                    priceScaleId: '',
                }});
                volumeSeries.setData(volumeData);

                document.querySelectorAll('#toolbar button').forEach(btn => {{
                    btn.addEventListener('click', () => {{
                        document.querySelectorAll('#toolbar button').forEach(b => b.classList.remove('active'));
                        btn.classList.add('active');
                        console.log('Timeframe changed to:', btn.dataset.res);
                    }});
                }});

                window.tradingChart = {{ chart, candleSeries, ema20Series, ema50Series, volumeChart, volumeSeries }};
            </script>
        </body>
        </html>
        """
        return html
    
    def update_symbol(self, symbol: str):
        """Update chart symbol."""
        self.current_symbol = symbol
        self.load_chart()


# =============================================================================
# Native Dashboard Components
# =============================================================================

class MetricCard(QFrame):
    """Bloomberg-style metric card."""
    
    def __init__(self, label: str, value: str = "0.00", color: str = "#e0e0e0", parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 12px;
                margin: 4px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.value = QLabel(value)
        self.value.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {color};")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.label)
        layout.addWidget(self.value)
    
    def update_value(self, value: str, color: str = None):
        self.value.setText(value)
        if color:
            self.value.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {color};")


class SessionTimelineWidget(QWidget):
    """3-row session timeline with vibrant colors."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.sessions = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("🌍 Global Trading Sessions Timeline")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(title)
        
        # Scroll area for timeline
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: #161b22; border: 1px solid #30363d; border-radius: 6px; }
            QScrollBar:horizontal { height: 8px; background: #0e1117; }
            QScrollBar::handle:horizontal { background: #30363d; border-radius: 4px; min-width: 20px; }
        """)
        
        self.timeline_widget = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_widget)
        self.timeline_layout.setSpacing(8)
        scroll.setWidget(self.timeline_widget)
        
        layout.addWidget(scroll)
        
        # Time scale
        self.time_scale = QLabel()
        self.time_scale.setStyleSheet("font-size: 9px; color: #6e7681; padding: 0 120px;")
        layout.addWidget(self.time_scale)
    
    def update_sessions(self, sessions: list[SessionInfo]):
        """Update session timeline."""
        self.sessions = sessions
        
        # Clear existing
        for i in reversed(range(self.timeline_layout.count())):
            self.timeline_layout.itemAt(i).widget().setParent(None)
        
        # Group sessions by row
        now = datetime.now(timezone.utc)
        past = []
        current = []
        future = []
        
        for s in sessions:
            start = datetime.fromisoformat(s.start_utc.replace('Z', '+00:00'))
            end = datetime.fromisoformat(s.end_utc.replace('Z', '+00:00'))
            
            if end < now:
                past.append(s)
            elif start <= now <= end:
                current.append(s)
            else:
                future.append(s)
        
        rows = [
            ("PAST / PASSING", past, "#8b949e"),
            ("CURRENT ACTIVE", current, "#3fb950"),
            ("COMING UP", future, "#58a6ff"),
        ]
        
        for row_title, row_sessions, row_color in rows:
            # Row container
            row_frame = QFrame()
            row_frame.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
            row_layout = QVBoxLayout(row_frame)
            row_layout.setSpacing(4)
            
            # Row title
            title_label = QLabel(row_title)
            title_label.setStyleSheet(f"color: {row_color}; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;")
            row_layout.addWidget(title_label)
            
            if not row_sessions:
                empty = QLabel("No sessions")
                empty.setStyleSheet("color: #6e7681; font-size: 12px; padding: 20px; text-align: center;")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row_layout.addWidget(empty)
            else:
                # Session blocks container
                blocks_container = QWidget()
                blocks_layout = QVBoxLayout(blocks_container)
                blocks_layout.setSpacing(2)
                blocks_layout.setContentsMargins(120, 0, 0, 0)
                
                for session in row_sessions:
                    start = datetime.fromisoformat(session.start_utc.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(session.end_utc.replace('Z', '+00:00'))
                    
                    # Calculate position and width (simplified - full width for demo)
                    block = QLabel(f"{session.name.upper()}  {start.strftime('%H:%M')} - {end.strftime('%H:%M')} UTC  |  {session.liquidity} liquidity  |  {session.volatility} volatility")
                    color = self.get_session_color(session)
                    block.setStyleSheet(f"""
                        background: {color}; color: #000; 
                        padding: 4px 12px; border-radius: 4px; 
                        font-size: 11px; font-weight: 500;
                    """)
                    block.setFixedHeight(32)
                    blocks_layout.addWidget(block)
                
                row_layout.addWidget(blocks_container)
            
            self.timeline_layout.addWidget(row_frame)
        
        # Update time scale
        self.update_time_scale(sessions)
    
    def get_session_color(self, session: SessionInfo) -> str:
        """Get vibrant color for session."""
        colors = {
            "sydney": "#ff6b6b", "tokyo": "#ffa500", "hong_kong": "#ffd700",
            "singapore": "#ffeb3b", "shanghai": "#90ee90", "mumbai": "#00ff7f",
            "dubai": "#00fa9a", "frankfurt": "#00bfff", "london": "#4169e1",
            "zurich": "#6495ed", "paris": "#8a2be2", "new_york": "#9370db",
            "chicago": "#ba55d3", "toronto": "#da70d6", "overlap_london_new_york": "#ff1493",
            "crypto_24h": "#00ffff", "global_fx": "#ff69b4"
        }
        return colors.get(session.name.lower(), "#58a6ff")
    
    def update_time_scale(self, sessions: list[SessionInfo]):
        """Update time scale."""
        if not sessions:
            self.time_scale.setText("")
            return
        
        all_times = []
        for s in sessions:
            start = datetime.fromisoformat(s.start_utc.replace('Z', '+00:00'))
            end = datetime.fromisoformat(s.end_utc.replace('Z', '+00:00'))
            all_times.extend([start, end])
        
        min_time = min(all_times)
        max_time = max(all_times)
        total_minutes = (max_time - min_time).total_seconds() / 60
        
        scale_parts = []
        for i in range(13):
            scale_time = min_time + pd.Timedelta(minutes=total_minutes * i / 12)
            scale_parts.append(f'<span style="margin: 0 40px;">{scale_time.strftime("%H:%M")}</span>')
        
        self.time_scale.setText(" ".join(scale_parts))


class OrderBookWidget(QWidget):
    """Level 2 Order Book / DOM widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("📊 Order Book (Level 2)")
        header.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(header)
        
        # Spread info
        self.spread_label = QLabel("Spread: 0.0 pips | Mid: 0.00000 | Imbalance: 0%")
        self.spread_label.setStyleSheet("font-size: 11px; color: #8b949e; margin-bottom: 8px;")
        layout.addWidget(self.spread_label)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Price", "Size", "Orders", "Side"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0e1117;
                color: #e0e0e0;
                border: 1px solid #30363d;
                gridline-color: #21262d;
                font-size: 11px;
            }
            QHeaderView::section {
                background: #161b22;
                color: #8b949e;
                border: none;
                padding: 4px;
                font-weight: 600;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
        """)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 80)
        layout.addWidget(self.table)
    
    def update_book(self, bids: list[tuple], asks: list[tuple]):
        """Update order book display."""
        max_rows = max(len(bids), len(asks))
        self.table.setRowCount(max_rows * 2)
        
        # Fill asks (top, red)
        for i, (price, size) in enumerate(asks[:15]):
            self.table.setItem(i, 0, QTableWidgetItem(f"{price:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{size:.2f}"))
            self.table.setItem(i, 2, QTableWidgetItem("1"))
            side_item = QTableWidgetItem("ASK")
            side_item.setForeground(QColor("#f85149"))
            self.table.setItem(i, 3, side_item)
            
            # Color ask rows
            for col in range(4):
                item = self.table.item(i, col)
                if item:
                    item.setBackground(QColor("#2d1b1b"))
        
        # Spread separator
        sep_row = 15
        self.table.setItem(sep_row, 0, QTableWidgetItem("─" * 15))
        self.table.setItem(sep_row, 1, QTableWidgetItem(""))
        self.table.setItem(sep_row, 2, QTableWidgetItem(""))
        self.table.setItem(sep_row, 3, QTableWidgetItem(""))
        
        # Fill bids (bottom, green)
        for i, (price, size) in enumerate(bids[:15]):
            row = sep_row + 1 + i
            self.table.setItem(row, 0, QTableWidgetItem(f"{price:.5f}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{size:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem("1"))
            side_item = QTableWidgetItem("BID")
            side_item.setForeground(QColor("#3fb950"))
            self.table.setItem(row, 3, side_item)
            
            # Color bid rows
            for col in range(4):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QColor("#1b2d1b"))
        
        # Update spread info
        if bids and asks:
            spread = asks[0][0] - bids[0][0]
            mid = (asks[0][0] + bids[0][0]) / 2
            bid_vol = sum(b[1] for b in bids)
            ask_vol = sum(a[1] for a in asks)
            imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol) * 100 if (bid_vol + ask_vol) > 0 else 0
            
            self.spread_label.setText(
                f"Spread: {spread:.5f} ({spread*10000:.1f} pips)  |  "
                f"Mid: {mid:.5f}  |  "
                f"Imbalance: {imbalance:+.1f}%"
            )


class ConsoleWidget(QTextEdit):
    """Console output widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                line-height: 1.5;
                padding: 12px;
            }
        """)
        self.document().setMaximumBlockCount(500)
        self.auto_scroll = True
    
    def append_log(self, level: str, message: str):
        """Append colored log message."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        colors = {
            "DEBUG": "#8b949e",
            "INFO": "#58a6ff",
            "SUCCESS": "#3fb950",
            "WARNING": "#d29922",
            "ERROR": "#f85149",
        }
        
        color = colors.get(level, "#e0e0e0")
        
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Format: [timestamp] [LEVEL] message
        html = f'<span style="color:#6e7681;">[{timestamp}]</span> <span style="color:#8b949e;">[{level}]</span> <span style="color:{color};">{message}</span><br>'
        cursor.insertHtml(html)
        
        if self.auto_scroll:
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class NativeDashboard(QMainWindow):
    """Main native dashboard window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Elite Autonomous Quantum Trading System")
        self.setMinimumSize(1600, 1000)
        
        # Initialize components
        self.ws_client = WebSocketClient()
        self.ws_client.message_received.connect(self.on_ws_message)
        self.ws_client.connection_changed.connect(self.on_connection_changed)
        
        # State
        self.market_data: dict[str, MarketData] = {}
        self.trades: list[Trade] = []
        self.account_info = AccountInfo(0, 0, 0, 0, 0, 0, 0)
        self.sessions: list[SessionInfo] = []
        self.order_book_bids: list[tuple] = []
        self.order_book_asks: list[tuple] = []
        
        # Metrics
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        self.win_rate = 0.0
        self.sharpe = 0.0
        
        self.init_ui()
        self.apply_dark_theme()
        
        # Timers
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start(500)  # 2 Hz
        
        # Connect WebSocket
        asyncio.create_task(self.ws_client.connect())
    
    def init_ui(self):
        """Initialize UI."""
        # Central widget with tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #0e1117; }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: 500;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: #238636;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #21262d;
                color: #e0e0e0;
            }
        """)
        self.setCentralWidget(self.tabs)
        
        # Create tabs
        self.create_overview_tab()
        self.create_sessions_tab()
        self.create_chart_tab()
        self.create_brain_tab()
        self.create_trades_tab()
        self.create_orderbook_tab()
        self.create_console_tab()
        self.create_bloomberg_tab()
        self.create_command_bar_tab()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("● DISCONNECTED")
        self.status_label.setStyleSheet("color: #f85149; font-weight: 600;")
        self.status_bar.addPermanentWidget(self.status_label)
        
        # Mode indicator
        self.mode_label = QLabel("🔴 MANUAL")
        self.mode_label.setStyleSheet("color: #f85149; font-weight: 600; margin-right: 16px;")
        self.status_bar.addPermanentWidget(self.mode_label)
        
        # Time
        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #58a6ff; font-family: monospace; margin-right: 16px;")
        self.status_bar.addPermanentWidget(self.time_label)
        self.update_time()
    
    def create_overview_tab(self):
        """Create Overview tab with live PnL and metrics."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Header with controls
        header_layout = QHBoxLayout()
        
        title = QLabel("📊 OVERVIEW")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #e0e0e0;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.start_btn = QPushButton("▶ START")
        self.start_btn.setStyleSheet("""
            QPushButton { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: 600; }
            QPushButton:hover { background: #2ea043; }
        """)
        self.start_btn.clicked.connect(self.start_trading)
        header_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton { background: #da3633; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: 600; }
            QPushButton:hover { background: #f85149; }
        """)
        self.stop_btn.clicked.connect(self.stop_trading)
        header_layout.addWidget(self.stop_btn)
        
        layout.addLayout(header_layout)
        
        # Live PnL Metrics
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)
        
        self.pnl_card = MetricCard("Total PnL", "$0.00", "#3fb950")
        metrics_layout.addWidget(self.pnl_card)
        
        self.daily_pnl_card = MetricCard("Daily PnL", "$0.00", "#3fb950")
        metrics_layout.addWidget(self.daily_pnl_card)
        
        self.equity_card = MetricCard("Equity", "$100,000.00", "#58a6ff")
        metrics_layout.addWidget(self.equity_card)
        
        self.margin_card = MetricCard("Free Margin", "$100,000.00", "#e0e0e0")
        metrics_layout.addWidget(self.margin_card)
        
        self.win_rate_card = MetricCard("Win Rate", "0.0%", "#58a6ff")
        metrics_layout.addWidget(self.win_rate_card)
        
        self.sharpe_card = MetricCard("Sharpe Ratio", "0.00", "#e0e0e0")
        metrics_layout.addWidget(self.sharpe_card)
        
        layout.addLayout(metrics_layout)
        
        # Selection info + Brain metrics
        split = QSplitter(Qt.Orientation.Horizontal)
        
        # Selection panel
        selection_widget = QWidget()
        selection_layout = QVBoxLayout(selection_widget)
        
        sel_title = QLabel("🎯 Current Selection")
        sel_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        selection_layout.addWidget(sel_title)
        
        self.selection_labels = {}
        for key in ["Method", "Style", "Strategy", "Session", "Symbols", "Confidence"]:
            label = QLabel(f"{key}: -")
            label.setStyleSheet("font-size: 13px; color: #e0e0e0; padding: 4px;")
            selection_layout.addWidget(label)
            self.selection_labels[key.lower()] = label
        
        selection_layout.addStretch()
        split.addWidget(selection_widget)
        
        # Brain metrics panel
        brain_widget = QWidget()
        brain_layout = QVBoxLayout(brain_widget)
        
        brain_title = QLabel("🧠 Brain Metrics")
        brain_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        brain_layout.addWidget(brain_title)
        
        self.brain_labels = {}
        for key in ["Decision Accuracy", "Total Trades", "Winning Trades", "Generation", "Health"]:
            label = QLabel(f"{key}: -")
            label.setStyleSheet("font-size: 13px; color: #e0e0e0; padding: 4px;")
            brain_layout.addWidget(label)
            self.brain_labels[key.lower().replace(" ", "_")] = label
        
        brain_layout.addStretch()
        split.addWidget(brain_widget)
        
        split.setSizes([400, 400])
        layout.addWidget(split)
        
        # Active positions table
        pos_title = QLabel("📋 Active Positions")
        pos_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-top: 16px; margin-bottom: 8px;")
        layout.addWidget(pos_title)
        
        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(8)
        self.positions_table.setHorizontalHeaderLabels(["Symbol", "Side", "Volume", "Entry", "Current", "PnL", "SL", "TP"])
        self.positions_table.horizontalHeader().setStretchLastSection(True)
        self.positions_table.setStyleSheet("""
            QTableWidget { background: #161b22; color: #e0e0e0; border: 1px solid #30363d; gridline-color: #21262d; font-size: 12px; }
            QHeaderView::section { background: #161b22; color: #8b949e; border: none; padding: 8px; font-weight: 600; font-size: 11px; text-transform: uppercase; }
            QTableWidget::item { padding: 8px 12px; }
        """)
        layout.addWidget(self.positions_table)
        
        self.tabs.addTab(widget, "📊 OVERVIEW")
    
    def create_sessions_tab(self):
        """Create Sessions tab with 3-row timeline."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Timeline
        self.session_timeline = SessionTimelineWidget()
        layout.addWidget(self.session_timeline)
        
        # Active session details
        details_title = QLabel("📋 Active Session Details")
        details_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-top: 16px; margin-bottom: 8px;")
        layout.addWidget(details_title)
        
        self.session_details = QTextEdit()
        self.session_details.setReadOnly(True)
        self.session_details.setStyleSheet("""
            QTextEdit { background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #e0e0e0; font-size: 12px; padding: 12px; }
        """)
        layout.addWidget(self.session_details)
        
        self.tabs.addTab(widget, "🕐 SESSIONS")
    
    def create_chart_tab(self):
        """Create Live Chart tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Symbol selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Symbol:"))
        self.chart_symbol = QComboBox()
        self.chart_symbol.addItems(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD", "SPY", "QQQ"])
        self.chart_symbol.currentTextChanged.connect(self.on_chart_symbol_changed)
        selector_layout.addWidget(self.chart_symbol)
        
        self.chart_timeframe = QComboBox()
        self.chart_timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1D"])
        self.chart_timeframe.setCurrentText("5m")
        selector_layout.addWidget(self.chart_timeframe)
        
        selector_layout.addStretch()
        layout.addLayout(selector_layout)
        
        # Chart
        self.chart = ChartWidget()
        layout.addWidget(self.chart)
        
        self.tabs.addTab(widget, "📈 LIVE CHART")
    
    def create_brain_tab(self):
        """Create Brain tab with detailed metrics."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Brain metrics grid
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)
        
        brain_metrics = [
            ("Decision Accuracy", "0.0%", "decision_accuracy"),
            ("Win Rate", "0.0%", "win_rate"),
            ("Total PnL", "$0.00", "total_pnl"),
            ("Sharpe Ratio", "0.00", "sharpe"),
            ("Generation", "0", "generation"),
            ("Health", "UNKNOWN", "health"),
            ("Total Decisions", "0", "total_decisions"),
            ("Correct Decisions", "0", "correct_decisions"),
            ("Experience Buffer", "0", "experience_buffer"),
        ]
        
        self.brain_metric_cards = {}
        for i, (label, value, key) in enumerate(brain_metrics):
            card = MetricCard(label, value)
            metrics_grid.addWidget(card, i // 3, i % 3)
            self.brain_metric_cards[key] = card
        
        layout.addLayout(metrics_grid)
        layout.addStretch()
        
        self.tabs.addTab(widget, "🧠 BRAIN")
    
    def create_trades_tab(self):
        """Create Trades tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Live trades table
        title = QLabel("📋 Live Trades")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(title)
        
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(9)
        self.trades_table.setHorizontalHeaderLabels(["Time", "Symbol", "Side", "Volume", "Entry", "Current", "PnL", "SL", "TP"])
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.setStyleSheet("""
            QTableWidget { background: #161b22; color: #e0e0e0; border: 1px solid #30363d; gridline-color: #21262d; font-size: 12px; }
            QHeaderView::section { background: #161b22; color: #8b949e; border: none; padding: 8px; font-weight: 600; font-size: 11px; text-transform: uppercase; }
            QTableWidget::item { padding: 8px 12px; }
        """)
        layout.addWidget(self.trades_table)
        
        self.tabs.addTab(widget, "📋 TRADES")
    
    def create_orderbook_tab(self):
        """Create Order Book tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.orderbook = OrderBookWidget()
        layout.addWidget(self.orderbook)
        
        self.tabs.addTab(widget, "📊 ORDER BOOK")
    
    def create_console_tab(self):
        """Create Console tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        controls_layout.addWidget(QLabel("Level:"))
        self.log_level = QComboBox()
        self.log_level.addItems(["ALL", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"])
        controls_layout.addWidget(self.log_level)
        
        self.auto_scroll_cb = QCheckBox("Auto Scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.toggled.connect(lambda v: setattr(self.console, 'auto_scroll', v))
        controls_layout.addWidget(self.auto_scroll_cb)
        
        controls_layout.addWidget(QLabel("Max Lines:"))
        self.max_lines = QSpinBox()
        self.max_lines.setRange(100, 2000)
        self.max_lines.setValue(500)
        controls_layout.addWidget(self.max_lines)
        
        clear_btn = QPushButton("Clear Console")
        clear_btn.clicked.connect(self.console.clear)
        controls_layout.addWidget(clear_btn)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Console
        self.console = ConsoleWidget()
        layout.addWidget(self.console)
        
        self.tabs.addTab(widget, "🖥️ CONSOLE")
    
    def create_bloomberg_tab(self):
        """Create Bloomberg Terminal tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("📟 Bloomberg Terminal Adapter")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(title)
        
        # Command input
        input_layout = QHBoxLayout()
        self.bloomberg_cmd = QLineEdit()
        self.bloomberg_cmd.setPlaceholderText("e.g., AAPL US EQUITY | ECO | WFX | PORT | HP PERIOD=1Y")
        self.bloomberg_cmd.returnPressed.connect(self.execute_bloomberg)
        input_layout.addWidget(self.bloomberg_cmd)
        
        exec_btn = QPushButton("EXECUTE")
        exec_btn.setStyleSheet("background: #238636; color: white; padding: 8px 16px; border-radius: 4px; font-weight: 600;")
        exec_btn.clicked.connect(self.execute_bloomberg)
        input_layout.addWidget(exec_btn)
        
        layout.addLayout(input_layout)
        
        # Quick macros
        macros_layout = QHBoxLayout()
        macros = [("ECO", "Economic Calendar"), ("WFX", "FX Monitor"), ("HP", "Historical Pricing"),
                  ("PORT", "Portfolio"), ("EMSX", "Execution"), ("IB", "Chat"), ("MSG", "Messages"), ("BPIPE", "B-Pipe")]
        
        for macro, desc in macros:
            btn = QPushButton(macro)
            btn.setToolTip(desc)
            btn.setStyleSheet("padding: 6px 12px; background: #161b22; border: 1px solid #30363d; border-radius: 4px; color: #e0e0e0;")
            btn.clicked.connect(lambda checked, m=macro: self.execute_bloomberg_command(m))
            macros_layout.addWidget(btn)
        
        macros_layout.addStretch()
        layout.addLayout(macros_layout)
        
        # Result display
        self.bloomberg_result = QTextEdit()
        self.bloomberg_result.setReadOnly(True)
        self.bloomberg_result.setStyleSheet("""
            QTextEdit { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #e0e0e0; font-family: monospace; font-size: 11px; padding: 12px; }
        """)
        layout.addWidget(self.bloomberg_result)
        
        self.tabs.addTab(widget, "📟 BLOOMBERG")
    
    def create_command_bar_tab(self):
        """Create Global Command Bar tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("💡 Global Command Bar")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(title)
        
        # Command palette
        input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("/help | /buy EURUSD 1.0 | /vwap SPY 1000 | /risk 2% | /chart BTCUSD 1h")
        self.command_input.returnPressed.connect(self.execute_command)
        input_layout.addWidget(self.command_input)
        
        exec_btn = QPushButton("EXECUTE")
        exec_btn.setStyleSheet("background: #238636; color: white; padding: 8px 16px; border-radius: 4px; font-weight: 600;")
        exec_btn.clicked.connect(self.execute_command)
        input_layout.addWidget(exec_btn)
        
        layout.addLayout(input_layout)
        
        # Command buttons grid
        commands_grid = QGridLayout()
        categories = {
            "📈 Trading": ["/buy", "/sell", "/close", "/close_all", "/positions", "/orders"],
            "📊 Analysis": ["/chart", "/technical", "/fundamental", "/sentiment", "/correlation"],
            "⚙️ Settings": ["/risk", "/leverage", "/mode", "/session", "/symbols"],
            "🧠 Brain": ["/retrain", "/evolve", "/evaluate", "/goals", "/health"],
            "📋 System": ["/help", "/status", "/logs", "/config", "/backup", "/shutdown"],
        }
        
        for col, (cat, cmds) in enumerate(categories.items()):
            group = QGroupBox(cat)
            group.setStyleSheet("QGroupBox { color: #8b949e; font-weight: 600; border: 1px solid #30363d; border-radius: 4px; margin-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(4)
            
            for cmd in cmds:
                btn = QPushButton(cmd)
                btn.setStyleSheet("""
                    QPushButton { background: #161b22; border: 1px solid #30363d; border-radius: 4px; color: #8b949e; padding: 6px; font-size: 11px; }
                    QPushButton:hover { background: #238636; border-color: #238636; color: white; }
                """)
                btn.clicked.connect(lambda checked, c=cmd: self.set_command(c))
                group_layout.addWidget(btn)
            
            commands_grid.addWidget(group, 0, col)
        
        layout.addLayout(commands_grid)
        
        # Result display
        self.command_result = QTextEdit()
        self.command_result.setReadOnly(True)
        self.command_result.setStyleSheet("""
            QTextEdit { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #e0e0e0; font-family: monospace; font-size: 11px; padding: 12px; }
        """)
        layout.addWidget(self.command_result)
        
        self.tabs.addTab(widget, "💡 COMMAND BAR")
    
    def apply_dark_theme(self):
        """Apply Bloomberg-style dark theme."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0e1117"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#0d1117"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#161b22"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#161b22"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#161b22"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#f85149"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#58a6ff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#238636"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)
        
        self.setStyleSheet("""
            QMainWindow { background: #0e1117; }
            QWidget { background: #0e1117; color: #e0e0e0; }
            QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 8px; padding-top: 8px; color: #8b949e; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QPushButton { background: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 6px 12px; color: #e0e0e0; }
            QPushButton:hover { background: #21262d; border-color: #58a6ff; }
            QPushButton:pressed { background: #238636; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 6px; color: #e0e0e0; selection-background-color: #238636;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #58a6ff; }
            QComboBox::drop-down { border: none; width: 20px; }
            QScrollBar:vertical { background: #0e1117; width: 10px; }
            QScrollBar::handle:vertical { background: #30363d; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #484f58; }
            QSplitter::handle { background: #30363d; width: 2px; }
        """)
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def on_chart_symbol_changed(self, symbol: str):
        """Handle chart symbol change."""
        self.chart.update_symbol(symbol)
    
    def execute_bloomberg(self):
        """Execute Bloomberg command."""
        cmd = self.bloomberg_cmd.text().strip()
        if cmd:
            self.execute_bloomberg_command(cmd)
    
    def execute_bloomberg_command(self, cmd: str):
        """Execute Bloomberg-style command."""
        self.bloomberg_cmd.setText(cmd)
        
        # Simple command parser
        result = {"command": cmd, "result": "Command executed (simulated)"}
        
        if cmd == "ECO":
            result = {"economic_calendar": [
                {"time": "12:30", "country": "US", "event": "CPI YoY", "actual": "3.2%", "forecast": "3.1%", "impact": "High"},
                {"time": "14:00", "country": "US", "event": "Fed Rate Decision", "actual": "5.50%", "forecast": "5.50%", "impact": "High"},
            ]}
        elif cmd == "WFX":
            result = {"fx_rates": {"EURUSD": 1.0852, "GBPUSD": 1.2650, "USDJPY": 149.85, "USDCHF": 0.8920}}
        elif cmd == "PORT":
            result = {"equity": 100000, "pnl": 1250.50, "positions": 3, "sharpe": 1.85}
        
        self.bloomberg_result.setPlainText(json.dumps(result, indent=2))
        self.console.append_log("INFO", f"Bloomberg: {cmd}")
    
    def set_command(self, cmd: str):
        """Set command in command bar."""
        self.command_input.setText(cmd)
    
    def execute_command(self):
        """Execute global command."""
        cmd = self.command_input.text().strip()
        if not cmd:
            return
        
        if not cmd.startswith('/'):
            cmd = '/' + cmd
        
        result = {"command": cmd, "status": "executed"}
        
        # Parse command
        parts = cmd[1:].split()
        if not parts:
            return
        
        base_cmd = parts[0].lower()
        
        if base_cmd in ["help", "h", "?"]:
            result = {
                "message": "Command Bar Help",
                "commands": {
                    "trading": ["/buy", "/sell", "/close", "/close_all", "/positions", "/orders"],
                    "analysis": ["/chart", "/technical", "/fundamental", "/sentiment", "/correlation"],
                    "execution": ["/vwap", "/twap", "/pov", "/is", "/iceberg"],
                    "risk": ["/risk", "/leverage", "/mode", "/session", "/symbols"],
                    "brain": ["/retrain", "/evolve", "/evaluate", "/goals", "/health"],
                    "system": ["/help", "/status", "/logs", "/config", "/backup", "/shutdown"]
                }
            }
        elif base_cmd in ["status", "st"]:
            result = {"system": "Elite Autonomous Trading System", "status": "RUNNING", "mode": "AUTO"}
        elif base_cmd in ["buy", "b"]:
            result = {"action": "buy", "symbol": parts[1] if len(parts) > 1 else "EURUSD", "status": "simulated"}
        elif base_cmd in ["sell", "s"]:
            result = {"action": "sell", "symbol": parts[1] if len(parts) > 1 else "EURUSD", "status": "simulated"}
        elif base_cmd in ["chart", "ch"]:
            symbol = parts[1] if len(parts) > 1 else "EURUSD"
            tf = parts[2] if len(parts) > 2 else "1h"
            self.chart_symbol.setCurrentText(symbol)
            self.chart_timeframe.setCurrentText(tf)
            result = {"action": "chart", "symbol": symbol, "timeframe": tf}
        elif base_cmd in ["risk"]:
            result = {"risk_per_trade": parts[1] if len(parts) > 1 else "2%"}
        elif base_cmd in ["evolve"]:
            result = {"action": "evolve", "status": "initiated"}
        
        self.command_result.setPlainText(json.dumps(result, indent=2))
        self.console.append_log("INFO", f"Command: {cmd}")
    
    def start_trading(self):
        """Start autonomous trading."""
        self.mode_label.setText("🟢 AUTO")
        self.mode_label.setStyleSheet("color: #3fb950; font-weight: 600; margin-right: 16px;")
        self.console.append_log("SUCCESS", "Autonomous trading STARTED")
    
    def stop_trading(self):
        """Stop autonomous trading."""
        self.mode_label.setText("🔴 MANUAL")
        self.mode_label.setStyleSheet("color: #f85149; font-weight: 600; margin-right: 16px;")
        self.console.append_log("WARNING", "Autonomous trading STOPPED")
    
    def on_ws_message(self, data: dict):
        """Handle WebSocket message."""
        msg_type = data.get("type", "")
        
        if msg_type == "init" or msg_type == "update":
            ws_data = data.get("data", {})
            
            # Update market data
            if "market_data" in ws_data:
                for symbol, md in ws_data["market_data"].items():
                    self.market_data[symbol] = MarketData(
                        symbol=symbol,
                        bid=md.get("bid", 0),
                        ask=md.get("ask", 0),
                        last=md.get("last", 0),
                        volume=md.get("volume", 0),
                        timestamp=datetime.fromisoformat(md.get("time", datetime.now(timezone.utc).isoformat()))
                    )
            
            # Update account
            if "account" in ws_data:
                acc = ws_data["account"]
                self.account_info = AccountInfo(
                    equity=acc.get("equity", 0),
                    balance=acc.get("balance", 0),
                    profit=acc.get("profit", 0),
                    daily_pnl=acc.get("daily_pnl", 0),
                    margin=acc.get("margin", 0),
                    free_margin=acc.get("free_margin", 0),
                    margin_level=acc.get("margin_level", 0)
                )
            
            # Update positions/trades
            if "positions" in ws_data:
                # Update positions table
                raise NotImplementedError("Not implemented")
            
            # Update selection
            if "selection" in ws_data:
                sel = ws_data["selection"]
                self.update_selection_display(sel)
            
            # Update brain metrics
            if "brain" in ws_data:
                brain = ws_data["brain"]
                self.update_brain_display(brain)
            
            # Update sessions
            if "sessions" in ws_data:
                sessions_data = ws_data["sessions"]
                self.sessions = [SessionInfo(**s) for s in sessions_data]
                self.session_timeline.update_sessions(self.sessions)
                self.update_session_details()
            
            # Update order book
            if "orderbook" in ws_data:
                ob = ws_data["orderbook"]
                self.order_book_bids = ob.get("bids", [])
                self.order_book_asks = ob.get("asks", [])
                self.orderbook.update_book(self.order_book_bids, self.order_book_asks)
    
    def on_connection_changed(self, connected: bool):
        """Handle WebSocket connection change."""
        if connected:
            self.status_label.setText("● CONNECTED")
            self.status_label.setStyleSheet("color: #3fb950; font-weight: 600;")
        else:
            self.status_label.setText("● DISCONNECTED")
            self.status_label.setStyleSheet("color: #f85149; font-weight: 600;")
    
    def update_selection_display(self, selection: dict):
        """Update selection display."""
        self.selection_labels["method"].setText(f"Method: {selection.get('method', '-')}")
        self.selection_labels["style"].setText(f"Style: {selection.get('style', '-')}")
        self.selection_labels["strategy"].setText(f"Strategy: {selection.get('strategy', '-')}")
        self.selection_labels["session"].setText(f"Session: {selection.get('session', '-')}")
        self.selection_labels["symbols"].setText(f"Symbols: {', '.join(selection.get('symbols', [])[:5])}")
        self.selection_labels["confidence"].setText(f"Confidence: {selection.get('confidence', 0):.1%}")
    
    def update_brain_display(self, brain: dict):
        """Update brain metrics display."""
        self.brain_metric_cards["decision_accuracy"].update_value(
            f"{brain.get('decision_accuracy', 0):.1f}%",
            "#3fb950" if brain.get('decision_accuracy', 0) > 50 else "#f85149"
        )
        self.brain_metric_cards["win_rate"].update_value(
            f"{brain.get('win_rate', 0):.1f}%",
            "#3fb950" if brain.get('win_rate', 0) > 50 else "#f85149"
        )
        self.brain_metric_cards["total_pnl"].update_value(
            f"${brain.get('total_pnl', 0):,.2f}",
            "#3fb950" if brain.get('total_pnl', 0) >= 0 else "#f85149"
        )
        self.brain_metric_cards["sharpe"].update_value(f"{brain.get('sharpe_ratio', 0):.2f}")
        self.brain_metric_cards["generation"].update_value(str(brain.get('generation', 0)))
        self.brain_metric_cards["health"].update_value(
            brain.get('health_status', 'UNKNOWN'),
            "#3fb950" if brain.get('health_status') == 'HEALTHY' else "#d29922" if brain.get('health_status') == 'DEGRADED' else "#f85149"
        )
        self.brain_metric_cards["total_decisions"].update_value(str(brain.get('total_decisions', 0)))
        self.brain_metric_cards["correct_decisions"].update_value(str(brain.get('correct_decisions', 0)))
        self.brain_metric_cards["experience_buffer"].update_value(str(brain.get('experience_buffer_size', 0)))
    
    def update_session_details(self):
        """Update session details panel."""
        if not self.sessions:
            self.session_details.setPlainText("No active sessions")
            return
        
        html_parts = []
        for s in self.sessions:
            start = datetime.fromisoformat(s.start_utc.replace('Z', '+00:00'))
            end = datetime.fromisoformat(s.end_utc.replace('Z', '+00:00'))
            color = self.session_timeline.get_session_color(s)
            session_html = (
                f'<div style="border-left: 4px solid {color}; padding: 8px; margin: 8px 0; background: #161b22;">'
                f'<div style="color: {color}; font-weight: 600;">🔴 ACTIVE: {s.name.upper()} ({s.market_type})</div>'
                f'<div>Start: {s.start_utc} UTC | End: {s.end_utc} UTC</div>'
                f'<div>Remaining: {s.time_remaining} | Progress: {s.progress:.1f}%</div>'
                f'</div>'
            )
            html_parts.append(session_html)
        self.session_details.setHtml(''.join(html_parts))