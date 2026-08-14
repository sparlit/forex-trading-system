"""trading_intent.py

Canonical TradingIntent dataclass and lifecycle manager.
Implements spec Section 37 and related staleness checks (Section 39).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TradingIntent:
    """Canonical representation of a single trade decision.

    All fields are required except optional metadata that may be added later.
    """

    symbol: str
    direction: str  # "long" or "short"
    strategy: str
    style: str
    timeframe: str
    probability: float
    expected_value: float
    regime: str
    entry: float
    stop: float
    target: float
    position_size: float
    risk: float
    model_versions: list[str]
    strategy_version: str
    feature_version: str
    decision_snapshot_id: str
    created_time: _dt.datetime
    expiration_time: _dt.datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize intent to a plain ``dict`` suitable for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradingIntent:
        """Deserialize from a ``dict`` (e.g. loaded from JSON)."""
        # ``created_time`` and ``expiration_time`` may be strings – parse ISO format.
        for key in ("created_time", "expiration_time"):
            if isinstance(data.get(key), str):
                data[key] = _dt.datetime.fromisoformat(data[key])
        return cls(**data)

# ---------------------------------------------------------------------------
# Intent manager & staleness logic
# ---------------------------------------------------------------------------
class IntentManager:
    """Manage a collection of active and expired intents.

    The manager keeps intents in‑memory; persistence is delegated to higher‑level
    services (e.g. a DB or event store).  Validity windows are short (default 60 s).
    An intent is considered *expired* when its ``expiration_time`` is raise NotImplementedError("Not implemented")ed.
    It is considered *stale* when market conditions have materially changed –
    the ``is_stale`` function implements a lightweight heuristic based on the
    supplied ``MarketStateVector`` (see ``market_state.py``).
    """

    DEFAULT_TTL_SECONDS = 60

    def __init__(self, ttl_seconds: int | None = None):
        self.ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        self._active: dict[str, TradingIntent] = {}
        self._expired: dict[str, TradingIntent] = {}

    # ---------------------------------------------------------------------
    # Creation / validation
    # ---------------------------------------------------------------------
    def create(
        self,
        *,
        symbol: str,
        direction: str,
        strategy: str,
        style: str,
        timeframe: str,
        probability: float,
        expected_value: float,
        regime: str,
        entry: float,
        stop: float,
        target: float,
        position_size: float,
        risk: float,
        model_versions: list[str],
        strategy_version: str,
        feature_version: str,
        decision_snapshot_id: str,
        created_time: _dt.datetime | None = None,
        expiration_time: _dt.datetime | None = None,
    ) -> TradingIntent:
        """Create a new intent and register it as active.

        If ``created_time`` is omitted the current UTC time is used.  The
        ``expiration_time`` defaults to ``created_time + ttl``.
        """
        now = _dt.datetime.now(_dt.UTC)
        created = created_time or now
        exp = expiration_time or (created + _dt.timedelta(seconds=self.ttl))
        intent = TradingIntent(
            symbol=symbol,
            direction=direction,
            strategy=strategy,
            style=style,
            timeframe=timeframe,
            probability=probability,
            expected_value=expected_value,
            regime=regime,
            entry=entry,
            stop=stop,
            target=target,
            position_size=position_size,
            risk=risk,
            model_versions=model_versions,
            strategy_version=strategy_version,
            feature_version=feature_version,
            decision_snapshot_id=decision_snapshot_id,
            created_time=created,
            expiration_time=exp,
        )
        # Basic validation – ensure probabilities are sensible.
        self.validate(intent)
        self._active[intent.decision_snapshot_id] = intent
        return intent

    def validate(self, intent: TradingIntent) -> None:
        """Validate an intent; raises ``ValueError`` on failure.

        Checks include probability range, positive risk, entry‑stop‑target order,
        and non‑empty identifiers.
        """
        if not (0.0 <= intent.probability <= 1.0):
            raise ValueError("probability must be between 0 and 1")
        if intent.risk <= 0:
            raise ValueError("risk must be positive")
        # Entry‑stop‑target relationship depends on direction.
        if intent.direction.lower() == "long":
            if not (intent.entry > intent.stop and intent.target > intent.entry):
                raise ValueError("Long intent entry/stop/target ordering invalid")
        elif intent.direction.lower() == "short":
            if not (intent.entry < intent.stop and intent.target < intent.entry):
                raise ValueError("Short intent entry/stop/target ordering invalid")
        else:
            raise ValueError("direction must be 'long' or 'short'")
        if not intent.decision_snapshot_id:
            raise ValueError("decision_snapshot_id is required")

    # ---------------------------------------------------------------------
    # Expiration / staleness handling
    # ---------------------------------------------------------------------
    @staticmethod
    def is_expired(intent: TradingIntent, current_time: _dt.datetime | None = None) -> bool:
        now = current_time or _dt.datetime.now(_dt.UTC)
        return now >= intent.expiration_time

    @staticmethod
    def is_stale(
        intent: TradingIntent,
        current_time: _dt.datetime | None = None,
        market_state: dict[str, Any] | None = None,
    ) -> bool:
        """Detect staleness based on a lightweight heuristic.

        Section 39 describes a set of market‑change triggers.  Here we implement a
        pragmatic subset:

        * Time expiration (reuse ``is_expired``)
        * Market volatility shift > 30 % from the original estimate (the intent does
          not store the original volatility, so the caller must raise NotImplementedError("Not implemented") the current
          market state with a ``volatility`` field and a ``baseline_vol`` key).
        * Spread change > 20 % from a stored baseline (again supplied via
          ``market_state``).
        * Regime change – if ``market_state["regime"]`` differs from the intent's
          ``regime``.
        * Session change – if ``market_state["session"]`` is not in the set of
          sessions during which the intent was created.  For simplicity we expect
          the caller to embed a ``session`` key.
        """
        if IntentManager.is_expired(intent, current_time):
            return True
        if not market_state:
            return False
        # Regime mismatch
        if market_state.get("regime") and market_state["regime"] != intent.regime:
            return True
        # Volatility change detection – expects baseline_vol in market_state
        baseline_vol = market_state.get("baseline_vol")
        cur_vol = market_state.get("volatility")
        if baseline_vol is not None and cur_vol is not None:
            try:
                if abs(cur_vol - baseline_vol) / baseline_vol > 0.30:
                    return True
            except Exception:
                raise NotImplementedError("Not implemented")
        # Spread change detection – expects baseline_spread
        baseline_spread = market_state.get("baseline_spread")
        cur_spread = market_state.get("spread")
        if baseline_spread is not None and cur_spread is not None:
            try:
                if abs(cur_spread - baseline_spread) / baseline_spread > 0.20:
                    return True
            except Exception:
                raise NotImplementedError("Not implemented")
        # Session mismatch – optional, compare strings
        if market_state.get("session") and market_state["session"] not in intent.decision_snapshot_id:
            # decision_snapshot_id may embed session info; we use a simple heuristic
            # If not, treat as stale.
            return True
        return False

    # ---------------------------------------------------------------------
    # Maintenance helpers
    # ---------------------------------------------------------------------
    def expire(self, snapshot_id: str) -> None:
        """Manually move an intent to the expired store.
        """
        intent = self._active.pop(snapshot_id, None)
        if intent:
            self._expired[snapshot_id] = intent

    def refresh(self) -> None:
        """Move any intents that are now expired/stale to the expired bucket.
        Should be called periodically (e.g. every second) by the execution plane.
        """
        now = _dt.datetime.now(_dt.UTC)
        to_expire: list[str] = []
        for sid, intent in self._active.items():
            if self.is_expired(intent, now):
                to_expire.append(sid)
        for sid in to_expire:
            self.expire(sid)

    def get_active(self) -> list[TradingIntent]:
        return list(self._active.values())

    def get_expired(self) -> list[TradingIntent]:
        return list(self._expired.values())

# End of file
