"""
Elite Autonomous Quantum Trading System - Enhanced Session Manager
Complete session management for all global markets with automatic symbol filtering.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MarketType(Enum):
    """Market types."""
    FOREX = "forex"
    CRYPTO = "crypto"
    EQUITIES = "equities"
    FUTURES = "futures"
    COMMODITIES = "commodities"
    INDICES = "indices"
    METALS = "metals"


class SessionType(Enum):
    """Session types."""
    FOREX = "forex"
    EQUITIES = "equities"
    FUTURES = "futures"
    CRYPTO = "crypto"
    EXTENDED_HOURS = "extended_hours"
    OVERLAP = "overlap"


@dataclass
class TradingSession:
    """Trading session definition."""
    name: str
    market_type: MarketType
    session_type: SessionType
    start_utc: time
    end_utc: time
    days: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4, 5, 6})  # All days by default
    major_symbols: list[str] = field(default_factory=list)
    break_start: time | None = None
    break_end: time | None = None
    timezone: str = "UTC"
    is_24h: bool = False
    liquidity: str = "medium"  # low, medium, high
    volatility: str = "medium"  # low, medium, high
    overlaps_with: list[str] = field(default_factory=list)


@dataclass
class ActiveSessionInfo:
    """Information about currently active session."""
    session: TradingSession
    progress: float  # 0.0 to 1.0
    time_remaining: timedelta
    is_active: bool
    overlaps: list[TradingSession] = field(default_factory=list)


class SessionManager:
    """
    Complete session manager for all global markets.
    Handles session detection, symbol filtering, and timeline visualization.
    """
    
    def __init__(self):
        self.sessions: dict[str, TradingSession] = {}
        self.symbol_sessions: dict[str, list[str]] = defaultdict(list)  # symbol -> session names
        self.session_symbols: dict[str, list[str]] = defaultdict(list)  # session -> symbols
        self.active_sessions: dict[str, TradingSession] = {}
        self.last_update: datetime | None = None
        
        # Initialize all sessions
        self._initialize_all_sessions()
        self._build_symbol_mappings()
        
        logger.info(f"SessionManager initialized with {len(self.sessions)} sessions")
    
    def _initialize_all_sessions(self):
        """Initialize all global trading sessions."""
        
        # ============================================================
        # 1. FOREX SESSIONS
        # ============================================================
        forex_sessions = [
            TradingSession(
                name="wellington",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(20, 0),
                end_utc=time(5, 0),
                major_symbols=["AUDUSD", "NZDUSD", "AUDJPY", "NZDJPY", "AUDNZD"],
                liquidity="medium",
                volatility="low",
                overlaps_with=["sydney"]
            ),
            TradingSession(
                name="sydney",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(22, 0),
                end_utc=time(7, 0),
                major_symbols=["AUDUSD", "NZDUSD", "AUDJPY", "NZDJPY", "AUDCHF"],
                liquidity="medium",
                volatility="medium",
                overlaps_with=["tokyo", "wellington"]
            ),
            TradingSession(
                name="tokyo",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(23, 0),
                end_utc=time(8, 0),
                major_symbols=["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY"],
                liquidity="high",
                volatility="medium",
                overlaps_with=["sydney", "hong_kong", "singapore"]
            ),
            TradingSession(
                name="hong_kong",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(1, 0),
                end_utc=time(10, 0),
                major_symbols=["USDHKD", "EURHKD", "GBPHKD", "AUDHKD"],
                liquidity="medium",
                volatility="low",
                overlaps_with=["tokyo", "singapore"]
            ),
            TradingSession(
                name="singapore",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(1, 0),
                end_utc=time(10, 0),
                major_symbols=["USDSGD", "EURSGD", "GBPSGD", "AUDSGD"],
                liquidity="medium",
                volatility="low",
                overlaps_with=["tokyo", "hong_kong"]
            ),
            TradingSession(
                name="frankfurt",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(6, 0),
                end_utc=time(15, 0),
                major_symbols=["EURUSD", "GBPEUR", "EURCHF", "EURGBP", "EURJPY"],
                liquidity="high",
                volatility="medium",
                overlaps_with=["london", "zurich"]
            ),
            TradingSession(
                name="london",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(7, 0),
                end_utc=time(16, 0),
                major_symbols=["EURUSD", "GBPUSD", "EURGBP", "GBPCHF", "GBPJPY", "EURCHF", "EURJPY"],
                liquidity="very_high",
                volatility="high",
                overlaps_with=["frankfurt", "zurich", "new_york", "new_york_am"]
            ),
            TradingSession(
                name="zurich",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(7, 0),
                end_utc=time(15, 0),
                major_symbols=["USDCHF", "EURCHF", "GBPCHF", "CHFJPY"],
                liquidity="high",
                volatility="medium",
                overlaps_with=["london", "frankfurt"]
            ),
            TradingSession(
                name="new_york",
                market_type=MarketType.FOREX,
                session_type=SessionType.FOREX,
                start_utc=time(12, 0),
                end_utc=time(21, 0),
                major_symbols=["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "XAUUSD", "XAGUSD"],
                liquidity="very_high",
                volatility="high",
                overlaps_with=["london", "new_york_pm"]
            ),
        ]
        
        # Add forex sessions
        for session in forex_sessions:
            self.sessions[session.name] = session
        
        # ============================================================
        # 2. EQUITY MARKETS (STOCK EXCHANGES)
        # ============================================================
        equity_sessions = [
            TradingSession(
                name="sydney_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(0, 0),
                end_utc=time(6, 0),
                days={0, 1, 2, 3, 4},  # Mon-Fri
                major_symbols=["ASX200", "BHP", "CBA", "CSL", "WBC", "ANZ"],
                liquidity="medium",
                volatility="medium"
            ),
            TradingSession(
                name="tokyo_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(0, 0),
                end_utc=time(6, 0),
                days={0, 1, 2, 3, 4},
                break_start=time(2, 30),
                break_end=time(3, 30),
                major_symbols=["NIKKEI225", "TOPIX", "7203", "9984", "6758", "9983"],
                liquidity="high",
                volatility="medium"
            ),
            TradingSession(
                name="hong_kong_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(1, 30),
                end_utc=time(8, 0),
                days={0, 1, 2, 3, 4},
                break_start=time(4, 0),
                break_end=time(5, 0),
                major_symbols=["HSI", "HSCEI", "0700", "0941", "1299", "2318", "3690"],
                liquidity="high",
                volatility="high"
            ),
            TradingSession(
                name="shanghai_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(1, 30),
                end_utc=time(7, 0),
                days={0, 1, 2, 3, 4},
                break_start=time(3, 30),
                break_end=time(5, 0),
                major_symbols=["SSE50", "CSI300", "600519", "601318", "600036"],
                liquidity="high",
                volatility="high"
            ),
            TradingSession(
                name="dubai_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(6, 0),
                end_utc=time(11, 45),
                days={6, 0, 1, 2, 3},  # Sun-Thu
                major_symbols=["DFMGI", "EMAAR", "DUBAI", "EMIRATES"],
                liquidity="medium",
                volatility="medium"
            ),
            TradingSession(
                name="saudi_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(7, 0),
                end_utc=time(12, 0),
                days={6, 0, 1, 2, 3},  # Sun-Thu
                major_symbols=["TASI", "2222", "1120", "2010", "1180"],
                liquidity="medium",
                volatility="medium"
            ),
            TradingSession(
                name="frankfurt_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(7, 0),
                end_utc=time(15, 30),
                days={0, 1, 2, 3, 4},
                major_symbols=["DAX40", "MDAX", "TECDAX", "SAP", "SIE", "VOW3", "BMW", "DTE"],
                liquidity="high",
                volatility="medium"
            ),
            TradingSession(
                name="london_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(7, 0),
                end_utc=time(15, 30),
                days={0, 1, 2, 3, 4},
                major_symbols=["FTSE100", "FTSE250", "VOD", "BP", "HSBA", "GSK", "AZN"],
                liquidity="high",
                volatility="medium"
            ),
            TradingSession(
                name="paris_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(7, 0),
                end_utc=time(15, 30),
                days={0, 1, 2, 3, 4},
                major_symbols=["CAC40", "MC", "OR", "AIR", "BNP", "SAN", "TTE"],
                liquidity="high",
                volatility="medium"
            ),
            TradingSession(
                name="johannesburg_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(7, 0),
                end_utc=time(15, 0),
                days={0, 1, 2, 3, 4},
                major_symbols=["JSE40", "NPN", "FSR", "ANG", "IMP", "MTN"],
                liquidity="medium",
                volatility="medium"
            ),
            TradingSession(
                name="b3_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(13, 0),
                end_utc=time(20, 0),
                days={0, 1, 2, 3, 4},
                major_symbols=["IBOV", "PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3"],
                liquidity="medium",
                volatility="high"
            ),
            TradingSession(
                name="mexico_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(13, 30),
                end_utc=time(20, 0),
                days={0, 1, 2, 3, 4},
                major_symbols=["IPC", "AMX", "WALMEX", "FEMSA", "CEMEX"],
                liquidity="medium",
                volatility="medium"
            ),
            TradingSession(
                name="us_equities",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EQUITIES,
                start_utc=time(13, 30),
                end_utc=time(20, 0),
                days={0, 1, 2, 3, 4},
                major_symbols=["SPX", "NDX", "DJI", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"],
                liquidity="very_high",
                volatility="high"
            ),
        ]
        
        for session in equity_sessions:
            self.sessions[session.name] = session
        
        # ============================================================
        # 3. US EXTENDED HOURS
        # ============================================================
        extended_sessions = [
            TradingSession(
                name="us_premarket",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EXTENDED_HOURS,
                start_utc=time(8, 0),
                end_utc=time(13, 30),
                days={0, 1, 2, 3, 4},
                major_symbols=["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA"],
                liquidity="low",
                volatility="high"
            ),
            TradingSession(
                name="us_afterhours",
                market_type=MarketType.EQUITIES,
                session_type=SessionType.EXTENDED_HOURS,
                start_utc=time(20, 0),
                end_utc=time(0, 0),
                days={0, 1, 2, 3, 4},
                major_symbols=["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA"],
                liquidity="low",
                volatility="high"
            ),
        ]
        
        for session in extended_sessions:
            self.sessions[session.name] = session
        
        # ============================================================
        # 4. FUTURES & COMMODITIES
        # ============================================================
        futures_sessions = [
            TradingSession(
                name="cme_futures",
                market_type=MarketType.FUTURES,
                session_type=SessionType.FUTURES,
                start_utc=time(22, 0),  # Sunday
                end_utc=time(21, 0),    # Friday
                days={6, 0, 1, 2, 3, 4},  # Sun-Fri
                break_start=time(21, 0),
                break_end=time(22, 0),
                major_symbols=["ES", "NQ", "YM", "RTY", "CL", "NG", "GC", "SI", "HG", "ZB", "ZN", "ZF"],
                liquidity="very_high",
                volatility="high",
                is_24h=False  # Has daily break
            ),
            TradingSession(
                name="ice_futures",
                market_type=MarketType.FUTURES,
                session_type=SessionType.FUTURES,
                start_utc=time(23, 0),  # Sunday
                end_utc=time(22, 0),    # Friday
                days={6, 0, 1, 2, 3, 4},
                major_symbols=["BRENT", "WTI", "GASOIL", "SUGAR", "COCOA", "COTTON"],
                liquidity="high",
                volatility="high"
            ),
        ]
        
        for session in futures_sessions:
            self.sessions[session.name] = session
        
        # ============================================================
        # 5. CRYPTO (24/7)
        # ============================================================
        crypto_session = TradingSession(
            name="crypto_24_7",
            market_type=MarketType.CRYPTO,
            session_type=SessionType.CRYPTO,
            start_utc=time(0, 0),
            end_utc=time(23, 59, 59),
            days={0, 1, 2, 3, 4, 5, 6},
            major_symbols=["BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT", "SOLUSD", "AVAXUSD", "DOTUSD"],
            liquidity="high",
            volatility="very_high",
            is_24h=True
        )
        self.sessions[crypto_session.name] = crypto_session
        
        # ============================================================
        # 6. METALS & COMMODITIES (via futures/forex overlap)
        # ============================================================
        # Gold/Silver trade via forex sessions + futures
        # They're covered by forex + futures sessions
        
        # ============================================================
        # 7. OVERLAP SESSIONS (Virtual sessions)
        # ============================================================
        overlap_sessions = [
            TradingSession(
                name="london_newyork_overlap",
                market_type=MarketType.FOREX,
                session_type=SessionType.OVERLAP,
                start_utc=time(12, 0),
                end_utc=time(16, 0),
                major_symbols=["EURUSD", "GBPUSD", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD"],
                liquidity="extreme",
                volatility="high",
                overlaps_with=["london", "new_york"]
            ),
            TradingSession(
                name="tokyo_london_overlap",
                market_type=MarketType.FOREX,
                session_type=SessionType.OVERLAP,
                start_utc=time(7, 0),
                end_utc=time(8, 0),
                major_symbols=["EURJPY", "GBPJPY", "CHFJPY", "AUDJPY", "NZDJPY"],
                liquidity="high",
                volatility="medium",
                overlaps_with=["tokyo", "london"]
            ),
            TradingSession(
                name="sydney_tokyo_overlap",
                market_type=MarketType.FOREX,
                session_type=SessionType.OVERLAP,
                start_utc=time(23, 0),
                end_utc=time(7, 0),
                major_symbols=["AUDUSD", "NZDUSD", "AUDJPY", "NZDJPY"],
                liquidity="medium",
                volatility="medium",
                overlaps_with=["sydney", "tokyo"]
            ),
        ]
        
        for session in overlap_sessions:
            self.sessions[session.name] = session
    
    def _build_symbol_mappings(self):
            """Build bidirectional symbol <-> session mappings."""
            for session_name, session in self.sessions.items():
                for symbol in session.major_symbols:
                    self.symbol_sessions[symbol].append(session_name)
                    self.session_symbols[session_name].append(symbol)
    
    async def initialize(self):
        """Initialize the session manager."""
        await self.update_active_sessions()
        logger.info("SessionManager initialized")
    
    def is_session_active(self, session: TradingSession, check_time: datetime | None = None) -> bool:
        """Check if a session is active at given time."""
        if check_time is None:
            check_time = datetime.now(UTC)
        
        # Check day
        if check_time.weekday() not in session.days:
            return False
        
        # Check time (handle overnight sessions)
        current_time = check_time.time()
        
        if session.start_utc <= session.end_utc:
            # Same day session
            in_session = session.start_utc <= current_time < session.end_utc
        else:
            # Overnight session
            in_session = current_time >= session.start_utc or current_time < session.end_utc
        
        # Check break
        if session.break_start and session.break_end:
            if session.break_start <= current_time < session.break_end:
                return False
        
        return in_session
    
    def is_in_break(self, session: TradingSession, check_time: datetime | None = None) -> bool:
        """Check if session is in break period."""
        if not session.break_start or not session.break_end:
            return False
        
        if check_time is None:
            check_time = datetime.now(UTC)
        
        current_time = check_time.time()
        return session.break_start <= current_time < session.break_end
    
    async def update_active_sessions(self):
            """Update the active sessions cache."""
            now = datetime.now(UTC)
            self.active_sessions = {}
        
            for session_name, session in self.sessions.items():
                if self.is_session_active(session, now):
                    self.active_sessions[session_name] = session
        
            self.last_update = now
            logger.debug(f"Active sessions: {list(self.active_sessions.keys())}")
    
    def get_active_sessions(self) -> dict[str, TradingSession]:
        """Get currently active sessions."""
        return self.active_sessions.copy()
    
    def get_active_symbols(self, market_type: MarketType | None = None) -> set[str]:
        """Get all tradable symbols for currently active sessions."""
        symbols = set()
        
        for session in self.active_sessions.values():
            if market_type is None or session.market_type == market_type:
                symbols.update(session.major_symbols)
        
        return symbols
    
    def get_active_sessions_by_market(self, market_type: MarketType) -> list[TradingSession]:
        """Get active sessions filtered by market type."""
        return [
            s for s in self.active_sessions.values()
            if s.market_type == market_type
        ]
    
    def get_session_info(self, session_name: str) -> ActiveSessionInfo | None:
        """Get detailed info about a session including progress."""
        session = self.sessions.get(session_name)
        if not session:
            return None
        
        now = datetime.now(UTC)
        is_active = self.is_session_active(session, now)
        
        if not is_active:
            return ActiveSessionInfo(
                session=session,
                progress=0.0,
                time_remaining=timedelta(0),
                is_active=False
            )
        
        # Calculate progress
        now_time = now.time()
        
        # Convert to minutes since midnight for calculation
        def time_to_minutes(t: time) -> int:
            return t.hour * 60 + t.minute
        
        start_min = time_to_minutes(session.start_utc)
        end_min = time_to_minutes(session.end_utc)
        now_min = time_to_minutes(now_time)
        
        # Handle overnight
        if end_min <= start_min:
            end_min += 24 * 60
            if now_min < start_min:
                now_min += 24 * 60
        
        total_min = end_min - start_min
        elapsed_min = now_min - start_min
        progress = max(0.0, min(1.0, elapsed_min / total_min)) if total_min > 0 else 1.0
        
        # Time remaining
        remaining_min = max(0, total_min - elapsed_min)
        time_remaining = timedelta(minutes=remaining_min)
        
        # Find overlaps
        overlaps = []
        for overlap_name in session.overlaps_with:
            overlap_session = self.sessions.get(overlap_name)
            if overlap_session and self.is_session_active(overlap_session, now):
                overlaps.append(overlap_session)
        
        return ActiveSessionInfo(
            session=session,
            progress=progress,
            time_remaining=time_remaining,
            is_active=True,
            overlaps=overlaps
        )
    
    def get_next_session(self, market_type: MarketType | None = None) -> ActiveSessionInfo | None:
        """Get the next upcoming session."""
        now = datetime.now(UTC)
        next_sessions = []
        
        for session in self.sessions.values():
            if market_type and session.market_type != market_type:
                continue
            
            if self.is_session_active(session):
                continue
            
            # Find next activation time
            next_start = self._get_next_session_start(session, now)
            if next_start:
                next_sessions.append((next_start, session))
        
        if not next_sessions:
            return None
        
        next_sessions.sort(key=lambda x: x[0])
        next_start, session = next_sessions[0]
        
        return ActiveSessionInfo(
            session=session,
            progress=0.0,
            time_remaining=next_start - now,
            is_active=False
        )
    
    def _get_next_session_start(self, session: TradingSession, from_time: datetime) -> datetime | None:
        """Calculate next session start time."""
        # Check next 7 days
        for i in range(7):
            check_date = from_time + timedelta(days=i)
            if check_date.weekday() not in session.days:
                continue
            
            start_dt = datetime.combine(check_date.date(), session.start_utc, tzinfo=UTC)
            if start_dt > from_time:
                return start_dt
        
        return None
    
    def get_session_timeline(self, hours_ahead: int = 24) -> list[dict[str, Any]]:
        """Get session timeline for visualization."""
        now = datetime.now(UTC)
        end_time = now + timedelta(hours=hours_ahead)
        timeline = []
        
        for session in self.sessions.values():
            # Find all occurrences in the time range
            current = now
            while current < end_time:
                if current.weekday() in session.days:
                    start_dt = datetime.combine(current.date(), session.start_utc, tzinfo=UTC)
                    end_dt = datetime.combine(current.date(), session.end_utc, tzinfo=UTC)
                    
                    # Handle overnight
                    if session.end_utc <= session.start_utc:
                        end_dt += timedelta(days=1)
                    
                    # Adjust for breaks
                    if session.break_start and session.break_end:
                        break_start = datetime.combine(current.date(), session.break_start, tzinfo=UTC)
                        break_end = datetime.combine(current.date(), session.break_end, tzinfo=UTC)
                        
                        # Split into two segments
                        if start_dt < now < end_dt:
                            timeline.append({
                                "session": session.name,
                                "name": session.name,
                                "start": max(start_dt, now).isoformat(),
                                "end": min(break_start, end_dt).isoformat(),
                                "market_type": session.market_type.value,
                                "symbols": session.major_symbols[:5],
                                "liquidity": session.liquidity,
                                "is_active": start_dt <= now < break_start
                            })
                            
                            if break_end < end_dt:
                                timeline.append({
                                    "session": session.name,
                                    "name": session.name,
                                    "start": max(break_end, now).isoformat(),
                                    "end": end_dt.isoformat(),
                                    "market_type": session.market_type.value,
                                    "symbols": session.major_symbols[:5],
                                    "liquidity": session.liquidity,
                                    "is_active": break_end <= now < end_dt
                                })
                        else:
                            if start_dt < end_time and end_dt > now:
                                timeline.append({
                                    "session": session.name,
                                    "name": session.name,
                                    "start": max(start_dt, now).isoformat(),
                                    "end": min(end_dt, end_time).isoformat(),
                                    "market_type": session.market_type.value,
                                    "symbols": session.major_symbols[:5],
                                    "liquidity": session.liquidity,
                                    "is_active": start_dt <= now < end_dt
                                })
                    else:
                        if start_dt < end_time and end_dt > now:
                            timeline.append({
                                "session": session.name,
                                "name": session.name,
                                "start": max(start_dt, now).isoformat(),
                                "end": min(end_dt, end_time).isoformat(),
                                "market_type": session.market_type.value,
                                "symbols": session.major_symbols[:5],
                                "liquidity": session.liquidity,
                                "is_active": start_dt <= now < end_dt
                            })
                
                current += timedelta(days=1)
        
        timeline.sort(key=lambda x: x["start"])
        return timeline
    
    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of all sessions."""
        active_count = len(self.active_sessions)
        total_count = len(self.sessions)
        
        by_market = defaultdict(int)
        for session in self.active_sessions.values():
            by_market[session.market_type.value] += 1
        
        next_session = self.get_next_session()
        
        return {
            "total_sessions": total_count,
            "active_sessions": active_count,
            "active_by_market": dict(by_market),
            "next_session": {
                "name": next_session.session.name,
                "starts_in": str(next_session.time_remaining),
                "market_type": next_session.session.market_type.value
            } if next_session else None,
            "last_update": self.last_update.isoformat() if self.last_update else None
        }
    
    def get_symbol_sessions(self, symbol: str) -> list[TradingSession]:
        """Get all sessions where a symbol is traded."""
        session_names = self.symbol_sessions.get(symbol, [])
        return [self.sessions[name] for name in session_names if name in self.sessions]
    
    def get_session_by_name(self, name: str) -> TradingSession | None:
        """Get session by name."""
        return self.sessions.get(name)
    
    def filter_symbols_by_active_sessions(self, symbols: list[str]) -> list[str]:
        """Filter symbols to only those tradeable in active sessions."""
        active_symbols = self.get_active_symbols()
        return [s for s in symbols if s in active_symbols]
    
    def get_session_overlap_matrix(self) -> dict[str, list[str]]:
            """Get session overlap matrix."""
            overlaps = defaultdict(list)
        
            for session_name, session in self.active_sessions.items():
                for overlap_name in session.overlaps_with:
                    if overlap_name in self.active_sessions:
                        overlaps[session_name].append(overlap_name)
        
            return dict(overlaps)


# Global instance
session_manager = SessionManager()