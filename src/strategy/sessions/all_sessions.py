"""
Session definitions and helper utilities for the Forex trading system.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass


@dataclass(frozen=True)
class TradingSession:
    name: str
    market_type: str  # e.g., "forex", "equities", "crypto", "futures"
    start_utc: int  # hour 0-23 (inclusive)
    end_utc: int  # hour 0-23 (exclusive, 24 means midnight next day)
    days: list[int]  # 0=Mon ... 6=Sun
    symbols: list[str]
    overlaps_with: list[str]

    def is_active(self, now: _dt.datetime) -> bool:
        """Return True if this session is active at the given UTC datetime.
        Handles sessions that span midnight.
        """
        if now.weekday() not in self.days:
            return False
        hour = now.hour + now.minute / 60.0
        if self.start_utc <= self.end_utc:
            return self.start_utc <= hour < self.end_utc
        # Cross‑midnight session (e.g., 20-5)
        return hour >= self.start_utc or hour < self.end_utc

    def overlaps(self, other: TradingSession) -> bool:
        """Determine if this session overlaps in time with another session.
        Simple check based on UTC hour ranges and common days.
        """
        common_days = set(self.days) & set(other.days)
        if not common_days:
            return False
        # Expand possible hour ranges (including cross‑midnight)
        def ranges(start, end):
            if start <= end:
                return [(start, end)]
            return [(start, 24), (0, end)]
        self_ranges = ranges(self.start_utc, self.end_utc)
        other_ranges = ranges(other.start_utc, other.end_utc)
        for s_start, s_end in self_ranges:
            for o_start, o_end in other_ranges:
                # Check interval overlap
                if max(s_start, o_start) < min(s_end, o_end):
                    return True
        return False


# ---------------------------------------------------------------------------
# Session catalogue (21+ sessions). Times are inclusive start, exclusive end.
# ---------------------------------------------------------------------------
ALL_SESSIONS: list[TradingSession] = [
    TradingSession(
        name="Wellington Forex",
        market_type="forex",
        start_utc=20,
        end_utc=5,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["NZDUSD", "AUDNZD"],
        overlaps_with=["Sydney Forex", "Tokyo Forex"],
    ),
    TradingSession(
        name="Sydney Forex",
        market_type="forex",
        start_utc=22,
        end_utc=7,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["AUDUSD", "AUDJPY"],
        overlaps_with=["Wellington Forex", "Tokyo Forex"],
    ),
    TradingSession(
        name="Tokyo Forex",
        market_type="forex",
        start_utc=23,
        end_utc=8,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["JPYUSD", "USDJPY"],
        overlaps_with=["Sydney Forex", "Hong Kong Forex"],
    ),
    TradingSession(
        name="Hong Kong Forex",
        market_type="forex",
        start_utc=1,
        end_utc=10,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["HKDUSD", "CNYUSD"],
        overlaps_with=["Tokyo Forex", "Singapore Forex"],
    ),
    TradingSession(
        name="Singapore Forex",
        market_type="forex",
        start_utc=1,
        end_utc=10,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["SGDUSD"],
        overlaps_with=["Hong Kong Forex"],
    ),
    TradingSession(
        name="Frankfurt Forex",
        market_type="forex",
        start_utc=6,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["EURUSD", "EURGBP"],
        overlaps_with=["London Forex", "Zurich Forex"],
    ),
    TradingSession(
        name="London Forex",
        market_type="forex",
        start_utc=7,
        end_utc=16,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["GBPUSD", "EURGBP"],
        overlaps_with=["Frankfurt Forex", "Zurich Forex", "New York Forex"],
    ),
    TradingSession(
        name="Zurich Forex",
        market_type="forex",
        start_utc=7,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["CHFUSD"],
        overlaps_with=["London Forex", "Frankfurt Forex"],
    ),
    TradingSession(
        name="New York Forex",
        market_type="forex",
        start_utc=12,
        end_utc=21,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["USDCAD", "USDCHF"],
        overlaps_with=["London Forex", "US Pre-Market"],
    ),
    TradingSession(
        name="Sydney ASX",
        market_type="equities",
        start_utc=0,
        end_utc=6,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["AAPL.AX", "BHP.AX"],
        overlaps_with=["Tokyo TSE"],
    ),
    TradingSession(
        name="Tokyo TSE",
        market_type="equities",
        start_utc=0,
        end_utc=6,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["7203.T", "9984.T"],
        overlaps_with=["Sydney ASX"],
    ),
    TradingSession(
        name="Hong Kong HKEX",
        market_type="equities",
        start_utc=1,
        end_utc=8,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["0700.HK"],
        overlaps_with=["Shanghai SSE"],
    ),
    TradingSession(
        name="Shanghai SSE",
        market_type="equities",
        start_utc=1,
        end_utc=7,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["600519.SS"],
        overlaps_with=["Hong Kong HKEX"],
    ),
    TradingSession(
        name="Dubai DFM",
        market_type="equities",
        start_utc=6,
        end_utc=11,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["DFM.AE"],
        overlaps_with=[],
    ),
    TradingSession(
        name="Saudi Tadawul",
        market_type="equities",
        start_utc=7,
        end_utc=12,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["TASI.SAU"],
        overlaps_with=[],
    ),
    TradingSession(
        name="Frankfurt Xetra",
        market_type="equities",
        start_utc=7,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["DAX"],
        overlaps_with=["London LSE"],
    ),
    TradingSession(
        name="London LSE",
        market_type="equities",
        start_utc=7,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["FTSE"],
        overlaps_with=["Frankfurt Xetra"],
    ),
    TradingSession(
        name="Euronext Paris",
        market_type="equities",
        start_utc=7,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["CAC40"],
        overlaps_with=[],
    ),
    TradingSession(
        name="Johannesburg JSE",
        market_type="equities",
        start_utc=7,
        end_utc=15,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["JSE"],
        overlaps_with=[],
    ),
    TradingSession(
        name="Sao Paulo B3",
        market_type="equities",
        start_utc=13,
        end_utc=20,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["IBOV"],
        overlaps_with=["Mexican BMV"],
    ),
    TradingSession(
        name="Mexican BMV",
        market_type="equities",
        start_utc=13,
        end_utc=20,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["MXX"],
        overlaps_with=["Sao Paulo B3"],
    ),
    TradingSession(
        name="US NYSE/NASDAQ",
        market_type="equities",
        start_utc=13,
        end_utc=20,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["AAPL", "MSFT"],
        overlaps_with=["US Pre-Market", "US After-Hours"],
    ),
    TradingSession(
        name="US Pre-Market",
        market_type="equities",
        start_utc=8,
        end_utc=13,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["AAPL", "MSFT"],
        overlaps_with=["New York Forex"],
    ),
    TradingSession(
        name="US After-Hours",
        market_type="equities",
        start_utc=20,
        end_utc=0,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["AAPL", "MSFT"],
        overlaps_with=[],
    ),
    TradingSession(
        name="CME Futures",
        market_type="futures",
        start_utc=22,
        end_utc=21,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["ES", "NQ"],
        overlaps_with=["ICE Futures"],
    ),
    TradingSession(
        name="ICE Futures",
        market_type="futures",
        start_utc=23,
        end_utc=22,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["CL", "NG"],
        overlaps_with=["CME Futures"],
    ),
    TradingSession(
        name="Crypto 24/7",
        market_type="crypto",
        start_utc=0,
        end_utc=24,
        days=[0, 1, 2, 3, 4, 5, 6],
        symbols=["BTCUSD", "ETHUSD"],
        overlaps_with=[],
    ),
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_active_sessions(now_utc: _dt.datetime) -> list[TradingSession]:
    """Return a list of sessions active at ``now_utc`` (UTC datetime)."""
    return [s for s in ALL_SESSIONS if s.is_active(now_utc)]


def get_next_session(now_utc: _dt.datetime) -> TradingSession | None:
    """Return the next session to start after ``now_utc``.
    If multiple sessions start at the same hour, the first in ``ALL_SESSIONS``
    order is returned. Returns ``None`` if the catalogue is empty.
    """
    if not ALL_SESSIONS:
        return None
    # Create a list of (session, start_datetime) for future starts within the next 7 days.
    candidates = []
    for offset_day in range(8):
        day = (now_utc + _dt.timedelta(days=offset_day)).date()
        weekday = day.weekday()
        for s in ALL_SESSIONS:
            if weekday not in s.days:
                continue
            start_hour = s.start_utc
            start_dt = _dt.datetime.combine(day, _dt.time(hour=start_hour), tzinfo=_dt.timezone.utc)
            if start_dt <= now_utc:
                # If start today already passed, look at next occurrence.
                if offset_day == 0:
                    continue
            candidates.append((s, start_dt))
    if not candidates:
        return None
    # Sort by start datetime
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]


def get_session_overlaps(session: TradingSession, now_utc: _dt.datetime) -> list[TradingSession]:
    """Return active sessions that overlap with the given ``session``.
    Overlap is defined by time intersection and shared day.
    """
    active = get_active_sessions(now_utc)
    return [s for s in active if s != session and session.overlaps(s)]


def get_symbols_for_active_sessions(now_utc: _dt.datetime) -> list[str]:
    """Aggregate symbols from all active sessions.
    If no non‑crypto sessions are active, returns the crypto symbols as fallback.
    """
    active = get_active_sessions(now_utc)
    if not active:
        # fallback to crypto symbols (there is always exactly one crypto session)
        crypto = next((s for s in ALL_SESSIONS if s.market_type == "crypto"), None)
        return crypto.symbols if crypto else []
    symbols = []
    for s in active:
        symbols.extend(s.symbols)
    return list(dict.fromkeys(symbols))  # dedupe while preserving order
