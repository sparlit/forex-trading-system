"""session_engine.py

Session Engine with DST and holiday awareness. Implements the set of
sessions described in the spec (Section 61) and provides helpers for detecting
current, next, previous and overlapping sessions.
"""

from __future__ import annotations

import calendar
import datetime as _dt
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Helper utilities for DST calculation
# ---------------------------------------------------------------------------

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> _dt.datetime:
    """Return the datetime of the *n*th ``weekday`` (0=Mon) in a month.
    ``weekday`` follows ``datetime.weekday()`` conventions.
    """
    first_day = _dt.date(year, month, 1)
    first_weekday = first_day.weekday()
    days_until = (weekday - first_weekday) % 7
    day = 1 + days_until + (n - 1) * 7
    return _dt.datetime(year, month, day)

def us_dst_range(year: int) -> tuple[_dt.datetime, _dt.datetime]:
    """Return the start and end UTC datetimes for US DST in *year*.
    US DST: second Sunday of March (02:00 local) to first Sunday of November.
    We return UTC times assuming the US Central time (UTC‑5 standard, UTC‑4 DST).
    For simplicity we compute the transition in UTC directly.
    """
    # Second Sunday of March at 02:00 local (standard time UTC‑5)
    start_local = _nth_weekday_of_month(year, 3, calendar.SUNDAY, 2).replace(hour=2)
    start_utc = start_local + _dt.timedelta(hours=5)  # shift to UTC
    # First Sunday of November at 02:00 local (DST time UTC‑4)
    end_local = _nth_weekday_of_month(year, 11, calendar.SUNDAY, 1).replace(hour=2)
    end_utc = end_local + _dt.timedelta(hours=4)
    return start_utc, end_utc

def eu_dst_range(year: int) -> tuple[_dt.datetime, _dt.datetime]:
    """Return the start and end UTC datetimes for EU DST in *year*.
    EU DST: last Sunday of March to last Sunday of October (02:00 local).
    Assume Central European Time (UTC+1 standard, UTC+2 DST).
    """
    # Last Sunday of March
    last_day_march = calendar.monthrange(year, 3)[1]
    last_date_march = _dt.date(year, 3, last_day_march)
    last_sunday_march = last_date_march - _dt.timedelta(days=(last_date_march.weekday() - calendar.SUNDAY) % 7)
    start_local = _dt.datetime.combine(last_sunday_march, _dt.time(2))
    start_utc = start_local - _dt.timedelta(hours=1)  # CET -> UTC
    # Last Sunday of October
    last_day_oct = calendar.monthrange(year, 10)[1]
    last_date_oct = _dt.date(year, 10, last_day_oct)
    last_sunday_oct = last_date_oct - _dt.timedelta(days=(last_date_oct.weekday() - calendar.SUNDAY) % 7)
    end_local = _dt.datetime.combine(last_sunday_oct, _dt.time(2))
    end_utc = end_local - _dt.timedelta(hours=2)  # CEST -> UTC
    return start_utc, end_utc

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TradingSession:
    name: str
    start_utc: _dt.time  # time of day in UTC
    end_utc: _dt.time
    overlaps_with: list[str] = field(default_factory=list)
    liquidity_level: str = "medium"
    # Optional extra metadata (e.g., asset class) can be added later.

# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------
class SessionEngine:
    """Provides session lookup with DST and holiday handling.

    The engine stores a static list of sessions (name, start, end) based on the
    spec.  DST adjustments are applied on the fly according to the current date.
    Holiday awareness is limited to a hardcoded list for 2024–2026.
    """

    # ---------------------------------------------------------------------
    # Holiday calendar (simplified). Keys are ``YYYY-MM-DD`` strings.
    # ---------------------------------------------------------------------
    _holidays = {
        # New Year
        "2024-01-01",
        "2025-01-01",
        "2026-01-01",
        # Christmas
        "2024-12-25",
        "2025-12-25",
        "2026-12-25",
        # Boxing Day
        "2024-12-26",
        "2025-12-26",
        "2026-12-26",
        # US Thanksgiving (fourth Thursday of November)
        "2024-11-28",
        "2025-11-27",
        "2026-11-26",
        # US Independence Day
        "2024-07-04",
        "2025-07-04",
        "2026-07-04",
        # Common FX holidays (example placeholders)
        "2024-04-01",  # Good Friday placeholder
        "2025-04-18",
        "2026-04-10",
    }

    def __init__(self):
        self.sessions: list[TradingSession] = []
        self._build_sessions()

    # ---------------------------------------------------------------------
    def _build_sessions(self) -> None:
        """Populate ``self.sessions`` with the spec's session definitions.

        Times are expressed as UTC ``datetime.time`` objects.  DST adjustments are
        applied later in ``detect_current_session``.
        """
        # Helper to create a time object.
        t = lambda h, m=0: _dt.time(hour=h, minute=m)

        # Forex sessions (based on SessionManager defaults, simplified).
        forex = [
            TradingSession(name="wellington", start_utc=t(20), end_utc=t(5), overlaps_with=["sydney"], liquidity_level="medium"),
            TradingSession(name="sydney", start_utc=t(22), end_utc=t(7), overlaps_with=["tokyo", "wellington"], liquidity_level="medium"),
            TradingSession(name="tokyo", start_utc=t(23), end_utc=t(8), overlaps_with=["hong_kong", "sydney"], liquidity_level="medium"),
            TradingSession(name="hong_kong", start_utc=t(0), end_utc=t(8), overlaps_with=["tokyo"], liquidity_level="high"),
            TradingSession(name="singapore", start_utc=t(0), end_utc=t(8), overlaps_with=["tokyo"], liquidity_level="high"),
            TradingSession(name="frankfurt", start_utc=t(6), end_utc=t(15), overlaps_with=["london", "zurich"], liquidity_level="high"),
            TradingSession(name="london", start_utc=t(7), end_utc=t(16), overlaps_with=["frankfurt", "zurich", "new_york"], liquidity_level="very_high"),
            TradingSession(name="zurich", start_utc=t(7), end_utc=t(15), overlaps_with=["london", "frankfurt"], liquidity_level="high"),
            TradingSession(name="new_york", start_utc=t(12), end_utc=t(21), overlaps_with=["london"], liquidity_level="very_high"),
        ]

        # Equity sessions (simplified, covering major exchanges).
        equity = [
            TradingSession(name="nyse", start_utc=t(13), end_utc=t(20), overlaps_with=["london"], liquidity_level="high"),
            TradingSession(name="nasdaq", start_utc=t(13), end_utc=t(20), overlaps_with=["london"], liquidity_level="high"),
            TradingSession(name="lse", start_utc=t(7), end_utc=t(15,30), overlaps_with=["frankfurt"], liquidity_level="high"),
            TradingSession(name="tsx", start_utc=t(13), end_utc=t(20), overlaps_with=[], liquidity_level="medium"),
        ]

        # Crypto 24/7 session – always active.
        crypto = [
            TradingSession(name="crypto", start_utc=t(0), end_utc=t(0), overlaps_with=[], liquidity_level="high"),
        ]

        self.sessions.extend(forex + equity + crypto)

    # ---------------------------------------------------------------------
    def _apply_dst(self, dt: _dt.datetime) -> _dt.datetime:
        """Adjust *dt* for US/EU DST where applicable.
        This method does **not** modify the stored session start/end times; it
        merely calculates offsets when checking membership.
        """
        year = dt.year
        # US DST applies to US sessions (new_york, nyse, nasdaq) – shift forward 1h during DST.
        us_start, us_end = us_dst_range(year)
        eu_start, eu_end = eu_dst_range(year)
        # Determine if dt is in US DST range.
        in_us_dst = us_start <= dt.replace(tzinfo=None) < us_end
        in_eu_dst = eu_start <= dt.replace(tzinfo=None) < eu_end
        # We'll return a dt with an hour offset applied for US or EU sessions.
        # Caller must know which region a session belongs to; we simply offset the
        # comparison time by -1 hour when inside DST for the relevant region.
        # For simplicity we always shift by -1 hour when inside any DST; the
        # start/end times of sessions are defined in *standard* UTC, so during DST
        # they appear one hour later.
        if in_us_dst or in_eu_dst:
            return dt - _dt.timedelta(hours=1)
        return dt

    # ---------------------------------------------------------------------
    def _is_holiday(self, dt: _dt.datetime) -> bool:
        return dt.date().isoformat() in self._holidays

    # ---------------------------------------------------------------------
    def detect_current_session(self, timestamp: _dt.datetime) -> list[TradingSession]:
        """Return a list of sessions active at *timestamp* (UTC).

        Sessions that span midnight have ``end_utc`` earlier than ``start_utc``.
        """
        if self._is_holiday(timestamp):
            return []
        # Apply DST offset for comparison.
        adjusted = self._apply_dst(timestamp)
        time_only = adjusted.time()
        active: list[TradingSession] = []
        for sess in self.sessions:
            if sess.start_utc <= sess.end_utc:
                # Normal same‑day window.
                if sess.start_utc <= time_only < sess.end_utc:
                    active.append(sess)
            else:
                # Overnight window (e.g., 20:00 -> 05:00).
                if time_only >= sess.start_utc or time_only < sess.end_utc:
                    active.append(sess)
        return active

    # ---------------------------------------------------------------------
    def get_next_session(self, timestamp: _dt.datetime) -> TradingSession:
        """Return the next session that will start after *timestamp*.
        If multiple sessions start at the same moment, the first in the list is
        returned.
        """
        adjusted = self._apply_dst(timestamp)
        candidates: list[tuple[_dt.datetime, TradingSession]] = []
        for sess in self.sessions:
            # Compute the next start datetime for this session relative to *timestamp*.
            today_start = _dt.datetime.combine(adjusted.date(), sess.start_utc)
            if today_start <= adjusted:
                today_start += _dt.timedelta(days=1)
            # Skip if the day is a holiday.
            if self._is_holiday(today_start):
                continue
            candidates.append((today_start, sess))
        if not candidates:
            raise ValueError("No sessions defined")
        nxt, sess = min(candidates, key=lambda x: x[0])
        return sess

    # ---------------------------------------------------------------------
    def get_previous_session(self, timestamp: _dt.datetime) -> TradingSession:
        """Return the most recent session that started before *timestamp*.
        """
        adjusted = self._apply_dst(timestamp)
        candidates: list[tuple[_dt.datetime, TradingSession]] = []
        for sess in self.sessions:
            today_start = _dt.datetime.combine(adjusted.date(), sess.start_utc)
            if today_start >= adjusted:
                today_start -= _dt.timedelta(days=1)
            if self._is_holiday(today_start):
                continue
            candidates.append((today_start, sess))
        if not candidates:
            raise ValueError("No sessions defined")
        prev, sess = max(candidates, key=lambda x: x[0])
        return sess

    # ---------------------------------------------------------------------
    def get_overlaps(self, timestamp: _dt.datetime) -> list[tuple[TradingSession, TradingSession]]:
        """Return pairs of overlapping sessions active at *timestamp*.
        The result contains each unordered pair once.
        """
        active = self.detect_current_session(timestamp)
        overlaps: list[tuple[TradingSession, TradingSession]] = []
        for i, a in enumerate(active):
            for b in active[i + 1 :]:
                if b.name in a.overlaps_with or a.name in b.overlaps_with:
                    overlaps.append((a, b))
        return overlaps

    # ---------------------------------------------------------------------
    def countdown_to_next(self, timestamp: _dt.datetime) -> _dt.timedelta:
        """Return time remaining until the next session starts.
        If a session is currently active, the countdown is to the *next* start
        after the current one.
        """
        next_sess = self.get_next_session(timestamp)
        adjusted = self._apply_dst(timestamp)
        next_start = _dt.datetime.combine(adjusted.date(), next_sess.start_utc)
        if next_start <= adjusted:
            next_start += _dt.timedelta(days=1)
        return next_start - adjusted

# End of file
